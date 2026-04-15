import io
import base64
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name
from odoo import _, models
from odoo.exceptions import ValidationError
from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value, ndigits=0):
    """Round using the round half up method instead of banker's rounding."""
    quantize_str = "1" if ndigits == 0 else "1." + "0" * ndigits
    return float(
        Decimal(str(value)).quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
    )


class ReportRatingSheetExport(models.AbstractModel):
    _name = "report.obbs_sis.report_rating_sheet_export"
    _description = "Rating Sheet Excel Export"

    def _validate_wizard(self, wizard):
        wizard.ensure_one()
        school_year = wizard.school_year_id
        section = wizard.section_id
        period = wizard.period_id
        if section.school_year_id != school_year:
            raise ValidationError(
                _("The selected section does not belong to the selected school year.")
            )
        if period.school_year_id != school_year:
            raise ValidationError(
                _("The selected grading period does not belong to the selected school year.")
            )
        return school_year, section, period

    def _get_data(self, wizard):
        school_year, section, period = self._validate_wizard(wizard)
        enrollments = (
            self.env["sis.enrollment"].sudo().search(
                [("section_id", "=", section.id), ("school_year_id", "=", school_year.id)]
            )
        )
        subjects = (
            self.env["slide.channel"]
            .sudo()
            .search([("section_id", "=", section.id)], order="card_order, id")
        )
        gradebooks = (
            self.env["sis.gradebook"]
            .sudo()
            .search(
                [
                    ("enrollment_id", "in", enrollments.ids),
                    ("activity_id.period_id", "=", period.id),
                ]
            )
        )
        comments = (
            self.env["sis.rating.comment"]
            .sudo()
            .search(
                [
                    ("enrollment_id", "in", enrollments.ids),
                    ("period_id", "=", period.id),
                ]
            )
        )
        return school_year, section, period, enrollments, subjects, gradebooks, comments

    def _generate_excel(self, wizard):
        school_year, section, period, enrollments, subjects, gradebooks, comments = self._get_data(wizard)
        company = school_year.company_id or self.env.company
        school_year_name = school_year.name or "School Year"
        advisor_name = section.advisor_id.name or "-"

        comment_map = {
            (c.enrollment_id.id, c.period_id.id): c.comment for c in comments
        }

        # Group subjects into regular and composite groups (by composite_subject_name)
        composite_map = {}  # {composite_name: [subject_record, ...]}
        regular_subjects = []
        for subj in subjects:
            if subj.is_composite_component and subj.composite_subject_name:
                composite_map.setdefault(subj.composite_subject_name, []).append(subj)
            else:
                regular_subjects.append(subj)

        # Build ordered_subjects list (columns) that respects card_order and inserts
        # composite header BEFORE its components. Algorithm:
        # - iterate subjects sorted by card_order,id (we already fetched ordered)
        # - when encountering first component of a composite, insert a composite header
        #   (dict marker) then append that component; subsequent components follow.
        ordered_subjects = []
        inserted_composites = set()
        # subjects is already ordered by card_order, id thanks to search
        for subj in subjects:
            # If subj is a composite component
            if subj.is_composite_component and subj.composite_subject_name:
                comp_name = subj.composite_subject_name
                # If composite header not yet inserted, insert header first
                if comp_name not in inserted_composites:
                    # composite entry is a dict marker (we'll treat differently later)
                    ordered_subjects.append(
                        {
                            "composite_name": comp_name,
                            "components": composite_map.get(comp_name, []),
                        }
                    )
                    inserted_composites.add(comp_name)
                # Append the component subject after its composite header
                ordered_subjects.append(subj)
            else:
                # normal subject: just append
                ordered_subjects.append(subj)

        # Now build the Excel file
        output = io.BytesIO()
        sheet_name = f"{section.name} - {period.name} - Rating Sheet"
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(
            sheet_name[:31]
        )  # Excel sheet names must be <= 31 chars

        # Formats
        bordered = workbook.add_format({"border": 1})
        centered = workbook.add_format({"border": 1, "align": "center"})
        bold_center = workbook.add_format(
            {"border": 1, "align": "center", "bold": True}
        )
        ga_format = workbook.add_format(
            {"border": 1, "align": "center", "num_format": "0.000"}
        )
        wrapped_text = workbook.add_format(
            {"border": 1, "text_wrap": True, "valign": "top"}
        )
        title = workbook.add_format(
            {"bold": True, "align": "center", "font_size": 14, "border": 1}
        )
        label = workbook.add_format({"border": 1, "bold": True})
        header = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "font_size": 24,
                "border": 1,
            }
        )
        address = workbook.add_format(
            {"align": "center", "valign": "vcenter", "font_size": 14, "border": 1}
        )
        top_left = workbook.add_format({"border": 1, "valign": "top"})

        # Column widths setup
        sheet.set_column("A:A", 25)
        sheet.set_column("B:B", 25)
        # Number of subject-type columns is length of ordered_subjects
        num_subject_cols = len(ordered_subjects)
        col_count = 2 + num_subject_cols + 2  # Student Name + subjects + GA + Comment
        last_col_letter = xl_col_to_name(col_count - 1)
        sheet.set_column(2, col_count - 2, 25)
        sheet.set_column(col_count - 1, col_count - 1, 75)

        for row_num in range(0, 6):
            sheet.set_row(row_num, 24)

        # Logo insertion
        if company.logo:
            sheet.insert_image(
                "A1",
                "logo.png",
                {
                    "image_data": io.BytesIO(base64.b64decode(company.logo)),
                    "x_scale": 0.75,
                    "y_scale": 0.75,
                    "x_offset": 94,
                    "y_offset": -12,
                    "positioning": 1,
                },
            )
        sheet.merge_range("A1:B6", "", bordered)
        sheet.merge_range(
            f"C1:{last_col_letter}3", company.name or "School Name", header
        )

        # Address
        address_parts = list(
            filter(
                None,
                [
                    company.partner_id.street,
                    company.partner_id.street2,
                    company.partner_id.city,
                    (
                        company.partner_id.state_id.name
                        if company.partner_id.state_id
                        else None
                    ),
                    company.partner_id.zip,
                    (
                        company.partner_id.country_id.name
                        if company.partner_id.country_id
                        else None
                    ),
                ],
            )
        )
        formatted_address = ", ".join(address_parts) or "School Address"
        sheet.merge_range(f"C4:{last_col_letter}6", formatted_address, address)

        # Metadata
        sheet.merge_range(f"A7:{last_col_letter}7", "Rating Sheet", title)
        sheet.merge_range("A8:B8", "School Year", label)
        sheet.merge_range(f"C8:{last_col_letter}8", school_year, bordered)
        sheet.merge_range("A9:B9", "Grade & Section", label)
        sheet.merge_range(f"C9:{last_col_letter}9", section.display_name, bordered)
        sheet.merge_range("A10:B10", "Grading Period", label)
        sheet.merge_range(f"C10:{last_col_letter}10", period.name, bordered)
        sheet.merge_range("A11:B11", "Advisor", label)
        sheet.merge_range(f"C11:{last_col_letter}11", advisor_name, bordered)

        # Table headers
        sheet.merge_range(11, 0, 11, 1, "Student Name", bold_center)
        col_idx = 2
        subject_label_map = {}  # real subject id -> column index
        composite_label_map = {}  # composite name -> column index (for header cells)

        for entry in ordered_subjects:
            if isinstance(entry, dict):
                # composite header
                comp_name = entry["composite_name"]
                sheet.write(11, col_idx, comp_name, bold_center)
                composite_label_map[comp_name] = col_idx
                col_idx += 1
            else:
                # normal subject column
                label_text = entry.subject_code or entry.name
                sheet.write(11, col_idx, label_text, bold_center)
                subject_label_map[entry.id] = col_idx
                col_idx += 1

        # General average and comments columns
        sheet.write(11, col_idx, "General Average", bold_center)
        ga_col = col_idx
        col_idx += 1

        sheet.write(11, col_idx, "Comments", bold_center)
        comments_col = col_idx
        col_idx += 1

        def write_student_block(title, student_list):
            nonlocal row
            sheet.merge_range(row, 0, row, col_idx - 1, title, label)
            row += 1

            for enrollment in student_list:
                sheet.merge_range(row, 0, row, 1, enrollment.full_name, top_left)
                grades_map = {}  # subject_id -> qg

                # compute QG per subject (same logic as before)
                for subj in subjects:
                    activities = (
                        self.env["sis.activity"]
                        .sudo()
                        .search(
                            [
                                ("channel_id", "=", subj.id),
                                ("period_id", "=", period.id),
                            ]
                        )
                    )
                    gb = gradebooks.filtered(
                        lambda g: g.enrollment_id.id == enrollment.id
                        and g.activity_id.id in activities.ids
                    )

                    qg = "-"
                    if gb:
                        total_ws = sum(g.weighted_score for g in gb)
                        ig = round_half_up(total_ws, 2)
                        transmuted = self.env["sis.transmutation.table"].search(
                            [("grade_range", "<=", ig)],
                            limit=1,
                            order="grade_range DESC",
                        )
                        if transmuted:
                            qg = float(transmuted.transmuted_grade)
                            grades_map[subj.id] = qg

                    # write to the column if the subject column exists in this sheet (it should)
                    if subj.id in subject_label_map:
                        sheet.write(row, subject_label_map[subj.id], qg, centered)

                # For composites: compute their averaged value and write into composite column
                composite_grades = {}
                # composite_map may contain components; composite_label_map indicates where to write
                for comp_name, comp_subjs in composite_map.items():
                    qgs = [
                        grades_map.get(s.id)
                        for s in comp_subjs
                        if grades_map.get(s.id) is not None
                    ]
                    if comp_name in composite_label_map:
                        if qgs:
                            avg = sum(qgs) / len(qgs)
                            rounded_avg = round_half_up(avg, 0)
                            sheet.write(
                                row,
                                composite_label_map[comp_name],
                                rounded_avg,
                                centered,
                            )
                            composite_grades[comp_name] = rounded_avg
                        else:
                            sheet.write(
                                row, composite_label_map[comp_name], "-", centered
                            )

                # Final General Average (GA): identical logic to before
                final_qgs = [
                    grades_map[subj.id]
                    for subj in regular_subjects
                    if grades_map.get(subj.id) is not None
                ] + list(composite_grades.values())

                if final_qgs:
                    ga = round_half_up(sum(final_qgs) / len(final_qgs), 3)
                    sheet.write(row, ga_col, ga, ga_format)
                else:
                    sheet.write(row, ga_col, "-", centered)

                # comments
                comment = comment_map.get((enrollment.id, period.id), "")
                sheet.write(row, comments_col, comment, wrapped_text)

                row += 1

        # Write student blocks
        row = 12
        males = enrollments.filtered(lambda e: e.gender == "male").sorted(
            key=lambda e: e.full_name
        )
        females = enrollments.filtered(lambda e: e.gender == "female").sorted(
            key=lambda e: e.full_name
        )
        write_student_block("Male", males)
        write_student_block("Female", females)

        workbook.close()
        output.seek(0)
        return output.read()

    def report_action(self, wizard):
        section = wizard.section_id
        period = wizard.period_id
        school_year, section, period = self._validate_wizard(wizard)
        filename = f"{school_year.name}_{section.name} - {period.name}_Rating Sheet.xlsx"

        file_content = self._generate_excel(wizard)
        file_data = base64.b64encode(file_content)

        attachment = self.env["ir.attachment"].search(
            [("name", "=", filename), ("res_model", "=", "sis.rating.sheet.wizard")],
            limit=1,
        )

        if attachment:
            attachment.write({"datas": file_data})
        else:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": filename,
                    "datas": file_data,
                    "type": "binary",
                    "res_model": "sis.rating.sheet.wizard",
                    "res_id": wizard.id,
                }
            )

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
