# -*- coding: utf-8 -*-
from odoo import models, fields, api


class CharacterBehavior(models.Model):
    _name = "sis.character.behavior"
    _description = "Character Behavior Statement"
    _rec_name = "display_name"
    _order = "group_order, sequence, id"  # ← CHANGED HERE

    # ───────────── CORE FIELDS ─────────────
    behavior_type = fields.Selection(
        [
            ("elementary", "Elementary / High School"),
            ("preschool", "Preschool"),
        ],
        string="Applies To",
        required=True,
        default="elementary",
    )

    group_name = fields.Char(
        string="Category / Group",
        help=(
            "Elementary: use Maka‑Diyos, Makatao, Makakalikasan, Makabansa\n"
            "Preschool: e.g. Work and Study Habits, Social Skills, Motor Skills, Spiritual Performance"
        ),
        required=True,
    )

    group_order = fields.Integer(
        string="Group Order",
        default=0,
        help="Used to control display order of groupings (e.g. Maka‑Diyos first)",
    )  # ← NEW FIELD

    description = fields.Text("Behavior Statement", required=True)
    sequence = fields.Integer(default=10)

    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
    )

    # ───────────── DISPLAY NAME ─────────────
    @api.depends("group_name", "description")
    def _compute_display_name(self):
        for rec in self:
            short = (rec.description or "")[:60]
            rec.display_name = f"{rec.group_name} – {short}"
