from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SisSections(models.Model):
    _name = "sis.sections"
    _description = "Sections"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "display_name"

    name = fields.Char(string="Section", required=True, tracking=True)
    grade_level_id = fields.Many2one(
        "sis.grade.level", string="Grade Level", required=True, tracking=True
    )
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        required=True,
        tracking=True,
        index=True,
        default=lambda self: self.env.company.active_school_year_id,
    )

    display_name = fields.Char(compute="_compute_display_name", store=True)

    enrollment_ids = fields.One2many(
        "sis.enrollment", "section_id", string="Enrollments"
    )

    advisor_id = fields.Many2one(
        "res.users",
        string="Advisor",
        domain=[("share", "=", False)],
        tracking=True,
    )

    _sql_constraints = [
        (
            "sis_sections_grade_school_year_uniq",
            "unique(name, grade_level_id, school_year_id)",
            "Section must be unique per grade level and school year.",
        )
    ]

    @api.depends("name", "grade_level_id.name")
    def _compute_display_name(self):
        for record in self:
            if record.grade_level_id:
                record.display_name = f"{record.grade_level_id.name} - {record.name}"
            else:
                record.display_name = record.name or ""

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

    def action_open_add_enrollees_wizard(self):
        self.ensure_one()
        return {
            "name": "Add Enrollees",
            "type": "ir.actions.act_window",
            "res_model": "sis.add.enrollees.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_grade_level_id": self.grade_level_id.id,
                "default_section_id": self.id,
                "default_school_year_id": self.school_year_id.id,
            },
        }
