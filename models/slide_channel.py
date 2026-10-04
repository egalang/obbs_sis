from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError
import jwt
import time
import logging
import re
import secrets

_logger = logging.getLogger(__name__)


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    JWT_APP_ID = "odoo-sis"
    JWT_SECRET = "6F6262735F736973"
    JITSI_DOMAIN = "jitsi.obbserver.com"

    # section_id = fields.Many2one(
    #     "sis.sections",
    #     string="Section",
    #     tracking=True,
    #     help="Select the section to enroll for this subject",
    # )
    section_id = fields.Many2one(
        "sis.sections",
        string="Section",
        tracking=True,
        help="Select the section to enroll for this subject",
        domain=lambda self: [
            (
                "school_year_id",
                "=",
                self.env.company.active_school_year_id.id
                if self.env.company.active_school_year_id
                else False,
            )
        ],
    )

    school_year_id = fields.Many2one(
        "sis.school.year",
        string="School Year",
        related="section_id.school_year_id",
        store=True,
        index=True,
        readonly=True,
    )

    subject_code = fields.Char(
        string="Subject Code",
        required=True,
        help="Unique code used for reporting (e.g., MATH01, MAPEH01).",
    )

    is_composite_component = fields.Boolean(
        string="Is Component of Composite Subject",
        help="Tick if this channel is part of a composite subject like MAPEH.",
    )
    composite_subject_name = fields.Char(
        string="Composite Subject",
        help="If part of a composite subject, specify its name (e.g., MAPEH).",
    )

    channel_partner_ids = fields.One2many(
        "slide.channel.partner",
        "channel_id",
        string="Enrolled Attendees Information",
        groups="obbs_sis.group_sis_faculty",
        domain=[("member_status", "!=", "invited")],
    )

    activity_type_ids = fields.One2many(
        "sis.activity.type",
        "channel_id",
        string="Activity Types",
        help="List of activity types related to this learning channel",
    )

    jitsi_room_name = fields.Char(
        string="Jitsi Room Name",
        readonly=True,
        help="Unique room name used for Jitsi meetings",
        tracking=True,
    )

    jitsi_room_secret = fields.Char(
        string="Jitsi Room Secret",
        readonly=True,
        copy=False,
        help="Random token appended to the meeting room to keep it unguessable. "
             "Only users issued an Odoo meeting link can join the room.",
    )

    meeting_start_datetime = fields.Datetime(
        string="Meeting Start Time",
        help="Start time for Jitsi meeting access",
        tracking=True,
    )

    meeting_end_datetime = fields.Datetime(
        string="Meeting End Time",
        help="End time for Jitsi meeting access",
        tracking=True,
    )

    is_website_user_allowed = fields.Boolean(
        compute="_compute_is_website_user_allowed",
        string="Can Website User Join Meeting?",
        compute_sudo=True,
    )

    is_meeting_in_future = fields.Boolean(
        compute="_compute_meeting_time_state", store=False
    )
    is_meeting_expired = fields.Boolean(
        compute="_compute_meeting_time_state", store=False
    )

    card_order = fields.Integer(
        string="Report Card Order",
        help="Controls the order in which this subject appears in the report card.",
        default=0,
    )

    @api.depends("meeting_start_datetime", "meeting_end_datetime")
    def _compute_meeting_time_state(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_meeting_in_future = False
            rec.is_meeting_expired = False

            if rec.meeting_start_datetime and rec.meeting_end_datetime:
                if now < rec.meeting_start_datetime:
                    rec.is_meeting_in_future = True
                elif now > rec.meeting_end_datetime:
                    rec.is_meeting_expired = True

    def _compute_is_website_user_allowed(self):
        user = self.env.user
        for channel in self:
            channel.is_website_user_allowed = channel._is_meeting_user_allowed(
                user=user
            )

    def _ensure_jitsi_room_name(self):
        """Set a deterministic and readable Jitsi room name based on the channel and section name."""
        for channel in self:
            vals = {}
            if not channel.jitsi_room_secret:
                vals["jitsi_room_secret"] = secrets.token_hex(8)
            base_name = channel.name or f"channel_{channel.id}"
            section_name = channel.section_id.name if channel.section_id else ""
            room_name = (
                f"{base_name.strip()} - {section_name.strip()}"
                if section_name
                else base_name.strip()
            )
            vals["jitsi_room_name"] = room_name
            channel.sudo().write(vals)

    def _get_meeting_room_slug(self):
        """Return the unguessable meeting room slug used in Jitsi URLs and JWTs."""
        self.ensure_one()
        if not self.jitsi_room_secret:
            self.sudo()._ensure_jitsi_room_name()
        base = self._slugify_room_name(self.jitsi_room_name)
        return f"{base}-{self.jitsi_room_secret}" if self.jitsi_room_secret else base

    def _is_meeting_user_allowed(self, user=None):
        """Check whether a user may join this channel's meeting.

        Allowed users are the channel faculty, members of the channel
        (synced attendees), or students with an accepted enrollment in the
        channel's section for its school year.
        """
        user = user or self.env.user
        for channel in self:
            if user.id == channel.user_id.id:
                return True
            channel_sudo = channel.sudo()
            partner_id = user.partner_id.id
            member_ids = channel_sudo.channel_partner_ids.mapped("partner_id").ids
            if partner_id in member_ids:
                return True
            if channel_sudo.section_id:
                enrolled = self.env["sis.enrollment"].sudo().search_count(
                    [
                        ("user_id", "=", user.id),
                        ("section_id", "=", channel_sudo.section_id.id),
                        ("enrollment_status", "=", "accepted"),
                    ],
                    limit=1,
                )
                if enrolled:
                    return True
        return False

    @api.model
    def create(self, vals):
        channel = super().create(vals)
        channel._ensure_jitsi_room_name()
        return channel

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals or "section_id" in vals:
            self._ensure_jitsi_room_name()
        return res

    def _slugify_room_name(self, name):
        # Lowercase, remove non-alphanumeric, replace with hyphen
        name = name.lower()
        name = re.sub(r"[^a-z0-9]+", "-", name)
        return name.strip("-")

    def action_faculty_join_jitsi(self):
        self.ensure_one()

        if self.user_id != self.env.user:
            raise AccessError("You are not authorized to join this meeting as faculty.")

        self._ensure_jitsi_room_name()

        time_now = int(time.time())
        room = self._get_meeting_room_slug()
        user = self.env.user

        payload = {
            "aud": self.JWT_APP_ID,
            "iss": self.JWT_APP_ID,
            "sub": user.email or f"partner_{user.partner_id.id}",
            "room": room,
            "exp": time_now + 3600,
            "iat": time_now,
            "nbf": time_now,
            "moderator": True,
            "context": {
                "user": {
                    "name": user.name or "Anonymous",
                    "email": user.email or "",
                },
            },
        }

        token = jwt.encode(payload, self.JWT_SECRET, algorithm="HS256")
        jitsi_url = f"https://{self.JITSI_DOMAIN}/{room}?jwt={token}"

        _logger.info(f"[Jitsi][Join][Faculty] Redirecting to: {jitsi_url}")

        return {
            "type": "ir.actions.act_url",
            "url": jitsi_url,
            "target": "new",
        }

    @api.constrains("activity_type_ids")
    def _check_activity_type_weights(self):
        for channel in self:
            weights = [atype.weight for atype in channel.activity_type_ids]

            for w in weights:
                if w < 0 or w > 100:
                    raise ValidationError(
                        _("Each activity weight must be between 0 and 100.")
                    )

            total_weight = sum(weights)
            if total_weight != 100:
                raise ValidationError(
                    _(
                        "The total weight of all activity types must equal 100. Current total: %s"
                    )
                    % total_weight
                )

            type_keys = [
                atype.name for atype in channel.activity_type_ids if atype.name
            ]
            duplicates = set(k for k in type_keys if type_keys.count(k) > 1)
            if duplicates:
                friendly_names = [
                    dict(self.env["sis.activity.type"].SELECTIONS).get(d, d)
                    for d in duplicates
                ]
                raise ValidationError(
                    _("Duplicate activity types are not allowed: %s")
                    % ", ".join(friendly_names)
                )

    @api.constrains("meeting_start_datetime", "meeting_end_datetime")
    def _check_meeting_datetime_range(self):
        for record in self:
            if record.meeting_start_datetime and record.meeting_end_datetime:
                if record.meeting_end_datetime < record.meeting_start_datetime:
                    raise ValidationError(
                        _(
                            "Meeting end time cannot be earlier than the start time.\n"
                            "Please correct the date range."
                        )
                    )


    @api.model
    def action_open_subjects_active_school_year(self):
        action = self.env.ref("obbs_sis.action_sis_subjects").sudo().read()[0]

        active_school_year = self.env.company.active_school_year_id

        ctx = action.get("context") or {}
        if isinstance(ctx, str):
            import ast
            ctx = ast.literal_eval(ctx)

        if active_school_year:
            ctx.update({
                "search_default_school_year_id": active_school_year.id,
                "default_school_year_id": active_school_year.id,
                "active_school_year_id": active_school_year.id,
            })
        else:
            ctx.update({
                "active_school_year_id": False,
            })

        action["context"] = ctx
        action.pop("id", None)
        return action

    def _ensure_exam_activities(self, period_ids=None, only_existing=False):
        """Ensure the three DepEd EXs activities exist for this subject/term.

        For DepEd 2026-format school years each subject/term must have exactly
        one Summative Test 1, one Summative Test 2 and one Term Examination
        with the fixed 30/30/40 split (DO 2026-015, item 6).  Existing
        activities are adopted by best-effort name matching; wrongly-named
        extras under the EXs type are removed.  Returns the number created.

        When ``only_existing`` is True, terms that currently have no EXs
        activity at all are left untouched (used by the data migration so it
        does not force empty EXs activities onto subjects that never had any,
        which would turn a blank report card cell into a 0 → transmuted 60).
        """
        self.ensure_one()
        if (
            not self.school_year_id
            or self.school_year_id.report_card_format != "deped_2026"
        ):
            return 0
        atype = self.activity_type_ids.filtered(
            lambda at: at.name == "quarterly_exam"
        )[:1]
        if not atype:
            return 0

        Period = self.env["sis.period"]
        if period_ids:
            periods = Period.browse(period_ids).exists()
        else:
            periods = Period.search(
                [("school_year_id", "=", self.school_year_id.id)],
                order="start_date, id",
            )

        created = 0
        for period in periods:
            if only_existing and not self._has_exam_activity(period, atype):
                continue
            created += self._ensure_exam_activities_for_period(period, atype)
        return created

    def _has_exam_activity(self, period, atype):
        return bool(
            self.env["sis.activity"].search_count(
                [
                    ("channel_id", "=", self.id),
                    ("period_id", "=", period.id),
                    ("activity_type_id", "=", atype.id),
                ]
            )
        )

    def _ensure_exam_activities_for_period(self, period, atype):
        Activity = self.env["sis.activity"]
        existing = Activity.search(
            [
                ("channel_id", "=", self.id),
                ("period_id", "=", period.id),
                ("activity_type_id", "=", atype.id),
            ],
            order="id",
        )

        assigned = {}
        extras = Activity
        for activity in existing:
            component = activity.exam_component or activity._match_exam_component(
                activity.name
            )
            if component and component not in assigned:
                assigned[component] = activity
            else:
                extras |= activity

        # Drop duplicates / unmapped leftovers before (re)writing components so
        # the uniqueness constraint cannot trip on a stale sibling.
        if extras:
            extras.unlink()

        created = 0
        for component, canonical_name, max_score in Activity.EXAM_COMPONENT_SPECS:
            activity = assigned.get(component)
            if activity:
                vals = {}
                if activity.exam_component != component:
                    vals["exam_component"] = component
                if (activity.name or "").strip() != canonical_name:
                    vals["name"] = canonical_name
                if vals:
                    activity.write(vals)
            else:
                activity = Activity.with_context(
                    sis_skip_exam_autoseed=True,
                    sis_skip_gradebook_autopopulate=True,
                ).create(
                    {
                        "name": canonical_name,
                        "period_id": period.id,
                        "activity_type_id": atype.id,
                        "channel_id": self.id,
                        "max_score": max_score,
                        "exam_component": component,
                    }
                )
                activity._bulk_create_gradebooks_for_enrollments(activity)
                created += 1

        return created

    def action_ensure_exam_activities(self):
        self.ensure_one()
        created = self._ensure_exam_activities()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Summative & Exam Activities"),
                "message": _(
                    "Ensured Summative Test 1, Summative Test 2 and Term "
                    "Examination for every term (%d created)."
                )
                % created,
                "type": "success" if created else "info",
                "sticky": False,
            },
        }

    def action_open_activities(self):
        self.ensure_one()
        action = self.env.ref("obbs_sis.action_sis_activity").sudo().read()[0]

        domain = [("channel_id", "=", self.id)]
        if self.school_year_id:
            domain.append(("school_year_id", "=", self.school_year_id.id))
        action["domain"] = domain

        ctx = action.get("context") or {}
        if isinstance(ctx, str):
            import ast

            ctx = ast.literal_eval(ctx)

        ctx.update(
            {
                "default_channel_id": self.id,
                "default_school_year_id": self.school_year_id.id if self.school_year_id else False,
                "search_default_group_by_activity_type": 1,
                "search_default_school_year_id": self.school_year_id.id if self.school_year_id else False,
            }
        )
        action["context"] = ctx

        # ✅ This is the only required change
        action.pop("id", None)
        return action

    def action_sync_attendees_from_section(self):
        for channel in self:
            if not channel.section_id:
                raise ValidationError(
                    _("Please set a Section before adding attendees.")
                )

            enrollments = channel.section_id.enrollment_ids.filtered(
                lambda e: e.enrollment_status == "accepted"
                and e.user_id
                and e.user_id.partner_id
                and (
                    not channel.school_year_id
                    or e.school_year_id.id == channel.school_year_id.id
                )
            )

            target_partners = enrollments.mapped("user_id.partner_id")
            SlideChannelPartner = self.env["slide.channel.partner"].sudo()

            current_attendees = SlideChannelPartner.search(
                [("channel_id", "=", channel.id), ("member_status", "=", "joined")]
            )
            current_partner_ids = current_attendees.mapped("partner_id").ids
            target_partner_ids = target_partners.ids

            partners_to_add = target_partners.filtered(
                lambda p: p.id not in current_partner_ids
            )
            partners_to_remove = current_attendees.filtered(
                lambda cp: cp.partner_id.id not in target_partner_ids
            )

            if partners_to_add:
                channel._action_add_members(partners_to_add, member_status="joined")
            if partners_to_remove:
                partners_to_remove.sudo().unlink()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _(
                    "Sync complete: Added %d, Removed %d attendee(s) from section."
                )
                % (len(partners_to_add), len(partners_to_remove)),
                "type": "success",
                "sticky": False,
            },
        }

    # def action_sync_attendees_from_section(self):
    #     for channel in self:
    #         if not channel.section_id:
    #             raise ValidationError(
    #                 _("Please set a Section before adding attendees.")
    #             )

    #         enrollments = channel.section_id.enrollment_ids.filtered(
    #             lambda e: e.enrollment_status == "accepted"
    #             and e.user_id
    #             and e.user_id.partner_id
    #         )
    #         target_partners = enrollments.mapped("user_id.partner_id")
    #         SlideChannelPartner = self.env["slide.channel.partner"].sudo()

    #         current_attendees = SlideChannelPartner.search(
    #             [("channel_id", "=", channel.id), ("member_status", "=", "joined")]
    #         )
    #         current_partner_ids = current_attendees.mapped("partner_id").ids
    #         target_partner_ids = target_partners.ids

    #         partners_to_add = target_partners.filtered(
    #             lambda p: p.id not in current_partner_ids
    #         )
    #         partners_to_remove = current_attendees.filtered(
    #             lambda cp: cp.partner_id.id not in target_partner_ids
    #         )

    #         if partners_to_add:
    #             channel._action_add_members(partners_to_add, member_status="joined")
    #         if partners_to_remove:
    #             partners_to_remove.sudo().unlink()

    #     return {
    #         "type": "ir.actions.client",
    #         "tag": "display_notification",
    #         "params": {
    #             "title": _("Success"),
    #             "message": _(
    #                 "Sync complete: Added %d, Removed %d attendee(s) from section."
    #             )
    #             % (len(partners_to_add), len(partners_to_remove)),
    #             "type": "success",
    #             "sticky": False,
    #         },
    #     }
