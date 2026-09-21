def migrate(cr, version):
    # 18.0.1.12: fold the Kindergarten competency catalog + ratings into the
    # Character Building model (sis.character.behavior / sis.character.rating).
    # Runs after the module data loads, so the 60 kinder behaviors exist;
    # sis.competency is no longer a registered model, hence raw SQL only.

    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'sis_competency'"
    )
    if not cr.fetchone():
        return

    helper_uid = (
        "SELECT id FROM res_users WHERE id > 1 ORDER BY id LIMIT 1"
    )

    # 1) Backfill any kinder behaviors for competencies not already seeded.
    cr.execute(
        f"""
        INSERT INTO sis_character_behavior
            (behavior_type, group_name, subgroup, description, sequence,
             group_order, display_name, create_uid, create_date, write_uid, write_date)
        SELECT 'kinder',
               c.domain,
               NULLIF(c.subgroup, ''),
               c.description,
               c.sequence,
               go.group_order,
               c.domain || ' – ' || left(c.description, 60),
               ({helper_uid}), NOW() AT TIME ZONE 'UTC',
               ({helper_uid}), NOW() AT TIME ZONE 'UTC'
        FROM sis_competency c
        JOIN (
            SELECT domain, row_number() OVER (ORDER BY min(id)) AS group_order
            FROM sis_competency
            GROUP BY domain
        ) go ON go.domain = c.domain
        LEFT JOIN sis_character_behavior b
            ON b.behavior_type = 'kinder'
           AND b.group_name = c.domain
           AND COALESCE(b.subgroup, '') = COALESCE(c.subgroup, '')
           AND b.description = c.description
        WHERE b.id IS NULL
        """
    )

    # 2) Copy competency ratings into character ratings (idempotent).
    cr.execute(
        f"""
        INSERT INTO sis_character_rating
            (enrollment_id, period_id, school_year_id, behavior_id, rating,
             sort_key, create_uid, create_date, write_uid, write_date)
        SELECT cr.enrollment_id,
               cr.period_id,
               e.school_year_id,
               b.id,
               cr.rating,
               lpad(cr.period_id::text, 4, '0') || '_' ||
               lpad(b.group_order::text, 4, '0') || '_' ||
               lpad(b.sequence::text, 4, '0') || '_' ||
               lpad(b.id::text, 4, '0'),
               ({helper_uid}), NOW() AT TIME ZONE 'UTC',
               ({helper_uid}), NOW() AT TIME ZONE 'UTC'
        FROM sis_competency_rating cr
        JOIN sis_competency c ON c.id = cr.competency_id
        JOIN sis_character_behavior b
            ON b.behavior_type = 'kinder'
           AND b.group_name = c.domain
           AND COALESCE(b.subgroup, '') = COALESCE(c.subgroup, '')
           AND b.description = c.description
        JOIN sis_enrollment e ON e.id = cr.enrollment_id
        ON CONFLICT (enrollment_id, period_id, behavior_id) DO NOTHING
        """
    )

    # 3) Drop the orphaned competency tables now that the data is moved.
    cr.execute("DROP TABLE IF EXISTS sis_competency_rating")
    cr.execute("DROP TABLE IF EXISTS sis_competency")

    # 3b) Remove stale preschool/legacy character rows from Kindergarten
    #     enrollments: the Kinder card is competency-based, so those rows are
    #     not rendered anywhere and only clutter the Character Building tab.
    cr.execute(
        """
        DELETE FROM sis_character_rating cr
        USING sis_character_behavior b, sis_enrollment e, sis_grade_level g
        WHERE cr.behavior_id = b.id
          AND cr.enrollment_id = e.id
          AND e.grade_level_id = g.id
          AND g.report_card_type = 'kinder'
          AND b.behavior_type <> 'kinder'
        """
    )

    # 4) Drop the stale external ids for the retired records (Odoo's
    #    _process_end skips them because the model is no longer registered).
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'obbs_sis'
          AND model IN ('sis.competency', 'sis.competency.rating')
        """
    )