def migrate(cr, version):
    """18.0.1.19 — backfill the new Nursery "Motor Skills: Able to throw and
    catch a ball" rating rows for existing nursery enrollments.

    The catalog record is added by ``data/character_behavior_data.xml``, but
    ``sis.character.rating`` rows are not created automatically for existing
    enrollments, so the Behavior tab would not list the new indicator until
    "Generate/Refresh Behaviors" was clicked. Reuse the idempotent per-enrollment
    generator (covers every period of each enrollment's school year).
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    enrollments = env["sis.enrollment"].search(
        [("grade_level_id.report_card_type", "=", "nursery")]
    )
    enrollments.action_generate_character_ratings()
    env.flush_all()

    print(
        "18.0.1.19: backfilled nursery character ratings for %d enrollment(s)."
        % len(enrollments)
    )
