from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SisInitializeSchoolYearWizard(models.TransientModel):
    _name = "sis.initialize.school.year.wizard"
    _description = "Initialize School Year"

    target_school_year_id = fields.Many2one(
        "sis.school.year",
        string="Target School Year",
        required=True,
    )
    source_school_year_id = fields.Many2one(
        "sis.school.year",
        string="Source School Year",
        required=True,
        domain="[('company_id', '=', company_id), ('id', '!=', target_school_year_id)]",
    )
    company_id = fields.Many2one(
        "res.company",
        related="target_school_year_id.company_id",
        store=False,
        readonly=True,
    )

    copy_sections = fields.Boolean(default=True)
    copy_tuitions = fields.Boolean(default=True)
    copy_periods = fields.Boolean(default=True)
    clear_existing = fields.Boolean(
        string="Clear Existing Draft Setup First",
        help="Delete existing sections, periods, and tuition setup already attached to the target school year before copying.",
    )
    activate_after_init = fields.Boolean(string="Set Target School Year Active After Initialization")
    result_message = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        if active_model == "sis.school.year" and active_id and "target_school_year_id" in fields_list:
            target = self.env["sis.school.year"].browse(active_id)
            res.setdefault("target_school_year_id", target.id)
            if target.previous_school_year_id and "source_school_year_id" in fields_list:
                res.setdefault("source_school_year_id", target.previous_school_year_id.id)
        return res

    def _validate(self):
        self.ensure_one()
        if self.target_school_year_id == self.source_school_year_id:
            raise ValidationError(_("The target and source school year must be different."))
        if self.target_school_year_id.company_id != self.source_school_year_id.company_id:
            raise ValidationError(_("Target and source school year must belong to the same company."))
        if self.target_school_year_id.state == "closed":
            raise UserError(_("Closed school years cannot be initialized."))
        if not (self.copy_sections or self.copy_tuitions or self.copy_periods):
            raise UserError(_("Select at least one setup group to copy."))

    def _shift_date(self, value):
        self.ensure_one()
        if not value:
            return value
        source_sy = self.source_school_year_id
        target_sy = self.target_school_year_id
        if not (source_sy.date_start and target_sy.date_start):
            return value
        delta = value - source_sy.date_start
        shifted = target_sy.date_start + delta
        return shifted

    def _prepare_period_dates(self, period):
        self.ensure_one()
        target_sy = self.target_school_year_id
        start_date = self._shift_date(period.start_date)
        end_date = self._shift_date(period.end_date)

        if target_sy.date_start and start_date and start_date < target_sy.date_start:
            start_date = target_sy.date_start
        if target_sy.date_end and end_date and end_date > target_sy.date_end:
            end_date = target_sy.date_end
        if start_date and end_date and start_date > end_date:
            start_date = end_date
        return start_date, end_date

    def _clear_existing_records(self):
        self.ensure_one()
        target_sy = self.target_school_year_id
        if self.copy_sections:
            self.env["sis.sections"].search([("school_year_id", "=", target_sy.id)]).unlink()
        if self.copy_periods:
            self.env["sis.period"].search([("school_year_id", "=", target_sy.id)]).unlink()
        if self.copy_tuitions:
            self.env["sis.tuition"].search([("school_year_id", "=", target_sy.id)]).unlink()

    def _copy_sections(self):
        self.ensure_one()
        Section = self.env["sis.sections"]
        source_records = Section.search([("school_year_id", "=", self.source_school_year_id.id)])
        created = 0
        skipped = 0
        for record in source_records:
            exists = Section.search_count([
                ("school_year_id", "=", self.target_school_year_id.id),
                ("grade_level_id", "=", record.grade_level_id.id),
                ("name", "=", record.name),
            ])
            if exists:
                skipped += 1
                continue
            record.copy({
                "school_year_id": self.target_school_year_id.id,
            })
            created += 1
        return created, skipped

    def _copy_periods(self):
        self.ensure_one()
        Period = self.env["sis.period"]
        source_records = Period.search([("school_year_id", "=", self.source_school_year_id.id)], order="start_date, id")
        created = 0
        skipped = 0
        for record in source_records:
            exists = Period.search_count([
                ("school_year_id", "=", self.target_school_year_id.id),
                ("code", "=", record.code),
            ])
            if exists:
                skipped += 1
                continue
            start_date, end_date = self._prepare_period_dates(record)
            Period.create({
                "name": record.name,
                "description": record.description,
                "code": record.code,
                "start_date": start_date,
                "end_date": end_date,
                "school_year_id": self.target_school_year_id.id,
            })
            created += 1
        return created, skipped

    def _copy_tuitions(self):
        self.ensure_one()
        Tuition = self.env["sis.tuition"]
        source_records = Tuition.search([("school_year_id", "=", self.source_school_year_id.id)])
        created = 0
        skipped = 0
        for record in source_records:
            exists = Tuition.search_count([
                ("school_year_id", "=", self.target_school_year_id.id),
                ("grade_level_id", "=", record.grade_level_id.id),
                ("payment_plan_id", "=", record.payment_plan_id.id),
            ])
            if exists:
                skipped += 1
                continue
            new_tuition = Tuition.create({
                "grade_level_id": record.grade_level_id.id,
                "payment_plan_id": record.payment_plan_id.id,
                "school_year_id": self.target_school_year_id.id,
            })
            for tranche in record.tranche_ids.sorted("tranche_number"):
                self.env["sis.tuition.tranche"].create({
                    "tuition_id": new_tuition.id,
                    "tranche_number": tranche.tranche_number,
                    "amount": tranche.amount,
                    "due_date": self._shift_date(tranche.due_date),
                })
            created += 1
        return created, skipped

    def action_initialize(self):
        self.ensure_one()
        self._validate()

        if self.clear_existing:
            self._clear_existing_records()

        created_sections = skipped_sections = 0
        created_periods = skipped_periods = 0
        created_tuitions = skipped_tuitions = 0

        if self.copy_sections:
            created_sections, skipped_sections = self._copy_sections()
        if self.copy_periods:
            created_periods, skipped_periods = self._copy_periods()
        if self.copy_tuitions:
            created_tuitions, skipped_tuitions = self._copy_tuitions()

        self.target_school_year_id.write({
            "previous_school_year_id": self.source_school_year_id.id,
        })

        lines = [
            _("School year initialization completed."),
            _("Source: %(source)s") % {"source": self.source_school_year_id.display_name},
            _("Target: %(target)s") % {"target": self.target_school_year_id.display_name},
        ]
        if self.copy_sections:
            lines.append(_("Sections created: %(created)s | skipped: %(skipped)s") % {"created": created_sections, "skipped": skipped_sections})
        if self.copy_periods:
            lines.append(_("Periods created: %(created)s | skipped: %(skipped)s") % {"created": created_periods, "skipped": skipped_periods})
        if self.copy_tuitions:
            lines.append(_("Tuition plans created: %(created)s | skipped: %(skipped)s") % {"created": created_tuitions, "skipped": skipped_tuitions})

        message = "\n".join(lines)
        self.result_message = message
        self.target_school_year_id.message_post(body=message.replace("\n", "<br/>") )

        if self.activate_after_init:
            self.target_school_year_id.action_set_active()

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
