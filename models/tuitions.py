from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SisTuition(models.Model):
    _name = "sis.tuition"
    _description = "Tuition Fees"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Tuition Name",
        compute="_compute_name",
        store=True,
        readonly=True,
        default="",
        tracking=True,
    )

    grade_level_id = fields.Many2one(
        "sis.grade.level", string="Grade Level", required=True, tracking=True
    )

    payment_plan_id = fields.Many2one(
        "sis.payment.plan", string="Payment Plan", required=True, tracking=True
    )
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        required=True,
        tracking=True,
        index=True,
        default=lambda self: self.env.company.active_school_year_id,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        readonly=True,
        default=lambda self: self.env.user.company_id.currency_id.id,
    )

    total_amount = fields.Monetary(
        string="Total Amount",
        currency_field="currency_id",
        compute="_compute_total_amount",
        tracking=True,
        readonly=True,
        help="Total cost of tuition plan base on tuition tranches",
    )

    tranche_ids = fields.One2many(
        "sis.tuition.tranche",
        "tuition_id",
        string="Tranches",
    )

    _sql_constraints = [
        (
            "sis_tuition_grade_payment_school_year_uniq",
            "unique(grade_level_id, payment_plan_id, school_year_id)",
            "A tuition plan already exists for the same grade level, payment plan, and school year.",
        )
    ]

    @api.depends("grade_level_id.name", "payment_plan_id.name")
    def _compute_name(self):
        for record in self:
            if record.grade_level_id and record.payment_plan_id:
                grade = record.grade_level_id.name or "Unknown Grade"
                term = record.payment_plan_id.name or "Unknown Term"
                record.name = f"{grade} - {term}"
            else:
                record.name = ""

    @api.onchange("grade_level_id", "payment_plan_id")
    def _onchange_tuition_details(self):
        for tuition in self:
            if tuition.tranche_ids:
                tuition.tranche_ids._compute_name()
                tuition.tranche_ids.write({"name": tuition.name})

    @api.depends("tranche_ids.amount")
    def _compute_total_amount(self):
        for record in self:
            try:
                if not record.tranche_ids:
                    record.total_amount = 0
                    continue

                total = 0
                for tranche in record.tranche_ids:
                    if tranche.amount < 0:
                        raise ValueError("The amount in a tranche cannot be negative.")
                    total += tranche.amount

                record.total_amount = total

            except ValueError as e:
                _logger.error(
                    f"Error calculating total amount for tuition {record.id}: {e}"
                )
                record.total_amount = 0

            except Exception as e:
                _logger.error(
                    f"Unexpected error while calculating total amount for tuition {record.id}: {e}"
                )
                record.total_amount = 0

    @api.constrains("grade_level_id", "payment_plan_id", "school_year_id")
    def _check_unique_grade_and_term(self):
        for record in self:
            domain = [
                ("grade_level_id", "=", record.grade_level_id.id),
                ("payment_plan_id", "=", record.payment_plan_id.id),
                ("school_year_id", "=", record.school_year_id.id),
                ("id", "!=", record.id),
            ]
            duplicate = self.search_count(domain)
            if duplicate:
                raise ValidationError(
                    _(
                        "A tuition plan already exists for Grade %(grade)s, Term %(term)s, and School Year %(school_year)s."
                    )
                    % {
                        "grade": record.grade_level_id.name,
                        "term": record.payment_plan_id.name,
                        "school_year": record.school_year_id.name,
                    }
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


class SisTuitionTranche(models.Model):
    _name = "sis.tuition.tranche"
    _description = "Tuition Tranche"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Tuition Tranches", compute="_compute_name", store=True, tracking=True
    )
    tuition_id = fields.Many2one("sis.tuition", string="Tuition", required=True)
    school_year_id = fields.Many2one(
        "sis.school.year",
        related="tuition_id.school_year_id",
        string="School Year",
        store=True,
        readonly=True,
    )
    tranche_number = fields.Integer(string="Tranche Number", required=True)
    amount = fields.Monetary(
        string="Amount", currency_field="currency_id", required=True, tracking=True
    )
    due_date = fields.Date(string="Due Date", required=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency", related="tuition_id.currency_id", string="Currency", store=True
    )

    @api.depends(
        "tranche_number",
        "tuition_id.grade_level_id.name",
        "tuition_id.payment_plan_id.name",
    )
    def _compute_name(self):
        for record in self:
            tuition_name = record.tuition_id.name or "Unknown Tuition"
            record.name = f"{tuition_name} - Tranche {record.tranche_number}"

    @api.constrains("tranche_number", "tuition_id")
    def _check_tranche_validations(self):
        for record in self:
            domain = [
                ("tuition_id", "=", record.tuition_id.id),
                ("tranche_number", "=", record.tranche_number),
                ("id", "!=", record.id),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _(
                        "Tranche number %(number)s already exists for the tuition plan '%(tuition)s'."
                    )
                    % {
                        "number": record.tranche_number,
                        "tuition": record.tuition_id.name,
                    }
                )

            if record.tranche_number <= 0:
                raise ValidationError(_("Tranche number must be a positive integer."))

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
