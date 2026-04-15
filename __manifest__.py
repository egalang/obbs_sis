# -*- coding: utf-8 -*-
{
    "name": "Obbserver School",
    "summary": "School Information System",
    "description": """
Manage All your School's Needs Seamlessly with the Power of Utilizing Odoo's Capabilities.
    """,
    "author": "OBBS Co.",
    "website": "https://obbsco.com",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    "category": "Education",
    "version": "18.0.1.8",
    # any module necessary for this one to work correctly
    "depends": ["base", "mail", "contacts", "website_sale", "website_slides", "portal"],
    # always loaded
    "data": [
        "security/sis_groups.xml",
        "security/record_rules.xml",
        "security/ir.model.access.csv",
        "data/paper_format_data.xml",
        "data/transmutation_table_data.xml",
        "data/character_behavior_data.xml",
        "data/ir_cron_data.xml",
        "wizard/enrollment_to_student_wizard.xml",
        "wizard/initialize_school_year_wizard.xml",
        "views/account_move.xml",
        "views/account_payment.xml",
        "views/activity.xml",
        "views/period.xml",
        "views/gradebook.xml",
        "views/res_company_views.xml",
        "views/enrollment.xml",
        "views/grade_level.xml",
        "views/sections.xml",
        "views/school_year.xml",
        "views/payment_plan.xml",
        "views/tuitions.xml",
        "views/tuition_tranches.xml",
        "views/student.xml",
        "views/slide_channel.xml",
        "views/attendance.xml",
        "views/transmutation_table.xml",
        "views/rating_comment.xml",
        "views/character_behavior.xml",
        "views/attendance_school_days.xml",
        # "views/jwt_blacklist.xml", <--- Deprecated , my be used in the future
        "report/ir_reports.xml",
        "views/student_id_template.xml",
        # "wizard/id_generation_wizard.xml",
        "views/enrollment_templates.xml",
        "views/enrollment_submission_templates.xml",
        "views/jitsi_meet_templates.xml",
        "views/report_card_template.xml",
        "views/mail_template_inherit.xml",
        "views/account_invoice_report_inherit.xml",
        "views/course_template_extend.xml",
        "wizard/progress_report_wizard.xml",
        "wizard/rating_sheet_wizard.xml",
        "data/mail_template_data.xml",
        "views/menu.xml",
    ],
    # only loaded in demonstration mode
    "demo": [
        "demo/demo.xml",
    ],
    "external_dependencies": {
        "python": ["qrcode"],
    },
    "application": True,
    "installable": True,
}
