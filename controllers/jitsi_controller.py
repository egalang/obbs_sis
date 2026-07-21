from odoo import http
from odoo.http import request
import time, jwt
import logging
import re

_logger = logging.getLogger(__name__)


class WebsiteJitsiController(http.Controller):
    JWT_APP_ID = "odoo-sis"
    JWT_SECRET = "6F6262735F736973"
    JITSI_DOMAIN = "jitsi.obbserver.com"

    @http.route(
        "/jitsi/join_web/<int:channel_id>", type="http", auth="user", website=True
    )
    def jitsi_join_website(self, channel_id, **kwargs):
        user = request.env.user
        _logger.info(
            f"[Jitsi][Join][Website] User: {user.name} (ID: {user.id}) is attempting to join channel {channel_id}"
        )

        channel = request.env["slide.channel"].sudo().browse(channel_id)

        if not channel.exists():
            _logger.warning(f"[Jitsi][Join][Website] Channel {channel_id} not found")
            return self._render_access_denied("Channel not found.")

        _logger.info(
            f"[Jitsi][Join][Website] Channel found: {channel.name} (Faculty: {channel.user_id.name})"
        )

        # Check enrollee status
        try:
            partner_ids = channel.channel_partner_ids.mapped("partner_id").ids
            is_enrollee = user.partner_id.id in partner_ids
            _logger.info(
                f"[Jitsi][Join][Website] Partner ID: {user.partner_id.id}, Enrolled Partner IDs: {partner_ids}"
            )
        except Exception as e:
            _logger.error(
                f"[Jitsi][Join][Website] Error checking enrollee status: {e}",
                exc_info=True,
            )
            return self._render_access_denied("Error verifying enrollment.")

        if not is_enrollee:
            _logger.warning(
                f"[Jitsi][Join][Website] Access denied: User {user.name} is not enrolled in channel {channel.name}"
            )
            return self._render_access_denied("You are not enrolled in this course.")

        # ✅ Time window check
        now_ts = time.time()
        if channel.meeting_start_datetime and channel.meeting_end_datetime:
            start_ts = channel.meeting_start_datetime.timestamp()
            end_ts = channel.meeting_end_datetime.timestamp()

            if not (start_ts <= now_ts <= end_ts):
                _logger.warning(
                    f"[Jitsi][Join][Website] User {user.name} attempted access outside of scheduled time window."
                )
                return self._render_access_denied(
                    "Meeting access is only allowed during the scheduled time."
                )

        # Ensure room name
        if not channel.jitsi_room_name:
            _logger.info(f"[Jitsi][Join][Website] No room name found, generating one.")
            channel.sudo()._ensure_jitsi_room_name()

        room = self._slugify_room_name(channel.jitsi_room_name)
        time_now = int(now_ts)

        payload = {
            "aud": self.JWT_APP_ID,
            "iss": self.JWT_APP_ID,
            "sub": "*",
            "room": room,
            "exp": time_now + 3600,
            "iat": time_now,
            "nbf": time_now,
            "moderator": False,
            "context": {
                "user": {
                    "name": user.name or "Anonymous",
                    "email": user.email or "",
                },
                # "moderator": False
            },
        }

        try:
            token = jwt.encode(payload, self.JWT_SECRET, algorithm="HS256")
            jitsi_url = f"https://{self.JITSI_DOMAIN}/{room}?jwt={token}"
            _logger.info(
                f"[Jitsi][Join][Website] Redirecting user {user.name} to: {jitsi_url}"
            )
            return request.make_response(
                "", status=303, headers=[("Location", jitsi_url)]
            )
        except Exception as e:
            _logger.error(
                f"[Jitsi][Join][Website] Error generating token or redirecting: {e}",
                exc_info=True,
            )
            return self._render_access_denied(
                "An error occurred while joining the meeting."
            )

    def _slugify_room_name(self, name):
        """Convert room name to a URL-safe slug."""
        name = name.lower()
        name = re.sub(r"[^a-z0-9]+", "-", name)
        return name.strip("-")

    def _render_access_denied(self, message):
        """Render custom access denied template with message"""
        return request.render("obbs_sis.jitsi_403", {"error_message": message})
