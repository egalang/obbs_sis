def migrate(cr, version):
    """18.0.1.15 — DepEd DO 2026-015 (p.39, item 6) 30/30/40 EXs split.

    Normalize the "Summative Tests and Term Examination" (EXs /
    ``quarterly_exam``) activities of every DepEd 2026-format school year so
    each subject/term has exactly:
        Summative Test 1  -> 30%
        Summative Test 2  -> 30%
        Term Examination  -> 40%

    Legacy (non ``deped_2026``) school years are deliberately left untouched.
    Only subject/term sets that already have at least one EXs activity are
    normalized: existing activities are adopted by best-effort name match,
    missing components are created (with gradebook rows for accepted enrollees)
    and misnamed duplicates are removed.  Terms with no EXs activity at all are
    left alone so an untouched report-card cell does not become a 0.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})

    school_years = env["sis.school.year"].search(
        [("report_card_format", "=", "deped_2026")]
    )
    if not school_years:
        print("18.0.1.15: no deped_2026 school year found - nothing to normalize.")
        return

    channels = env["slide.channel"].search(
        [("school_year_id", "in", school_years.ids)]
    )

    total_channels = 0
    total_created = 0
    for channel in channels:
        if not any(at.name == "quarterly_exam" for at in channel.activity_type_ids):
            continue
        # only_existing: do not create EXs activities for subjects/terms that
        # never had any (that would turn a blank report-card cell into a 0).
        total_created += channel._ensure_exam_activities(only_existing=True)
        total_channels += 1

    print(
        "18.0.1.15: normalized EXs activities for %d deped_2026 school year(s), "
        "%d channel(s) with an EXs activity type; created %d activities."
        % (len(school_years), total_channels, total_created)
    )
