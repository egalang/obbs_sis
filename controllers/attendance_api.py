# -*- coding: utf-8 -*-
import json
import time
import hmac
import hashlib
import logging
from datetime import datetime, timezone

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 🔑  COMMON AUTH MIX‑IN  (reuse across modules)
# ---------------------------------------------------------------------------
class APITokenMixin:
    ACCESS_TTL = 7 * 24 * 60 * 60  # 7 days
    REFRESH_TTL = 14 * 24 * 60 * 60  # 14 days

    # ..............................................................
    # Helpers
    # ..............................................................
    @staticmethod
    def _json(payload, status=200):
        return http.Response(
            json.dumps(payload), status=status, content_type="application/json"
        )

    def _get_secret(self):
        return (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("sis.secret_key", "default-secret")
        )

    def _generate_token(self, user_id, tag="A"):
        ts = str(int(time.time()))
        msg = f"{tag}:{user_id}:{ts}"
        sig = hmac.new(
            self._get_secret().encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
        return f"{tag}:{user_id}:{ts}:{sig}"

    def _validate_token(self, token, tag="A"):
        try:
            tok_tag, user_id, ts, sig = token.split(":")
            ts = int(ts)
        except Exception:  # badly‑formatted string
            return None

        if tok_tag != tag:
            return None
        ttl = self.ACCESS_TTL if tag == "A" else self.REFRESH_TTL
        if time.time() - ts > ttl:  # expired
            return None

        msg = f"{tok_tag}:{user_id}:{ts}"
        expected_sig = hmac.new(
            self._get_secret().encode(), msg.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, sig):
            return None
        return int(user_id)

    def _current_user(self):
        token = request.httprequest.headers.get("Authorization", "").replace(
            "Bearer ", ""
        )
        uid = self._validate_token(token, "A")
        if not uid:
            return None
        return request.env["res.users"].sudo().browse(uid)


# ---------------------------------------------------------------------------
# 📒  ATTENDANCE + AUTH CONTROLLER  (this module)
# ---------------------------------------------------------------------------
class AttendanceAPIController(http.Controller, APITokenMixin):

    # ───────────────────────────────────────────────────────────────
    # AUTH  –  /api/auth/login  (POST)
    # ───────────────────────────────────────────────────────────────
    @http.route(
        "/api/auth/login", type="http", auth="public", csrf=False, methods=["POST"]
    )
    def login(self):
        try:
            data = json.loads(request.httprequest.data or "{}")
        except Exception:
            return self._json({"error": "Malformed JSON body"}, 400)

        login = (data.get("login") or "").strip().lower()
        password = data.get("password")
        if not login or not password:
            return self._json({"error": "login and password required"}, 400)

        user = request.env["res.users"].sudo().search([("login", "=", login)], limit=1)
        if not user or not user.active:
            return self._json({"error": "Invalid login"}, 401)

        try:
            user.with_user(user)._check_credentials(
                {"type": "password", "password": password}, {"interactive": True}
            )
        except Exception:
            return self._json({"error": "Invalid password"}, 401)

        access_token = self._generate_token(user.id, "A")
        refresh_token = self._generate_token(user.id, "R")

        return self._json(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "access_expires_in": self.ACCESS_TTL,
                "refresh_expires_in": self.REFRESH_TTL,
                "user_id": user.id,
                "partner_id": user.partner_id.id or None,
                "name": user.name,
            }
        )

    # ───────────────────────────────────────────────────────────────
    # AUTH  –  /api/auth/refresh  (POST)
    # ───────────────────────────────────────────────────────────────
    @http.route(
        "/api/auth/refresh", type="http", auth="public", csrf=False, methods=["POST"]
    )
    def refresh(self):
        try:
            data = json.loads(request.httprequest.data or "{}")
            rtoken = data.get("refresh_token")
        except Exception:
            return self._json({"error": "Malformed JSON body"}, 400)

        if not rtoken:
            return self._json({"error": "refresh_token is required"}, 400)

        uid = self._validate_token(rtoken, "R")
        if not uid:
            return self._json({"error": "Invalid or expired refresh_token"}, 401)

        return self._json(
            {
                "access_token": self._generate_token(uid, "A"),
                "access_expires_in": self.ACCESS_TTL,
            }
        )

    # ───────────────────────────────────────────────────────────────
    # AUTH  –  /api/auth/whoami  (GET)
    # ───────────────────────────────────────────────────────────────
    @http.route(
        "/api/auth/whoami", type="http", auth="public", csrf=False, methods=["GET"]
    )
    def whoami(self):
        user = self._current_user()
        if not user:
            return self._json({"error": "Session expired"}, 401)

        # Safe env attached to the actual user
        user_env = request.env(user=user)

        return self._json(
            {
                "id": user.id,
                "name": user.name,
                "email": user.login,
                "is_system": user_env.is_system(),
                "is_admin": user_env.is_admin(),
                "is_portal_user": user.share,
                "is_internal_user": not user.share,
            }
        )

    # ───────────────────────────────────────────────────────────────
    # ATTENDANCE  –  /api/attendances  (GET)
    # ───────────────────────────────────────────────────────────────
    @http.route(
        "/api/attendances", type="http", auth="public", csrf=False, methods=["GET"]
    )
    def get_attendances(self):
        user = self._current_user()
        if not user:
            return self._json({"error": "Unauthorized"}, 401)

        # Get query parameters
        try:
            limit = int(request.httprequest.args.get("limit", 20))  # Default 20
            offset = int(request.httprequest.args.get("offset", 0))  # Default 0
            parent_id = request.httprequest.args.get("parent_id")
            date_from = request.httprequest.args.get("date_from")
            date_to = request.httprequest.args.get("date_to")

            # Validate pagination parameters
            if limit < 1 or limit > 1000:  # Prevent abuse
                return self._json({"error": "limit must be between 1 and 1000"}, 400)
            if offset < 0:
                return self._json({"error": "offset must be >= 0"}, 400)

            # Validate parent_id if provided
            if parent_id:
                parent_id = int(parent_id)
                if parent_id <= 0:
                    return self._json(
                        {"error": "parent_id must be a positive integer"}, 400
                    )

            # Validate date parameters if provided
            if date_from:
                try:
                    datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                except ValueError:
                    return self._json(
                        {
                            "error": "date_from must be in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                        },
                        400,
                    )

            if date_to:
                try:
                    datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                except ValueError:
                    return self._json(
                        {
                            "error": "date_to must be in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
                        },
                        400,
                    )

        except ValueError:
            return self._json({"error": "Invalid parameter format"}, 400)

        try:
            # Build domain filters
            domain = []

            # Filter by parent_id if provided
            if parent_id:
                domain.append(("enrollment_id.partner_id", "=", parent_id))

            # Filter by date range if provided
            if date_from:
                domain.append(("attendance_datetime", ">=", date_from))

            if date_to:
                domain.append(("attendance_datetime", "<=", date_to))

            # Get attendance logs with pagination and filters
            AttendanceLog = request.env["sis.student.attendance.log"].sudo()

            # Get total count with filters
            total_count = AttendanceLog.search_count(domain)

            # Get records with limit/offset, ordered by datetime descending (newest first)
            logs = AttendanceLog.search(
                domain, limit=limit, offset=offset, order="attendance_datetime desc"
            )

            # Prepare response data
            records = []
            for log in logs:
                records.append(
                    {
                        "id": log.id,
                        "enrollment_id": log.enrollment_id.id,
                        "enrollment_name": log.enrollment_id.display_name,
                        "section_display_name": log.section_display_name,
                        "log_type": log.log_type,
                        "attendance_datetime": (
                            log.attendance_datetime.isoformat()
                            if log.attendance_datetime
                            else None
                        ),
                    }
                )

            return self._json(
                {
                    "status": "success",
                    "pagination": {
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_next": (offset + limit) < total_count,
                        "has_prev": offset > 0,
                        "next_offset": (
                            offset + limit if (offset + limit) < total_count else None
                        ),
                        "prev_offset": max(0, offset - limit) if offset > 0 else None,
                    },
                    "data": records,
                }
            )

        except Exception as e:
            _logger.exception("Failed to fetch attendance logs")
            return self._json({"error": "Internal server error"}, 500)

    # ───────────────────────────────────────────────────────────────
    # ATTENDANCE  –  /api/attendance/log  (POST)
    # ───────────────────────────────────────────────────────────────
    @http.route(
        "/api/attendance/log", type="http", auth="public", csrf=False, methods=["POST"]
    )
    def log_attendance(self):
        user = self._current_user()
        if not user:
            return self._json({"error": "Unauthorized"}, 401)
        if user.share:
            return self._json({"error": "Access denied: internal users only"}, 403)

        try:
            data = json.loads(request.httprequest.data or "{}")
        except Exception:
            return self._json({"error": "Malformed JSON body"}, 400)

        enrollment_id = data.get("enrollment_id")
        log_type = data.get("log_type")
        if not enrollment_id or not log_type:
            return self._json({"error": "enrollment_id and log_type are required"}, 400)

        enrollment = request.env["sis.enrollment"].sudo().browse(int(enrollment_id))
        if not enrollment.exists():
            return self._json({"error": "Student does not exist"}, 404)

        try:
            log = (
                request.env["sis.student.attendance.log"]
                .sudo()
                .create(
                    {
                        "enrollment_id": enrollment.id,
                        "log_type": log_type,
                    }
                )
            )
        except ValidationError as ve:
            return self._json({"error": str(ve)}, 400)
        except Exception as e:
            _logger.exception("Failed to log attendance")
            return self._json({"error": str(e)}, 500)

        return self._json(
            {
                "status": "success",
                "log_id": log.id,
                "student_name": enrollment.full_name,
                "section_name": enrollment.section_id.display_name,
            },
            201,
        )

    @http.route(
        "/api/attendances/notify",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def notify_attendance(self):
        user = self._current_user()
        if not user:
            return self._json({"error": "Unauthorized"}, 401)

        try:
            parent_id = int(request.httprequest.args.get("parent_id", 0))
        except Exception:
            return self._json({"error": "parent_id required and must be int"}, 400)

        if parent_id <= 0:
            return self._json({"error": "Invalid parent_id"}, 400)

        AttendanceLog = request.env["sis.student.attendance.log"].sudo()

        # Fetch logs not yet notified for this parent
        logs = AttendanceLog.search(
            [
                ("enrollment_id.partner_id", "=", parent_id),
                ("log_type", "in", ["school_in", "school_out"]),
                ("is_notified", "=", False),
            ]
        )

        if not logs:
            return self._json({"status": "empty", "data": []})

        # Prepare the data
        data = [
            {
                "id": log.id,
                "log_type": log.log_type,
                "attendance_datetime": log.attendance_datetime.isoformat(),
                "student_name": log.enrollment_id.full_name,
                "section_name": log.enrollment_id.section_id.display_name,
            }
            for log in logs
        ]

        # Mark them as notified
        logs.write({"is_notified": True})

        return self._json({"status": "success", "count": len(data), "data": data})
    
    # ───────────────────────────────────────────────────────────────
    # STUDENTS  –  /api/students/enrollments  (GET)
    # ───────────────────────────────────────────────────────────────
    @http.route(
        "/api/students/enrollments",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def get_student_enrollments(self):
        user = self._current_user()
        if not user:
            return self._json({"error": "Unauthorized"}, 401)

        try:
            limit = int(request.httprequest.args.get("limit", 200))
            offset = int(request.httprequest.args.get("offset", 0))
            school_year_id = request.httprequest.args.get("school_year_id")
            section_id = request.httprequest.args.get("section_id")
            grade_level_id = request.httprequest.args.get("grade_level_id")
            search = (request.httprequest.args.get("search") or "").strip()

            if limit < 1 or limit > 5000:
                return self._json({"error": "limit must be between 1 and 5000"}, 400)
            if offset < 0:
                return self._json({"error": "offset must be >= 0"}, 400)

            if school_year_id:
                school_year_id = int(school_year_id)
                if school_year_id <= 0:
                    return self._json(
                        {"error": "school_year_id must be a positive integer"}, 400
                    )

            if section_id:
                section_id = int(section_id)
                if section_id <= 0:
                    return self._json(
                        {"error": "section_id must be a positive integer"}, 400
                    )

            if grade_level_id:
                grade_level_id = int(grade_level_id)
                if grade_level_id <= 0:
                    return self._json(
                        {"error": "grade_level_id must be a positive integer"}, 400
                    )

        except ValueError:
            return self._json({"error": "Invalid parameter format"}, 400)

        try:
            Enrollment = request.env["sis.enrollment"].sudo()

            domain = []

            # Keep only active enrollments/students for attendance usage
            if "active" in Enrollment._fields:
                domain.append(("active", "=", True))

            # Optional filters
            if school_year_id and "school_year_id" in Enrollment._fields:
                domain.append(("school_year_id", "=", school_year_id))

            if section_id and "section_id" in Enrollment._fields:
                domain.append(("section_id", "=", section_id))

            if grade_level_id and "grade_level_id" in Enrollment._fields:
                domain.append(("grade_level_id", "=", grade_level_id))

            if search:
                search_domain = ["|", "|",
                    ("full_name", "ilike", search),
                    ("display_name", "ilike", search),
                    ("student_number", "ilike", search),
                ]
                domain += search_domain

            total_count = Enrollment.search_count(domain)
            enrollments = Enrollment.search(
                domain,
                limit=limit,
                offset=offset,
                order="id desc",
            )

            data = []
            for rec in enrollments:
                school_year_name = None
                if "school_year_id" in rec._fields and rec.school_year_id:
                    school_year_name = rec.school_year_id.display_name

                grade_level_name = None
                if "grade_level_id" in rec._fields and rec.grade_level_id:
                    grade_level_name = rec.grade_level_id.display_name

                section_name = None
                if "section_id" in rec._fields and rec.section_id:
                    section_name = rec.section_id.display_name

                student_number = None
                if "student_number" in rec._fields:
                    student_number = rec.student_number
                elif "student_no" in rec._fields:
                    student_number = rec.student_no

                partner_id = None
                if "partner_id" in rec._fields and rec.partner_id:
                    partner_id = rec.partner_id.id

                student_name = None
                if "full_name" in rec._fields and rec.full_name:
                    student_name = rec.full_name
                elif "student_id" in rec._fields and rec.student_id:
                    student_name = rec.student_id.display_name
                else:
                    student_name = rec.display_name

                data.append(
                    {
                        "enrollment_id": rec.id,
                        "student_name": student_name,
                        "student_number": student_number,
                        "partner_id": partner_id,
                        "section_name": section_name,
                        "grade_level_name": grade_level_name,
                        "school_year": school_year_name,
                        "is_active": getattr(rec, "active", True),
                    }
                )

            return self._json(
                {
                    "status": "success",
                    "pagination": {
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_next": (offset + limit) < total_count,
                        "has_prev": offset > 0,
                        "next_offset": (
                            offset + limit if (offset + limit) < total_count else None
                        ),
                        "prev_offset": max(0, offset - limit) if offset > 0 else None,
                    },
                    "data": data,
                }
            )

        except Exception:
            _logger.exception("Failed to fetch student enrollments")
            return self._json({"error": "Internal server error"}, 500)
