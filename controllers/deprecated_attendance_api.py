from odoo import http, fields
from odoo.http import request
import jwt
import datetime
import uuid
import logging

_logger = logging.getLogger(__name__)


class AttendanceAPIController(http.Controller):
    SECRET_KEY = None  # Loaded once per request lifecycle

    def _get_secret_key(self):
        if not self.SECRET_KEY:
            self.SECRET_KEY = (
                request.env["ir.config_parameter"]
                .sudo()
                .get_param("sis.attendance_jwt_secret")
            )
        return self.SECRET_KEY

    def _decode_token(self, token):
        try:
            return jwt.decode(token, self._get_secret_key(), algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return {"error": "Token expired"}
        except jwt.InvalidTokenError:
            return {"error": "Invalid token"}

    def _is_blacklisted(self, jti):
        return (
            request.env["sis.jwt.blacklist"].sudo().search([("jti", "=", jti)], limit=1)
        )

    def _validate_token(self, auth_header):
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split("Bearer ")[1]
        payload = self._decode_token(token)

        if "error" in payload or self._is_blacklisted(payload.get("jti")):
            return None

        user = request.env["res.users"].sudo().browse(payload.get("user_id"))
        return user if user.exists() else None

    @http.route(
        "/api/auth/login", type="json", auth="none", methods=["POST"], csrf=False
    )
    def login(self):
        data = request.httprequest.get_json()
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return {"status": "error", "message": "Email and password are required"}

        user = request.env["res.users"].sudo().search([("login", "=", email)], limit=1)
        if not user or user.share:
            return {"status": "error", "message": "Invalid login credentials"}

        try:
            user = user.with_user(user)
            credentials = {"type": "password", "password": password}
            user.sudo()._check_credentials(credentials, {"interactive": True})
        except Exception:
            return {"status": "error", "message": "Invalid login credentials"}

        jti = str(uuid.uuid4())
        payload = {
            "user_id": user.id,
            "name": user.name,
            "email": user.login,
            "jti": jti,
            "exp": (
                datetime.datetime.utcnow() + datetime.timedelta(hours=12)
            ).timestamp(),
        }

        token = jwt.encode(payload, self._get_secret_key(), algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("utf-8")

        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        avatar_url = f"{base_url}/api/public/avatar/{user.id}"

        return {
            "status": "success",
            "token": token,
            "user_data": {
                "user_id": user.id,
                "name": user.name,
                "email": user.login,
                "avatar_url": avatar_url,
            },
        }

    @http.route(
        "/api/auth/logout", type="json", auth="none", methods=["POST"], csrf=False
    )
    def logout(self):
        auth_header = request.httprequest.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return {
                "status": "error",
                "message": "Missing or invalid Authorization header",
            }

        token = auth_header.split("Bearer ")[1]
        payload = self._decode_token(token)

        if "error" in payload:
            return {"status": "error", "message": payload["error"]}

        jti = payload.get("jti")
        user_id = payload.get("user_id")

        if not jti or not user_id:
            return {"status": "error", "message": "Invalid token payload"}

        if not self._is_blacklisted(jti):
            request.env["sis.jwt.blacklist"].sudo().create(
                {
                    "jti": jti,
                    "user_id": user_id,
                    "blacklisted_on": fields.Datetime.now(),
                }
            )

        return {"status": "success", "message": "Logged out successfully"}

    @http.route(
        "/api/attendance/log", type="json", auth="none", methods=["POST"], csrf=False
    )
    def log_attendance(self):
        data = request.httprequest.get_json()
        auth_header = request.httprequest.headers.get("Authorization", "")

        user = self._validate_token(auth_header)
        if not user:
            return {"status": "error", "message": "Unauthorized"}

        enrollment_id = data.get("enrollment_id")
        log_type = data.get("log_type")

        if not enrollment_id or not log_type:
            return {"status": "error", "message": "Missing required fields"}

        try:
            log = (
                request.env["sis.student.attendance.log"]
                .sudo()
                .create(
                    {
                        "enrollment_id": enrollment_id,
                        "log_type": log_type,
                        # attendance_datetime is handled by model default
                    }
                )
            )
            return {
                "status": "success",
                "message": "Attendance log recorded",
                "log_id": log.id,
            }
        except Exception as e:
            _logger.exception("Failed to log attendance")
            return {"status": "error", "message": str(e)}
