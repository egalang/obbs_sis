from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Activity(models.Model):
    _name = "sis.activity"
    _description = "Student Activity"

    name = fields.Char(string="Activity Name", required=True)

    period_id = fields.Many2one(
        "sis.period",
        string="Grading Period",
        required=True,
        help="Grading period this activity belongs to.",
    )

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="period_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    activity_type_id = fields.Many2one(
        "sis.activity.type",
        string="Activity Type",
        required=True,
        help="Type of activity (e.g., Written Works, Performance Tasks).",
    )

    channel_id = fields.Many2one(
        "slide.channel",
        string="Course",
        required=True,
        help="Course this activity is associated with.",
    )

    max_score = fields.Float(
        string="Max Score", required=True, help="The maximum score of the activity"
    )

    gradebook_ids = fields.One2many("sis.gradebook", "activity_id", string="Grades")

    section_id = fields.Many2one(
        "sis.sections",
        string="Section",
        compute="_compute_section_id",
        store=True,
        readonly=True,
    )

    @api.onchange("channel_id")
    def _onchange_channel_id_set_domain_for_activity_type(self):
        if self.channel_id:
            return {
                "domain": {
                    "activity_type_id": [("channel_id", "=", self.channel_id.id)]
                }
            }
        return {"domain": {"activity_type_id": []}}

    @api.depends("channel_id.section_id")
    def _compute_section_id(self):
        for record in self:
            record.section_id = record.channel_id.section_id if record.channel_id else False

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        today = date.today()
        if "period_id" in fields_list:
            domain = [("start_date", "<=", today), ("end_date", ">=", today)]
            context_school_year_id = self.env.context.get("default_school_year_id")
            school_year = self.env["sis.school.year"].browse(context_school_year_id) if context_school_year_id else self.env.company.active_school_year_id
            if school_year:
                domain.append(("school_year_id", "=", school_year.id))
            period = self.env["sis.period"].search(domain, limit=1)
            if period:
                defaults["period_id"] = period.id
        return defaults

    @api.constrains("max_score")
    def _check_max_score_positive(self):
        for record in self:
            if record.max_score <= 0:
                raise ValidationError(_("Max Score must be greater than zero."))

    @api.constrains("period_id", "channel_id")
    def _check_period_channel_school_year_alignment(self):
        for record in self:
            section = record.channel_id.section_id
            if not record.period_id or not section:
                continue
            if section.school_year_id != record.period_id.school_year_id:
                raise ValidationError(
                    _("The selected course section must belong to the same school year as the grading period.")
                )

    @api.onchange("channel_id")
    def _onchange_channel_id_auto_populate_gradebook(self):
        if not self.channel_id or not self.channel_id.section_id:
            return

        section = self.channel_id.section_id
        domain = [
            ("section_id", "=", section.id),
            ("enrollment_status", "=", "accepted"),
        ]
        if self.period_id and self.period_id.school_year_id:
            domain.append(("school_year_id", "=", self.period_id.school_year_id.id))
        enrollments = self.env["sis.enrollment"].search(domain)

        existing_enrollment_ids = {line.enrollment_id.id for line in self.gradebook_ids}
        new_lines = [
            (0, 0, {"enrollment_id": e.id})
            for e in enrollments
            if e.id not in existing_enrollment_ids
        ]
        self.gradebook_ids = [(4, line.id) for line in self.gradebook_ids] + new_lines

    @api.model
    def create(self, vals):
        activity = super().create(vals)
        if vals.get("channel_id"):
            channel = self.env["slide.channel"].browse(vals["channel_id"])
            section = channel.section_id
            if section:
                domain = [
                    ("section_id", "=", section.id),
                    ("enrollment_status", "=", "accepted"),
                ]
                if activity.period_id and activity.period_id.school_year_id:
                    domain.append(("school_year_id", "=", activity.period_id.school_year_id.id))
                enrollments = self.env["sis.enrollment"].search(domain)
                existing_enrollments = {line.enrollment_id.id for line in activity.gradebook_ids}
                for enrollment in enrollments:
                    if enrollment.id not in existing_enrollments:
                        self.env["sis.gradebook"].create(
                            {
                                "activity_id": activity.id,
                                "enrollment_id": enrollment.id,
                            }
                        )
        return activity
