from odoo import http
from odoo.http import request
from datetime import datetime
import logging

# Set up a logger for debugging purposes
_logger = logging.getLogger(__name__)


class EnrollmentForm(http.Controller):

    def _validate_date(self, date_str, field_label):
        if not date_str:
            return None
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if date_obj.year < 1900 or date_obj.year > 2100:
                raise ValueError(f"{field_label} year must be between 1900 and 2100.")
            return date_obj.date()
        except ValueError:
            raise ValueError(
                f"Invalid {field_label}. Please use the format DD-MM-YYYY."
            )

    @http.route(["/enroll"], type="http", auth="user", website=True, csrf=True)
    def enroll_form(self, **kw):
        company = request.env.company.sudo()

        return request.render(
            "obbs_sis.website_enrollment_form",
            {
                "grade_levels": request.env["sis.grade.level"].sudo().search([]),
                "school_years": request.env["sis.school.year"]
                .sudo()
                .search([], order="id desc"),
                "active_school_year": company.sudo().active_school_year_id,
                "payment_plans": request.env["sis.payment.plan"].sudo().search([]),
            },
        )

    @http.route(["/enroll/submit"], type="http", auth="user", website=True, csrf=True)
    def enroll_submit(self, **post):
        try:
            company = request.env.company.sudo()
            active_school_year = company.active_school_year_id
            if not active_school_year:
                raise ValueError("The company does not have an active school year set.")

            grade_level_id = int(post.get("grade_level_id"))
            payment_plan_id = int(post.get("tuition_id"))

            # --- Duplicate PSA number check ---
            psa_no = post.get("psa_no")
            if psa_no:
                existing = (
                    request.env["sis.enrollment"]
                    .sudo()
                    .search(
                        [
                            ("school_year_id", "=", active_school_year.id),
                            ("psa_no", "=", psa_no),
                        ],
                        limit=1,
                    )
                )
                if existing:
                    raise ValueError(
                        f"A record with the same PSA No. ({psa_no}) already exists for the school year {active_school_year.name}."
                    )

            # Tuition plan lookup
            matching_tuition_plans = (
                request.env["sis.tuition"]
                .sudo()
                .search(
                    [
                        ("grade_level_id", "=", grade_level_id),
                        ("payment_plan_id", "=", payment_plan_id),
                        ("school_year_id", "=", active_school_year.id),
                    ],
                    limit=1,
                )
            )

            if not matching_tuition_plans:
                raise ValueError(
                    "No matching tuition plan found for the selected grade level and term."
                )

            selected_tuition_plan = matching_tuition_plans[0]

            # Date validation
            birth_date = self._validate_date(post.get("birth_date"), "Birth Date")
            first_shot_date = self._validate_date(
                post.get("first_shot_date"), "First Shot Date"
            )
            full_vaccination_date = self._validate_date(
                post.get("full_vaccination_date"), "Full Vaccination Date"
            )

            vals = {
                "school_year_id": active_school_year.id,
                "company_id": company.id,
                "lrn_no": post.get("lrn_no"),
                "first_name": post.get("first_name"),
                "middle_name": post.get("middle_name"),
                "last_name": post.get("last_name"),
                "ext_name": post.get("ext_name"),
                "birth_date": birth_date,
                "psa_no": psa_no,
                "gender": post.get("gender"),
                "grade_level_id": grade_level_id,
                "enrollment_type": post.get("enrollment_type"),
                "is_indigenous": post.get("is_indigenous"),
                "indigenous_group": post.get("indigenous_group"),
                "mother_tongue": post.get("mother_tongue"),
                "is_vaccinated": post.get("is_vaccinated"),
                "first_shot_date": first_shot_date,
                "full_vaccination_date": full_vaccination_date,
                "house_street": post.get("house_street"),
                "barangay": post.get("barangay"),
                "city_province": post.get("city_province"),
                "zip_code": post.get("zip_code"),
                "father_full_name": post.get("father_full_name"),
                "mother_full_name": post.get("mother_full_name"),
                "guardian_full_name": post.get("guardian_full_name"),
                "home_phone": post.get("home_phone"),
                "office_phone": post.get("office_phone"),
                "user_mobile": post.get("user_mobile"),
                "last_school_name": post.get("last_school_name"),
                "last_school_id": post.get("last_school_id"),
                "last_school_address": post.get("last_school_address"),
                "last_grade_level_id": (
                    int(post.get("last_grade_level_id"))
                    if post.get("last_grade_level_id")
                    else False
                ),
                "last_school_year_id": (
                    int(post.get("last_school_year_id"))
                    if post.get("last_school_year_id")
                    else False
                ),
                "tuition_id": selected_tuition_plan.id,
                "agreed": post.get("agreed") == "on",
            }

            enrollment = request.env["sis.enrollment"].sudo().create(vals)
            enrollment.send_enrollment_notification_email()

            return request.redirect("/enroll/thanks")

        except Exception as e:
            _logger.error(f"Error during enrollment submission: {str(e)}")
            return request.render(
                "obbs_sis.website_enrollment_form",
                {
                    "error": str(e),
                    "post": post,
                    "grade_levels": request.env["sis.grade.level"].sudo().search([]),
                    "school_years": request.env["sis.school.year"].sudo().search([]),
                    "active_school_year": company.sudo().active_school_year_id,
                    "payment_plans": request.env["sis.payment.plan"].sudo().search([]),
                },
            )

    @http.route(["/enroll/thanks"], type="http", auth="user", website=True)
    def enroll_thanks(self, **kw):
        return request.render("obbs_sis.website_enroll_thanks")
