# ICC/OIA ERP Production Upgradation and Implementation Plan

**Document version:** 1.0  
**Status:** Approved implementation baseline  
**Prepared:** 16 July 2026  
**Product:** ICC/OIA Operations Suite  
**Authoritative format:** This Markdown document. The matching DOCX is the stakeholder distribution copy.

## 1. Executive summary

The International Christite Community (ICC) and the Office of International Affairs (OIA) need one authoritative operational system for planning, delivering, governing, and learning from ICC activities and India Gateway Program (IGP) engagements. The system must support the distinct operating models of the two wings: ICC retains annual leadership and associate teams, while IGP assembles a different operational team for each incoming program.

The recommended product direction is to upgrade `icc-platform-2` into a modular OIA Operations Suite. A rewrite is not justified: v2 already provides the stronger interaction model and visual foundation. The production build will retain server-rendered Flask, Jinja, and Bootstrap, while replacing its demonstrator assumptions with a PostgreSQL data model, formal migrations, scoped authorization, auditable workflows, structured imports, and production infrastructure on Google Cloud Platform (GCP).

The first implementation milestone is a demonstrator, explicitly labelled **“Demonstrator—Not Production.”** Production approval follows hardening, migration rehearsals, an ICC pilot, an IGP pilot, and approval by the product owner, an OIA faculty owner, one ICC head, and one IGP head.

### 1.1 Locked decisions

- Upgrade `icc-platform-2`; do not rewrite the product.
- Use a modular Flask/Jinja/Bootstrap application with PostgreSQL and formal migrations.
- Target GCP: Cloud Run, Cloud SQL for PostgreSQL, Secret Manager, Cloud Tasks, Cloud Scheduler, and Cloud Monitoring. Cloud Run provides managed HTTPS container hosting and autoscaling; Cloud SQL supports regional high availability and automated recovery options. See [Cloud Run](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run), [Cloud SQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability), and [Secret Manager](https://docs.cloud.google.com/secret-manager/docs/creating-and-accessing-secrets).
- Retain platform-managed accounts initially. Build an identity-provider adapter so a CHRIST directory or Google SSO can replace authentication later without changing operational records.
- Store sensitive IGP requirement status and restricted Google Drive references, not passport, visa, or C-Form files.
- Build a three-day demonstrator, not a production release.
- Start production with a fresh database. Synthetic v2 seed data remains development-only.
- Release approval requires the product owner, an OIA faculty owner, one ICC head, and one IGP head.

### 1.2 V1 deletion decision

**Do not delete `icc-platform` yet.**

It contains uncommitted work and useful v1-only concepts absent from v2, including project components, project CRUD, explicit permission rules, public feedback, student history, magazine logic, and PWA/offline support.

Delete the local folder only after:

1. Committing its complete current state to an `archive/v1-final` branch.
2. Creating a Git bundle and checksum outside the folder.
3. Recording a capability inventory in this PRD.
4. Carrying forward project components, scoped permission concepts, public feedback, and PWA readiness.
5. Recording the magazine, journey timeline, and engagement score as deferred—not lost—requirements.
6. Confirming that the archive can be restored.

## 2. Product vision, purpose, and boundaries

### 2.1 Vision

Create a durable institutional memory and operational control plane for OIA activities: one system in which authorized stakeholders can understand what is planned, what is due, who is responsible, what evidence exists, what happened, and what must be carried forward to the next team or academic year.

The product is not merely an event tracker. It is an operations suite that connects governance, people, programs, execution, evidence, approvals, and reporting while respecting the different structures, privacy needs, and authority boundaries of ICC and IGP.

### 2.2 Goals

- Replace fragmented spreadsheets, folders, messages, and informal handovers with structured, auditable workflows.
- Preserve annual ICC leadership and associate history while supporting program-specific IGP recruitment and teams.
- Make responsibilities, deadlines, approvals, and closure blockers visible.
- Reproduce operational and narrative reports from structured source records.
- Reduce duplicate data entry through templates, bulk operations, and staged imports.
- Preserve privacy by storing sensitive-document status and restricted references instead of sensitive file binaries.
- Give faculty and student leaders reliable oversight without exposing records beyond their assigned scope.
- Build a foundation that can later integrate institutional identity and other university systems.

### 2.3 Product boundary

The OIA Operations Suite is the authoritative operational record for:

- ICC governance and the Events, Media, and Culturals wings.
- IGP incoming exchange, immersion, summer-school, and visitor programs.
- Partner-university and mobility cohorts.
- Teams, volunteers, buddies, participants, schedules, tasks, checklists, documents, attendance, feedback, budgets, reports, and institutional memory.

The initial production release excludes:

- International admissions processing.
- Academic records and course administration.
- Official FRRO or visa case management.
- University accounting or payment execution.
- File-binary storage outside Google Drive.
- Native mobile applications.
- Magazine generation and gamified engagement scoring.

Operational finance is included only as budget estimates, approval requests, commitments, official reference numbers, and status. The university finance system remains authoritative for payments.

## 3. Stakeholders and operating model

### 3.1 Primary stakeholders

- **OIA faculty and administrators:** institutional oversight, approvals, compliance readiness, continuity, reporting, and audit access.
- **ICC Secretary / USC:** cross-wing governance, annual planning, coordination, and consolidated reporting.
- **ICC wing heads:** delivery ownership for Events, Media, and Culturals, including teams, assignments, schedules, and closure.
- **ICC associates:** annual team members who need focused work queues, resources, attendance, contribution history, and feedback.
- **IGP heads and program leads:** partner and cohort management, program readiness, recruitment, logistics, buddies, checklists, and reports.
- **IGP volunteers and buddies:** program-specific assignments, schedules, resources, interaction logs, and escalation paths.
- **Participants and exchange students:** permitted schedules, resources, personal records, and feedback forms.
- **Auditors and institutional reviewers:** read-only, scoped access to approved reports, evidence metadata, and audit trails.

### 3.2 Operating-model constraints

- ICC and IGP are related organizationally but must remain separate operational and authorization domains.
- ICC leadership and associate rosters are fixed for an academic year and preserved historically.
- IGP operational teams are created for each program; only heads are expected to persist across programs.
- A person may hold multiple roles, but each role must have explicit scope and effective dates.
- A person may participate without having a platform account.
- Leadership transitions must not rewrite historical ownership, approvals, attendance, or reports.

## 4. Organization and authorization

### 4.1 Roles

- System Administrator
- OIA Faculty Administrator
- Faculty Coordinator
- ICC Secretary / USC
- ICC Events Head
- ICC Media Head
- ICC Culturals Head
- ICC Associate
- IGP Head
- IGP Program Lead
- Volunteer
- Buddy
- Participant / Exchange Student
- Auditor / Read-only

### 4.2 Scope model

Every role assignment carries one or more explicit scopes:

- Platform
- Operating unit: ICC or IGP
- Campus
- Wing
- Academic year
- Project/program

### 4.3 Authorization rules

- Faculty administrators may be global or campus-scoped.
- ICC roles cannot administer IGP unless separately assigned.
- IGP teams can access only their assigned programs.
- Wing heads manage their wing’s work and cross-wing assignments explicitly delegated to them.
- Volunteers and buddies see only assignments, resources, logs, and personal history relevant to them.
- Participants see their own data, permitted project resources, schedules, and feedback forms.
- Sensitive checklist links require an additional named permission.
- System administration does not automatically grant access to sensitive operational content.
- Every permission-changing action is audited.

### 4.4 Role access matrix

| Role | Default scope | Manage projects | Approve work | People/team access | Sensitive links | Reports/audit |
|---|---|---:|---:|---|---:|---|
| System Administrator | Platform | Configuration only unless separately assigned | No implicit operational approval | Account administration | No implicit access | Platform audit and health |
| OIA Faculty Administrator | Platform or campus | Yes, within scope | Yes | All scoped records | Named permission required | Full scoped reporting |
| Faculty Coordinator | Campus/project | Yes, within assignment | Delegated approvals | Scoped teams and participants | Named permission required | Scoped reporting |
| ICC Secretary / USC | ICC/academic year | Cross-wing ICC | Governance approvals | ICC annual rosters | No default access | ICC consolidated reports |
| ICC Wing Head | Wing/academic year | Wing projects | Wing approvals | Wing associates | No default access | Wing reports |
| ICC Associate | Wing/project | Assigned updates | No | Own and assigned team context | No | Personal/assigned views |
| IGP Head | IGP | All IGP programs | IGP operational approvals | Program teams and cohorts | Named permission required | IGP consolidated reports |
| IGP Program Lead | Program | Assigned program | Delegated approvals | Assigned team/cohort | Named permission required | Program reports |
| Volunteer / Buddy | Project/program | No | No | Own assignments and permitted participants | No | Personal history |
| Participant | Self/project | No | No | Self only | No | Own permitted records |
| Auditor | Assigned read-only scope | No | No | Read-only | Named permission required | Approved records and audit |

## 5. Functional requirements

### 5.1 Organization and annual governance

- Campuses, operating units, wings, academic years, positions, and terms.
- ICC annual leadership and associate rosters.
- Program-specific IGP teams.
- Acting and delegated positions with effective dates.
- Historical roster preservation across leadership transitions.

### 5.2 Projects and programs

- Create, edit, clone, approve, cancel, archive, and search projects.
- Types: ICC event, ICC internal activity, IGP inbound program, immersion, exchange cohort, visitor program, and mobility activity.
- Fields include campus, owner, wing, partner institution, objectives, audience, venue, dates, times, capacity, expected and actual reach, status, collaborators, budget, risks, and closure summary.
- Lifecycle: **Draft → Pending Approval → Planned → Active → Closing → Completed → Archived**.
- Cancelled is a terminal state requiring a reason.
- Projects cannot complete until mandatory closure requirements are satisfied or formally waived.

### 5.3 Components, sessions, and schedules

- Project days, sessions, performances, tours, workshops, travel movements, inaugurations, and valedictories.
- Session-level venue, timing, owner, capacity, programme sequence, participant group, attendance, and resources.
- Calendar views by campus, unit, wing, academic year, and owner.
- Conflict warnings for venue, lead, and team scheduling.

### 5.4 Tasks, checklists, and approvals

- Reusable templates for ICC events and each IGP program category.
- Tasks with owner, accountable approver, due date, priority, dependencies, evidence, comments, reminders, and status.
- Checklist instances created from versioned templates.
- Statuses: Not Started, In Progress, Blocked, Submitted, Approved, Rejected, Waived, and Completed.
- Rejections require comments; waivers require faculty approval and justification.
- External departments, vendors, and faculty can be responsible contacts without requiring accounts.
- Every supplied Summer School checklist item must be represented as an operational requirement.

### 5.5 People, teams, and recruitment

- Separate `Person` from `UserAccount`; people may participate without signing in.
- University registration number is optional but unique when present.
- Guest and parent attendance defaults to aggregate counts unless identity is operationally necessary.
- ICC associates remain assigned for an academic year.
- Support IGP applications, interviews, selection, rejection, program assignment, and prior-program history.
- Support bulk participant and team assignment.
- Store skills, interests, availability, campus, category, nationality/country, emergency-contact visibility rules, and consent status.

### 5.6 Attendance and contribution

- Attendance is session-specific and independent of contribution.
- Only authorized coordinators verify attendance.
- Allow one attendance record per person/session, with change history.
- Support individual rosters, bulk marking, spreadsheet import, and aggregate audience counts.
- Contributions record activity, wing, description, hours, evidence, approver, and approval state.
- Recognition uses transparent history and totals; no universal leaderboard is included in production.

### 5.7 IGP and buddy operations

- Partner institution, cohort, dates, participant roster, arrival/departure movements, accommodation-readiness status, itinerary, and program contacts.
- Buddy recruitment, interview outcome, one-to-one assignment, day-wise assignment, airport assignment, interaction logs, concerns, and escalation.
- Prevent overlapping or duplicate buddy assignments unless explicitly approved.
- Sensitive requirements store status, owner, expiry/due date, verification date, verifier, classification, and restricted Drive reference only.

### 5.8 Documents and Google Drive

- Required-document templates by project/program type.
- Metadata: category, title, version, owner, requirement, status, Drive file/folder ID, permission classification, approval, and superseded version.
- Validate Drive links and permission visibility through the Drive API.
- Never broaden Drive sharing automatically.
- Track missing, submitted, approved, rejected, expired, and superseded documents.
- Use Drive roles and permission metadata for access checks. See [Google Drive permissions](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions).

### 5.9 Feedback and experience

- Configurable feedback forms and question types.
- Public token-based feedback for selected projects without requiring an account.
- One-response, anonymous, or repeat-response policy selected per form.
- Quantitative summaries and moderated qualitative comments.
- Experience/testimonial consent and publication status.

### 5.10 Budgets and operational requests

- Project budget, category lines, estimate, approved amount, commitment, actual amount, official finance reference, owner, and approval.
- Advance, remuneration, vendor, vehicle, food, venue, gift, and equipment requests.
- No payment execution or accounting-ledger behavior.

### 5.11 Reporting and institutional memory

- Project operational report.
- ICC event narrative report.
- IGP program and checklist-completion report.
- Monthly OIA activity report.
- Academic-year impact report.
- Attendance, contribution, volunteer, buddy, partner, campus, and document-completeness reports.
- Coffee Meet & Greet roster, action list, schedule, document index, reach totals, and narrative must be reproducible from structured data.
- Reports are versioned snapshots with author, filters, generation time, approval status, and source-record references.
- Narrative reports require human approval before publication.

### 5.12 Administration and notifications

- Data dictionaries, controlled categories, template versioning, archival rules, audit search, import monitoring, and account administration.
- In-app and email notifications for assignments, approaching deadlines, rejections, approvals, missing documents, and closure blockers.
- User-configurable noncritical notification preferences.
- Critical security and assignment notifications cannot be disabled.

## 6. Data dictionary and core entities

| Domain | Entity | Purpose and key constraints |
|---|---|---|
| Identity | Person | Operational identity independent of login; optional unique registration number; privacy classification and consent. |
| Identity | UserAccount | Authentication state linked optionally to one Person; provider-independent operational identity. |
| Organization | Campus / OperatingUnit / Wing | Explicit organizational boundaries used by authorization and reporting. |
| Governance | AcademicYear / Position / RoleAssignment | Effective-dated annual leadership, membership, acting roles, and delegated authority. |
| Partnership | PartnerInstitution / Cohort | Foreign-university relationships and program participant groups. |
| Delivery | Project | Authoritative event/program record with immutable code, lifecycle, ownership, reach, risk, budget, and closure. |
| Delivery | Component / Session | Project structure, dated programme items, locations, capacity, ownership, and schedule conflicts. |
| Execution | Task | Assignable work with due date, dependencies, evidence, approver, and audited status. |
| Execution | ChecklistTemplate / ChecklistInstance / ChecklistItem | Versioned reusable requirements and their project-specific completion/waiver history. |
| Workforce | TeamAssignment / Application | Annual ICC membership or program-specific IGP recruitment and allocation. |
| Participation | Attendance | Unique person/session record or aggregate audience count; verification history. |
| Participation | Contribution | Hours/evidence independent of attendance, with approval status. |
| IGP | BuddyAssignment / BuddyLog | Assignment periods, assignment type, overlap rules, interactions, concerns, and escalation. |
| Documents | DocumentRequirement / DocumentRecord | Required evidence metadata, restricted Drive reference, classification, status, version, and approval. |
| Experience | FeedbackForm / FeedbackQuestion / FeedbackResponse | Token policy, anonymity policy, quantitative answers, moderated comments, and consent. |
| Finance | BudgetLine / OperationalRequest | Operational estimate, approval, commitment, actual amount, and official reference without payment execution. |
| Reporting | ReportSnapshot | Versioned generated report, filters, source references, approval, and publication state. |
| Imports | ImportBatch / ImportRow | Source provenance, staged parse, validation result, explicit commit, and reconciliation. |
| Platform | AuditEvent / Notification | Append-only change and security history; user-visible work and deadline signals. |

### 6.1 Shared data rules

- Use UUID primary keys and immutable human-readable codes such as `ICC-2026-CEN-001`.
- Store timestamps in UTC and display them in Asia/Kolkata.
- Use soft archival for operational records; destructive deletion is restricted to erroneous unreferenced drafts.
- Enforce database constraints for uniqueness, status values, ratings, nonnegative hours/amounts, date order, and scoped assignments.
- Keep audit events append-only with actor, action, entity, before/after summary, timestamp, request ID, and IP metadata.
- Encrypt transport with TLS; rely on managed encryption at rest and avoid storing prohibited sensitive content.
- Retention: operational records seven years, audit/security records seven years, rejected applications one year, password-reset data minutes/hours, and sensitive links only as long as operationally required.

## 7. Technical architecture

### 7.1 Application architecture

- Preserve the v2 server-rendered Flask/Jinja/Bootstrap approach.
- Refactor into a modular monolith with domain packages for identity, organization, projects, workforce, execution, IGP, documents, feedback, reporting, imports, and audit.
- Use SQLAlchemy 2.x, PostgreSQL, Alembic, Flask-Login, Flask-WTF CSRF protection, and rate limiting.
- Use Gunicorn in a multi-stage Docker image.
- Keep static dependencies locally bundled; production UI must not depend on public CDNs.

### 7.2 GCP deployment architecture

- Cloud Run hosts the web service.
- Cloud Run Jobs execute schema migrations and large imports.
- Cloud Tasks handles asynchronous notification and report jobs.
- Cloud Scheduler triggers reminders, archival, and routine maintenance.
- Cloud SQL for PostgreSQL uses regional high availability, point-in-time recovery, daily backups, and tested restoration.
- Secret Manager stores database credentials, signing keys, mail credentials, and Drive credentials.
- Development, staging, and production use separate GCP projects or fully isolated services and databases.
- Terraform provides reproducible infrastructure.
- Cloud Logging, Error Reporting, uptime checks, dashboards, and alerts provide observability.

### 7.3 Public interfaces

Provide `/api/v1` JSON endpoints, used by imports and future integrations, while the web UI uses the same service layer:

- `/organizations`, `/campuses`, `/academic-years`, `/role-assignments`
- `/projects`, `/projects/{id}/components`, `/sessions`, `/tasks`, `/checklists`
- `/people`, `/teams`, `/applications`, `/participants`
- `/attendance`, `/contributions`, `/buddy-assignments`, `/buddy-logs`
- `/documents`, `/documents/validate-drive-link`
- `/feedback-forms`, `/feedback-responses`
- `/budgets`, `/operational-requests`
- `/imports`, `/reports`, `/audit-events`

Interface rules:

- Cursor pagination, filter parameters, and deterministic sorting.
- RFC 7807-style error responses.
- Optimistic concurrency version on editable records.
- Idempotency keys for imports, attendance batches, notifications, and report jobs.
- CSV/XLSX templates for people, ICC roster, projects, participants, attendance, checklists, and document indexes.
- Import flow: upload → staged parse → validation → preview → explicit commit → reconciliation report.
- Future institutional identity integration uses an `IdentityProvider` interface with internal-password and external-directory implementations. Operational `Person` IDs never depend on authentication-provider IDs.

## 8. Security, privacy, quality, and service levels

### 8.1 Security and privacy

- No default production accounts, hard-coded secrets, or demo passwords.
- Password hashing uses a modern memory-hard configuration; enforce length, breached-password checks, reset expiry, session rotation, lockout, and recovery audit.
- CSRF protection applies to all browser mutations.
- Authorization is checked in both the service and route layers.
- Prevent cross-project identifier access and verify parent-child ownership on every mutation.
- Use secure cookies, strict security headers, origin checks, request-size limits, upload-type validation, and rate limits.
- Sensitive IGP files remain in restricted Drive storage. The ERP stores only operational status, classification, verification metadata, and restricted references.
- Sensitive content is never included in offline caches, public feedback routes, logs, analytics, or notification bodies.

### 8.2 Accessibility and performance

- Meet WCAG 2.1 AA, including keyboard operation, semantic labels, responsive layouts, and screen-reader-compatible errors.
- Common authenticated pages should meet p95 server response under 500 ms at 200 concurrent users.
- Target 99.5% availability, recovery point objective of 15 minutes, and recovery time objective of four hours.
- PWA support includes an installable shell, safe static caching, and offline read-only access to previously viewed nonsensitive schedules/tasks; sensitive IGP data is never cached offline.

## 9. Delivery and implementation plan

### 9.1 Plan artifacts

1. Write this complete Markdown PRD in the workspace root.
2. Generate a matching DOCX from the approved content.
3. Render every DOCX page to PNG, inspect all pages, and correct layout defects.
4. Include version, status, decision log, glossary, role matrix, data dictionary, acceptance matrix, and revision history.

### 9.2 Three-day demonstrator

#### Day 1 — foundation

- Archive v1 safely and initialize `icc-platform-2` as the `icc-erp` Git repository.
- Remove demo credentials from normal startup.
- Establish PostgreSQL-compatible models, Alembic baseline, environment configuration, and CSRF.
- Implement organization hierarchy, scoped roles, project CRUD, components, and lifecycle.
- Create the development Docker stack and automated test workflow.

#### Day 2 — operational workflows

- Implement people without accounts, teams, tasks, checklist templates/instances, documents, sessions, attendance, contributions, and basic IGP/buddy assignment.
- Add staged import for the supplied event summary, Coffee Meet roster/action list, and Summer School checklist.
- Build Drive-link metadata validation with a mock mode when production credentials are unavailable.

#### Day 3 — demonstration and evidence

- Implement dashboards, closure blockers, event/IGP report previews, audit history, and core exports.
- Deploy the demonstrator to a nonproduction Cloud Run service with a development database.
- Load validated sample data, execute the demo script, run automated tests, and produce a known-limitations register.
- Label every screen and environment as **“Demonstrator—Not Production.”**

### 9.3 Fourteen-week production program

1. **Week 1:** stakeholder workflow validation and data dictionary sign-off.
2. **Weeks 2–3:** production security, infrastructure, migration framework, audit, backup, and restore.
3. **Weeks 4–5:** organization, identity adapter, scoped RBAC, annual ICC governance.
4. **Weeks 6–7:** projects, sessions, tasks, checklists, approvals, documents, budgets.
5. **Weeks 8–9:** people, recruitment, teams, attendance, contribution, imports.
6. **Weeks 10–11:** IGP cohorts, logistics readiness, buddies, partners, sensitive-link handling.
7. **Week 12:** feedback, reports, analytics, notifications, and PWA.
8. **Week 13:** migration rehearsal and ICC/IGP pilot.
9. **Week 14:** accessibility, performance, security, restore drill, training, and release sign-off.

## 10. Data migration and reconciliation

- Build a fresh production database.
- Preserve v2 synthetic records only in fixtures.
- Normalize campuses, project names, roles, wings, countries, categories, programme names, and document types through controlled mapping tables.
- Stage every source workbook; never write source rows directly into production tables.
- Resolve people using registration number first, approved email second, and reviewed name/program matching last.
- Preserve source file, sheet, row, import batch, and transformation notes for audit.
- Reconcile event count, participant count, volunteer count, attendance, documents, checklist items, and Drive links.
- Run imports twice in staging to prove idempotency.
- The product owner signs the reconciliation report before production commit.

### 10.1 Supplied-data acceptance targets

- **2026 ICC Events Report Summary:** every source event is staged, mapped to campus/type/status, validated, and either committed or listed with a review reason.
- **Coffee Meet & Greet folder:** the system reproduces its 31-person core/volunteer roster, action list, schedule, document index, audience totals, and approved narrative report.
- **Summer School checklist:** every source checklist requirement is represented with owner/contact, status, evidence/reference, due date where available, approval/waiver state, and source-row provenance.

## 11. Pilot, training, and go-live

- Pilot one ICC event from planning through closure.
- Pilot one IGP program from recruitment/checklist creation through final report.
- Train faculty, ICC heads, IGP heads, associates, and volunteers using role-specific guides.
- Provide a support process, incident owner, rollback procedure, and seven-day hypercare period.
- Production approval requires signatures from the product owner, OIA faculty owner, ICC head, and IGP head.

### 11.1 Release gates

| Gate | Evidence | Required approver |
|---|---|---|
| Workflow validation | Signed workflows and data dictionary | Product owner + OIA faculty |
| Security and privacy | Threat review, authorization tests, no critical/high findings | OIA faculty + technical owner |
| Migration rehearsal | Reconciliation report and idempotent staging runs | Product owner |
| ICC pilot | Completed project with approved closure report | ICC head + OIA faculty |
| IGP pilot | Completed program/checklist report | IGP head + OIA faculty |
| Recovery readiness | Backup restore and rollback evidence | Technical owner |
| Production acceptance | Acceptance matrix with no blocking failures | All four release approvers |

## 12. Test and acceptance plan

### 12.1 Automated testing

- Unit tests for lifecycle rules, permissions, checklist gates, imports, calculations, and report compilation.
- Integration tests against PostgreSQL and mocked Drive/email services.
- End-to-end browser tests for every role’s critical journey.
- Minimum 80% service-layer coverage and complete coverage of authorization decisions.
- Security scans for dependencies, secrets, unsafe queries, CSRF, IDOR, session fixation, rate limits, and privilege escalation.
- Load tests for 200 concurrent users and large attendance/import batches.
- Accessibility testing with automated checks plus keyboard and screen-reader review.
- Backup restoration and point-in-time recovery drill.
- PDF/XLSX/DOCX output rendering and reconciliation tests.

### 12.2 Required scenarios

- ICC head cannot approve IGP work without a separate assignment.
- Campus-scoped faculty cannot access another campus’s restricted records.
- Volunteer sees only assigned projects and personal records.
- A participant can exist and attend without an account.
- Duplicate person and attendance imports are rejected or reconciled.
- Attendance and contribution remain independent.
- Project closure is blocked by missing required documents, unresolved tasks, and incomplete report data.
- A faculty-approved waiver allows closure and appears in the audit trail.
- Sensitive Drive links are hidden from unauthorized roles and never cached offline.
- Buddy assignments reject invalid, duplicate, or overlapping allocations.
- Rejected tasks/documents require reasons and notify the owner.
- Report totals reconcile exactly with underlying records and import reports.
- Concurrent edits return a conflict instead of silently overwriting data.
- Cancelled and archived projects remain historically reportable.

### 12.3 Production acceptance matrix

| Area | Acceptance criterion | Evidence | Blocking |
|---|---|---|---:|
| Sample ICC data | Coffee Meet & Greet reproduces roster, action list, schedule, document index, audience totals, and approved narrative | Reconciliation + report snapshot | Yes |
| Sample IGP data | Summer School reproduces every checklist requirement and approval history | Checklist report + source mapping | Yes |
| Data hygiene | No synthetic data or default credentials exist in production | Environment/database audit | Yes |
| Authorization | Role/scope matrix passes stakeholder review and automated decisions | Signed matrix + test report | Yes |
| Deployment | Staging-to-production deployment and rollback succeed | Deployment record | Yes |
| Recovery | Backup restoration meets RPO/RTO targets | Restore drill report | Yes |
| Security | No unresolved critical or high findings | Security report | Yes |
| Accessibility | No blocking WCAG defects | Accessibility report | Yes |
| Migration | Reconciliation differences are approved or zero | Signed reconciliation | Yes |
| Governance | Four release approvers sign production acceptance | Acceptance record | Yes |

## 13. V1 capability inventory and disposition

| V1 capability | V2 baseline | Decision |
|---|---|---|
| Project CRUD and project components | Partially absent | Carry forward into core project domain. |
| Explicit permission-rule concepts | Simplified role checks | Replace with scoped, effective-dated role assignments and named sensitive permissions. |
| Public feedback | Absent/incomplete | Carry forward as token-based configurable feedback. |
| PWA/offline shell | Absent/incomplete | Carry forward with nonsensitive read-only cache rules. |
| Student journey/history | Partially represented | Defer a dedicated journey timeline; preserve source events through person participation history. |
| Magazine generation | Absent | Defer outside initial production boundary. |
| Engagement score/leaderboard | Simplified contribution metrics | Do not carry universal scoring into production; defer any future recognition model. |

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ERP scope expands into admissions, academics, immigration, or accounting | Delivery failure and unclear authority | Enforce the product boundary and require change control for adjacent domains. |
| Historic data is inconsistent or duplicated | Unreliable reports and adoption loss | Stage, normalize, preview, reconcile, and obtain explicit import approval. |
| Broad roles expose sensitive IGP references | Privacy/security incident | Scope every assignment, add named sensitive permission, and audit access. |
| Student leadership turnover breaks continuity | Loss of institutional memory | Effective-dated roles, immutable history, templates, closure requirements, and handover reports. |
| Demonstrator is mistaken for production | Premature use and data risk | Persistent environment labels, synthetic/nonproduction database, and no production approval claim. |
| Solo delivery creates concentration risk | Maintenance and schedule risk | Modular architecture, tests, runbooks, Terraform, documented decisions, and stakeholder gates. |
| Drive link permissions drift | Broken evidence or unintended exposure | Metadata validation, visibility checks, alerts, and never auto-broaden sharing. |

## 15. Decision log

| ID | Date | Decision | Rationale | Status |
|---|---|---|---|---|
| D-001 | 2026-07-16 | Upgrade v2; do not restart as v3 | v2 has the strongest UI and interaction foundation; gaps are domain and production-hardening gaps. | Locked |
| D-002 | 2026-07-16 | Use modular monolith | Appropriate for a solo/AI-assisted team and current scale; preserves clear domain boundaries without distributed-system overhead. | Locked |
| D-003 | 2026-07-16 | GCP deployment | Best alignment with Google Drive, managed container hosting, managed PostgreSQL, secrets, and scheduled/background services. | Locked |
| D-004 | 2026-07-16 | Platform accounts first, identity adapter later | Enables delivery without coupling operational records to an unavailable institutional directory. | Locked |
| D-005 | 2026-07-16 | Sensitive files remain in restricted Drive | Minimizes privacy exposure and avoids duplicating authoritative restricted files. | Locked |
| D-006 | 2026-07-16 | Fresh production database | Existing v2 data is synthetic and not migration-worthy as production truth. | Locked |
| D-007 | 2026-07-16 | Demonstrator precedes production | Three days can validate workflows and architecture but cannot satisfy production security, migration, pilot, and recovery gates. | Locked |
| D-008 | 2026-07-16 | Do not delete v1 until archive gates pass | V1 contains uncommitted work and unique design concepts needed for traceability. | Locked |

## 16. Glossary

| Term | Definition |
|---|---|
| ICC | International Christite Community, the student body supporting international and NRI student interaction at CHRIST University. |
| IGP | India Gateway Program, the operational wing handling incoming exchange, immersion, summer-school, and related foreign-university programs. |
| OIA | Office of International Affairs. |
| USC | University Student Council. |
| Operating unit | Primary operational boundary: ICC or IGP. |
| Wing | A function within ICC, principally Events, Media, or Culturals; IGP is separated operationally despite its organizational relationship. |
| Project | Generic delivery record for an ICC event/activity or IGP program/cohort. |
| Component | A structural subdivision of a project, such as a day, workstream, or programme segment. |
| Session | A scheduled activity with time, venue, owner, participants, and attendance. |
| Closure blocker | A mandatory unresolved task, document, checklist requirement, or report field that prevents project completion. |
| Waiver | Faculty-approved exception to a mandatory closure requirement, including justification and audit history. |
| Person | Operational human record that can exist without a login account. |
| Role assignment | Effective-dated permission grant to a person/account with explicit organizational and/or project scope. |
| Restricted Drive reference | Identifier or link to a sensitive file whose contents remain outside the ERP and whose visibility requires named permission. |
| Report snapshot | Versioned, reproducible report generated from identified source records and requiring approval where narrative content is involved. |
| RPO | Recovery point objective: maximum acceptable data loss measured in time. |
| RTO | Recovery time objective: maximum target time to restore service. |

## 17. Assumptions and deferred requirements

### 17.1 Assumptions

- Markdown is the authoritative PRD; DOCX is the stakeholder distribution copy.
- Google Drive remains the authoritative file store.
- Platform accounts remain initial authentication; institutional identity is a future adapter.
- The three-day deliverable is explicitly a demonstrator.
- Production delivery requires approximately fourteen weeks even with intensive AI assistance.

### 17.2 Deferred requirements

- Magazine generation.
- Gamified engagement scoring and universal leaderboards.
- Dedicated student journey timeline beyond participation history.
- Native mobile applications.
- Official immigration casework.
- Admissions and academic administration.
- Payment processing and accounting-ledger functions.

## 18. Revision history

| Version | Date | Author | Change | Status |
|---|---|---|---|---|
| 1.0 | 2026-07-16 | Product implementation team | Initial approved production-upgradation PRD and implementation baseline. | Approved baseline |

