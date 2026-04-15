# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SisSchoolYear(models.Model):
    _name = "sis.school.year"
    _description = "School Year"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(
        string="School Year",
        required=True,
        tracking=True,
    )
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        default="draft",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    previous_school_year_id = fields.Many2one(
        "sis.school.year",
        string="Previous School Year",
        domain="[('company_id', '=', company_id)]",
    )

    section_count = fields.Integer(compute="_compute_related_counts")
    period_count = fields.Integer(compute="_compute_related_counts")
    tuition_count = fields.Integer(compute="_compute_related_counts")
    enrollment_count = fields.Integer(compute="_compute_related_counts")

    _sql_constraints = [
        (
            "sis_school_year_name_company_uniq",
            "unique(name, company_id)",
            "School year name must be unique per company.",
        )
    ]

    @api.depends("state")
    def _compute_related_counts(self):
        section_data = self.env["sis.sections"]._read_group(
            [("school_year_id", "in", self.ids)], ["school_year_id"], ["__count"]
        )
        period_data = self.env["sis.period"]._read_group(
            [("school_year_id", "in", self.ids)], ["school_year_id"], ["__count"]
        )
        tuition_data = self.env["sis.tuition"]._read_group(
            [("school_year_id", "in", self.ids)], ["school_year_id"], ["__count"]
        )
        enrollment_data = self.env["sis.enrollment"]._read_group(
            [("school_year_id", "in", self.ids)], ["school_year_id"], ["__count"]
        )

        section_map = {record.id: count for record, count in section_data}
        period_map = {record.id: count for record, count in period_data}
        tuition_map = {record.id: count for record, count in tuition_data}
        enrollment_map = {record.id: count for record, count in enrollment_data}

        for record in self:
            record.section_count = section_map.get(record.id, 0)
            record.period_count = period_map.get(record.id, 0)
            record.tuition_count = tuition_map.get(record.id, 0)
            record.enrollment_count = enrollment_map.get(record.id, 0)

    @api.constrains("date_start", "date_end")
    def _check_date_range(self):
        for record in self:
            if record.date_start and record.date_end and record.date_start > record.date_end:
                raise ValidationError(
                    _("School year start date cannot be later than the end date.")
                )

    @api.constrains("state", "company_id")
    def _check_single_active_school_year(self):
        for record in self.filtered(lambda r: r.state == "active" and r.company_id):
            duplicate = self.search(
                [
                    ("id", "!=", record.id),
                    ("company_id", "=", record.company_id.id),
                    ("state", "=", "active"),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Only one active school year is allowed per company.")
                )

    @api.constrains("previous_school_year_id", "company_id")
    def _check_previous_school_year_company(self):
        for record in self:
            if (
                record.previous_school_year_id
                and record.previous_school_year_id.company_id != record.company_id
            ):
                raise ValidationError(
                    _("Previous school year must belong to the same company.")
                )

    def action_set_active(self):
        for record in self:
            if not record.company_id:
                continue
            others = self.search(
                [
                    ("id", "!=", record.id),
                    ("company_id", "=", record.company_id.id),
                    ("state", "=", "active"),
                ]
            )
            if others:
                others.write({"state": "closed"})
            record.write({"state": "active"})
            record.company_id.active_school_year_id = record.id
        return True

    def action_set_draft(self):
        for record in self:
            if record.state == "closed" and not self.env.user.has_group("obbs_sis.group_sis_admin"):
                raise UserError(_("Only SIS Administrators can reopen a closed school year."))
            record.state = "draft"
            if record.company_id.active_school_year_id == record:
                record.company_id.active_school_year_id = False
        return True

    def action_close_school_year(self):
        for record in self:
            record.state = "closed"
            if record.company_id.active_school_year_id == record:
                record.company_id.active_school_year_id = False
        return True

    def action_open_initialize_wizard(self):
        self.ensure_one()
        return {
            "name": _("Initialize School Year"),
            "type": "ir.actions.act_window",
            "res_model": "sis.initialize.school.year.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_target_school_year_id": self.id,
                "default_source_school_year_id": self.previous_school_year_id.id,
            },
        }

    def _open_related_records(self, model_name, action_name, extra_domain=None):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(action_name)
        action["domain"] = [("school_year_id", "=", self.id)] + (extra_domain or [])
        action["context"] = {
            **self.env.context,
            "default_school_year_id": self.id,
            "search_default_group_by_school_year": 0,
            "active_school_year_id": self.id,
        }
        return action

    def action_view_sections(self):
        return self._open_related_records("sis.sections", "obbs_sis.action_sis_sections")

    def action_view_periods(self):
        return self._open_related_records("sis.period", "obbs_sis.action_sis_period")

    def action_view_tuitions(self):
        return self._open_related_records("sis.tuition", "obbs_sis.action_sis_tuition_fees")

    def action_view_enrollments(self):
        return self._open_related_records("sis.enrollment", "obbs_sis.action_sis_enrollment")
