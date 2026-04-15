# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SisGradeLevel(models.Model):
    _name = "sis.grade.level"
    _description = "Grade Level"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Grade Level", required=True, tracking=True)
    description = fields.Text(
        string="Description", tracking=True, help="Brief description of the grade level"
    )
    code = fields.Char(
        string="Code", tracking=True, help="Unique code for the grade level"
    )

    id_type = fields.Selection(
        [
            ("preschool", "Preschool"),
            ("elementary", "Elementary"),
            ("highschool", "High School"),
        ],
        string="ID Type for Student ID",
        required=True,
        default="preschool",
        help="Used to determine the template for student ID card",
    )

    next_grade_level_id = fields.Many2one(
        "sis.grade.level",
        string="Next Grade Level",
        tracking=True,
        help="Select the next grade level progression",
    )