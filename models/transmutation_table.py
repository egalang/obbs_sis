from odoo import models, fields, api

# DepEd DO 2026-015, Table 4 "Adjusted Transmutation Table" (effective SY
# 2026-2027 only).  Stored as the lower bound of each Initial-Grade band so it
# works with the existing "largest threshold <= IG" lookup.
ADJUSTED_TRANSMUTATION_2026_2027 = [
    (0.00, 60),
    (4.68, 61),
    (9.35, 62),
    (14.01, 63),
    (18.68, 64),
    (23.35, 65),
    (28.01, 66),
    (32.68, 67),
    (37.34, 68),
    (42.01, 69),
    (46.67, 70),
    (51.34, 71),
    (56.01, 72),
    (60.67, 73),
    (65.34, 74),
    (70.00, 75),
    (71.18, 76),
    (72.36, 77),
    (73.54, 78),
    (74.72, 79),
    (75.90, 80),
    (77.08, 81),
    (78.26, 82),
    (79.44, 83),
    (80.62, 84),
    (81.80, 85),
    (82.98, 86),
    (84.16, 87),
    (85.34, 88),
    (86.52, 89),
    (87.70, 90),
    (88.88, 91),
    (90.06, 92),
    (91.24, 93),
    (92.42, 94),
    (93.60, 95),
    (94.78, 96),
    (95.96, 97),
    (97.14, 98),
    (98.32, 99),
    (99.50, 100),
]


class TransmutationTable(models.Model):
    _name = "sis.transmutation.table"
    _description = "Grade Transmutation Table"
    _order = "grade_range DESC"

    grade_range = fields.Float(string="Initial Grade Threshold", required=True)
    transmuted_grade = fields.Integer(string="Transmuted Grade", required=True)
    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        index=True,
        ondelete="cascade",
        help="Leave empty for the default/legacy table. Set it to apply a "
        "school-year-specific table (e.g. the SY 2026-2027 Adjusted "
        "Transmutation Table).",
    )

    @api.model
    def transmute(self, initial_grade, school_year=None):
        """Return the transmuted-grade row for an Initial Grade.

        Prefers the row for ``school_year`` and falls back to the legacy
        (no school year) table when the school year has none.
        """
        domain = [("grade_range", "<=", initial_grade)]
        if school_year:
            record = self.search(
                domain + [("school_year_id", "=", school_year.id)], limit=1
            )
            if record:
                return record
        return self.search(domain + [("school_year_id", "=", False)], limit=1)

    @api.model
    def _seed_adjusted_2026_2027(self):
        """Seed the official Adjusted Transmutation Table for DepEd 2026-format
        school years (idempotent)."""
        school_years = self.env["sis.school.year"].search(
            [("report_card_format", "=", "deped_2026")]
        )
        for school_year in school_years:
            for threshold, transmuted in ADJUSTED_TRANSMUTATION_2026_2027:
                record = self.search(
                    [
                        ("school_year_id", "=", school_year.id),
                        ("grade_range", "=", threshold),
                    ],
                    limit=1,
                )
                if record:
                    if record.transmuted_grade != transmuted:
                        record.transmuted_grade = transmuted
                else:
                    self.create(
                        {
                            "school_year_id": school_year.id,
                            "grade_range": threshold,
                            "transmuted_grade": transmuted,
                        }
                    )
