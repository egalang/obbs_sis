from odoo import models, fields, api


class ActivityType(models.Model):
    _name = "sis.activity.type"
    _description = "Activity Types"

    SELECTIONS = [
        ("written_works", "Written Works"),
        ("performance_tasks", "Performance Tasks"),
        ("quarterly_exam", "Quarterly Exam"),
    ]

    name = fields.Selection(
        selection=SELECTIONS,
        string="Activity Type",
        required=True,
        help="Select the activity types for this subject",
    )
    description = fields.Text(
        string="Description",
        help="Short descriptive information regarding the activity",
    )
    weight = fields.Integer(string="Weight (%)", help="e.g. 50 (for 50%).")
    channel_id = fields.Many2one("slide.channel", string="Channel")

    display_name = fields.Char(
        string="Display Name", compute="_compute_display_name", store=False
    )

    @api.depends("name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = dict(self.SELECTIONS).get(rec.name, rec.name)
