# -*- coding: utf-8 -*-
from odoo import models, fields, _
from collections import defaultdict
import base64
import io
import logging
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None


def round_half_up(value, ndigits=0):
    """Round using the round half up method instead of banker's rounding."""
    quantize_str = "1" if ndigits == 0 else "1." + "0" * ndigits
    return float(
        Decimal(str(value)).quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
    )


def _age_parts(birth_date, asof):
    """Return (years, months) a person is/will be on a given date, else None."""
    if not birth_date or not asof:
        return None
    if asof < birth_date:
        return None
    years = asof.year - birth_date.year
    months = asof.month - birth_date.month
    if months < 0:
        years -= 1
        months += 12
    if asof.day < birth_date.day:
        months -= 1
        if months < 0:
            months += 12
            years -= 1
    return years, months


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
        term_numbers = {p.id: i + 1 for i, p in enumerate(periods)}

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
        month_labels = {
            6: "June", 7: "July", 8: "Aug", 9: "Sept", 10: "Oct",
            11: "Nov", 12: "Dec", 1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
        }
        month_order = [6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4]
        att_by_month = {int(a.month or 0): a for a in att if a.month}
        attendance = []
        for m in month_order:
            a = att_by_month.get(m)
            attendance.append(
                {
                    "month": month_labels[m],
                    "year": (a.year if a else ""),
                    "present": (a.present_days or 0) if a else 0,
                    "expected": (a.expected_days or 0) if a else 0,
                    "absent": (a.absent_days or 0) if a else 0,
                    "tardy": (a.tardy_days or 0) if a else 0,
                }
            )
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
        term_comments = {
            c.period_id.id: {
                "can_do": c.comment_can_do or "",
                "to_improve": c.comment_to_improve or "",
            }
            for c in comments_rec
            if c.period_id
        }

        # Grade 1: source the term narratives from the Character Building model
        # (behavior_type='grade1', group 'Narratives') instead of sis.rating.comment.
        if (
            enrollment.grade_level_id
            and enrollment.grade_level_id.report_card_type == "grade1"
        ):
            narrative_field = {
                "What Your Child Can Do": "can_do",
                "What Your Child Is Learning To Improve": "to_improve",
            }
            grade1_comments = {}
            narrative_recs = (
                self.env["sis.character.rating"]
                .sudo()
                .search(
                    [
                        ("enrollment_id", "=", enrollment.id),
                        ("school_year_id", "=", enrollment.school_year_id.id),
                        ("behavior_id.behavior_type", "=", "grade1"),
                    ]
                )
            )
            for rec in narrative_recs:
                if not rec.period_id or not rec.behavior_id:
                    continue
                field_name = narrative_field.get(
                    (rec.behavior_id.description or "").strip()
                )
                if field_name:
                    grade1_comments.setdefault(rec.period_id.id, {})[field_name] = (
                        rec.rating or ""
                    )
            term_comments = {
                prd.id: grade1_comments.get(prd.id, {}) for prd in periods
            }

        char_recs = (
            self.env["sis.character.rating"]
            .sudo()
            .search(
                [("enrollment_id", "=", enrollment.id), ("school_year_id", "=", enrollment.school_year_id.id)],
                order="sort_key",
            )
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

        comp_recs = (
            self.env["sis.character.rating"]
            .sudo()
            .search(
                [
                    ("enrollment_id", "=", enrollment.id),
                    ("school_year_id", "=", enrollment.school_year_id.id),
                    ("behavior_id.behavior_type", "=", "kinder"),
                ],
                order="sort_key",
            )
            or []
        )
        comp_map = {}
        for r in comp_recs:
            if not r.period_id or not r.behavior_id:
                continue
            prd = r.period_id.id
            comp_map.setdefault(prd, []).append(
                {
                    "domain": r.behavior_id.group_name or "",
                    "subgroup": r.behavior_id.subgroup or "",
                    "competency": r.behavior_id.description or "",
                    "rating": r.rating or "",
                    "group_order": r.behavior_id.group_order or 0,
                    "sequence": r.behavior_id.sequence or 0,
                    "sort_key": r.sort_key or "",
                }
            )

        comp_rows = {}
        for p_id, items in comp_map.items():
            tno = term_numbers.get(p_id)
            for item in items:
                key = (item["domain"], item["subgroup"], item["competency"])
                row = comp_rows.setdefault(
                    key,
                    {
                        "domain": item["domain"],
                        "subgroup": item["subgroup"],
                        "competency": item["competency"],
                        "group_order": item["group_order"],
                        "sequence": item["sequence"],
                        "t1": "",
                        "t2": "",
                        "t3": "",
                    },
                )
                if tno in (1, 2, 3):
                    row["t%d" % tno] = item["rating"]
        competency_matrix = sorted(
            comp_rows.values(),
            key=lambda r: (
                r["group_order"],
                r["domain"],
                r["subgroup"],
                r["sequence"],
            ),
        )
        # Number competencies 1..N within each developmental domain.
        domain_counters = {}
        for row in competency_matrix:
            n = domain_counters.get(row["domain"], 0) + 1
            domain_counters[row["domain"]] = n
            row["display_no"] = n

        # Split the domains into two balanced columns for the progress report.
        competency_columns = [[], []]
        if competency_matrix:
            domain_sizes = []
            for row in competency_matrix:
                if not domain_sizes or domain_sizes[-1][0] != row["domain"]:
                    domain_sizes.append([row["domain"], 0])
                domain_sizes[-1][1] += 1
            total = len(competency_matrix)
            best_split, best_diff, cumulative = 1, None, 0
            for i, (_domain, size) in enumerate(domain_sizes[:-1]):
                cumulative += size
                diff = abs(total - 2 * cumulative)
                if best_diff is None or diff < best_diff:
                    best_diff, best_split = diff, i + 1
            left_domains = {d[0] for d in domain_sizes[:best_split]}
            for row in competency_matrix:
                competency_columns[0 if row["domain"] in left_domains else 1].append(row)

        group_order_map = {
            b.group_name: b.group_order
            for b in self.env["sis.character.behavior"].sudo().search([])
        }
        char_rows = {}
        for p_id, items in char_map.items():
            tno = term_numbers.get(p_id)
            for item in items:
                key = (item["group"], item["description"])
                row = char_rows.setdefault(
                    key,
                    {
                        "group": item["group"],
                        "description": item["description"],
                        "t1": "",
                        "t2": "",
                        "t3": "",
                    },
                )
                if tno in (1, 2, 3):
                    row["t%d" % tno] = item["rating"]

        # Nursery: always render the full behavior catalog (with any ratings
        # overlaid) so sections II-V show every indicator + AVERAGE row even
        # when nothing has been rated yet.
        if (
            enrollment.grade_level_id
            and enrollment.grade_level_id.report_card_type == "nursery"
        ):
            catalog = (
                self.env["sis.character.behavior"]
                .sudo()
                .search(
                    [("behavior_type", "=", "nursery")],
                    order="group_order, sequence, id",
                )
            )
            seeded = {}
            for b in catalog:
                key = (b.group_name or "", b.description or "")
                seeded[key] = {
                    "group": b.group_name or "",
                    "description": b.description or "",
                    "t1": "",
                    "t2": "",
                    "t3": "",
                }
            for key, row in char_rows.items():
                if key in seeded:
                    seeded[key].update(
                        {"t1": row["t1"], "t2": row["t2"], "t3": row["t3"]}
                    )
                else:
                    seeded[key] = row
            char_rows = seeded

        character_matrix = sorted(
            char_rows.values(),
            key=lambda r: (group_order_map.get(r["group"], 99) or 0),
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

        deped_logo = ""
        deped_logo_path = (
            Path(__file__).resolve().parents[1] / "static/src/img/deped.png"
        )
        if deped_logo_path.exists():
            deped_logo = base64.b64encode(deped_logo_path.read_bytes()).decode("utf-8")
        # Prefer the website attachment (the renderable, QtWebKit-safe source).
        # Odoo's `/web/image/...?height=256` controller flattens palette PNGs to a
        # washed-out RGBA, so read the raw attachment bytes ourselves and convert
        # them to RGB (color type 2), which wkhtmltopdf/QtWebKit renders.
        deped_attachment = (
            self.env["ir.attachment"]
            .sudo()
            .search([("name", "=", "deped.png"), ("res_model", "=", "website")],
                    limit=1)
        )
        if deped_attachment:
            try:
                with_image = deped_attachment.raw
                if with_image:
                    with Image.open(io.BytesIO(with_image)) as img:
                        rgb_img = img.convert("RGB")
                        rgb_img.thumbnail((400, 400), Image.LANCZOS)
                        out = io.BytesIO()
                        rgb_img.save(out, format="PNG")
                        deped_logo = base64.b64encode(out.getvalue()).decode("utf-8")
            except Exception:
                _logger.exception("Could not process deped.png attachment")

        age_begin = _age_parts(
            enrollment.birth_date,
            enrollment.school_year_id.date_start if enrollment.school_year_id else None,
        )
        age_end = _age_parts(
            enrollment.birth_date,
            enrollment.school_year_id.date_end if enrollment.school_year_id else None,
        )

        data = {
            "student_name": enrollment.full_name or "",
            "grade_level": enrollment.grade_level_id.name or "",
            "section": enrollment.section_id.display_name or "",
            "section_name": (
                enrollment.section_id.name
                if enrollment.section_id
                else ""
            ),
            "age": enrollment.age or "",
            "lrn": enrollment.lrn_no or "",
            "sex": (enrollment.gender.title() if enrollment.gender else ""),
            "birth_date": (
                enrollment.birth_date.strftime("%B %d, %Y")
                if enrollment.birth_date
                else ""
            ),
            "school_year": (enrollment.school_year_id.name if enrollment.school_year_id else ""),
            "report_format": (
                enrollment.school_year_id.report_card_format
                if enrollment.school_year_id
                else "legacy"
            ),
            "report_card_type": (
                enrollment.grade_level_id.report_card_type
                if enrollment.grade_level_id
                else "legacy"
            ),
            "school_name": Company.name or "School Name",
            "school_logo": school_logo,
            "deped_logo": deped_logo,
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
            "term_numbers": term_numbers,
            "subjects": all_subjects_for_display,
            "grades": grades,
            "general_average": general_avg,
            "quarterly_general_averages": quarterly_general_averages,
            "attendance": {"monthly": attendance, "totals": attendance_totals},
            "comments": comments,
            "term_comments": term_comments,
            "age_begin_sy_years": age_begin[0] if age_begin else "",
            "age_begin_sy_months": age_begin[1] if age_begin else "",
            "age_end_sy_years": age_end[0] if age_end else "",
            "age_end_sy_months": age_end[1] if age_end else "",
            "character": char_map,
            "competencies": comp_map,
            "competency_matrix": competency_matrix,
            "competency_columns": competency_columns,
            "character_matrix": character_matrix,
        }

        return data


class ReportCardExportLongbond(ReportCardExport):
    _name = "report.obbs_sis.report_card_template_longbond_print"
    _description = "Grade 1 / Kindergarten Report Card PDF - data provider (long bond portrait)"


class ReportCardExportNursery(ReportCardExport):
    _name = "report.obbs_sis.report_card_template_nursery_print"
    _description = "Nursery Report Card PDF - data provider (letter landscape)"
