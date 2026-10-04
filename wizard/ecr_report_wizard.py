from odoo import api, fields, models


class EcrReportWizard(models.TransientModel):
    _name = "sis.ecr.report.wizard"
    _description = "Generate Official ECR"

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

    @api.onchange("school_year_id")
    def _onchange_school_year_id(self):
        self.channel_id = False

    def generate_ecr(self):
        return self.env["report.obbs_sis.ecr_export"].ecr_report_action(self)
