from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    enrollment_id = fields.Many2one(
        "sis.enrollment",
        string="Student",
        compute="_compute_enrollment_id",
        store=True,
        readonly=True,
        help="The enrollee linked to the payment",
    )
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="enrollment_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    @api.depends("invoice_ids.enrollment_id")
    def _compute_enrollment_id(self):
        for payment in self:
            enrollments = payment.invoice_ids.mapped("enrollment_id")
            payment.enrollment_id = enrollments[0] if enrollments else False
