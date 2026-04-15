from odoo import api, fields, models
import re


class AccountMove(models.Model):
    _inherit = "account.move"

    enrollment_id = fields.Many2one(
        "sis.enrollment",
        string="Student",
        compute="_compute_enrollment",
        store=True,
        readonly=True,
        help="The enrollee linked to the invoice",
    )
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="enrollment_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    enrollment_id_visible = fields.Boolean(
        compute="_compute_enrollment_id_visible",
        store=False,
    )

    @api.depends("invoice_origin")
    def _compute_enrollment(self):
        pattern = re.compile(r"Enrollment #(\d+)")
        for inv in self:
            match = pattern.search(inv.invoice_origin or "")
            if match:
                enrollment_id = int(match.group(1))
                enrollment = self.env["sis.enrollment"].browse(enrollment_id)
                inv.enrollment_id = enrollment if enrollment.exists() else False
            else:
                inv.enrollment_id = False

    @api.depends("invoice_origin")
    def _compute_enrollment_id_visible(self):
        for rec in self:
            rec.enrollment_id_visible = bool(
                rec.invoice_origin and rec.invoice_origin.startswith("Enrollment #")
            )
