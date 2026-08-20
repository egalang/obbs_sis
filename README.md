# Odoo Custom Module: `obbs_sis`

**OBBServer School** is a custom Odoo 18 School Information System (SIS) application for managing school operations. It covers the full lifecycle of a student: online and portal enrollment, academic structure (grade levels, sections, subjects, grading periods), tuition & billing, a DepEd-aligned gradebook with transmuted grading, attendance tracking, character building / conduct ratings, report cards, student ID cards, and a REST API plus Jitsi video-meeting integration for parents, students, and faculty.

- **Version:** 18.0.1.8
- **Category:** Education (Application)
- **Dependencies:** `base`, `mail`, `contacts`, `website_sale`, `website_slides`, `portal`
- **Python dependency:** `qrcode` (used to generate the QR code on student ID cards)

## Features

### Enrollment & Students
- **Enrollment applications** (`sis.enrollment`) capturing the full DepEd learner profile: names, birth date, gender, PSA/BReN number, LRN (Learner Reference Number), address, parents/guardians, returning-learner info (`balik_aral`), and Data Privacy consent.
- Workflow **pending → reviewed → accepted**, with status buttons and automatic email notifications.
- **Re-enrollment history chain** (`previous/root/next` links): one-click re-enrollment into a new school year with automatic grade-level advancement, section assignment, and tuition re-matching.
- Auto-creation of portal user accounts on acceptance and automatic generation of tranche invoices.
- Public **website enrollment form** (`/enroll`) and a full **portal experience** (`/my/enrollments`): view, update, re-enroll, and delete (while pending) applications.
- **Add Enrollees wizard** to bulk-assign accepted enrollments to a section and grade level.

### School Structure
- **School Years** (`sis.school.year`) with draft/active/closed states and a single-active-year-per-company constraint.
- **Initialize School Year wizard**: rolls a new school year forward by copying sections, date-shifted grading periods, and tuition plans (with tranches) from a previous year; can auto-activate the target year.
- **Grade Levels** (`sis.grade.level`) with `id_type` (preschool/elementary/highschool) and next-grade linkage for auto-advancement.
- **Sections** (`sis.sections`) bound to grade level + school year, with an assigned advisor.
- **Grading Periods** (`sis.period`), e.g. quarters Q1–Q4, validated within the school year.
- **Subjects** modeled on Odoo's eLearning `slide.channel`, with subject codes, composite-subject support (e.g. MAPEH), activity types, and report-card ordering.
- Closed school years make setup records read-only for non-admin users.

### Tuition & Billing
- **Payment Plans** (`sis.payment.plan`), **Tuition Fees** (`sis.tuition`) per grade level + payment plan + school year, and **Tuition Tranches** (`sis.tuition.tranche`) defining the installment schedule (amount + due date).
- On acceptance, one customer invoice (`account.move`) is generated per tranche, linked to the enrollment; invoice and payment records carry the enrollment and school year context.

### Gradebook & Grading
- **Activities** (`sis.activity`) with DepEd assessment components (Written Works, Performance Tasks, Quarterly Exam) and weights that must total 100% per subject.
- **Gradebook** (`sis.gradebook`): per-student per-activity scores, auto-populated from the section's accepted enrollments, with percentage and weighted scores.
- **Transmutation table** (`sis.transmutation.table`): the seeded DepEd-aligned 41-row table converting Initial Grades (0–100) to standardized Quarterly Grades (60–100), used by all report generators.
- **General Average** computation (3-decimal, round-half-up) and composite-subject averaging.

### Reports (QWeb PDF + Excel exports)
- **Report Card** (report.obbs_sis.report_card_template): A4 landscape PDF with periodic ratings, final rating + remarks (PASSED/FAILED threshold 75), attendance record, character building by core values, and a separate **Preschool** progress-report layout.
- **Student ID Card** (report.obbs_sis.student_id_report): physical ID card front/back per `id_type` template, with student photo, a **QR code encoding the enrollment ID** (`qrcode`), LRN, and an ESC logo for Education Service Contracting scholars.
- **Progress Report** and **Rating Sheet** Excel exports (xlsxwriter) per subject/period and per section/period, including transmuted grades and advisor comments.

### Attendance
- **Attendance logs** (`sis.student.attendance.log`) with `school_in/out` and `class_in/out` types.
- **School Days reference** (`sis.attendance.school_days`): expected number of school days per month per school year.
- **Monthly summaries** (`sis.attendance.monthly_summary`) for present/absent/tardy days, updated automatically by the daily cron job (`ir_cron_update_monthly_attendance`).

### Character Building / Conduct
- **Character Behaviors** (`sis.character.behavior`) seeded with DepEd core values (Maka-Diyos, Makatao, Makakalikasan, Makabansa) and preschool groups (Work/Study Habits, Social Skills, Motor Skills, Spiritual Performance).
- **Character ratings** (`sis.character.rating`) per student/period/behavior with AO/SO/RO/NO legends (elementary) and O/VS/S/MS/NI (preschool).
- **Advisor comments** (`sis.rating.comment`) per student and grading period; generators create blank rows across all periods on demand.

### REST API (HMAC token auth)
Custom HMAC-SHA256 signed tokens (secret stored in `ir.config_parameter` `sis.secret_key`, default `default-secret`; access tokens valid 7 days, refresh tokens 14 days). Endpoints:

| Route | Method | Description |
|---|---|---|
| `/api/auth/login` | POST | Authenticate and obtain access/refresh tokens |
| `/api/auth/refresh` | POST | Exchange a refresh token for a new access token |
| `/api/auth/whoami` | GET | Current user identity and system flags |
| `/api/attendances` | GET | Paginated attendance log list with filters |
| `/api/attendance/log` | POST | Record an attendance log (internal users) |
| `/api/attendances/notify` | GET | Parent notification feed; returns and marks un-notified `school_in/out` logs |
| `/api/students/enrollments` | GET | Paginated enrollment listing for device/app pickers |

### Jitsi Video Meetings
- Website route `/jitsi/join_web/<channel_id>` redirects enrolled users to a scheduled Jitsi meeting with a signed non-moderator JWT; faculty receive a moderator JWT.
- A **"Meeting Room"** tab on the course page shows the schedule and join button.
- **Meeting exclusivity**: only enrolled students (or the course faculty) can obtain a meeting link. The meeting room name is appended with a per-channel random secret so it cannot be guessed from the course name, and each issued JWT is user-specific (`sub` = user identity) instead of a shared wildcard. For full enforcement, the Jitsi server must validate the JWT — configure it with `enableAuth`/JWT auth (`appId: "odoo-sis"` and `appSecret` matching the module's `JWT_SECRET`), otherwise anyone holding a generated link (even without the token) can still enter the open room.

### Email Notifications
- Enrollment received / enrollment accepted mail templates with the school's contact info and registrar email; accessible via an "SIS Email Templates" menu.

## Roles & Permissions

Hierarchical security groups (`sis_groups.xml`): **SIS Faculty** → **SIS Registrar** → **SIS Admin**. Portal users only see their own enrollments; faculty see only their own subjects; closed school years are read-only for non-admins. Transmutation table is faculty read-only / registrar-admin full.

## Installation (Docker-based Deployment)

### Prerequisites

- Docker 20+ installed on your system.
- Odoo 18 and PostgreSQL 15 Docker images.
- The module requires the Python package `qrcode` (see step 3).

### Steps to Install

1. **Start the PostgreSQL container**:

   ```bash
   docker run -d \
     --name odoo-db \
     -e POSTGRES_DB=odoo \
     -e POSTGRES_USER=odoo \
     -e POSTGRES_PASSWORD=odoo \
     -v odoo-db-data:/var/lib/postgresql/data \
     postgres:15
   ```

2. **Start the Odoo container** (run from the directory that contains the `obbs_sis` folder, e.g. `addons/`):

   ```bash
   docker run -d \
     --name odoo \
     --link odoo-db:db \
     -p 8069:8069 \
     -v "$PWD/obbs_sis:/mnt/extra-addons" \
     -v odoo-data:/var/lib/odoo \
     -e HOST=db \
     -e USER=odoo \
     -e PASSWORD=odoo \
     -e DBNAME=odoo \
     odoo:18
   ```

3. **Install the `qrcode` Python dependency** inside the Odoo container (required to generate student ID card QR codes):

   ```bash
   docker exec -u root odoo pip install qrcode
   ```

4. Open `http://localhost:8069`, create the `odoo` database (or log in), enable developer mode, go to **Apps**, and install the **Obbserver School** module (set the Apps filter to "Apps" and search for `obbs_sis`).

### Key Points

1. **PostgreSQL container**: environment variables set the database name, user, and password, persisted in the `odoo-db-data` volume.
2. **Odoo container**: linked to the database container; the module is mounted into `/mnt/extra-addons` (the official image's extra addons path); `odoo-data` persists the filestore.
3. **Module installation**: install via the Odoo interface once the containers are running. On first load, seed data (transmutation table, character behaviors, paper format, cron, mail templates) is installed automatically.

Note: this uses `docker run` (with the legacy `--link`) for a manual setup. Prefer **Docker Compose** with a custom network and a `requirements.txt`/custom image for production.

## Configuration

After installation, configure:

- **Company settings** (`res.company` → *School Setting* tab): set the **Active School Year** (the default year used across all SIS operations) and **Registrar Email** (used on enrollment emails). The active school year is also set from the School Year form's "Set Active" button.
- **API secret**: `Settings → Technical → System Parameters` → key `sis.secret_key` (default `default-secret`). **Change this in production** — it signs all API tokens.
- **Subjects**: each `slide.channel` needs a subject code and activity types whose weights total 100%.
- **Tuition**: create payment plans, then tuition fees per grade level + plan + year with tranches (these drive auto-invoicing on acceptance).
- **School days reference**: record the expected monthly school days per school year for accurate attendance summaries.

## Main Menus

- **SIS** root menu → **Enrollment**, **Students**, **Faculty**, **Subjects**, **Reports** (Progress Report, Rating Sheet, Attendance Logs), **Configurations** (school years, periods, grade levels, sections, transmutation table, school days, payment plans, tuitions, tranches, character behaviors, email templates).

## Migrations

Upgrade-safe migrations are included: `18.0.1.1` backfills school-year/company/state on existing records; `18.0.1.3`/`18.0.1.4` add the enrollment re-enrollment history chain and backfill history roots (grouped by LRN, then PSA).
