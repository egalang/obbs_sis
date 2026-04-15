# models/rating_comment.py
from odoo import models, fields, api


class RatingComment(models.Model):
    _name = "sis.rating.comment"
    _description = "Advisor Comment for Rating Sheet"
    _rec_name = "enrollment_id"

    enrollment_id = fields.Many2one("sis.enrollment", required=True, ondelete="cascade")
    period_id = fields.Many2one("sis.period", required=True, ondelete="cascade")
    comment = fields.Text("Advisor Comment")

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="enrollment_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    _sql_constraints = [
        (
            "unique_enrollment_period",
            "unique(enrollment_id, period_id)",
            "A comment already exists for this student in this grading period.",
        )
    ]
