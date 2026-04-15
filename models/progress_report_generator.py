import base64
import io

import xlsxwriter
from odoo import _, models
from odoo.exceptions import ValidationError
from xlsxwriter.utility import xl_col_to_name


class ReportExport(models.AbstractModel):
    _name = "report.obbs_sis.progress_report_export"
    _description = "Progress Report Excel Sheet Export"

    def _validate_wizard(self, wizard):
        wizard.ensure_one()
        school_year = wizard.school_year_id
        channel = wizard.channel_id
        period = wizard.period_id
        section = channel.section_id

        if period.school_year_id != school_year:
            raise ValidationError(
                _("The selected grading period does not belong to the selected school year.")
            )
        if not section:
            raise ValidationError(_("The selected subject has no assigned section."))
        if section.school_year_id != school_year:
            raise ValidationError(
                _("The selected subject section does not belong to the selected school year.")
            )
        return school_year, channel, period, section

    def _get_data(self, wizard):
        school_year, channel, period, section = self._validate_wizard(wizard)
        enrollments = self.env["sis.enrollment"].search(
            [
                ("section_id", "=", section.id),
                ("school_year_id", "=", school_year.id),
            ]
        )
        activities = self.env["sis.activity"].search(
            [("channel_id", "=", channel.id), ("period_id", "=", period.id)]
        )
        gradebooks = self.env["sis.gradebook"].search(
            [
                ("activity_id", "in", activities.ids),
                ("enrollment_id", "in", enrollments.ids),
            ]
        )
        return school_year, channel, period, section, enrollments, activities, gradebooks

    def _generate_excel(self, wizard):
        school_year, channel, period, section, enrollments, activities, gradebooks = (
            self._get_data(wizard)
        )
        company = school_year.company_id or self.env.company

        activity_type_map = {}
        for activity in activities:
            type_name = activity.activity_type_id.name
            if type_name not in activity_type_map:
                activity_type_map[type_name] = {
                    "weight": activity.activity_type_id.weight,
                    "label": activity.activity_type_id.display_name,
                    "activities": [],
                }
            activity_type_map[type_name]["activities"].append(activity)

        output = io.BytesIO()
        sheet_name = f"{school_year.name} - {channel.name} - {period.name}"
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(sheet_name[:31])

        sheet.set_column("A:A", 25)
        sheet.set_column("B:B", 25)
        for row in range(0, 6):
            sheet.set_row(row, 24)

        title_format = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "font_size": 24,
                "border": 1,
            }
        )
        address_format = workbook.add_format(
            {"align": "center", "valign": "vcenter", "font_size": 16, "border": 1}
        )
        bordered_format = workbook.add_format({"border": 1})
        bordered_center_format = workbook.add_format({"border": 1, "align": "center"})
        bordered_bold_center_format = workbook.add_format(
            {"border": 1, "align": "center", "bold": True}
        )
        bordered_label_format = workbook.add_format({"border": 1, "bold": True})
        bordered_title_format = workbook.add_format(
            {"border": 1, "bold": True, "align": "center", "font_size": 14}
        )

        col = 2
        activity_type_order = ["written_works", "performance_tasks", "quarterly_exam"]
        for type_code in activity_type_map:
            col += len(activity_type_map[type_code]["activities"]) + 3
        col += 2
        last_col_letter = xl_col_to_name(col - 1)

        if company.logo:
            logo_data = base64.b64decode(company.logo)
            sheet.insert_image(
                "A1",
                "logo.png",
                {
                    "image_data": io.BytesIO(logo_data),
                    "x_scale": 0.75,
                    "y_scale": 0.75,
                    "x_offset": 94,
                    "y_offset": -12,
                    "positioning": 1,
                },
            )
        sheet.merge_range("A1:B6", "", bordered_format)

        partner = company.partner_id
        address_parts = filter(
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
        formatted_address = ", ".join(address_parts)

        sheet.merge_range(
            f"C1:{last_col_letter}3", company.name or "School Name", title_format
        )
        sheet.merge_range(
            f"C4:{last_col_letter}6",
            formatted_address or "School Address",
            address_format,
        )

        sheet.merge_range(
            f"A7:{last_col_letter}7", "Progress Report", bordered_title_format
        )
        sheet.merge_range("A8:B8", "School Year", bordered_label_format)
        sheet.merge_range(f"C8:{last_col_letter}8", school_year.name, bordered_format)
        sheet.merge_range("A9:B9", "Subject", bordered_label_format)
        sheet.merge_range(f"C9:{last_col_letter}9", channel.name, bordered_format)
        sheet.merge_range("A10:B10", "Grade & Section", bordered_label_format)
        sheet.merge_range(f"C10:{last_col_letter}10", section.display_name, bordered_format)
        sheet.merge_range("A11:B11", "Grading Period", bordered_label_format)
        sheet.merge_range(f"C11:{last_col_letter}11", period.name, bordered_format)

        sheet.merge_range("A12:B12", "Student Name", bordered_bold_center_format)
        col = 2
        for type_code in activity_type_order:
            if type_code not in activity_type_map:
                continue
            type_info = activity_type_map[type_code]
            act_list = type_info["activities"]
            weight = type_info["weight"]
            type_label = f"{type_info['label']} {weight}%"
            start_col = col
            prefix = (
                "WW"
                if type_code == "written_works"
                else "PT" if type_code == "performance_tasks" else "QE"
            )
            for i in range(len(act_list)):
                sheet.write(12, col, f"{prefix}{i+1}", bordered_center_format)
                col += 1
            for label in ["Total", "PS", "WS"]:
                sheet.write(12, col, label, bordered_bold_center_format)
                col += 1
            sheet.merge_range(
                11, start_col, 11, col - 1, type_label, bordered_bold_center_format
            )

        sheet.write(11, col, "", bordered_bold_center_format)
        sheet.write(12, col, "IG", bordered_bold_center_format)
        final_grade_col = col
        col += 1
        sheet.write(11, col, "", bordered_bold_center_format)
        sheet.write(12, col, "QG", bordered_bold_center_format)
        qg_col = col
        col += 1

        row = 13

        def write_student_section(title, students):
            nonlocal row
            sheet.merge_range(row, 0, row, col - 1, title, bordered_label_format)
            row += 1
            for enrollment in students:
                sheet.merge_range(row, 0, row, 1, enrollment.full_name, bordered_format)
                gb_entries = gradebooks.filtered(
                    lambda gb: gb.enrollment_id.id == enrollment.id
                )
                col_idx, total_ws = 2, 0

                for type_code in activity_type_order:
                    if type_code not in activity_type_map:
                        continue
                    type_activities = activity_type_map[type_code]["activities"]
                    score_sum, max_sum, ps_sum, ws_sum = 0, 0, 0, 0
                    for activity in type_activities:
                        gb = gb_entries.filtered(lambda g: g.activity_id.id == activity.id)
                        if gb and gb.score is not None:
                            score, max_score = gb.score, activity.max_score
                            score_sum += score
                            max_sum += max_score
                            ps_sum += gb.percentage_score
                            ws_sum += gb.weighted_score
                            sheet.write(
                                row,
                                col_idx,
                                f"{int(score)}/{int(max_score)}",
                                bordered_center_format,
                            )
                        else:
                            sheet.write(row, col_idx, "-", bordered_center_format)
                        col_idx += 1

                    sheet.write(
                        row,
                        col_idx,
                        f"{int(score_sum)}/{int(max_sum)}" if max_sum else "-",
                        bordered_center_format,
                    )
                    col_idx += 1
                    sheet.write(row, col_idx, round(ps_sum, 2), bordered_center_format)
                    col_idx += 1
                    sheet.write(row, col_idx, round(ws_sum, 2), bordered_center_format)
                    col_idx += 1
                    total_ws += ws_sum

                ig_value = round(total_ws, 2)
                sheet.write(row, final_grade_col, ig_value, bordered_center_format)

                transmuted = self.env["sis.transmutation.table"].search(
                    [("grade_range", "<=", ig_value)], limit=1, order="grade_range DESC"
                )
                qg = transmuted.transmuted_grade if transmuted else "-"
                sheet.write(row, qg_col, qg, bordered_center_format)
                row += 1

        males = enrollments.filtered(lambda e: e.gender == "male").sorted(
            key=lambda e: e.full_name
        )
        females = enrollments.filtered(lambda e: e.gender == "female").sorted(
            key=lambda e: e.full_name
        )
        write_student_section("Male", males)
        write_student_section("Female", females)

        prepared_by = channel.user_id.name if channel.user_id else ""
        sheet.merge_range(row, 0, row, 1, "Prepared By", bordered_label_format)
        sheet.merge_range(row, 2, row, col - 1, prepared_by, bordered_format)

        workbook.close()
        output.seek(0)
        return output.read()

    def report_action(self, wizard):
        school_year, channel, period, _section = self._validate_wizard(wizard)
        filename = f"{school_year.name}_{channel.name} - {period.name}_Progress Report.xlsx"

        attachment = self.env["ir.attachment"].search(
            [("name", "=", filename), ("res_model", "=", "sis.progress.report.wizard")],
            limit=1,
        )

        file_content = self._generate_excel(wizard)
        file_data = base64.b64encode(file_content)

        if attachment:
            attachment.write({"datas": file_data})
        else:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": filename,
                    "datas": file_data,
                    "type": "binary",
                    "res_model": "sis.progress.report.wizard",
                    "res_id": wizard.id,
                }
            )

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
