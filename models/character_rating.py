# -*- coding: utf-8 -*-
from odoo import models, fields, api


class CharacterRating(models.Model):
    _name = "sis.character.rating"
    _description = "Student Character Rating"
    _order = "sort_key, behavior_id"

    enrollment_id = fields.Many2one(
        "sis.enrollment",
        required=True,
        ondelete="cascade",
    )
    period_id = fields.Many2one(
        "sis.period",
        required=True,
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
    behavior_id = fields.Many2one(
        "sis.character.behavior",
        required=True,
        ondelete="restrict",
    )

    group_name = fields.Char(
        related="behavior_id.group_name",
        store=False,
        readonly=True,
    )

    description = fields.Text(
        related="behavior_id.description",
        readonly=True,
        store=False,
    )

    rating = fields.Char(
        string="Rating",
        help=(
            "Elementary/HS legend: AO = Always Observed, SO = Sometimes Observed, "
            "RO = Rarely Observed, NO = Not Observed\n"
            "Preschool legend: O = Outstanding, VS = Very Satisfactory, S = Satisfactory, "
            "MS = Moderately Satisfactory, NI = Needs Improvement"
        ),
    )

    sort_key = fields.Char(
        compute="_compute_sort_key",
        store=True,
        index=True,
    )

    @api.depends(
        "period_id",
        "behavior_id.group_order",
        "behavior_id.sequence",
    )
    def _compute_sort_key(self):
        for rec in self:
            rec.sort_key = (
                f"{rec.period_id.id:04d}_"
                f"{rec.behavior_id.group_order:04d}_"
                f"{rec.behavior_id.sequence:04d}_"
                f"{rec.behavior_id.id:04d}"
            )

    _sql_constraints = [
        (
            "unique_character_rating",
            "unique(enrollment_id, period_id, behavior_id)",
            "Each behavior must only be rated once per student per period.",
        )
    ]
