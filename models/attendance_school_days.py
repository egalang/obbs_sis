from calendar import monthrange
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
import calendar


class AttendanceSchoolDays(models.Model):
    _name = "sis.attendance.school_days"
    _description = "Reference: School Days per Month"
    _order = "school_year_id desc, year desc, month asc"

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        required=True,
        index=True,
        default=lambda self: self.env.company.active_school_year_id,
    )
    month = fields.Selection(
        selection=[(str(i), calendar.month_name[i]) for i in range(1, 13)],
        required=True,
        string="Month",
    )
    year = fields.Char(required=True, string="Year")
    school_days = fields.Integer(string="Expected School Days", required=True)

    _sql_constraints = [
        (
            "uniq_month_year_school_year",
            "unique(month, year, school_year_id)",
            "Expected school days must be unique per month per year and school year.",
        )
    ]

    @api.constrains("school_days")
    def _check_school_days_non_negative(self):
        for record in self:
            if record.school_days < 0:
                raise ValidationError(_("Expected school days cannot be negative."))

    @api.constrains("month", "year", "school_year_id")
    def _check_month_within_school_year(self):
        for record in self:
            if not (record.month and record.year and record.school_year_id):
                continue
            try:
                month = int(record.month)
                year = int(record.year)
                last_day = monthrange(year, month)[1]
                ref_date = date(year, month, last_day)
            except Exception:
                raise ValidationError(_("Month and year must form a valid calendar period."))

            school_year = record.school_year_id
            if school_year.date_start and ref_date < school_year.date_start:
                raise ValidationError(
                    _("School days reference must fall within the selected school year.")
                )
            if school_year.date_end and date(year, month, 1) > school_year.date_end:
                raise ValidationError(
                    _("School days reference must fall within the selected school year.")
                )

    def _check_closed_school_year_write(self):
        if self.env.user.has_group("obbs_sis.group_sis_admin"):
            return
        blocked = self.filtered(lambda r: r.school_year_id.state == "closed")
        if blocked:
            raise UserError(
                _("Closed school year attendance references are read-only for non-admin users.")
            )

    def write(self, vals):
        self._check_closed_school_year_write()
        return super().write(vals)

    def unlink(self):
        self._check_closed_school_year_write()
        return super().unlink()
