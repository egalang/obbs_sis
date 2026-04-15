from odoo import models, fields, api


class SisAddEnrolleesWizard(models.TransientModel):
    _name = "sis.add.enrollees.wizard"
    _description = "Add Enrollees Wizard"

    enrollment_ids = fields.Many2many(
        "sis.enrollment",
        domain=[
            ("enrollment_status", "=", "accepted")
        ],  # Restrict to accepted enrollments
    )

    section_id = fields.Many2one(
        "sis.sections",
        string="Section",
        required=True,
        default=lambda self: self.env.context.get("default_section_id"),
    )
    grade_level_id = fields.Many2one(
        "sis.grade.level",
        string="Grade Level",
        readonly=True,
        compute="_compute_grade_level_id",
        store=True,
    )

    @api.depends("section_id")
    def _compute_grade_level_id(self):
        for rec in self:
            rec.grade_level_id = (
                rec.section_id.grade_level_id if rec.section_id else False
            )

    def action_assign_enrollments(self):
        for enrollment in self.enrollment_ids:
            enrollment.write(
                {
                    "grade_level_id": self.grade_level_id.id,
                    "section_id": self.section_id.id,
                }
            )
        return {"type": "ir.actions.act_window_close"}