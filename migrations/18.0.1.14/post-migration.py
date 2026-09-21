def migrate(cr, version):
    # 18.0.1.14: the Nursery progress report switched from the custom
    # Letter-landscape paper format to the shared A4 landscape format
    # (format='A4' avoids the wkhtmltopdf custom-size / orientation swap that
    # rendered the card in portrait). Drop the now-unused record + its xmlid.
    cr.execute(
        """
        DELETE FROM report_paperformat p
        USING ir_model_data d
        WHERE d.module = 'obbs_sis'
          AND d.model = 'report.paperformat'
          AND d.res_id = p.id
          AND d.name = 'paperformat_letter_landscape_custom'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'obbs_sis'
          AND model = 'report.paperformat'
          AND name = 'paperformat_letter_landscape_custom'
        """
    )
