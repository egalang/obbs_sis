def migrate(cr, version):
    # Route Kindergarten and Nursery grade levels to their new report card types.
    cr.execute(
        """
        UPDATE sis_grade_level
        SET report_card_type = 'kinder'
        WHERE lower(name) = 'kindergarten'
        """
    )
    cr.execute(
        """
        UPDATE sis_grade_level
        SET report_card_type = 'nursery'
        WHERE lower(name) LIKE 'nursery%'
        """
    )
    # Wire the data-driven print action (runs after module data is loaded, so
    # the report action xmlids exist).
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    actions = {
        "kinder": "obbs_sis.action_report_longbond_report_card",
        "grade1": "obbs_sis.action_report_longbond_report_card",
        "nursery": "obbs_sis.action_report_nursery_report_card",
    }
    for card_type, xmlid in actions.items():
        action = env.ref(xmlid, raise_if_not_found=False)
        if not action:
            continue
        env.cr.execute(
            """
            UPDATE sis_grade_level
            SET report_action_id = %s
            WHERE report_card_type = %s AND report_action_id IS NULL
            """,
            (action.id, card_type),
        )
    # Nursery sections use the shared landscape nursery layout for their
    # grade level report actions too (sanitize any legacy A4 landscape refs).
    env.cr.execute(
        """
        UPDATE sis_grade_level sg
        SET report_action_id = sub.id
        FROM ir_act_report_xml sub
        WHERE sg.report_card_type = 'nursery'
          AND sub.report_name = 'obbs_sis.report_card_template_nursery_print'
          AND (sg.report_action_id IS NULL OR sg.report_action_id <> sub.id)
        """
    )