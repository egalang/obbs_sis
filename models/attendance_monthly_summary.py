from collections import defaultdict
from datetime import datetime
import calendar

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AttendanceMonthlySummary(models.Model):
    _name = "sis.attendance.monthly_summary"
    _description = "Monthly Attendance Summary"
    _order = "school_year_id desc, year desc, month asc"

    enrollment_id = fields.Many2one(
        "sis.enrollment",
        required=True,
        ondelete="cascade",
    )
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="enrollment_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    month = fields.Selection(
        selection=[(str(i), calendar.month_name[i]) for i in range(1, 13)],
        required=True,
    )

    year = fields.Char(required=True)

    present_days = fields.Integer(string="Days Present")

    expected_days = fields.Integer(
        string="School Days (Expected)",
        compute="_compute_expected_days",
        inverse="_inverse_expected_days",
        store=True,
    )

    absent_days = fields.Integer(
        string="Days Absent",
        compute="_compute_absent_days",
        inverse="_inverse_absent_days",
        store=True,
    )

    tardy_days = fields.Integer(string="Tardy Days")

    _sql_constraints = [
        (
            "uniq_enroll_month",
            "unique(enrollment_id, month, year)",
            "One summary per student per month.",
        )
    ]

    @api.depends("month", "year", "school_year_id")
    def _compute_expected_days(self):
        ref_model = self.env["sis.attendance.school_days"]
        for rec in self:
            if not rec.month or not rec.year or not rec.school_year_id:
                rec.expected_days = 0
                continue

            ref_row = ref_model.search(
                [
                    ("school_year_id", "=", rec.school_year_id.id),
                    ("month", "=", rec.month),
                    ("year", "=", rec.year),
                ],
                limit=1,
            )
            rec.expected_days = ref_row.school_days if ref_row else 0

    def _inverse_expected_days(self):
        ref_model = self.env["sis.attendance.school_days"]
        for rec in self:
            if not rec.month or not rec.year or not rec.school_year_id:
                continue

            ref_row = ref_model.search(
                [
                    ("school_year_id", "=", rec.school_year_id.id),
                    ("month", "=", rec.month),
                    ("year", "=", rec.year),
                ],
                limit=1,
            )

            values = {
                "school_year_id": rec.school_year_id.id,
                "month": rec.month,
                "year": rec.year,
                "school_days": rec.expected_days,
            }
            if ref_row:
                ref_row.school_days = rec.expected_days
            else:
                ref_model.create(values)

    @api.depends("expected_days", "present_days")
    def _compute_absent_days(self):
        for rec in self:
            rec.absent_days = max(0, rec.expected_days - rec.present_days)

    def _inverse_absent_days(self):
        for rec in self:
            rec.present_days = max(0, rec.expected_days - rec.absent_days)

    @api.constrains("present_days", "expected_days", "tardy_days")
    def _check_day_values(self):
        for rec in self:
            if rec.present_days < 0 or rec.expected_days < 0 or rec.tardy_days < 0:
                raise ValidationError(_("Attendance day values cannot be negative."))


class AttendanceMonthlySummaryCron(models.Model):
    _inherit = "sis.attendance.monthly_summary"

    @api.model
    def cron_update_attendance_summary(self):
        school_day_refs = self.env["sis.attendance.school_days"].search([])

        for ref in school_day_refs:
            if not ref.school_year_id:
                continue

            month = int(ref.month)
            year = int(ref.year)

            start_date = datetime(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = datetime(year, month, last_day, 23, 59, 59)

            enrollments = self.env["sis.enrollment"].search(
                [("school_year_id", "=", ref.school_year_id.id)]
            )
            if not enrollments:
                continue

            logs = self.env["sis.student.attendance.log"].search(
                [
                    ("school_year_id", "=", ref.school_year_id.id),
                    ("attendance_datetime", ">=", start_date),
                    ("attendance_datetime", "<=", end_date),
                    ("log_type", "in", ["class_in", "class_out"]),
                ]
            )

            grouped = defaultdict(set)
            for log in logs:
                if not log.enrollment_id:
                    continue
                key = (log.enrollment_id.id, log.attendance_datetime.date())
                grouped[key].add(log.log_type)

            counter = defaultdict(int)
            for (enroll_id, _), tags in grouped.items():
                if {"class_in", "class_out"}.issubset(tags):
                    counter[enroll_id] += 1

            for enrollment in enrollments:
                present_days = counter.get(enrollment.id, 0)

                summary = self.search(
                    [
                        ("enrollment_id", "=", enrollment.id),
                        ("month", "=", str(month)),
                        ("year", "=", str(year)),
                    ],
                    limit=1,
                )

                values = {
                    "enrollment_id": enrollment.id,
                    "month": str(month),
                    "year": str(year),
                    "present_days": present_days,
                }

                if summary:
                    summary.write(values)
                else:
                    self.create(values)
