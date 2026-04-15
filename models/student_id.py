import base64
import qrcode
from io import BytesIO
from odoo import models, tools
import logging
import os

_logger = logging.getLogger(__name__)


class StudentIdReport(models.AbstractModel):
    _name = "report.obbs_sis.student_id_report"
    _description = "Student ID Report"

    def _get_report_values(self, docids, data=None):
        _logger.info(f"_get_report_values called with data={data}")

        ctx = (data or {}).get("context", {})
        active_ids = ctx.get("active_ids") or [ctx.get("active_id")]
        active_ids = [i for i in active_ids if i]
        _logger.info(f"Using active_ids: {active_ids}")

        enrollments = self.env["sis.enrollment"].browse(active_ids)

        # Preload reusable images (same across students)
        back_img_base64 = self._load_image_base64("school-id_back.png")
        esc_logo_base64 = self._load_image_base64("esc_logo.png")

        # Prepare list of docs with per-student QR and photo
        return {
            "doc_ids": active_ids,
            "doc_model": "sis.enrollment",
            "docs": enrollments,
            "get_qr": self._generate_qr_code,
            "get_photo": self._get_student_photo,
            "get_front_img": self._get_front_image_name,
            "load_image": self._load_image_base64,
            "back_img": back_img_base64,
            "esc_logo": esc_logo_base64,
        }

    def _get_student_photo(self, enrollment):
        if enrollment and enrollment.image_1920:
            return (
                enrollment.image_1920.decode("utf-8")
                if isinstance(enrollment.image_1920, bytes)
                else enrollment.image_1920
            )
        return False

    def _get_front_image_name(self, id_type):
        filename = {
            "preschool": "preschool-id_front.png",
            "elementary": "elementary-id_front.png",
            "highschool": "highschool-id_front.png",
        }.get(id_type, "preschool-id_front.png")
        return self._load_image_base64(filename)

    def _load_image_base64(self, image_name):
        try:
            addons_path = tools.config["addons_path"].split(",")[0]
            image_path = os.path.join(
                addons_path, "obbs_sis", "static", "src", "img", image_name
            )
            _logger.info(f"Loading image from: {image_path}")
            with open(image_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
                _logger.info(f"Encoded image {image_name}, size={len(encoded)} chars")
                return encoded
        except Exception as e:
            _logger.error(f"Error loading image {image_name}: {e}")
            return False

    def _generate_qr_code(self, enrollment):
        if not enrollment:
            return False

        qr_content = f"{enrollment.id}"
        try:
            qr = qrcode.make(qr_content)
            buffer = BytesIO()
            qr.save(buffer, format="PNG")
            qr_img_base64 = base64.b64encode(buffer.getvalue()).decode()
            _logger.info(
                f"QR code generated for: {qr_content}, size={len(qr_img_base64)} chars"
            )
            return qr_img_base64
        except Exception as e:
            _logger.error(f"Error generating QR code: {e}")
            return False
