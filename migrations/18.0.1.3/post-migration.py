from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Enrollment = env["sis.enrollment"].with_context(active_test=False)
    records = Enrollment.search([], order="create_date asc, id asc")

    groups = {}
    for record in records:
        if record.lrn_no:
            key = ("lrn", record.lrn_no.strip().upper())
        elif record.psa_no:
            key = ("psa", record.psa_no.strip().upper())
        else:
            key = ("single", record.id)
        groups.setdefault(key, []).append(record)

    for chain in groups.values():
        root = chain[0]
        previous = False
        for record in chain:
            values = {}
            if not record.root_enrollment_id:
                values["root_enrollment_id"] = root.id
            if previous and not record.previous_enrollment_id and record.id != root.id:
                values["previous_enrollment_id"] = previous.id
            if values:
                # record.write(values)
                record.with_context(skip_history_check=True).write(values)
            previous = record
