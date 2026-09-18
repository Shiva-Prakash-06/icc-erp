# ICC/IGP Automation and Simplification Plan

## 1. Product rules

- Make uploaded artifacts the primary input. Users should confirm inferred results, not retype document content.
- Use this inference order: existing manual correction → structured spreadsheet/CSV → document content → filename/folder context → system default.
- Never overwrite a manually corrected value during re-import without explicit confirmation.
- Remove partner, closure, governance, recruitment, attendance-verification, document-control, and extended person fields from routine project forms.
- Infer the current user as owner, academic year from dates, campus from user/default campus, unit from the ICC/IGP entry point, and category/type from the source.
- Derive display status from dates: future = Planned, current = Active, past = Completed. Retain cancellation/archive as exceptional administrative actions.
- Infer closure summaries from the event/program details and report body. Closure must not block completion.
- Preserve RBAC, privacy controls, audit history, CSRF, and restricted-document handling even though governance forms are removed.
- Keep project dates as the overall envelope and schedule rows as detailed occurrences. Do not create a duplicate `MAIN` session for IGP programs with an itinerary.
- Keep binaries in Google Drive; store only IDs, metadata, provenance, and structured records in the application database.

## 2. Imports, storage, and inference

### IGP itinerary

- Add a project-scoped `Itinerary` bulk importer accepting `.xlsx`, `.csv`, and extensionless CSV files such as `references/Summer School Itinerary`.
- Support both:
  - the supplied wide layout: one date row with time-slot, breakfast, lunch, and dinner columns;
  - a canonical future layout: `Date`, `Start Time`, `End Time`, `Activity`, `Venue`, `Type`, `Breakfast`, `Lunch`, `Dinner`.
- Infer the program title from the first title row, project start/end from the first and last valid dates, default venue from footer notes, and session type from activity text.
- Convert each nonblank activity into a `ProjectSession`; merge adjacent time slots containing the same normalized activity.
- Embedded times such as “11:00 AM–12:00 Noon” override column times. Arrivals, departures, travel, holidays, and unscheduled excursions become all-day entries instead of receiving fake times.
- Ignore blank cells and `-`. Preserve meal availability, footer notes, class venues, and duration notes in the active itinerary revision metadata.
- Add an `ItineraryRevision` record containing the source document, checksum, parser version, inferred metadata, warnings, and active flag. Link derived sessions to the revision with stable source keys.
- Re-import idempotently. A new file creates a new active revision, updates matching imported sessions, adds new ones, and deactivates removed imported sessions. Sessions with attendance are retained as historical records.
- Render the active itinerary as a spacious day-by-day timeline with meal indicators and concise venue notes. Use a compact calendar/table alternative on desktop and stacked day cards on mobile.

### IGP repository documents

- Add multi-file project upload with automatic Drive storage and categorization.
- Map the reference patterns as follows:
  - `UC Screen Flyer.pdf` → Screen Banner
  - `Lamppost.pdf` → Lamppost
  - `Copy of Welcome notes .pdf` → Welcome Notes
  - `UC students Certs.pdf` → Participant Certificates
  - `UC Buddies Certs.pdf` → Buddy Certificates
  - `Daywise Buddies - Summer School.csv` → Daywise Buddy Allocation
  - `UC Inaug Schedule.pdf` → Inauguration Schedule
  - `UC Valedictory Schedule.pdf` → Valedictory Schedule
  - `Summer School Claimsheet.pdf` → Attendance Claim
  - `Summer School Buddies Allocation.csv` → Buddy Allocation source
  - `_Summer School- Check List.xlsx` → Operational Checklist
- Accept PDF, DOCX, XLSX, CSV, PPTX, JPG, JPEG, and PNG, with a 100 MiB total-file limit.
- Implement resumable 8 MiB chunk uploads proxied to Google Drive. Store short-lived upload-session state in Redis in production and memory in development.
- Configure `GOOGLE_DRIVE_REPOSITORY_ROOT_ID`; automatically create one folder per project.
- Upgrade Drive access from metadata-only to the minimum read/write scopes required for upload, download, and native Google-file export. Never change existing sharing permissions automatically.
- Continue accepting pasted Drive links as an alternative.
- Infer document title, category, MIME type, classification, uploader, project, and availability. Do not show document-control fields.
- Default classification:
  - Public: screen banners, lampposts, invitation posters, and promotional assets.
  - Restricted: buddy allocations, daywise allocations, attendance claims, welcome notes containing credentials/contact data, and reimbursement data.
  - Internal: certificates, ceremony schedules, reports, scripts, presentations, checklists, and uncategorized program material.
- Replace document approval states in the normal UI with computed availability: Available, Missing, or Inaccessible. Retain legacy approval/waiver columns read-only for compatibility.
- Deduplicate by project plus Drive ID/checksum. Uploading a changed replacement automatically supersedes the prior record without asking for version metadata.
- Extract only useful metadata—document date, institution, participant names, and detected category. Do not persist full extracted document text when the Drive file remains authoritative.

### Buddy allocation

- Add a project-scoped buddy-allocation importer accepting the supplied headers `SNo`, `International Student`, `Christ Buddy`, and `Contact`, plus common header aliases.
- Ignore `SNo`; infer project and assignment dates from the selected IGP.
- Match existing people by registration number or email when supplied. Otherwise match exact normalized names within the same project and role; ambiguous matches remain staged for correction.
- Create a minimal `Person` for missing international participants and enroll them as participants without creating login accounts.
- Create a minimal `Person`, project team assignment, `User`, project-scoped `BUDDY` role assignment, and `BuddyAssignment` for missing buddies.
- Allow account email to be nullable. Generate a unique username from the buddy’s name, adding a stable numeric/contact suffix on collision.
- Use a shared default password from the required `AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD` production secret. Never hardcode, log, return through APIs, or store the plaintext outside configuration.
- Mark every provisioned account Approved and `needs_password_reset=True`; first login must force a policy-compliant password change.
- Show/export generated usernames after commit so the coordinator can distribute them with the separately communicated default password.
- Treat identical participant and buddy names as separate role-scoped identities unless a stronger identifier proves they are the same person.
- Preserve overlap and duplicate-pair protections. Errors appear in the staging preview and do not partially commit.

### Reimbursements

- Add a lightweight `ReimbursementEntry` entity with `project_id`, `date`, `party_name`, `bill_number`, `amount`, `particular`, and `status`.
- Do not store `S. No`; derive it from the displayed/exported ordering.
- Infer currency as INR.
- Accept XLSX/CSV with exactly: `S. No`, `Date`, `Party Name`, `Bill Number`, `Amount`, `Particular`, `Status`.
- Ignore `S. No` on import. Default blank status to `Pending`; otherwise preserve the supplied status as trimmed text.
- Provide bulk upload, CSV/XLSX export, inline status editing, and a collapsed manual “Add reimbursement” form. Do not introduce reimbursement approval or payment-ledger workflows.

### ICC sources and attendance

- Keep `2026 ICC EVENTS REPORT SUMMARY.xlsx` as the canonical ICC event import.
- Infer event code, ICC unit, Events wing, academic year, category, dates, times, venue, audience, status, and one `MAIN` event session.
- Turn poster, backdrop, programme, photo, and report links into categorized repository records automatically.
- Add event-folder ingestion that attaches Coffee Meet & Greet-style files to the matching event using normalized title and date.
- Parse the `STU LIST` volunteer format from `Final Volunteer List - Coffee Meet & Greet - Sheet1 (1).xlsx`.
- Use name and registration number to create/match people and team assignments. Ignore programme/course, student type, and section/group headings.
- Map attendance values case-insensitively:
  - Present: `Present`, `P`, `Yes`, `1`, `✓`
  - Absent: `Absent`, `A`, `No`, `0`
  - Blank: create no attendance record
- Attach imported attendance to the event’s `MAIN` session with `verified_by_id` and `verified_at` unset. Verification remains an in-application action.
- Import named guests only when the guest sheet contains actual rows; do not create accounts for guests or parents.
- Infer actual reach in this order: explicitly labelled report total → complete guest-attendance roster → present session attendance → blank. Do not treat a volunteer-only roster as total event reach.

### Import staging and provenance

- Add project-scoped import types: `itinerary`, `buddy_allocations`, `reimbursements`, `icc_event_folder`, and `icc_volunteer_attendance`.
- Every import follows upload → inference preview → commit. Only unparseable dates/times, ambiguous identities, conflicting project matches, or invalid money values require intervention.
- Store the authoritative source in Drive and keep a compact `ImportBatch` manifest with project, document, checksum, parser version, row counts, warnings, and target IDs.
- Retain full staged row JSON only until successful commit. After commit, retain full details only for rejected/ambiguous rows and compact provenance for successful rows.
- Use the supplied references as parser and visual-behaviour examples, not as automatically seeded production data. Create sanitized fixtures for committed tests.

## 3. Reporting and UI simplification

### Complete ICC report generation

- Replace the flattened key/value report as the primary user-facing export with an assembled PDF report.
- Select the latest available `Event Report` document as the authoritative body. Convert DOCX/PPTX to PDF and preserve its paragraphs, tables, embedded images, signatures, layout, and authorship.
- If the source is already PDF, include its pages unchanged.
- Append relevant testimonial documents and programme/schedule pages. Avoid duplicating images already embedded in the authoritative report.
- If no authoritative event report exists, generate a concise report from event metadata, schedule, attendance/reach, and available repository evidence.
- Fetch Drive binaries only during report generation, use temporary storage, enforce MIME/size/time limits, and delete temporary files immediately afterward.
- Store report snapshots with included document IDs, Drive modified times/checksums, inferred metrics, and source record IDs so exports are reproducible.
- Add a report preflight endpoint returning dependencies as `included`, `missing`, `inaccessible`, or `unsupported`.
- The download UI must show missing dependencies outside the report and offer “Download available report anyway.” The resulting download is a PDF only; missing items are not inserted into the PDF.
- Require an explicit `allow_incomplete=1` retry after the warning, but treat it as acknowledgement rather than approval.
- Restricted documents must never be embedded in a public export or exposed to a user without the existing sensitive-link permission.
- Keep legacy XLSX/DOCX snapshot exports available through the API for compatibility, but make “Complete PDF report” the visible UI action.

### Lightweight application structure

- Keep the Flask/Jinja server-rendered architecture and small JavaScript islands; do not introduce a SPA.
- Replace the six-step setup wizard with direct source actions:
  - `Import ICC event summary`
  - `Create IGP from itinerary`
  - `Upload program/event documents`
  - `Create manually`
- Manual creation asks only for title and start/end date. Unit comes from the chosen entry point; campus, year, type, category, owner, code, and status are inferred. Venue and audience live under an optional “More details” disclosure.
- Use one context-sensitive project page:
  - IGP: Overview, Itinerary, Buddies, Files, Reimbursements, Report
  - ICC: Overview, Attendance, Files, Report
- Hide empty specialist modules under “More” rather than presenting tasks, checklists, risks, budgets, operational requests, feedback, and legacy governance simultaneously.
- Remove lifecycle-transition, publication, document-decision, waiver, recruitment, and closure-summary forms from routine project screens. Keep exceptional cancellation/archive and public publishing controls restricted to administrative areas.
- Make each section show a short summary and one primary action. Put import previews and long tables on dedicated pages.
- Use progressive disclosure for optional fields, 44 px touch targets, visible labels, inline validation, responsive stacked layouts, and restrained status colour.
- Increase whitespace, use a consistent content width, remove the projects card/board/table switcher, and provide one searchable project list with concise cards/rows.
- Hide technical provenance and inferred defaults by default; expose them in a compact “Source details” disclosure for troubleshooting.

## 4. Application interfaces and migration

- Add project-scoped endpoints/API equivalents for itinerary import, buddy-allocation import, reimbursement import/export, ICC attendance import, report preflight, and resumable document upload.
- Add a new Alembic migration rather than modifying an existing historical migration.
- Migration changes:
  - make `users.email` nullable while keeping non-null emails unique;
  - add `ItineraryRevision`;
  - add itinerary revision/source key, all-day, active, and import provenance fields to `ProjectSession`;
  - add `ReimbursementEntry`;
  - add project/source-document references to import batches;
  - add document checksum/uploader metadata needed for upload deduplication;
  - add optional source-import linkage to buddy assignments.
- Backfill effective project status from dates for ordinary projects, preserving Cancelled and Archived.
- Stop treating closure summary, document approval, or checklist completion as completion blockers.
- Existing IGP `MAIN` sessions are retained until an itinerary is committed. At that point, deactivate only an inferred `MAIN` session with no attendance or dependent records.
- Do not destructively remove legacy governance, approval, publication, or document-control columns in this release; stop requesting/writing them in normal flows and retain them for compatibility and privacy safeguards.
- Preserve unrelated changes in the current dirty worktree.

## 5. Tests and acceptance criteria

- Parser tests must confirm:
  - the extensionless Summer School itinerary is recognized as CSV;
  - all 29 dated itinerary days are represented;
  - repeated adjacent activity cells merge correctly;
  - embedded times override column times;
  - meals, footer venues, all-day travel, arrivals, holidays, and departures render correctly;
  - re-import is idempotent and does not delete sessions with attendance.
- Buddy tests must import all 19 supplied allocation rows, provision missing buddy accounts with project-scoped roles, handle the `Ben`/`Ben` role collision safely, force first-login password reset, and never expose the configured default password.
- Document tests must classify every named IGP reference correctly, upload in chunks, deduplicate identical files, supersede changed files, reject executable/macro files, and enforce restricted access.
- Reimbursement tests must validate dates and nonnegative numeric amounts, ignore imported serial numbers, default blank status, preserve supplied status, and round-trip CSV/XLSX exports.
- ICC tests must import all event-summary rows, create one event session per event, attach evidence links, parse volunteer attendance variants, leave blank attendance untouched, and keep imported attendance unverified.
- Report tests must verify the Coffee Meet & Greet DOCX body and all five embedded images survive PDF assembly, testimonials can be appended, inaccessible dependencies appear only in preflight/UI warnings, and incomplete download requires acknowledgement.
- UI/E2E tests must cover mobile and desktop import flows, keyboard navigation, focus after validation errors, empty states, file-upload progress, light project pages, and no horizontal overflow.
- Run the full Python test suite, API/RBAC/security tests, migration reconciliation, Playwright workflows, accessibility checks, and visual snapshots before handoff.

### Locked assumptions

- Google Drive is the authoritative binary repository.
- Direct uploads support up to 100 MiB through resumable chunks.
- Buddy accounts use a shared secret-managed default password and mandatory first-login reset.
- Email is optional only for provisioned accounts; ordinary self-registration still requires email.
- Report downloads use PDF plus an external UI warning for missing dependencies.
- Partner institution and capacity remain optional and blank when not inferable.
- Public publishing remains a separate restricted safety control; imported content is not automatically made public.
