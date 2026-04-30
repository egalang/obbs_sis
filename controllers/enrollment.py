from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError
import logging

_logger = logging.getLogger(__name__)


class EnrollmentPortal(CustomerPortal):

    def _portal_enrollment_domain(self):
        user = request.env.user
        return ["|", ("partner_id", "=", user.partner_id.id), ("user_id", "=", user.id)]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)

        Enrollment = request.env["sis.enrollment"]
        if "enrollment_count" in counters:
            if Enrollment.has_access("read"):
                values["enrollment_count"] = Enrollment.sudo().search_count(self._portal_enrollment_domain())
            else:
                values["enrollment_count"] = 0

        return values
    
    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def portal_my_home(self, **kwargs):
        values = self._prepare_home_portal_values(['enrollment_count'])
        return request.render("portal.portal_my_home", values)

    @http.route(["/my/enrollments"], type="http", auth="user", website=True)
    def portal_my_enrollments(self, **kwargs):
        enrollments = (
            request.env["sis.enrollment"]
            .sudo()
            .search(self._portal_enrollment_domain(), order="school_year_id desc, id desc")
        )
        return request.render(
            "obbs_sis.portal_enrollment_list",  # Step 1 template
            {
                "enrollments": enrollments,  # Data for rendering
                "page_name": "enrollment",  # Step 2 for breadcrumb
            },
        )

    @http.route(
        ["/my/enrollments/<int:enrollment_id>"], type="http", auth="user", website=True
    )
    def portal_enrollment_page(self, enrollment_id, **kwargs):
        enrollment = request.env["sis.enrollment"].sudo().browse(enrollment_id)
        if not enrollment.exists():
            return request.redirect("/my/enrollments")

        partner = request.env.user.partner_id
        if (
            enrollment.partner_id != partner
            and enrollment.user_id != request.env.user
            and not request.env.user.has_group("base.group_system")
        ):
            raise AccessError("You don't have access to this enrollment record.")

        if partner not in enrollment.message_partner_ids:
            enrollment.message_subscribe(partner_ids=[partner.id])

        return request.render(
            "obbs_sis.portal_enrollment_page",
            {
                "enrollment": enrollment,
                "page_name": "student_enrollment",
            },
        )

    @http.route(
        ["/my/enrollments/<int:enrollment_id>/update"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_update_enrollment_page(self, enrollment_id, **kwargs):
        enrollment = request.env["sis.enrollment"].sudo().browse(enrollment_id)
        if not enrollment.exists():
            return request.redirect("/my/enrollments")

        partner = request.env.user.partner_id
        if (
            enrollment.partner_id != partner
            and enrollment.user_id != request.env.user
            and not request.env.user.has_group("base.group_system")
        ):
            raise AccessError("You don't have access to this enrollment record.")

        return request.render(
            "obbs_sis.portal_update_enrollment_page",
            {
                "enrollment": enrollment,
                "grade_levels": request.env["sis.grade.level"].sudo().search([]),
                "school_years": request.env["sis.school.year"].sudo().search([]),
                "payment_plans": request.env["sis.payment.plan"].sudo().search([]),
            },
        )

    @http.route(
        ["/my/enrollments/<int:enrollment_id>/update/submit"],
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def portal_update_enrollment_submit(self, enrollment_id, **post):
        enrollment = request.env["sis.enrollment"].sudo().browse(enrollment_id)
        if not enrollment.exists():
            return request.redirect("/my/enrollments")

        partner = request.env.user.partner_id
        if (
            enrollment.partner_id != partner
            and enrollment.user_id != request.env.user
            and not request.env.user.has_group("base.group_system")
        ):
            raise AccessError("You don't have access to this enrollment record.")

        try:

            grade_level_id = int(post.get("grade_level_id") or 0)
            payment_plan_id = int(post.get("tuition_id") or 0)

            # Match tuition plan
            matching_tuition_plan = (
                request.env["sis.tuition"]
                .sudo()
                .search(
                    [
                        ("grade_level_id", "=", grade_level_id),
                        ("payment_plan_id", "=", payment_plan_id),
                        ("school_year_id", "=", enrollment.school_year_id.id if hasattr(enrollment, "school_year_id") else active_school_year.id),
                    ],
                    limit=1,
                )
            )

            if not matching_tuition_plan:
                raise ValueError(
                    "No matching tuition plan found for the selected grade level and payment plan."
                )

            selected_tuition_plan = matching_tuition_plan[0]

            values = {
                # Student Info
                "first_name": post.get("first_name"),
                "middle_name": post.get("middle_name"),
                "last_name": post.get("last_name"),
                "ext_name": post.get("ext_name"),
                "birth_date": post.get("birth_date"),
                "lrn_no": post.get("lrn_no"),
                "psa_no": post.get("psa_no"),
                "gender": post.get("gender"),
                "grade_level_id": grade_level_id,
                "enrollment_type": post.get("enrollment_type"),
                "mother_tongue": post.get("mother_tongue"),
                "is_indigenous": post.get("is_indigenous"),
                "indigenous_group": post.get("indigenous_group"),
                # Vaccination
                "is_vaccinated": post.get("is_vaccinated"),
                "first_shot_date": post.get("first_shot_date"),
                "full_vaccination_date": post.get("full_vaccination_date"),
                # Address
                "house_street": post.get("house_street"),
                "barangay": post.get("barangay"),
                "city_province": post.get("city_province"),
                "zip_code": post.get("zip_code"),
                # Parents / Guardians
                "father_full_name": post.get("father_full_name"),
                "mother_full_name": post.get("mother_full_name"),
                "guardian_full_name": post.get("guardian_full_name"),
                "tuition_id": selected_tuition_plan.id,
            }

            enrollment.write(values)
            return request.redirect("/enroll/update/thanks")

        except Exception as e:
            _logger.error(f"Error updating enrollment: {str(e)}")
            return request.render(
                "obbs_sis.portal_update_enrollment_page",
                {
                    "error": str(e),
                    "enrollment": enrollment,
                    "grade_levels": request.env["sis.grade.level"].sudo().search([]),
                    "school_years": request.env["sis.school.year"].sudo().search([]),
                    "payment_plans": request.env["sis.payment.plan"].sudo().search([]),
                },
            )


    @http.route(
        ["/my/enrollments/<int:enrollment_id>/re-enroll"],
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def portal_reenroll_enrollment(self, enrollment_id, **post):
        enrollment = request.env["sis.enrollment"].sudo().browse(enrollment_id)
        if not enrollment.exists():
            return request.redirect("/my/enrollments")

        partner = request.env.user.partner_id
        if (
            enrollment.partner_id != partner
            and enrollment.user_id != request.env.user
            and not request.env.user.has_group("base.group_system")
        ):
            raise AccessError("You don't have access to this enrollment record.")

        try:
            new_enrollment = enrollment.action_create_reenrollment()
            return request.redirect(f"/my/enrollments/{new_enrollment.id}/update")
        except Exception as e:
            _logger.error(f"Error during re-enrollment: {str(e)}")
            return request.redirect(f"/my/enrollments/{enrollment.id}?error=reenroll")

    @http.route("/enroll/update/thanks", type="http", auth="user", website=True)
    def enroll_update_thanks(self, **kw):
        return request.render("obbs_sis.website_enroll_update_thanks")

    @http.route(
        ["/my/enrollments/<int:enrollment_id>/delete"],
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def portal_delete_enrollment(self, enrollment_id, **post):
        enrollment = request.env["sis.enrollment"].sudo().browse(enrollment_id)

        if not enrollment.exists():
            return request.redirect("/my/enrollments")

        partner = request.env.user.partner_id
        if (
            enrollment.partner_id != partner
            and enrollment.user_id != request.env.user
            and not request.env.user.has_group("base.group_system")
        ):
            raise AccessError("You don't have access to this enrollment record.")

        # ✅ Only allow delete if still pending
        if enrollment.enrollment_status != "pending":
            return request.redirect(f"/my/enrollments/{enrollment.id}?error=not_allowed")

        try:
            enrollment.unlink()
            return request.redirect("/my/enrollments")
        except Exception as e:
            _logger.error(f"Error deleting enrollment: {str(e)}")
            return request.redirect(f"/my/enrollments/{enrollment.id}?error=delete")