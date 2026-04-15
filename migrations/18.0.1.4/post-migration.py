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
    # Stay defensive in case a prior failed upgrade left the database only
    # partially updated. If the columns are not available yet, skip quietly.
    if not _column_exists(cr, 'sis_enrollment', 'previous_enrollment_id'):
        return
    if not _column_exists(cr, 'sis_enrollment', 'root_enrollment_id'):
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Enrollment = env['sis.enrollment'].with_context(active_test=False)
    records = Enrollment.search([], order='create_date asc, id asc')

    groups = {}
    for record in records:
        if record.lrn_no:
            key = ('lrn', record.lrn_no.strip().upper())
        elif record.psa_no:
            key = ('psa', record.psa_no.strip().upper())
        else:
            key = ('single', record.id)
        groups.setdefault(key, []).append(record)

    for chain in groups.values():
        root = chain[0]
        previous = False
        for record in chain:
            values = {}
            if not record.root_enrollment_id:
                values['root_enrollment_id'] = root.id
            if previous and not record.previous_enrollment_id and record.id != root.id:
                values['previous_enrollment_id'] = previous.id
            if values:
                # record.write(values)
                record.with_context(skip_history_check=True).write(values)
            previous = record
