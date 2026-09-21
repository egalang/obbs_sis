def migrate(cr, version):
    # Route "Grade 1" grade levels to the DepEd Grade 1 Progress Report template.
    cr.execute(
        """
        UPDATE sis_grade_level
        SET report_card_type = 'grade1'
        WHERE lower(name) = 'grade 1'
        """
    )