from odoo import api, SUPERUSER_ID


def _backfill_school_year_for_records(env, model_name):
    records = env[model_name].with_context(active_test=False).search([])
    for record in records:
        values = {}
        company = getattr(record, "company_id", False) or env.company
        school_year = getattr(record, "school_year_id", False)
        if not school_year and company and company.active_school_year_id:
            values["school_year_id"] = company.active_school_year_id.id
        if model_name == "sis.school.year":
            if not record.company_id:
                values["company_id"] = company.id
            if not record.state:
                values["state"] = "active" if company.active_school_year_id == record else "draft"
        if values:
            # record.write(values)
            record.with_context(skip_history_check=True).write(values)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model_name in [
        # "sis.school.year",
        "sis.enrollment",
        "sis.sections",
        "sis.period",
        "sis.tuition",
    ]:
        if model_name in env:
            _backfill_school_year_for_records(env, model_name)
