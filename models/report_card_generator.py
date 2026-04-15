# -*- coding: utf-8 -*-
from odoo import models, fields, _
from collections import defaultdict
import logging
import calendar
from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value, ndigits=0):
    """Round using the round half up method instead of banker's rounding."""
    quantize_str = "1" if ndigits == 0 else "1." + "0" * ndigits
    return float(
        Decimal(str(value)).quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
    )


_logger = logging.getLogger(__name__)


class ReportCardExport(models.AbstractModel):
    _name = "report.obbs_sis.report_card_template"
    _description = "Report Card PDF – data provider"

    def _get_report_values(self, docids, data=None):
        """Prepare all report data as superuser and return a callable for QWeb template."""
        self_sudo = self.sudo()
        enrollments = self_sudo.env["sis.enrollment"].sudo().browse(docids)

        docs_precomputed = {}
        for enrollment in enrollments:
            try:
                docs_precomputed[enrollment.id] = self_sudo._prepare_data(
                    enrollment.sudo()
                )
                _logger.debug(
                    "Prepared report data for enrollment %s: %s subjects",
                    enrollment.id,
                    len(docs_precomputed[enrollment.id].get("subjects") or []),
                )
            except Exception:
                _logger.exception(
                    "Error preparing report for enrollment %s", enrollment.id
                )
                docs_precomputed[enrollment.id] = {
                    "is_preschool": False,
                    "comments": {},
                    "attendance": {"monthly": [], "totals": {}},
                    "periods": [],
                    "subjects": [],
                    "grades": {},
                    "character": {},
                }

        def get_report_data(enrollment):
            return docs_precomputed.get(enrollment.id, {})

        return {
            "doc_ids": docids,
            "doc_model": "sis.enrollment",
            "docs": enrollments,
            "get_report_data": get_report_data,
        }

    def _prepare_data(self, enrollment):
        enrollment = enrollment.sudo()
        self = self.with_context(lang=(enrollment.partner_id.lang or self.env.lang))
        Company = self.env.company.sudo()

        _logger.debug(
            "Starting report data preparation for: %s", enrollment.display_name
        )

        periods = (
            self.env["sis.period"]
            .sudo()
            .search([("school_year_id", "=", enrollment.school_year_id.id)], order="start_date")
            or []
        )

        subjects = (
            self.env["slide.channel"]
            .sudo()
            .search(
                [("section_id", "=", enrollment.section_id.id)], order="card_order, id"
            )
            or []
        )

        # Separate composite components and regular subjects
        composite_groups = defaultdict(list)
        regular_subjects = []
        for subj in subjects:
            if subj.is_composite_component and subj.composite_subject_name:
                composite_groups[subj.composite_subject_name].append(subj)
            else:
                regular_subjects.append(subj)

        gradebooks = (
            self.env["sis.gradebook"]
            .sudo()
            .search([("enrollment_id", "=", enrollment.id), ("school_year_id", "=", enrollment.school_year_id.id)])
            or self.env["sis.gradebook"]
        )

        def _compute_qg(subj, prd):
            """Compute the transmuted grade per subject & period (whole number)."""
            activities = (
                self.env["sis.activity"]
                .sudo()
                .search([("channel_id", "=", subj.id), ("period_id", "=", prd.id)])
            )
            gbs = gradebooks.filtered(lambda g: g.activity_id.id in activities.ids)
            if not gbs:
                return "-"
            ig = sum(gbs.mapped("weighted_score") or [0])
            ig = round_half_up(ig, 2)  # ensure 2 decimals before transmutation
            trans = (
                self.env["sis.transmutation.table"]
                .sudo()
                .search([("grade_range", "<=", ig)], limit=1, order="grade_range DESC")
            )
            return float(trans.transmuted_grade) if trans else "-"

        grades = {}
        all_subjects_for_display = []

        # Flatten all subjects for ordering
        all_subjects = []

        # Add regular subjects
        all_subjects.extend(regular_subjects)

        # Add composite components
        for components in composite_groups.values():
            all_subjects.extend(components)

        # Sort everything by card_order first, then ID
        all_subjects_sorted = sorted(
            all_subjects, key=lambda s: (s.card_order or 0, s.id)
        )

        # Track which composite placeholders have been added
        composite_added = set()

        for subj in all_subjects_sorted:
            # If it's a composite component, add its composite placeholder before it
            if subj.is_composite_component and subj.composite_subject_name:
                composite_name = subj.composite_subject_name
                if composite_name not in composite_added:
                    composite_subject = self.env["slide.channel"].new(
                        {
                            "subject_code": composite_name,
                            "name": composite_name,
                            "is_composite_component": False,
                            "composite_subject_name": None,
                        }
                    )
                    all_subjects_for_display.append(composite_subject)
                    composite_added.add(composite_name)

                    # Compute composite average
                    components = composite_groups[composite_name]
                    row = {}
                    for prd in periods:
                        scores = [_compute_qg(c, prd) for c in components]
                        valid_scores = [
                            v for v in scores if isinstance(v, (int, float))
                        ]
                        row[prd.id] = (
                            round_half_up(sum(valid_scores) / len(valid_scores), 0)
                            if valid_scores
                            else "-"
                        )
                    finals = [v for v in row.values() if isinstance(v, (int, float))]
                    row["final"] = (
                        round_half_up(sum(finals) / len(finals), 3) if finals else "-"
                    )
                    grades[composite_name] = row

            # Compute individual subject grades
            row = {}
            for prd in periods:
                row[prd.id] = _compute_qg(subj, prd)
            finals = [v for v in row.values() if isinstance(v, (int, float))]
            row["final"] = (
                round_half_up(sum(finals) / len(finals), 3) if finals else "-"
            )
            grades[subj.id] = row

            all_subjects_for_display.append(subj)

        # General Average (finals only, 3 decimals)
        finals_all = [
            row["final"]
            for subj, row in grades.items()
            if isinstance(row.get("final"), (int, float))
            and not (
                isinstance(subj, int)
                and self.env["slide.channel"].browse(subj).is_composite_component
            )
        ]
        general_avg = (
            round_half_up(sum(finals_all) / len(finals_all), 3) if finals_all else "-"
        )

        # Quarterly General Averages (3 decimals)
        quarterly_general_averages = {}
        for prd in periods:
            period_scores = [
                row.get(prd.id)
                for subj, row in grades.items()
                if isinstance(row.get(prd.id), (int, float))
                and not (
                    isinstance(subj, int)
                    and self.env["slide.channel"].browse(subj).is_composite_component
                )
            ]
            quarterly_general_averages[prd.id] = (
                round_half_up(sum(period_scores) / len(period_scores), 3)
                if period_scores
                else "-"
            )

        # Attendance
        att = (
            self.env["sis.attendance.monthly_summary"]
            .sudo()
            .search([("enrollment_id", "=", enrollment.id), ("school_year_id", "=", enrollment.school_year_id.id)])
            or []
        )
        attendance = [
            {
                "month": (
                    calendar.month_abbr[int(a.month or 0)].upper() if a.month else ""
                ),
                "year": a.year or "",
                "present": a.present_days or 0,
                "expected": a.expected_days or 0,
                "absent": a.absent_days or 0,
                "tardy": a.tardy_days or 0,
            }
            for a in sorted(att, key=lambda x: (x.year or 0, int(x.month or 0)))
        ]
        attendance_totals = {
            "expected": sum(a["expected"] for a in attendance),
            "present": sum(a["present"] for a in attendance),
            "absent": sum(a["absent"] for a in attendance),
            "tardy": sum(a["tardy"] for a in attendance),
        }

        comments_rec = (
            self.env["sis.rating.comment"]
            .sudo()
            .search([("enrollment_id", "=", enrollment.id), ("school_year_id", "=", enrollment.school_year_id.id)])
            or []
        )
        comments = {
            c.period_id.id: c.comment or "" for c in comments_rec if c.period_id
        }

        char_recs = (
            self.env["sis.character.rating"]
            .sudo()
            .search([("enrollment_id", "=", enrollment.id), ("school_year_id", "=", enrollment.school_year_id.id)])
            or []
        )
        char_map = {}
        for r in char_recs:
            if not r.period_id or not r.behavior_id:
                continue
            prd = r.period_id.id
            char_map.setdefault(prd, []).append(
                {
                    "group": r.behavior_id.group_name or "",
                    "description": r.behavior_id.description or "",
                    "rating": r.rating or "",
                }
            )

        partner = Company.partner_id
        address_parts = list(
            filter(
                None,
                [
                    partner.street,
                    partner.street2,
                    partner.city,
                    partner.state_id.name if partner.state_id else None,
                    partner.zip,
                    partner.country_id.name if partner.country_id else None,
                ],
            )
        )
        formatted_address = ", ".join(address_parts) or "School Address"

        school_logo = (
            Company.logo.decode("utf-8")
            if Company.logo and isinstance(Company.logo, bytes)
            else Company.logo or ""
        )

        data = {
            "student_name": enrollment.full_name or "",
            "grade_level": enrollment.grade_level_id.name or "",
            "section": enrollment.section_id.display_name or "",
            "age": enrollment.age or "",
            "lrn": enrollment.lrn_no or "",
            "sex": (enrollment.gender.title() if enrollment.gender else ""),
            "school_year": (enrollment.school_year_id.name if enrollment.school_year_id else ""),
            "school_name": Company.name or "School Name",
            "school_logo": school_logo,
            "school_address": formatted_address,
            "advisor": (
                enrollment.section_id.advisor_id.name
                if enrollment.section_id and enrollment.section_id.advisor_id
                else ""
            ),
            "is_preschool": (
                enrollment.grade_level_id.id_type == "preschool"
                if enrollment.grade_level_id
                else False
            ),
            "periods": periods,
            "subjects": all_subjects_for_display,
            "grades": grades,
            "general_average": general_avg,
            "quarterly_general_averages": quarterly_general_averages,
            "attendance": {"monthly": attendance, "totals": attendance_totals},
            "comments": comments,
            "character": char_map,
        }

        return data
