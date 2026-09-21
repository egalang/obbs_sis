def migrate(cr, version):
    cr.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS sis_gradebook_enrollment_activity_uniq
        ON sis_gradebook (enrollment_id, activity_id)
        """
    )