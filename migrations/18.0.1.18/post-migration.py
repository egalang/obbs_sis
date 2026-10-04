def migrate(cr, version):
    """18.0.1.18 — normalize ``sis.enrollment.full_name`` whitespace.

    Legacy name components (first/middle/last/ext) contain trailing spaces,
    which produced double spaces and space-before-comma in ``full_name`` and
    broke exact-match XLOOKUP lookups in the generated ECR. ``full_name`` is a
    stored computed field, so changing ``_compute_full_name`` does not rewrite
    existing rows; recompute every enrollment once.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    enrollments = env["sis.enrollment"].search([])
    enrollments._compute_full_name()
    env.flush_all()

    print(
        "18.0.1.18: recomputed full_name for %d enrollment(s)."
        % len(enrollments)
    )
