from odoo import models, fields


class GenerateIdWizard(models.TransientModel):
    _name = "sis.generate.id.wizard"
    _description = "Generate Student ID Wizard"

    enrollment_id = fields.Many2one("sis.enrollment", required=True)
    id_type = fields.Selection(
        [
            ("preschool", "Pre-School"),
            ("elementary", "Elementary"),
            ("highschool", "High School"),
        ],
        string="ID Type",
        required=True,
    )

    def action_generate_id(self):
        return self.env.ref("obbs_sis.action_report_student_id").report_action(
            self.enrollment_id, data={"id_type": self.id_type}
        )
