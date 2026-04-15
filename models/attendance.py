from odoo import _, fields, models


class StudentAttendanceLog(models.Model):
    _name = "sis.student.attendance.log"
    _description = "Student Attendance Log"
    _order = "attendance_datetime desc, id desc"

    enrollment_id = fields.Many2one(
        "sis.enrollment",
        string="Enrollment",
        required=True,
        ondelete="cascade",
        help="Select the student's enrollment record associated with this log entry.",
    )

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="enrollment_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    section_id = fields.Many2one(
        "sis.sections",
        string="Section",
        related="enrollment_id.section_id",
        store=True,
        index=True,
        readonly=True,
    )

    log_type = fields.Selection(
        [
            ("school_in", "School In"),
            ("school_out", "School Out"),
            ("class_in", "Class In"),
            ("class_out", "Class Out"),
        ],
        string="Log Type",
        required=True,
        help="Type of attendance event: School In/Out or Class In/Out.",
    )

    attendance_datetime = fields.Datetime(
        string="Datetime",
        required=True,
        default=fields.Datetime.now,
        help="Date and time when the attendance log was recorded.",
    )

    section_display_name = fields.Char(
        string="Section",
        related="enrollment_id.section_id.display_name",
        store=False,
        help="Displays the section linked to the enrollment.",
    )

    is_notified = fields.Boolean(
        string="Notified",
        default=False,
        help="Indicates if the parent has been notified about this attendance log.",
    )
