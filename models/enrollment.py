from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError
from datetime import date
import logging

# Set up a logger for debugging purposes
_logger = logging.getLogger(__name__)


class SisEnrollment(models.Model):
    _name = "sis.enrollment"
    _description = "Enrollment Form"
    _inherit = ["mail.thread", "mail.activity.mixin", "image.mixin"]
    _rec_name = "full_name"
    _order = "id desc"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        required=True,
        tracking=True,
        index=True,
        default=lambda self: self.env.company.active_school_year_id,
    )

    enrollment_type = fields.Selection(
        [
            ("no_lrn", "No LRN"),
            ("with_lrn", "With LRN"),
            ("balik_aral", "Returning (Balik-Aral)"),
        ],
        string="Enrollment Type",
        required=True,
        tracking=True,
    )

    psa_no = fields.Char(string="PSA Birth Certificate No.", tracking=True)
    lrn_no = fields.Char(string="Learner Reference Number (LRN)", tracking=True)

    first_name = fields.Char(string="First Name", required=True, tracking=True)
    middle_name = fields.Char(string="Middle Name", tracking=True)
    last_name = fields.Char(string="Last Name", required=True, tracking=True)
    ext_name = fields.Char(string="Extension Name", tracking=True)

    full_name = fields.Char(
        string="Full Name", compute="_compute_full_name", store=True, tracking=True
    )

    birth_date = fields.Date(string="Date of Birth", required=True, tracking=True)
    age = fields.Integer(
        string="Age", compute="_compute_age", store=True, tracking=True
    )

    gender = fields.Selection(
        [("male", "Male"), ("female", "Female")],
        string="Sex",
        required=True,
        tracking=True,
    )

    grade_level_id = fields.Many2one(
        "sis.grade.level", string="Grade Level", required=True, tracking=True
    )

    section_id = fields.Many2one(
        "sis.sections",
        string="Section",
        domain="[('grade_level_id', '=', grade_level_id), ('school_year_id', '=', school_year_id)]",
    )

    is_indigenous = fields.Selection(
        selection=[("yes", "Yes"), ("no", "No")],
        string="Belonging to any Indigenous Peoples (IP) Community/Indigenous Cultural Community?",
        tracking=True,
    )
    indigenous_group = fields.Char(string="If Yes, Please Specify", tracking=True)

    mother_tongue = fields.Char(string="Mother Tongue", required=True, tracking=True)

    # === VACCINATION INFORMATION ===
    is_vaccinated = fields.Selection(
        selection=[("yes", "Yes"), ("no", "No")],
        string="Is the learner vaccinated against COVID-19?",
        tracking=True,
    )
    first_shot_date = fields.Date(string="First Shot")
    full_vaccination_date = fields.Date(string="Full Vaccination")

    # === ADDRESS INFORMATION ===
    house_street = fields.Char(string="House No. & Street", required=True)
    barangay = fields.Char(string="Barangay", required=True)
    city_province = fields.Char(string="City/Municipality/Province", required=True)
    zip_code = fields.Char(string="ZIP Code", required=True)

    # === PARENT / GUARDIAN INFORMATION ===
    father_full_name = fields.Char(string="Father's Full Name", required=True)
    mother_full_name = fields.Char(string="Mother's Full Name", required=True)
    guardian_full_name = fields.Char(string="Guardian's Full Name")

    home_phone = fields.Char(string="Home Mobile Number")
    office_phone = fields.Char(string="Office Mobile Number")
    user_mobile = fields.Char(string="User's Mobile Number")

    # === RETURNING LEARNERS (BALIK-ARAL) ===
    last_grade_level_id = fields.Many2one(
        "sis.grade.level", string="Last Grade Level Completed"
    )
    last_school_year_id = fields.Many2one(
        "sis.school.year", string="Last School Year Completed"
    )
    last_school_name = fields.Char(string="Previous School Name")
    last_school_id = fields.Char(string="Previous School ID")
    last_school_address = fields.Char(string="Previous School Address")

    # === PAYMENT INFORMATION ===
    tuition_id = fields.Many2one(
        "sis.tuition",
        string="Selected Tuition Plan",
        required=True,
        domain="[('grade_level_id', '=', grade_level_id), ('school_year_id', '=', school_year_id)]",
        tracking=True,
    )

    # === PRIVACY STATEMENT ===
    agreed = fields.Boolean(
        string="I hereby certify that the information given is true.", required=True
    )

    # === ENROLLMENT STATUS ===
    enrollment_status = fields.Selection(
        [
            ("pending", "Pending"),
            ("reviewed", "Reviewed"),
            ("accepted", "Accepted"),
        ],
        string="Enrollment Status",
        default="pending",
        tracking=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Parent User Account",
        default=lambda self: self.env.user.partner_id,
        index=True,
        tracking=True,
    )

    user_id = fields.Many2one(
        "res.users", string="Portal User", readonly=True, tracking=True
    )

    previous_enrollment_id = fields.Many2one(
        "sis.enrollment",
        string="Previous Enrollment",
        index=True,
        copy=False,
        tracking=True,
    )
    root_enrollment_id = fields.Many2one(
        "sis.enrollment",
        string="History Root",
        index=True,
        copy=False,
    )
    next_enrollment_ids = fields.One2many(
        "sis.enrollment", "previous_enrollment_id", string="Next Enrollments"
    )
    history_enrollment_ids = fields.One2many(
        "sis.enrollment", "root_enrollment_id", string="Enrollment History"
    )
    history_count = fields.Integer(
        string="History Count", compute="_compute_history_count"
    )
    can_reenroll = fields.Boolean(
        string="Can Re-enroll", compute="_compute_can_reenroll"
    )

    invoice_count = fields.Integer(
        string="Total Invoices", compute="_compute_invoice_stats", store=False
    )
    posted_invoice_count = fields.Integer(
        string="Posted Invoices", compute="_compute_invoice_stats", store=False
    )

    student_photo = fields.Image(max_width=128, max_height=128)

    subject_ids = fields.Many2many(
        "slide.channel",
        "enrollment_subject_rel",  # name of the relational table
        "enrollment_id",
        "channel_id",
        string="Subjects",
        help="Subjects (eLearning courses) the student is enrolled in.",
    )

    rating_comment_ids = fields.One2many(
        "sis.rating.comment", "enrollment_id", string="Advisor Comments"
    )

    character_rating_ids = fields.One2many(
        "sis.character.rating", "enrollment_id", string="Character Ratings"
    )

    attendance_summary_ids = fields.One2many(
        "sis.attendance.monthly_summary", "enrollment_id", string="Monthly Attendance"
    )

    @api.depends("root_enrollment_id")
    def _compute_history_count(self):
        for record in self:
            root = record.root_enrollment_id or record
            record.history_count = self.search_count([("root_enrollment_id", "=", root.id)]) if root.id else 0

    @api.depends("school_year_id", "root_enrollment_id")
    def _compute_can_reenroll(self):
        active_school_year = self.env.company.active_school_year_id
        for record in self:
            can_reenroll = bool(active_school_year) and record.school_year_id != active_school_year
            if can_reenroll:
                root = record.root_enrollment_id or record
                duplicate = self.search_count([
                    ("root_enrollment_id", "=", root.id),
                    ("school_year_id", "=", active_school_year.id),
                    ("id", "!=", record.id),
                ])
                can_reenroll = duplicate == 0
            record.can_reenroll = can_reenroll

    def _history_root(self):
        self.ensure_one()
        return self.root_enrollment_id or self

    def _get_history_domain(self):
        self.ensure_one()
        return [("root_enrollment_id", "=", self._history_root().id)]

    def _prepare_reenrollment_vals(self, target_school_year):
        self.ensure_one()
        vals = {}
        copy_fields = [
            "company_id", "enrollment_type", "psa_no", "lrn_no", "first_name",
            "middle_name", "last_name", "ext_name", "birth_date", "gender",
            "grade_level_id", "is_indigenous", "indigenous_group", "mother_tongue",
            "is_vaccinated", "first_shot_date", "full_vaccination_date", "house_street",
            "barangay", "city_province", "zip_code", "father_full_name",
            "mother_full_name", "guardian_full_name", "home_phone", "office_phone",
            "user_mobile", "last_grade_level_id", "last_school_year_id", "last_school_name",
            "last_school_id", "last_school_address", "agreed", "student_photo",
            "partner_id", "user_id",
        ]
        for field_name in copy_fields:
            field = self._fields.get(field_name)
            if not field:
                continue
            value = self[field_name]
            if field.type == "many2one":
                vals[field_name] = value.id or False
            else:
                vals[field_name] = value

        # === DETERMINE NEXT GRADE LEVEL ===
        next_grade_level = self.grade_level_id.next_grade_level_id or self.grade_level_id

        vals.update({
            "school_year_id": target_school_year.id,
            "previous_enrollment_id": self.id,
            "root_enrollment_id": self._history_root().id,
            "enrollment_status": "pending",
            "grade_level_id": next_grade_level.id,
            "section_id": False,
        })

        # vals.update({
        #     "school_year_id": target_school_year.id,
        #     "previous_enrollment_id": self.id,
        #     "root_enrollment_id": self._history_root().id,
        #     "enrollment_status": "pending",
        #     "section_id": False,
        # })

        if self.grade_level_id:
            vals["last_grade_level_id"] = self.grade_level_id.id
        if self.school_year_id:
            vals["last_school_year_id"] = self.school_year_id.id

        # === AUTO-SELECT FIRST AVAILABLE SECTION FOR NEXT GRADE ===
        sections = self.env["sis.sections"].search([
            ("school_year_id", "=", target_school_year.id),
            ("grade_level_id", "=", next_grade_level.id),
        ], order="name asc")

        vals["section_id"] = sections[0].id if sections else False
        # matching_section = self.env["sis.sections"].search([
        #     ("school_year_id", "=", target_school_year.id),
        #     ("grade_level_id", "=", self.grade_level_id.id),
        #     ("name", "=", self.section_id.name),
        # ], limit=1) if self.section_id else False
        # vals["section_id"] = matching_section.id if matching_section else False

        # === MATCH TUITION WITH SAME PAYMENT PLAN + NEW GRADE LEVEL ===
        matching_tuition = False

        if self.tuition_id:
            domain = [
                ("school_year_id", "=", target_school_year.id),
                ("grade_level_id", "=", next_grade_level.id),
            ]

            if getattr(self.tuition_id, "payment_plan_id", False):
                domain.append(("payment_plan_id", "=", self.tuition_id.payment_plan_id.id))

            matching_tuition = self.env["sis.tuition"].search(domain, limit=1)

        vals["tuition_id"] = matching_tuition.id if matching_tuition else False
        # matching_tuition = False
        # if self.tuition_id:
        #     domain = [("school_year_id", "=", target_school_year.id)]
        #     if self.tuition_id.grade_level_id:
        #         domain.append(("grade_level_id", "=", self.tuition_id.grade_level_id.id))
        #     if getattr(self.tuition_id, "payment_plan_id", False):
        #         domain.append(("payment_plan_id", "=", self.tuition_id.payment_plan_id.id))
        #     matching_tuition = self.env["sis.tuition"].search(domain, limit=1)
        # vals["tuition_id"] = matching_tuition.id if matching_tuition else False

        return vals

    def action_create_reenrollment(self, target_school_year_id=False):
        self.ensure_one()
        target_school_year = self.env["sis.school.year"].browse(target_school_year_id) if target_school_year_id else self.env.company.active_school_year_id
        if not target_school_year:
            raise ValidationError(_("No active school year is configured."))
        if self.school_year_id == target_school_year:
            raise ValidationError(_("This enrollment already belongs to the target school year."))

        history_domain = self._get_history_domain() + [("school_year_id", "=", target_school_year.id)]
        existing = self.search(history_domain, limit=1)
        if existing:
            return existing

        vals = self._prepare_reenrollment_vals(target_school_year)
        new_enrollment = self.copy(vals)
        if not new_enrollment.root_enrollment_id:
            new_enrollment.root_enrollment_id = self._history_root().id
        return new_enrollment

    def action_open_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Enrollment History"),
            "res_model": "sis.enrollment",
            "view_mode": "list,form",
            "domain": self._get_history_domain(),
            "context": {
                "default_root_enrollment_id": self._history_root().id,
                "search_default_group_school_year": 1,
            },
        }

    def action_reenroll_to_active_school_year(self):
        self.ensure_one()
        enrollment = self.action_create_reenrollment()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sis.enrollment",
            "res_id": enrollment.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_generate_advisor_comments(self):
        """Generate advisor comment records for each grading period if missing."""
        RatingComment = self.env["sis.rating.comment"]
        Period = self.env["sis.period"]

        for enrollment in self:
            # Fetch existing comments for this enrollment
            existing = RatingComment.search([("enrollment_id", "=", enrollment.id)])
            existing_keys = set(rc.period_id.id for rc in existing)

            to_create = []
            for period in Period.search([('school_year_id', '=', enrollment.school_year_id.id)]):
                if period.id not in existing_keys:
                    to_create.append(
                        {
                            "enrollment_id": enrollment.id,
                            "period_id": period.id,
                            # Leave 'comment' blank for advisor to fill
                        }
                    )

            if to_create:
                RatingComment.create(to_create)

    # ------------------------------------------------------------------
    def action_generate_character_ratings(self):
        """
        Create any missing rating lines for this enrollment across *all* periods,
        based on grade‑level type (preschool vs. elementary).
        """
        Rating = self.env["sis.character.rating"]
        Behavior = self.env["sis.character.behavior"]
        Period = self.env["sis.period"]

        for enrollment in self:
            btype = (
                "preschool"
                if enrollment.grade_level_id.id_type == "preschool"
                else "elementary"
            )
            behaviors = Behavior.search([("behavior_type", "=", btype)])

            for period in Period.search([('school_year_id', '=', enrollment.school_year_id.id)]):
                for beh in behaviors:
                    exists = Rating.search_count(
                        [
                            ("enrollment_id", "=", enrollment.id),
                            ("period_id", "=", period.id),
                            ("behavior_id", "=", beh.id),
                        ]
                    )
                    if not exists:
                        Rating.create(
                            {
                                "enrollment_id": enrollment.id,
                                "period_id": period.id,
                                "behavior_id": beh.id,
                                # 'rating' left blank for teacher to fill in
                            }
                        )

    @api.onchange("grade_level_id")
    def _onchange_grade_level_id(self):
        self.section_id = False

    @api.onchange("school_year_id")
    def _onchange_school_year_id(self):
        self.section_id = False
        self.tuition_id = False

    @api.constrains("school_year_id", "company_id")
    def _check_school_year_matches_company(self):
        for record in self:
            if (
                record.school_year_id
                and record.company_id
                and record.school_year_id.company_id
                and record.school_year_id.company_id != record.company_id
            ):
                raise ValidationError(
                    _("The selected school year must belong to the same company.")
                )

    @api.constrains("grade_level_id", "section_id", "school_year_id")
    def _check_section_matches_grade(self):
        for record in self:
            if (
                record.section_id
                and record.section_id.grade_level_id != record.grade_level_id
            ):
                raise ValidationError(
                    _("The selected section does not match the selected grade level.")
                )
            if (
                record.section_id
                and record.school_year_id
                and record.section_id.school_year_id != record.school_year_id
            ):
                raise ValidationError(
                    _("The selected section must belong to the selected school year.")
                )

    @api.constrains("tuition_id", "grade_level_id", "school_year_id")
    def _check_tuition_matches_grade_and_school_year(self):
        for record in self:
            if record.tuition_id and record.tuition_id.grade_level_id != record.grade_level_id:
                raise ValidationError(
                    _("The selected tuition plan does not match the selected grade level.")
                )
            if (
                record.tuition_id
                and record.school_year_id
                and record.tuition_id.school_year_id != record.school_year_id
            ):
                raise ValidationError(
                    _("The selected tuition plan must belong to the selected school year.")
                )

    # @api.constrains("previous_enrollment_id", "root_enrollment_id", "school_year_id", "lrn_no", "psa_no")
    # def _check_history_integrity(self):
    #     for record in self:
    #         if record.previous_enrollment_id and record.previous_enrollment_id.id == record.id:
    #             raise ValidationError(_("An enrollment cannot reference itself as previous enrollment."))
    #         root = record.root_enrollment_id or record
    #         if record.previous_enrollment_id and record.previous_enrollment_id._history_root() != root:
    #             raise ValidationError(_("Previous enrollment must belong to the same student history chain."))
    #         duplicate_domain = [("school_year_id", "=", record.school_year_id.id), ("id", "!=", record.id)]
    #         if root.id:
    #             duplicate_domain.append(("root_enrollment_id", "=", root.id))
    #             if self.search_count(duplicate_domain):
    #                 raise ValidationError(_("A re-enrollment for this student history already exists in the selected school year."))
                
    @api.constrains("previous_enrollment_id", "root_enrollment_id", "school_year_id", "lrn_no", "psa_no")
    def _check_history_integrity(self):
        if self.env.context.get("skip_history_check"):
            return

        for record in self:
            if record.previous_enrollment_id and record.previous_enrollment_id.id == record.id:
                raise ValidationError(_("An enrollment cannot reference itself as previous enrollment."))

            root = record.root_enrollment_id or record

            if record.previous_enrollment_id and record.previous_enrollment_id._history_root() != root:
                raise ValidationError(_("Previous enrollment must belong to the same student history chain."))

            duplicate_domain = [
                ("school_year_id", "=", record.school_year_id.id),
                ("id", "!=", record.id),
            ]

            if root.id:
                duplicate_domain.append(("root_enrollment_id", "=", root.id))
                if self.search_count(duplicate_domain):
                    raise ValidationError(_("A re-enrollment for this student history already exists in the selected school year."))

    def _sanitize_uppercase_fields(self, vals):
        upper_fields = [
            "lrn_no",
            "psa_no",
            "first_name",
            "middle_name",
            "last_name",
            "ext_name",
            "father_full_name",
            "mother_full_name",
            "guardian_full_name",
            "house_street",
            "barangay",
            "city_province",
            "last_school_name",
            "last_school_address",
            "indigenous_group",
            "mother_tongue",
        ]
        for field in upper_fields:
            if field in vals and isinstance(vals[field], str):
                vals[field] = vals[field].upper()

    def _compute_invoice_stats(self):
        for rec in self:
            all_invoices = self.env["account.move"].search(
                [("invoice_origin", "=", f"Enrollment #{rec.id}")]
            )
            rec.invoice_count = len(all_invoices)
            rec.posted_invoice_count = len(
                all_invoices.filtered(lambda inv: inv.state == "posted")
            )


    # === COMPUTE FULL NAME ===
    @api.depends("first_name", "middle_name", "last_name", "ext_name")
    def _compute_full_name(self):
        for record in self:
            # Start with last name + comma
            parts = [record.last_name + "," if record.last_name else ""]
            # Add first name
            if record.first_name:
                parts.append(record.first_name)
            # Add middle name
            if record.middle_name:
                parts.append(record.middle_name)
            # Add ext name
            if record.ext_name:
                parts.append(record.ext_name)
            # Join everything with spaces
            record.full_name = " ".join(filter(None, parts))

    # === COMPUTE AGE FROM BIRTHDATE ===
    @api.depends("birth_date")
    def _compute_age(self):
        for record in self:
            if record.birth_date:
                today = date.today()
                born = record.birth_date
                age = (
                    today.year
                    - born.year
                    - ((today.month, today.day) < (born.month, born.day))
                )
                record.age = age
            else:
                record.age = 0

    @api.onchange("birth_date")
    def _onchange_birth_date(self):
        if self.birth_date:
            today = date.today()
            born = self.birth_date
            self.age = (
                today.year
                - born.year
                - ((today.month, today.day) < (born.month, born.day))
            )
        else:
            self.age = 0

    # === CONSTRAINTS ===
    @api.constrains("agreed")
    def _check_agreement(self):
        for record in self:
            if not record.agreed:
                raise ValidationError(
                    "You must agree to the privacy statement to proceed."
                )

    def send_enrollment_notification_email(self):
        """Send notification email using the template."""
        template = self.env.ref("obbs_sis.email_template_enrollment_notification")

        for record in self:
            if not record.create_uid or not record.create_uid.partner_id.email:
                raise UserError(_("Missing email recipient."))

            company = self.env.company
            company_name = company.name  # 👈 retain your original logic
            registrar_email = company.registrar_email

            template.send_mail(
                record.id,
                email_values={
                    "email_to": record.create_uid.partner_id.email,
                    "email_from": company_name,  # 👈 still using name here
                    "email_cc": registrar_email if registrar_email else False,
                },
                force_send=True,
            )

    def send_enrollment_accepted_email(self):
        """Send an email when enrollment status is accepted."""
        template = self.env.ref("obbs_sis.email_template_enrollment_accepted")

        for record in self:
            if not record.create_uid or not record.create_uid.partner_id.email:
                raise UserError(_("Missing email recipient."))

            company = self.env.company
            company_name = company.name  # 👈 keep the name as the sender
            registrar_email = company.registrar_email

            template.send_mail(
                record.id,
                email_values={
                    "email_to": record.create_uid.partner_id.email,
                    "email_from": company_name,
                    "email_cc": registrar_email if registrar_email else False,
                },
                force_send=True,
            )

    def _generate_tranche_invoices(self):
        account_move = self.env["account.move"]

        for enrollment in self:
            if not enrollment.tuition_id or not enrollment.tuition_id.tranche_ids:
                continue

            partner = enrollment.create_uid.partner_id
            if not partner:
                raise UserError(
                    _(
                        "No partner associated with the user who submitted this enrollment."
                    )
                )

            journal = self.env["account.journal"].search(
                [("type", "=", "sale")], limit=1
            )
            if not journal:
                raise UserError(_("Please configure a sales journal (type = sale)."))

            income_account = self.env["account.account"].search(
                [("account_type", "=", "income")], limit=1
            )
            if not income_account:
                raise UserError(_("Please configure at least one income account."))

            for tranche in enrollment.tuition_id.tranche_ids:
                invoice_vals = {
                    "move_type": "out_invoice",
                    "partner_id": partner.id,
                    "invoice_date_due": tranche.due_date,
                    "invoice_date": fields.Date.context_today(self),
                    "journal_id": journal.id,
                    "invoice_origin": f"Enrollment #{enrollment.id}",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": tranche.name,
                                "quantity": 1,
                                "price_unit": tranche.amount,
                                "account_id": income_account.id,
                            },
                        )
                    ],
                }

                invoice = account_move.create(invoice_vals)

    # Create Portal User for Student
    def action_create_portal_user(self):
        for enrollment in self:
            if (
                not enrollment.user_id
                and enrollment.first_name
                and enrollment.last_name
                and enrollment.birth_date
            ):
                # Construct login name: lastnamefirstname, lowercase, no spaces
                login_base = f"{enrollment.last_name}{enrollment.first_name}".replace(
                    " ", ""
                ).lower()
                login_name = login_base
                counter = 1

                # Ensure login is unique
                while (
                    self.env["res.users"]
                    .sudo()
                    .search([("login", "=", login_name)], limit=1)
                ):
                    login_name = f"{login_base}{counter}"
                    counter += 1

                # Construct default password: lastname + birth year
                birth_year = enrollment.birth_date.year
                default_password = f"{enrollment.last_name}{birth_year}".replace(
                    " ", ""
                ).lower()

                # Try to find an existing partner
                partner = (
                    self.env["res.partner"]
                    .sudo()
                    .search(
                        [
                            ("name", "=", enrollment.full_name),
                            ("phone", "=", enrollment.user_mobile),
                        ],
                        limit=1,
                    )
                )

                if not partner:
                    partner = (
                        self.env["res.partner"]
                        .sudo()
                        .create(
                            {
                                "name": enrollment.full_name,
                                "email": login_name,
                                "phone": enrollment.user_mobile,
                            }
                        )
                    )

                # Create the user account
                user = (
                    self.env["res.users"]
                    .with_context(no_reset_password=True)
                    .sudo()
                    .create(
                        {
                            "name": enrollment.full_name,
                            "login": login_name,
                            "email": login_name,
                            "partner_id": partner.id,
                            "groups_id": [
                                (6, 0, [self.env.ref("base.group_portal").id])
                            ],
                            "password": default_password,
                            "karma": 3,  # Mark as verified
                        }
                    )
                )

                enrollment.user_id = user

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sanitize_uppercase_fields(vals)
            if "company_id" not in vals:
                vals["company_id"] = self.env.company.id
            if "partner_id" not in vals and self.env.user.partner_id:
                vals["partner_id"] = self.env.user.partner_id.id
            if "school_year_id" not in vals and self.env.company.active_school_year_id:
                vals["school_year_id"] = self.env.company.active_school_year_id.id

        records = super().create(vals_list)

        for record, vals in zip(records, vals_list):
            if not record.school_year_id:
                raise ValidationError(
                    _("Active School Year must be set on the Company before creating enrollment.")
                )
            if not record.root_enrollment_id:
                record.root_enrollment_id = vals.get("root_enrollment_id") or record.id
            if record.create_uid and record.create_uid.partner_id:
                record.message_subscribe(partner_ids=[record.create_uid.partner_id.id])
            if record.partner_id:
                record.message_subscribe(partner_ids=[record.partner_id.id])

        return records

    def write(self, vals):
        self._sanitize_uppercase_fields(vals)
        res = super().write(vals)

        for record in self:
            # Ensure school year is present
            if not record.school_year_id:
                raise ValidationError(
                    _("Active School Year must be set on the Company before saving enrollment.")
                )

            # Sync image to connected user
            if "image_1920" in vals:
                user = record.user_id  # or replace with record.user_id if applicable
                if user and user.image_1920 != record.image_1920:
                    user.image_1920 = record.image_1920

            # Handle acceptance workflow
            if vals.get("enrollment_status") == "accepted":
                record.action_create_portal_user()
                record._generate_tranche_invoices()
                record.send_enrollment_accepted_email()

        return res

    def unlink(self):
        for enrollment in self:
            # ✅ Prevent deletion unless pending
            if enrollment.enrollment_status != "pending":
                raise UserError("You can only delete enrollments that are still pending.")
            
            user = enrollment.user_id
            partner = user.partner_id if user else None

            # Delete user (which usually unlinks from partner but doesn't delete the partner)
            if user:
                user.sudo().unlink()

            # Delete partner if still exists and not linked to another user
            # if partner and not self.env["res.users"].sudo().search(
            #     [("partner_id", "=", partner.id)], limit=1
            # ):
            #     partner.sudo().unlink()

        return super().unlink()

    # === ACTIONS ===
    def action_view_related_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Related Invoices",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("invoice_origin", "=", f"Enrollment #{self.id}")],
            "context": {
                "default_invoice_origin": f"Enrollment #{self.id}",
                "default_move_type": "out_invoice",  # customer invoice
                "default_partner_id": self.partner_id.id,  # use parent user account
                "default_enrollment_id": self.id,   # link back to enrollment
            },
        }

    #! Deprecated, planning to implement a different approach 06/30/2025
    # def action_open_generate_id_wizard(self):
    #     return {
    #         "name": "Generate Student ID",
    #         "type": "ir.actions.act_window",
    #         "res_model": "sis.generate.id.wizard",  # ✅ Correct model name
    #         "view_mode": "form",
    #         "target": "new",
    #         "context": {
    #             "default_enrollment_id": self.id,
    #         },
    #     }

    def action_mark_reviewed(self):
        for record in self:
            if record.enrollment_status == "pending":
                record.enrollment_status = "reviewed"

    def action_accept_application(self):
        for record in self:
            if record.enrollment_status == "reviewed":
                record.enrollment_status = "accepted"
