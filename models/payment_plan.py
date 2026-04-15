# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SisPaymentPlan(models.Model):
    _name = "sis.payment.plan"
    _description = "Payment Plans"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Payment Plan", required=True, tracking=True)
