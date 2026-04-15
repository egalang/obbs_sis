from odoo import models, fields, api


class TransmutationTable(models.Model):
    _name = "sis.transmutation.table"
    _description = "Grade Transmutation Table"
    _order = "grade_range DESC"

    grade_range = fields.Float(string="Initial Grade Threshold", required=True)
    transmuted_grade = fields.Integer(string="Transmuted Grade", required=True)
