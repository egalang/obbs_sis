import re
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# DepEd DO 2026-015 (p.39, item 6): inside the EXs component
# ("Summative Tests and Term Examination") the weight is distributed as
# Summative Test 1 = 30%, Summative Test 2 = 30%, Term Examination = 40%.
EXAM_COMPONENT_SELECTION = [
    ("st1", "Summative Test 1"),
    ("st2", "Summative Test 2"),
    ("te", "Term Examination"),
]

# component code -> share (%) of the EXs activity-type weight
EXAM_COMPONENT_WEIGHTS = {"st1": 30.0, "st2": 30.0, "te": 40.0}

# ordered spec used to auto-generate the three required activities
# (component code, canonical name, default max score)
EXAM_COMPONENT_SPECS = [
    ("st1", "Summative Test 1", 30.0),
    ("st2", "Summative Test 2", 30.0),
    ("te", "Term Examination", 40.0),
]


class Activity(models.Model):
    _name = "sis.activity"
    _description = "Student Activity"

    # Class-level aliases so other models can reach them via a recordset
    # (e.g. self.env["sis.activity"].EXAM_COMPONENT_SPECS).
    EXAM_COMPONENT_SELECTION = EXAM_COMPONENT_SELECTION
    EXAM_COMPONENT_WEIGHTS = EXAM_COMPONENT_WEIGHTS
    EXAM_COMPONENT_SPECS = EXAM_COMPONENT_SPECS

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

    exam_component = fields.Selection(
        selection=EXAM_COMPONENT_SELECTION,
        string="EXs Component",
        help="For 'Summative Tests and Term Examination' only. The component "
        "weight is fixed by DepEd DO 2026-015: Summative Test 1 = 30%, "
        "Summative Test 2 = 30%, Term Examination = 40%.",
    )

    component_weight = fields.Float(
        string="Component Weight (%)",
        compute="_compute_component_weight",
        store=True,
        readonly=True,
        help="Share of this activity inside its activity type. Fixed at "
        "ST1 = 30 / ST2 = 30 / TE = 40 for the EXs component.",
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

    @api.depends("exam_component")
    def _compute_component_weight(self):
        for record in self:
            record.component_weight = EXAM_COMPONENT_WEIGHTS.get(
                record.exam_component, 0.0
            )

    @api.model
    def _match_exam_component(self, name):
        """Best-effort map of a (legacy) activity name to an EXs component code.

        Used by the migration and by the auto-generation helper to adopt
        already-created activities whose names vary across sections
        (e.g. "ST1", "Summative 1", "TERM 1 EXAM").  Returns False when the
        name cannot be confidently matched.
        """
        if not name:
            return False
        key = re.sub(r"[^a-z0-9]+", "", name.lower())
        if key in ("s1", "st1") or "summative1" in key or "summativetest1" in key:
            return "st1"
        if key in ("s2", "st2") or "summative2" in key or "summativetest2" in key:
            return "st2"
        # "Summative Term 1/2" style (a 'term' token sits between the word and
        # the number, so the contiguous checks above miss it).
        if "summative" in key and "exam" not in key:
            if "1" in key and "2" not in key:
                return "st1"
            if "2" in key and "1" not in key:
                return "st2"
        if (
            ("term" in key and "exam" in key)
            or key in ("te", "te1", "t1", "term1", "term2", "term3")
            or (key.startswith("term") and "summative" not in key)
        ):
            return "te"
        return False

    def _is_deped_2026_exam(self):
        """True when this is an EXs activity in a DepEd 2026-format school year."""
        self.ensure_one()
        return bool(
            self.activity_type_id
            and self.activity_type_id.name == "quarterly_exam"
            and self.school_year_id
            and self.school_year_id.report_card_format == "deped_2026"
        )

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

    @api.constrains("activity_type_id", "exam_component", "channel_id", "period_id")
    def _check_exam_component_rules(self):
        for record in self:
            if record.exam_component:
                duplicate = self.search(
                    [
                        ("id", "!=", record.id),
                        ("channel_id", "=", record.channel_id.id),
                        ("period_id", "=", record.period_id.id),
                        ("exam_component", "=", record.exam_component),
                    ],
                    limit=1,
                )
                if duplicate:
                    raise ValidationError(
                        _(
                            "Only one '%s' activity is allowed per subject and term."
                        )
                        % dict(EXAM_COMPONENT_SELECTION).get(record.exam_component)
                    )
            elif record._is_deped_2026_exam():
                raise ValidationError(
                    _(
                        "A 'Summative Tests and Term Examination' activity must "
                        "specify an EXs Component (Summative Test 1, Summative "
                        "Test 2 or Term Examination)."
                    )
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
        if self.env.context.get("sis_skip_gradebook_autopopulate"):
            return activity
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
        if not self.env.context.get("sis_skip_exam_autoseed"):
            self._auto_seed_exam_siblings(activity)
        return activity

    def _auto_seed_exam_siblings(self, activities):
        """When an EXs activity is created, make sure the other components exist.

        Only applies to DepEd 2026-format school years (DO 2026-015 is effective
        SY 2026-2027).  The sibling creation is guarded by a context flag to
        avoid recursion.
        """
        for activity in activities:
            if (
                activity.exam_component
                and activity._is_deped_2026_exam()
                and activity.channel_id
                and activity.period_id
            ):
                activity.channel_id.with_context(
                    sis_skip_exam_autoseed=True
                )._ensure_exam_activities(period_ids=[activity.period_id.id])

    def _bulk_create_gradebooks_for_enrollments(self, activity):
        """Bulk-insert gradebook rows for a (new) activity using raw SQL.

        Mirrors the ORM auto-populate behaviour but avoids the per-row
        @api.constrains full-table searches that make the ORM path very slow.
        """
        section = activity.channel_id.section_id
        if not section or not activity.period_id:
            return
        self.env.cr.execute(
            """
            INSERT INTO sis_gradebook
                (activity_id, enrollment_id, school_year_id, section_id,
                 channel_id, period_id, gender, score, create_uid, create_date,
                 write_uid, write_date)
            SELECT %(activity)s, e.id, e.school_year_id, e.section_id,
                   %(channel)s, %(period)s, e.gender, NULL,
                   %(uid)s, now(), %(uid)s, now()
            FROM sis_enrollment e
            WHERE e.section_id = %(section)s
              AND e.school_year_id = %(school_year)s
              AND e.enrollment_status = 'accepted'
            """,
            {
                "activity": activity.id,
                "channel": activity.channel_id.id,
                "period": activity.period_id.id,
                "section": section.id,
                "school_year": activity.period_id.school_year_id.id,
                "uid": self.env.uid,
            },
        )
