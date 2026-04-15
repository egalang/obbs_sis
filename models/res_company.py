from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    active_school_year_id = fields.Many2one(
        "sis.school.year",
        string="Active School Year",
        tracking=True,
        domain="[('company_id', '=', id)]",
    )

    registrar_email = fields.Char(
        string="Registrar Email",
        tracking=True,
    )

    @api.constrains("active_school_year_id")
    def _check_active_school_year_company(self):
        for company in self:
            if (
                company.active_school_year_id
                and company.active_school_year_id.company_id != company
            ):
                raise ValidationError(
                    _("The active school year must belong to the same company.")
                )
