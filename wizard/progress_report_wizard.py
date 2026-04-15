from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProgressReportWizard(models.TransientModel):
    _name = "sis.progress.report.wizard"
    _description = "Generate Progress Report"

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        required=True,
        default=lambda self: self.env.company.active_school_year_id,
    )
    channel_id = fields.Many2one(
        "slide.channel",
        string="Subject",
        required=True,
        domain="[('section_id.school_year_id', '=', school_year_id)]",
    )
    period_id = fields.Many2one(
        "sis.period",
        string="Grading Period",
        required=True,
        domain="[('school_year_id', '=', school_year_id)]",
    )

    @api.onchange("school_year_id")
    def _onchange_school_year_id(self):
        self.channel_id = False
        self.period_id = False

    @api.constrains("school_year_id", "period_id")
    def _check_period_school_year(self):
        for wizard in self:
            if wizard.period_id and wizard.period_id.school_year_id != wizard.school_year_id:
                raise ValidationError(
                    _("The selected grading period must belong to the selected school year.")
                )

    def generate_report(self):
        return self.env["report.obbs_sis.progress_report_export"].report_action(self)
