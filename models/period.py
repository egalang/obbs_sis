from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class Period(models.Model):
    _name = "sis.period"
    _description = "Grading Period"
    _order = "school_year_id desc, start_date, id"

    name = fields.Char(string="Period Name", required=True)
    description = fields.Text(string="Description")
    code = fields.Char(
        required=True,
        string="Code",
        help="Unique code for the grading period",
    )

    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        required=True,
        index=True,
        default=lambda self: self.env.company.active_school_year_id,
    )

    _sql_constraints = [
        (
            "sis_period_code_school_year_uniq",
            "unique(code, school_year_id)",
            "Grading period code must be unique per school year.",
        )
    ]

    @api.constrains("start_date", "end_date")
    def _check_date_range(self):
        for record in self:
            if (
                record.start_date
                and record.end_date
                and record.start_date > record.end_date
            ):
                raise ValidationError(_("Start Date cannot be after End Date."))

    @api.constrains("start_date", "end_date", "school_year_id")
    def _check_dates_within_school_year(self):
        for record in self:
            if not record.school_year_id:
                continue
            sy = record.school_year_id
            if sy.date_start and record.start_date and record.start_date < sy.date_start:
                raise ValidationError(
                    _("Grading period start date must fall within the selected school year.")
                )
            if sy.date_end and record.end_date and record.end_date > sy.date_end:
                raise ValidationError(
                    _("Grading period end date must fall within the selected school year.")
                )

    def _check_closed_school_year_write(self):
        if self.env.user.has_group("obbs_sis.group_sis_admin"):
            return
        blocked = self.filtered(lambda r: r.school_year_id.state == "closed")
        if blocked:
            raise UserError(
                _("Closed school year setup records are read-only for non-admin users.")
            )

    def write(self, vals):
        self._check_closed_school_year_write()
        return super().write(vals)

    def unlink(self):
        self._check_closed_school_year_write()
        return super().unlink()
