# -*- coding: utf-8 -*-
"""Official DepEd Electronic-Class Record (ECR) export for SY 2026-2027.

Fills the official ``Grades SY 26-27.xlsx`` template (shipped under
``static/src/templates``) with Odoo enrollment/activity/gradebook data for one
subject + section across all three terms, keeping the template's live formulas.

The ECR is a fixed 5 WW / 3 PT layout.  This exporter keeps that baseline and
expands the WW/PT blocks (inserting columns and regenerating the affected
headers, merges, widths, image anchors and formulas) when a subject actually
has more activities than the standard.
"""
import base64
import io
from copy import copy

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools import file_open

ECR_TEMPLATE_PATH = "obbs_sis/static/src/templates/ecr_sy2026_2027_blank.xlsx"

EXAM_COMPONENT_ORDER = ["st1", "st2", "te"]
EXAM_COMPONENT_WEIGHTS = {"st1": 30, "st2": 30, "te": 40}
EXAM_COMPONENT_MAX = 3

STANDARD_WW = 5
STANDARD_PT = 3
MAX_PER_GENDER = 50
TERM_SHEETS = ["TERM 1", "TERM 2", "TERM 3"]

# Fixed columns (1-based) used by the official template.
WW_FIRST = 6          # F
WW_TOTAL = 11         # K
PT_FIRST = 14         # N
PT_TOTAL = 17         # Q
LAST_TEMPLATE_COL = 30  # AD


def _cl(idx):
    return get_column_letter(idx)


class EcrReportExport(models.AbstractModel):
    _name = "report.obbs_sis.ecr_export"
    _description = "Official DepEd ECR (SY 2026-2027) Excel export"

    # ------------------------------------------------------------------
    # Data gathering
    # ------------------------------------------------------------------
    def _validate_wizard(self, wizard):
        wizard.ensure_one()
        school_year = wizard.school_year_id
        channel = wizard.channel_id
        section = channel.section_id
        if not section:
            raise ValidationError(
                _("The selected subject has no assigned section.")
            )
        if section.school_year_id != school_year:
            raise ValidationError(
                _(
                    "The selected subject section does not belong to the "
                    "selected school year."
                )
            )
        return school_year, channel, section

    def _get_data(self, wizard):
        school_year, channel, section = self._validate_wizard(wizard)

        enrollments = (
            self.env["sis.enrollment"]
            .search(
                [
                    ("section_id", "=", section.id),
                    ("school_year_id", "=", school_year.id),
                    ("enrollment_status", "=", "accepted"),
                ],
                order="full_name",
            )
        )
        males = enrollments.filtered(lambda e: e.gender == "male")
        females = enrollments.filtered(lambda e: e.gender == "female")
        if len(males) > MAX_PER_GENDER or len(females) > MAX_PER_GENDER:
            raise ValidationError(
                _(
                    "The ECR supports up to %(max)s learners per gender. This "
                    "section has %(m)s male and %(f)s female accepted learners."
                )
                % {"max": MAX_PER_GENDER, "m": len(males), "f": len(females)}
            )

        periods = self.env["sis.period"].search(
            [("school_year_id", "=", school_year.id)], order="start_date, id"
        )
        if len(periods) != 3:
            raise ValidationError(
                _(
                    "The ECR requires exactly 3 grading periods, but %s were "
                    "found for this school year."
                )
                % len(periods)
            )

        Activity = self.env["sis.activity"]
        terms = []
        all_activities = Activity
        for period in periods:
            activities = Activity.search(
                [("channel_id", "=", channel.id), ("period_id", "=", period.id)],
                order="id",
            )
            all_activities |= activities
            terms.append(
                {
                    "period": period,
                    "ww": activities.filtered(
                        lambda a: a.activity_type_id.name == "written_works"
                    ),
                    "pt": activities.filtered(
                        lambda a: a.activity_type_id.name == "performance_tasks"
                    ),
                    "exs": {
                        comp: activities.filtered(
                            lambda a: a.activity_type_id.name == "quarterly_exam"
                            and a.exam_component == comp
                        )[:1]
                        for comp in EXAM_COMPONENT_ORDER
                    },
                }
            )

        gradebooks = self.env["sis.gradebook"].search(
            [("activity_id", "in", all_activities.ids)]
        )
        score_map = {
            (g.enrollment_id.id, g.activity_id.id): g.score
            for g in gradebooks
            if g.score is not None
        }

        type_weights = {
            t.name: (t.weight or 0)
            for t in channel.activity_type_ids
        }

        return {
            "school_year": school_year,
            "channel": channel,
            "section": section,
            "males": males,
            "females": females,
            "terms": terms,
            "score_map": score_map,
            "type_weights": type_weights,
        }

    # ------------------------------------------------------------------
    # Column layout
    # ------------------------------------------------------------------
    def _layout(self, ww_n, pt_n):
        c = WW_FIRST
        ww = list(range(c, c + ww_n))
        c += ww_n
        ww_total, ww_ps, ww_ws = c, c + 1, c + 2
        c += 3
        pt = list(range(c, c + pt_n))
        c += pt_n
        pt_total, pt_ps, pt_ws = c, c + 1, c + 2
        c += 3
        st = [c, c + 1, c + 2]
        c += 3
        ws = [c, c + 1, c + 2]
        c += 3
        exs_ps, exs_ws = c, c + 1
        c += 2
        ig, tg, desc = c, c + 1, c + 2
        c += 3
        return {
            "ww": ww,
            "ww_total": ww_total,
            "ww_ps": ww_ps,
            "ww_ws": ww_ws,
            "pt": pt,
            "pt_total": pt_total,
            "pt_ps": pt_ps,
            "pt_ws": pt_ws,
            "st": st,
            "ws": ws,
            "exs_ps": exs_ps,
            "exs_ws": exs_ws,
            "ig": ig,
            "tg": tg,
            "desc": desc,
            "last": desc,
        }

    # ------------------------------------------------------------------
    # Cell writers
    # ------------------------------------------------------------------
    def _write_row12(self, ws, layout):
        ws.cell(12, layout["ww"][0]).value = "WRITTEN / ORAL WORKS (WWs)"
        ws.cell(12, layout["pt"][0]).value = "PRODUCT / PERFORMANCE TASKS (PTs)"
        ws.cell(12, layout["st"][0]).value = "EXAMINATIONS (EXs)"
        ws.cell(12, layout["ig"]).value = "Initial Grade"
        ws.cell(12, layout["tg"]).value = "Term Grade"
        ws.cell(12, layout["desc"]).value = "Descriptor"

    def _write_row14(self, ws, layout):
        for i, col in enumerate(layout["ww"], start=1):
            ws.cell(14, col).value = i
        for label, col in (
            ("Total", layout["ww_total"]),
            ("PS", layout["ww_ps"]),
            ("WS", layout["ww_ws"]),
        ):
            ws.cell(14, col).value = label
        for i, col in enumerate(layout["pt"], start=1):
            ws.cell(14, col).value = i
        for label, col in (
            ("Total", layout["pt_total"]),
            ("PS", layout["pt_ps"]),
            ("WS", layout["pt_ws"]),
        ):
            ws.cell(14, col).value = label
        for label, col in zip(["ST1", "ST2", "TE"], layout["st"]):
            ws.cell(14, col).value = label
        for label, col in zip(["WS ST1", "WS ST2", "WS TE"], layout["ws"]):
            ws.cell(14, col).value = label
        ws.cell(14, layout["exs_ps"]).value = "PS"
        ws.cell(14, layout["exs_ws"]).value = "WS"

    def _write_row15(self, ws, layout, term, type_weights):
        ww_max = [a.max_score for a in term["ww"]]
        pt_max = [a.max_score for a in term["pt"]]
        st_max = [
            term["exs"][c].max_score if term["exs"][c] else None
            for c in EXAM_COMPONENT_ORDER
        ]
        for col, value in zip(layout["ww"], ww_max):
            ws.cell(15, col).value = value
        for col, value in zip(layout["pt"], pt_max):
            ws.cell(15, col).value = value
        for col, value in zip(layout["st"], st_max):
            ws.cell(15, col).value = value

        ww_first, ww_last = _cl(layout["ww"][0]), _cl(layout["ww"][-1])
        pt_first, pt_last = _cl(layout["pt"][0]), _cl(layout["pt"][-1])
        ws.cell(15, layout["ww_total"]).value = (
            '=IF(COUNT($%s15:$%s15)=0,"",SUM($%s15:$%s15))'
            % (ww_first, ww_last, ww_first, ww_last)
        )
        ws.cell(15, layout["ww_ps"]).value = 100
        ws.cell(15, layout["ww_ws"]).value = type_weights.get("written_works", 0) / 100.0
        ws.cell(15, layout["pt_total"]).value = (
            '=IF(COUNT($%s15:$%s15)=0,"",SUM($%s15:$%s15))'
            % (pt_first, pt_last, pt_first, pt_last)
        )
        ws.cell(15, layout["pt_ps"]).value = 100
        ws.cell(15, layout["pt_ws"]).value = type_weights.get("performance_tasks", 0) / 100.0
        for col, weight in zip(layout["ws"], (30, 30, 40)):
            ws.cell(15, col).value = weight
        ws.cell(15, layout["exs_ps"]).value = 100
        ws.cell(15, layout["exs_ws"]).value = type_weights.get("quarterly_exam", 0) / 100.0

    def _write_student_formulas(self, ws, layout, r):
        wwt, wwp, wwsw = (
            _cl(layout["ww_total"]),
            _cl(layout["ww_ps"]),
            _cl(layout["ww_ws"]),
        )
        ptt, ptp, ptsw = (
            _cl(layout["pt_total"]),
            _cl(layout["pt_ps"]),
            _cl(layout["pt_ws"]),
        )
        st1, st2, te = (_cl(c) for c in layout["st"])
        w1, w2, w3 = (_cl(c) for c in layout["ws"])
        eps, ews = _cl(layout["exs_ps"]), _cl(layout["exs_ws"])
        ig, tg, desc = _cl(layout["ig"]), _cl(layout["tg"]), _cl(layout["desc"])
        ww_first, ww_last = _cl(layout["ww"][0]), _cl(layout["ww"][-1])
        pt_first, pt_last = _cl(layout["pt"][0]), _cl(layout["pt"][-1])

        ws.cell(r, layout["ww_total"]).value = (
            '=IF(COUNT($%s%d:$%s%d)=0,"",SUM($%s%d:$%s%d))'
            % (ww_first, r, ww_last, r, ww_first, r, ww_last, r)
        )
        ws.cell(r, layout["ww_ps"]).value = (
            '=IF(ISERROR(IF(${t}{r}="","",ROUND((${t}{r}/${t}$15)*${p}$15,2))),"",'
            'IF(${t}{r}="","",ROUND((${t}{r}/${t}$15)*${p}$15,2)))'
        ).format(t=wwt, p=wwp, r=r)
        ws.cell(r, layout["ww_ws"]).value = (
            '=IF($%s%d="","",ROUND($%s%d*$%s$15,2))' % (wwp, r, wwp, r, wwsw)
        )
        ws.cell(r, layout["pt_total"]).value = (
            '=IF(COUNT($%s%d:$%s%d)=0,"",SUM($%s%d:$%s%d))'
            % (pt_first, r, pt_last, r, pt_first, r, pt_last, r)
        )
        ws.cell(r, layout["pt_ps"]).value = (
            '=IF(ISERROR(IF(${t}{r}="","",ROUND((${t}{r}/${t}$15)*${p}$15,2))),"",'
            'IF(${t}{r}="","",ROUND((${t}{r}/${t}$15)*${p}$15,2)))'
        ).format(t=ptt, p=ptp, r=r)
        ws.cell(r, layout["pt_ws"]).value = (
            '=IF($%s%d="","",ROUND($%s%d*$%s$15,2))' % (ptp, r, ptp, r, ptsw)
        )
        for i in range(len(EXAM_COMPONENT_ORDER)):
            st = _cl(layout["st"][i])
            w = _cl(layout["ws"][i])
            ws.cell(r, layout["ws"][i]).value = (
                '=IFERROR(IF(%s%d="","",ROUND(%s%d/$%s$15*$%s$15,2)),"")'
                % (st, r, st, r, st, w)
            )
        ws.cell(r, layout["exs_ps"]).value = (
            '=IF(COUNT($%s%d:$%s%d)=0,"",SUM($%s%d:$%s%d))'
            % (w1, r, w3, r, w1, r, w3, r)
        )
        ws.cell(r, layout["exs_ws"]).value = (
            '=IFERROR(IF(%s%d="","",ROUND(%s%d*$%s$15,2)),"")' % (eps, r, eps, r, ews)
        )
        ws.cell(r, layout["ig"]).value = (
            '=IF(C{r}="","",IFERROR(ROUND({m}{r}+{s}{r}+{a}{r},2),""))'.format(
                r=r, m=wwsw, s=ptsw, a=ews
            )
        )
        ws.cell(r, layout["tg"]).value = ArrayFormula(
            "%s%d" % (tg, r),
            '=IF(C{r}="","",IFERROR(_xlfn.XLOOKUP({ig}{r},'
            "HELPER!$C$8:$C$48,HELPER!$D$8:$D$48,,1),\"\"))".format(
                r=r, ig=ig
            ),
        )
        ws.cell(r, layout["desc"]).value = ArrayFormula(
            "%s%d" % (desc, r),
            '=IF(C{r}="","",IFERROR(_xlfn.XLOOKUP({tg}{r},'
            "HELPER!$F$8:$F$48,HELPER!$G$8:$G$48,,1),\"\"))".format(
                r=r, tg=tg
            ),
        )

    def _write_student_scores(self, ws, layout, r, term, enrollment, score_map):
        for col, activity in zip(layout["ww"], term["ww"]):
            ws.cell(r, col).value = score_map.get((enrollment.id, activity.id))
        for col, activity in zip(layout["pt"], term["pt"]):
            ws.cell(r, col).value = score_map.get((enrollment.id, activity.id))
        for col, comp in zip(layout["st"], EXAM_COMPONENT_ORDER):
            activity = term["exs"][comp]
            ws.cell(r, col).value = (
                score_map.get((enrollment.id, activity.id)) if activity else None
            )

    # ------------------------------------------------------------------
    # Expansion (only when the subject exceeds the standard 5 WW / 3 PT)
    # ------------------------------------------------------------------
    def _capture_styles(self, ws):
        def st(coord):
            return copy(ws[coord]._style)

        return {
            "label": st("E5"),
            "value": st("F5"),
            "info_label": st("N10"),
            "info_value": st("Q10"),
            "group": st("F12"),
            "act_hdr": st("F14"),
            "tot_hdr": st("K14"),
            "row15_act": st("F15"),
            "row15_tot": st("K15"),
            "data_act": st("F18"),
            "data_tot": st("K18"),
            "data_ws": st("W18"),
            "banner": st("B2"),
        }

    def _dynamic_merges(self, layout, delta):
        last = _cl(layout["last"])
        return [
            "F5:%s5" % _cl(12 + delta),
            "F7:%s7" % _cl(22 + delta),
            "F10:I10",
            "J10:%s10" % _cl(13 + delta),
            "F11:I11",
            "J11:%s11" % _cl(13 + delta),
            "%s5:%s5" % (_cl(18 + delta), _cl(22 + delta)),
            "%s5:%s5" % (_cl(26 + delta), _cl(28 + delta)),
            "%s7:%s7" % (_cl(26 + delta), _cl(28 + delta)),
            "%s10:%s11" % (_cl(14 + delta), _cl(16 + delta)),
            "%s10:%s11" % (_cl(17 + delta), _cl(24 + delta)),
            "%s10:%s11" % (_cl(25 + delta), _cl(26 + delta)),
            "%s10:%s11" % (_cl(27 + delta), _cl(30 + delta)),
            "F12:%s13" % _cl(layout["ww_ws"]),
            "%s12:%s13" % (_cl(layout["pt"][0]), _cl(layout["pt_ws"])),
            "%s12:%s13" % (_cl(layout["st"][0]), _cl(layout["exs_ws"])),
            _cl(layout["ig"]) + "12:" + _cl(layout["ig"]) + "15",
            _cl(layout["tg"]) + "12:" + _cl(layout["tg"]) + "15",
            _cl(layout["desc"]) + "12:" + _cl(layout["desc"]) + "15",
            "B2:%s3" % last,
            "B9:%s9" % last,
            "B16:%s16" % last,
            "B17:%s17" % last,
            "B68:%s68" % last,
        ]

    def _shift_column_dimensions(self, ws, delta_ww, delta_pt):
        old = {
            key: (dim.width, dim.hidden, dim.bestFit)
            for key, dim in ws.column_dimensions.items()
        }
        ws.column_dimensions.clear()
        for letter, (width, hidden, best_fit) in old.items():
            idx = column_index_from_string(letter)
            if idx >= PT_TOTAL:
                idx += delta_ww + delta_pt
            elif idx >= WW_TOTAL:
                idx += delta_ww
            dim = ws.column_dimensions[_cl(idx)]
            dim.width = width
            dim.hidden = hidden
            dim.bestFit = best_fit

    def _expand_sheet(self, ws, layout, delta_ww, delta_pt, styles):
        delta = delta_ww + delta_pt

        # Capture the prototype activity-column styles before cells move.
        ww_proto = {r: copy(ws.cell(r, WW_FIRST + STANDARD_WW - 1)._style) for r in range(1, 121)}
        pt_proto = {r: copy(ws.cell(r, PT_FIRST + STANDARD_PT - 1)._style) for r in range(1, 121)}

        for rng in [str(m) for m in ws.merged_cells.ranges if m.max_col >= 6]:
            ws.unmerge_cells(rng)

        if delta_pt:
            ws.insert_cols(PT_TOTAL, delta_pt)
        if delta_ww:
            ws.insert_cols(WW_TOTAL, delta_ww)

        self._shift_column_dimensions(ws, delta_ww, delta_pt)

        # Style the newly inserted activity columns from the prototype.
        for r in range(1, 121):
            for c in range(WW_TOTAL, WW_TOTAL + delta_ww):
                ws.cell(r, c)._style = copy(ww_proto[r])
            for c in range(PT_TOTAL, PT_TOTAL + delta_pt):
                ws.cell(r, c)._style = copy(pt_proto[r])

        # Move the right-side images with the inserted columns.
        for image in ws._images:
            anchor = image.anchor._from
            if anchor.col >= PT_TOTAL:
                anchor.col += delta
            elif anchor.col >= WW_TOTAL:
                anchor.col += delta_ww

        # Clear the header block so stale (shifted) content does not linger.
        for r in (5, 7, 10, 11, 12, 13, 14, 15):
            for c in range(WW_FIRST, layout["last"] + 1):
                ws.cell(r, c).value = None

        self._rewrite_header_info(ws, delta, styles)
        self._write_row12(ws, layout)
        self._write_row14(ws, layout)

        for rng in self._dynamic_merges(layout, delta):
            ws.merge_cells(rng)

    def _rewrite_header_info(self, ws, delta, styles):
        def put(row, col, value, style):
            cell = ws.cell(row, col)
            cell.value = value
            if style is not None:
                cell._style = copy(style)

        put(5, 5, "REGION", styles["label"])
        put(5, 6, "='INPUT DATA'!E10", styles["value"])
        put(7, 5, "SCHOOL NAME", styles["label"])
        put(7, 6, "='INPUT DATA'!E14", styles["value"])

        put(5, 17 + delta, "DIVISION", styles["info_label"])
        put(5, 18 + delta, "='INPUT DATA'!E11", styles["info_value"])
        put(5, 25 + delta, "SCHOOL ID", styles["info_label"])
        put(5, 26 + delta, "='INPUT DATA'!E13", styles["info_value"])
        put(7, 25 + delta, "SCHOOL YEAR", styles["info_label"])
        put(7, 26 + delta, "='INPUT DATA'!E15", styles["info_value"])

        put(10, 6, "GRADE LEVEL", styles["label"])
        put(10, 10, "='INPUT DATA'!E25", styles["value"])
        put(11, 6, "SECTION", styles["label"])
        put(11, 10, "='INPUT DATA'!E26", styles["value"])

        put(10, 14 + delta, "TEACHER", styles["info_label"])
        put(10, 17 + delta, "='INPUT DATA'!E23", styles["info_value"])
        put(10, 25 + delta, "SUBJECT", styles["info_label"])
        put(10, 27 + delta, "='INPUT DATA'!E24", styles["info_value"])

    # ------------------------------------------------------------------
    # INPUT DATA + FINAL GRADES
    # ------------------------------------------------------------------
    def _fill_input_data(self, wb, data):
        ws = wb["INPUT DATA"]
        ws["E15"] = data["school_year"].name
        channel = data["channel"]
        ws["E23"] = channel.user_id.name or ""
        ws["E24"] = channel.name or ""
        ws["E25"] = data["section"].grade_level_id.name or ""
        ws["E26"] = data["section"].name or ""
        for slot, enrollment in enumerate(data["males"]):
            ws.cell(11 + slot, 11).value = enrollment.full_name
        for slot, enrollment in enumerate(data["females"]):
            ws.cell(11 + slot, 14).value = enrollment.full_name

    def _fix_final_grades(self, wb, term_grade_letters):
        ws = wb["FINAL GRADES"]
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if isinstance(value, ArrayFormula):
                    text = value.text
                elif isinstance(value, str):
                    text = value
                else:
                    continue
                if not text.startswith("="):
                    continue
                new_text = text
                for idx, letter in term_grade_letters.items():
                    if letter == "AC":
                        continue
                    if "'TERM %d'!" % (idx + 1) in new_text:
                        new_text = new_text.replace("$AC$", "$%s$" % letter)
                if new_text != text:
                    if isinstance(value, ArrayFormula):
                        cell.value = ArrayFormula(value.ref, new_text)
                    else:
                        cell.value = new_text

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    def _fill_term_sheet(self, ws, term, data, term_index):
        ww_n = max(STANDARD_WW, len(term["ww"]))
        pt_n = max(STANDARD_PT, len(term["pt"]))
        layout = self._layout(ww_n, pt_n)
        term["layout"] = layout
        delta_ww = ww_n - STANDARD_WW
        delta_pt = pt_n - STANDARD_PT

        if delta_ww or delta_pt:
            self._expand_sheet(
                ws, layout, delta_ww, delta_pt, self._capture_styles(ws)
            )
        else:
            self._write_row12(ws, layout)
            self._write_row14(ws, layout)

        self._write_row15(ws, layout, term, data["type_weights"])

        for r in list(range(18, 68)) + list(range(69, 119)):
            self._write_student_formulas(ws, layout, r)

        score_map = data["score_map"]
        for slot, enrollment in enumerate(data["males"]):
            self._write_student_scores(ws, layout, 18 + slot, term, enrollment, score_map)
        for slot, enrollment in enumerate(data["females"]):
            self._write_student_scores(ws, layout, 69 + slot, term, enrollment, score_map)

    def _generate_ecr(self, wizard):
        data = self._get_data(wizard)
        with file_open(ECR_TEMPLATE_PATH, "rb") as handle:
            wb = openpyxl.load_workbook(io.BytesIO(handle.read()))

        self._fill_input_data(wb, data)

        term_grade_letters = {}
        for term_index, term in enumerate(data["terms"]):
            ws = wb[TERM_SHEETS[term_index]]
            self._fill_term_sheet(ws, term, data, term_index)
            term_grade_letters[term_index] = _cl(term["layout"]["tg"])

        self._fix_final_grades(wb, term_grade_letters)

        wb.calculation.fullCalcOnLoad = True
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.read()

    def ecr_report_action(self, wizard):
        school_year, channel, section = self._validate_wizard(wizard)
        filename = (
            "%s_%s - %s_Official ECR.xlsx"
            % (school_year.name, channel.name, section.name)
        )

        attachment = self.env["ir.attachment"].search(
            [
                ("name", "=", filename),
                ("res_model", "=", "sis.ecr.report.wizard"),
            ],
            limit=1,
        )

        file_data = base64.b64encode(self._generate_ecr(wizard))
        if attachment:
            attachment.write({"datas": file_data})
        else:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": filename,
                    "datas": file_data,
                    "type": "binary",
                    "res_model": "sis.ecr.report.wizard",
                    "res_id": wizard.id,
                }
            )

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
