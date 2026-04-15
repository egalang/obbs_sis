from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Gradebook(models.Model):
    _name = "sis.gradebook"
    _description = "Gradebook Entry"
    _order = "school_year_id desc, section_id, enrollment_id, activity_id"

    enrollment_id = fields.Many2one(
        comodel_name="sis.enrollment",
        string="Student Enrollment",
        required=True,
        help="The student enrolled in the class/section.",
        domain=lambda self: self._get_enrollment_domain(),
    )

    activity_id = fields.Many2one(
        comodel_name="sis.activity",
        string="Activity",
        required=True,
        help="The activity for which the grade is recorded.",
        ondelete="cascade",
    )

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="enrollment_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )
    section_id = fields.Many2one(
        "sis.sections",
        string="Section",
        related="enrollment_id.section_id",
        store=True,
        index=True,
        readonly=True,
    )
    channel_id = fields.Many2one(
        "slide.channel",
        string="Course",
        related="activity_id.channel_id",
        store=True,
        index=True,
        readonly=True,
    )
    period_id = fields.Many2one(
        "sis.period",
        string="Grading Period",
        related="activity_id.period_id",
        store=True,
        index=True,
        readonly=True,
    )

    score = fields.Float(
        string="Score",
        help="The grade or score the student earned for this activity.",
    )

    remarks = fields.Text(
        string="Remarks",
        help="Optional remarks or comments on the performance.",
    )

    weight = fields.Integer(
        string="Weight (%)",
        compute="_compute_weight_from_channel_activity_type",
        store=False,
        help="Weight of the activity type as defined in the channel.",
    )

    total_max = fields.Float(
        string="Total Max Score",
        compute="_compute_total_max",
        store=False,
        help="Total max score of all activities with same type in this course.",
    )

    percentage_score = fields.Float(
        string="Percentage Score",
        compute="_compute_percentage_score",
        store=False,
        help="Percentage score = (score / total_max) * 100",
    )

    weighted_score = fields.Float(
        string="Weighted Score",
        compute="_compute_weighted_score",
        store=False,
        help="Score weighted by activity weight and max score.",
    )

    gender = fields.Selection(
        related="enrollment_id.gender",
        string="Gender",
        store=True,
    )

    @api.depends(
        "activity_id",
        "activity_id.activity_type_id",
        "activity_id.channel_id",
        "activity_id.period_id",
    )
    def _compute_total_max(self):
        for rec in self:
            rec.total_max = 0.0
            activity = rec.activity_id
            if (
                not activity
                or not activity.activity_type_id
                or not activity.channel_id
                or not activity.period_id
            ):
                continue

            relevant_activities = self.env["sis.activity"].search(
                [
                    ("channel_id", "=", activity.channel_id.id),
                    ("activity_type_id", "=", activity.activity_type_id.id),
                    ("period_id", "=", activity.period_id.id),
                ]
            )

            rec.total_max = sum(a.max_score for a in relevant_activities if a.max_score)

    @api.depends(
        "activity_id",
        "activity_id.activity_type_id",
        "activity_id.channel_id.activity_type_ids",
    )
    def _compute_weight_from_channel_activity_type(self):
        for rec in self:
            rec.weight = 0
            activity = rec.activity_id
            if activity and activity.activity_type_id and activity.channel_id:
                match = activity.channel_id.activity_type_ids.filtered(
                    lambda at: at.id == activity.activity_type_id.id
                )
                rec.weight = match[0].weight if match else 0

    @api.depends("score", "total_max", "weight")
    def _compute_weighted_score(self):
        for rec in self:
            if not rec.score or not rec.total_max or not rec.weight:
                rec.weighted_score = 0.0
            else:
                rec.weighted_score = (rec.score * rec.weight) / rec.total_max

    @api.depends("score", "total_max")
    def _compute_percentage_score(self):
        for rec in self:
            if not rec.score or not rec.total_max:
                rec.percentage_score = 0.0
            else:
                rec.percentage_score = (rec.score / rec.total_max) * 100

    def _get_enrollment_domain(self):
        domain = []
        section_id = self.env.context.get("section_id")
        school_year_id = self.env.context.get("school_year_id")
        if section_id:
            domain.append(("section_id", "=", section_id))
        if school_year_id:
            domain.append(("school_year_id", "=", school_year_id))
        return domain

    @api.constrains("enrollment_id", "activity_id")
    def _check_unique_enrollment_activity(self):
        for record in self:
            if record.enrollment_id and record.activity_id:
                exists = self.search(
                    [
                        ("id", "!=", record.id),
                        ("enrollment_id", "=", record.enrollment_id.id),
                        ("activity_id", "=", record.activity_id.id),
                    ]
                )
                if exists:
                    raise ValidationError(
                        _("A student can only have one grade per activity.")
                    )

    @api.constrains("enrollment_id", "activity_id")
    def _check_enrollment_activity_alignment(self):
        for record in self:
            if not record.enrollment_id or not record.activity_id:
                continue
            activity_school_year = record.activity_id.period_id.school_year_id
            activity_section = record.activity_id.channel_id.section_id
            if activity_school_year and record.enrollment_id.school_year_id != activity_school_year:
                raise ValidationError(
                    _("The selected enrollment must belong to the same school year as the activity.")
                )
            if activity_section and record.enrollment_id.section_id != activity_section:
                raise ValidationError(
                    _("The selected enrollment must belong to the same section as the activity course.")
                )

    @api.constrains("score", "activity_id")
    def _check_score_does_not_exceed_max(self):
        for rec in self:
            if rec.score is not None:
                if rec.score < 0:
                    raise ValidationError(_("The score must not be less than zero."))
                if rec.activity_id and rec.activity_id.max_score is not None:
                    if rec.score > rec.activity_id.max_score:
                        raise ValidationError(
                            _(
                                "Score %.2f cannot exceed the activity's maximum score %.2f."
                            )
                            % (rec.score, rec.activity_id.max_score)
                        )
