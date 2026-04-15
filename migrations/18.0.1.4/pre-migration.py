from odoo import SUPERUSER_ID, api


def _column_exists(cr, table_name, column_name):
    cr.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table_name, column_name),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    # Make the Phase 3 history columns available before any ORM code or
    # subsequent migrations try to read/write them. This keeps upgrades safe
    # even when the registry was previously left in a partially applied state.
    if not _column_exists(cr, 'sis_enrollment', 'previous_enrollment_id'):
        cr.execute(
            "ALTER TABLE sis_enrollment ADD COLUMN IF NOT EXISTS previous_enrollment_id integer"
        )
    if not _column_exists(cr, 'sis_enrollment', 'root_enrollment_id'):
        cr.execute(
            "ALTER TABLE sis_enrollment ADD COLUMN IF NOT EXISTS root_enrollment_id integer"
        )

    cr.execute(
        "CREATE INDEX IF NOT EXISTS sis_enrollment_previous_enrollment_id_idx ON sis_enrollment (previous_enrollment_id)"
    )
    cr.execute(
        "CREATE INDEX IF NOT EXISTS sis_enrollment_root_enrollment_id_idx ON sis_enrollment (root_enrollment_id)"
    )

    # Best-effort foreign keys. These are added only when absent so repeated
    # upgrades remain safe.
    cr.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'sis_enrollment_previous_enrollment_id_fkey'
            ) THEN
                ALTER TABLE sis_enrollment
                ADD CONSTRAINT sis_enrollment_previous_enrollment_id_fkey
                FOREIGN KEY (previous_enrollment_id)
                REFERENCES sis_enrollment (id)
                ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )
    cr.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'sis_enrollment_root_enrollment_id_fkey'
            ) THEN
                ALTER TABLE sis_enrollment
                ADD CONSTRAINT sis_enrollment_root_enrollment_id_fkey
                FOREIGN KEY (root_enrollment_id)
                REFERENCES sis_enrollment (id)
                ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )

    # Flush DDL early. Odoo wraps the overall upgrade in a transaction, but
    # explicit commit here ensures the columns are visible before later steps
    # in this same upgrade attempt run ORM fetches that include them.
    cr.commit()
