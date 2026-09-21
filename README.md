# Obbserver School (`obbs_sis`)

A custom Odoo 18 School Information System (SIS) for managing the full lifecycle of a student: enrollment, academic structure, tuition & billing, a DepEd-aligned gradebook with transmuted grading, attendance tracking, character building / conduct ratings, report cards (including the new DepEd Learner's Performance Report for SY 2026-2027), student ID cards, a REST API, and Jitsi video-meeting integration.

- **Version:** 18.0.1.8
- **Category:** Education
- **Author:** OBBS Co. ([obbsco.com](https://obbsco.com))
- **Dependencies:** `base`, `mail`, `contacts`, `website_sale`, `website_slides`, `portal`
- **External Python dependency:** `qrcode` (student ID card QR generation)

---

## Features

### Enrollment & Students

- **Enrollment applications** (`sis.enrollment`) capturing the full DepEd learner profile: names, birth date, gender, PSA/BReN number, LRN, address, parents/guardians, returning-learner status (`balik_aral`), and data-privacy consent.
- Workflow: pending → reviewed → accepted, with status buttons and email notifications.
- **Re-enrollment history chain** (`previous_root_next` links): one-click re-enrollment into a new school year with automatic grade-level advancement, section assignment, and tuition re-matching.
- Auto-creation of portal user accounts on acceptance; automatic generation of tranche invoices.
- Public website enrollment form (`/enroll`) and a full portal experience (`/my/enrollments`): view, update, re-enroll, and delete (while pending) applications.
- **Add Enrollees wizard** for bulk-assigning accepted enrollments to a section and grade level.

### School Structure

- **School Years** (`sis.school.year`): draft / active / closed states; single-active-year-per-company constraint.
  - `report_card_format` field: `deped_2026` (routes to the new DepEd template) or `legacy`.
- **Initialize School Year wizard**: rolls a new school year forward by copying sections, date-shifted grading periods, and tuition plans (with tranches) from a previous year; can auto-activate the target year.
- **Grade Levels** (`sis.grade.level`): `id_type` (preschool / elementary / highschool); `next_grade_level_id` for auto-advancement.
  - `report_card_type` field: `deped` (routes to the DepEd template), `preschool`, or `legacy`.
- **Sections** (`sis.sections`): bound to grade level + school year, with an assigned advisor.
- **Grading Periods** (`sis.period`), e.g. quarters Q1–Q4 or trimester terms, validated within the school year.
- **Subjects**: modelled on Odoo's eLearning `slide.channel`, with subject codes, composite-subject support (e.g. MAPEH), activity types, and report-card ordering.
- Closed school years make setup records read-only for non-admin users.

### Tuition & Billing

- **Payment Plans** (`sis.payment.plan`), **Tuition Fees** (`sis.tuition`) per grade level + payment plan + school year, and **Tuition Tranches** (`sis.tuition.tranche`) defining the installment schedule (amount + due date).
- On acceptance, one customer invoice (`account.move`) is generated per tranche, linked to the enrollment.

### Gradebook & Grading

- **Activities** (`sis.activity`): DepEd assessment components (Written Works, Performance Tasks, Quarterly Exam / Summative Test) with weights that must total 100% per subject.
- **Gradebook** (`sis.gradebook`): per-student, per-activity scores, auto-populated from the section's accepted enrollments, with percentage and weighted scores.
- **Transmutation table** (`sis.transmutation.table`): the seeded 41-row DepEd-aligned table converting Initial Grades (0–100) to Transmuted Grades (60–100), used by all report generators.
- **General Average** computation: 3-decimal, round-half-up; composite-subject averaging supported.

### Reports (QWeb PDF + Excel Exports)

#### Report Card (`report.obbs_sis.report_card_template`)

Bound on `sis.enrollment`. Paper format: **A4 Landscape, 12.7 mm (½-inch) margins** (`paperformat_a4_landscape_custom`).

Routing (three-way dispatch):

| Condition | Template |
|---|---|
| `is_preschool` on grade level | `report_card_template_preschool` |
| `school_year.report_card_format == 'deped_2026'` **and** `grade_level.report_card_type == 'deped'` | `report_card_template_deped` |
| Everything else | `report_card_template_regular` |

**DepEd Learner's Performance Report** (SY 2026-2027, Grade 2–JHS / SHS):

- **Page 1 — Cover Letter**: occupies the right half of the page (bordered box). Contains school name, logo, "LEARNER'S PERFORMANCE REPORT", School Year, a Dear Parents/Guardians message, and the School Principal + Teacher signature block.
- **Page 2 — Report Card** (two-column layout):
  - *Left column*: DepEd header (Republic of the Philippines → Dept. of Education → Region IV-A CALABARZON → Schools Division Office of Rizal → Taytay, Rizal); student info (Name / Age / Sex / Birthday / Grade / Section / LRN); **LEARNING PROGRESS AND ACHIEVEMENT** table (Learning Areas × Term 1 / Term 2 / Term 3 + Final Grade + Remarks (PASSED/FAILED, threshold ≥75), General Average row); **PERFORMANCE DESCRIPTORS** legend (Grading Scale | Descriptors | Remarks: 90–100 Advancing Passed … 0–64 Emerging Failed).
  - *Right column*: **ATTENDANCE** table (always shows all months June–April with a TOTAL column; rows: No. of School Days / Days Present / Days Absent / Times Tardy — defaults to 0 when no monthly summaries exist); **TEACHER'S COMMENTS / REMARKS** (per term); **PARENT'S / GUARDIAN'S SIGNATURE**; **CERTIFICATE OF TRANSFER**.
- Data provider: `ReportCardExport` in `report_card_generator.py`, which pre-computes all grades, attendance, comments, and term numbers for QWeb.

#### Student ID Card (`report.obbs_sis.student_id_report`)

QWeb PDF bound on `sis.enrollment`. Layouts differ by `id_type` (preschool / elementary / highschool), with a photo, a QR code encoding the enrollment ID, LRN, and an ESC logo for Education Service Contracting scholars.

#### Excel Exports

- **Progress Report** and **Rating Sheet** (xlsxwriter): per subject/period and per section/period, including transmuted grades and advisor comments. Launched from **Reports** wizards.

### Attendance

- **Attendance logs** (`sis.student.attendance.log`) with `school_in/out` and `class_in/out` types.
- **School Days reference** (`sis.attendance.school_days`): expected number of school days per month per school year.
- **Monthly summaries** (`sis.attendance.monthly_summary`): present / absent / tardy days, updated automatically by a daily cron job (`ir_cron_update_monthly_attendance`).

### Character Building / Conduct

- **Character Behaviors** (`sis.character.behavior`): seeded with DepEd core values (Maka-Diyos, Makatao, Makakalikasan, Makabansa) and preschool groups.
- **Character Ratings** (`sis.character.rating`) per student / period / behavior with AO/SO/RO/NO legends (elementary) and O/VS/S/MS/NI (preschool).
- **Advisor Comments** (`sis.rating.comment`) per student and grading period.

### REST API (HMAC-SHA256 Token Auth)

Custom HMAC tokens (secret in `ir.config_parameter` key `sis.secret_key`, default `default-secret`; access tokens valid 7 days, refresh tokens 14 days).

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

- Route `/jitsi/join_web/<channel_id>` redirects enrolled users to a scheduled Jitsi meeting with a signed non-moderator JWT; faculty receive a moderator JWT.
- A "Meeting Room" tab on the course page shows the schedule and join button.
- Meeting exclusivity enforced via JWT user identity (`sub`); for full enforcement, configure the Jitsi server with `enableAuth` / JWT auth (`appId: "odoo-sis"`).

### Email Notifications

- Enrollment received / enrollment accepted mail templates, accessible via an "SIS Email Templates" menu.

---

## Roles & Permissions

Hierarchical security groups (`sis_groups.xml`):

- **SIS Faculty** → **SIS Registrar** → **SIS Admin**

Portal users see only their own enrollments; faculty see only their own subjects; closed school years are read-only for non-admins. Transmutation table is faculty read-only / registrar-admin full.

---

## Installation (Docker)

### Prerequisites

- Docker 20+ with Docker Compose (recommended for production).
- Odoo 18 and PostgreSQL 15 Docker images.
- The `qrcode` Python package (installed in step 3).

### Quick-Start (docker run)

1. **PostgreSQL:**

   ```bash
   docker run -d --name odoo-db \
     -e POSTGRES_DB=odoo \
     -e POSTGRES_USER=odoo \
     -e POSTGRES_PASSWORD=odoo \
     -v odoo-db-data:/var/lib/postgresql/data \
     postgres:15
   ```

2. **Odoo** (mount the directory containing `obbs_sis/` into `/mnt/extra-addons`):

   ```bash
   docker run -d --name odoo --link odoo-db:db \
     -p 8069:8069 \
     -v /path/to/parent-dir:/mnt/extra-addons \
     -v odoo-data:/var/lib/odoo \
     -e HOST=db -e USER=odoo -e PASSWORD=odoo -e DBNAME=odoo \
     odoo:18
   ```

   If your parent directory contains other addons, Odoo scans all sub-directories with a `__manifest__.py`. If port 8069 is occupied, add `--no-http` when running shell commands against this instance.

3. **Install `qrcode`** inside the container:

   ```bash
   docker exec -u root odoo pip install qrcode
   ```

4. Open `http://localhost:8069`, create the database (or log in), enable developer mode, go to **Apps**, and install **Obbserver School** (search `obbs_sis` with the Apps filter active).

Seed data (transmutation table, character behaviors, paper format, cron job, mail templates) is installed automatically on first load.

---

## Configuration

After installation:

- **Company settings** (`res.company` → School Setting tab): set the **Active School Year** (the default year used across all SIS operations) and **Registrar Email** (enrollment emails).
- **School Year report format**: on the School Year form, set `report_card_format` to `deped_2026` to activate the DepEd Learner's Performance Report template for that year.
- **Grade Level report type**: on the Grade Level form, set `report_card_type` to `deped` to route grades through the DepEd template.
- **API secret**: `Settings → Technical → System Parameters` → key `sis.secret_key` (default `default-secret`). **Change this in production.**
- **Subjects**: each `slide.channel` needs a subject code and activity types whose weights total 100%.
- **Tuition**: create payment plans, then tuition fees per grade level + plan + year with tranches.
- **School Days**: record the expected monthly school days per school year for attendance summaries.

---

## Main Menus

**SIS** root menu → Enrollment, Students, Faculty, Subjects, Reports (Progress Report, Rating Sheet, Attendance Logs), Configurations (School Year, Periods, Grade Levels, Sections, Transmutation Table, School Days, Payment Plans, Tuition Fees, Tuition Tranches, Character Behaviors, Email Templates).

---

## Development Test Data

A test-data populator (`scripts/populate_test_data.py`) creates a realistic gradebook for SY 2026-2027 (three grading periods / trimester terms), three target students, and predictable scores:

| Student | Grade | LRN | Expected Outcome |
|---|---|---|---|
| OLAVIDES, CADENCE MIGUEL | 2 | 403044240004 | All PASSED, Final ~95 |
| SAMERA, KENDRA GWYNETH | 5 | 403129210011 | All PASSED, Final ~90 |
| BARLAAN, KLINE BRAVEBEN | 10 | 425643160042 | TLE FAILED (72), overall ~83 |

Run from inside the Odoo shell:

```bash
odoo-bin shell -d <db_name> --no-http < scripts/populate_test_data.py
```

The script is idempotent: rerunning creates no duplicate records.

---

## Migrations

Upgrade-safe migrations:

| Version | What it does |
|---|---|
| `18.0.1.1` | Backfills `school_year_id`, `company_id`, and `state` on existing records. |
| `18.0.1.3` | Adds the enrollment re-enrollment history chain (`previous/root/next` fields). |
| `18.0.1.4` | Pre-migration: adds `previous_enrollment_id` / `root_enrollment_id` columns if missing. Post-migration: backfills history roots (grouped by LRN, then PSA). |
