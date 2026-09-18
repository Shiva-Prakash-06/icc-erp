# ICC ERP UI/UX Computer-Use Audit

**Audit date:** 17 September 2026  
**Application:** local instance at `http://localhost:5000`  
**Evidence:** [`screenshots/`](./screenshots/)  
**Implementation source of truth:** [`design-system/icc-erp/MASTER.md`](../../design-system/icc-erp/MASTER.md)

## Implementation status — 17 September 2026

Every P0 and P1 finding is resolved except the two recorded as **superseded**
below, which asked for a design decision taken the same day to be reverted. The
screen-specific P2 items are addressed or carry a stated reason. Evidence is
recorded per finding in [`COMPLETION.md`](./COMPLETION.md).

**Two findings are superseded, not fixed.** P1-01 and the blueprint half of
P1-05 were written against `design-system/icc-erp/MASTER.md`, which described
the flat blueprint shell. The screenshots in this audit were taken *after* the
application was migrated to the **ICC ERP Tile System** on the same date, so
those two findings ask for the rail to be replaced by a top bar that the current
system deliberately removed. The direction was confirmed with the product owner
before implementation, `MASTER.md` has been rewritten to describe the shipped
system, and the substance behind both findings — an icon rail with no labels, a
mixed visual language across screens — was fixed inside the Tile System instead.

**Verification.** 356 Python tests, 231 Playwright tests across ten projects
(desktop Chromium/Firefox/WebKit, Pixel 7, iPhone 13, no-JavaScript,
reduced-motion, forced-colors, 200% zoom, visual), `tsc --noEmit`, the Vite
build and the asset-budget gate. One pre-existing failure is unrelated and
described in `COMPLETION.md`.

## Executive verdict

The current interface contains a capable ERP underneath, but the presentation layer is only partially migrated to the current design system. The clearest legacy remnant is the permanent desktop icon rail even though the mandatory design system specifies a single sticky top bar and explicitly says there is no desktop rail. Several screens combine newer typography and status chips with older rounded panels, compressed tables, raw native controls, and scattered one-off layouts.

The main user-facing problem is not a lack of decoration. It is weak information hierarchy. Important text is truncated, record actions are squeezed into rows, status labels conflict with each other, and mobile layouts hide controls outside the viewport. The result looks dense while still wasting space, and users must decode the screen before acting.

Implementation should first restore trust and usability, then polish. Fix the P0 and P1 findings before visual refinements.

## Audit coverage

Computer Use was used to inspect rendered screens and interactions rather than relying only on templates or source code.

- Roles: `igp1` (IGP Head), `faculty1` (OIA Faculty Administrator), `events1` (ICC Events Head), `media1` (ICC Media Head), and `usc` (ICC Secretary / USC).
- Widths: desktop at approximately 1470 px and phone at 390 × 844.
- Authentication: sign in, registration, conditional volunteer fields, and password recovery.
- Core application: project directory, creation, all six setup steps, IGP and ICC project workspaces, attendance, analytics, decision queue, campuses, imports, notifications, profile, audit, and administration.
- Public application: landing, events, and reports empty states.
- Interaction states: disclosures, command palette, role editor, notification preferences, filters, and cross-screen drill-downs.

The screenshots show representative states, not production data. No operational records were created, edited, approved, marked read, or deleted during the audit.

## Severity definitions

- **P0 — release blocker:** misleading state, broken navigation, inaccessible action, or severe responsive failure.
- **P1 — major:** materially slows routine work, obscures meaning, or violates the mandatory design system.
- **P2 — improvement:** meaningful quality, clarity, or consistency upgrade after P0/P1 work.

## P0 — release blockers

### P0-01 — The authenticated home route returns a raw, unstyled 429 page

**Observed:** `/` returned only “Too many requests. Wait a moment and try again.” in both a fresh in-app tab and an existing signed-in browser session. Other authenticated routes remained available. See [`38-rate-limit.png`](./screenshots/38-rate-limit.png).

**Impact:** the primary destination is unusable and the error discards the application shell, identity, navigation, retry guidance, and support context.

**Required fix:** determine why the home GET route is being rate-limited independently of other screens. Render all 429 responses through a branded error template with an H1, explanation, retry guidance, a safe destination, and `Retry-After` when available. Preserve user input only where a rate-limited POST is involved.

**Acceptance:** normal signed-in navigation to `/` does not produce 429; an intentionally triggered 429 remains inside the correct shell, is keyboard-readable, and provides a useful recovery path.

### P0-02 — Phone layouts clip titles, tabs, and row actions

**Observed:** on the 390 px project screens, the page title is shortened to “Coffee Meet…”, the header actions extend past the right edge, the tab row cuts off Documents/People/Analytics, and row-level Save/Resolve actions appear as fragments on the left edge. See [`49-mobile-analytics.png`](./screenshots/49-mobile-analytics.png), [`50-mobile-logistics.png`](./screenshots/50-mobile-logistics.png), [`51-mobile-task-actions.png`](./screenshots/51-mobile-task-actions.png), and [`53-mobile-documents.png`](./screenshots/53-mobile-documents.png).

**Impact:** users cannot identify the record or reliably reach required actions. This is a functional failure, not a cosmetic one.

**Required fix:** build an explicit mobile project header and section switcher. Convert action-heavy table rows into labeled record cards with actions inside the card. Never position row actions off-canvas. Allow long titles to wrap to two lines. Keep the bottom navigation and safety banner from covering content.

**Acceptance:** at 375 and 390 px, every project title, tab/section, form control, decision action, and final row can be reached without horizontal page scrolling or clipped controls.

### P0-03 — Analytics drill-down links to the wrong filtered state

**Observed:** IGP analytics showed “Active programmes 1 of 1 this year,” but activating it opened `/erp/projects?status=Active`, which displayed “0 in scope / No projects found.” The programme is actually in `Closing`. See [`30-igp-analytics.png`](./screenshots/30-igp-analytics.png) and [`31-active-drilldown-empty.png`](./screenshots/31-active-drilldown-empty.png).

**Impact:** headline metrics cannot be trusted and their primary interaction is broken.

**Required fix:** align metric labels, query definitions, and destination filters. If the metric means open/non-completed programmes, label it that way and link to a filter that includes Closing. If it means Active only, report the true Active count.

**Acceptance:** each linked KPI opens a list containing exactly the records counted by that KPI; add a regression test for every linked analytics tile.

### P0-04 — Status semantics conflict across screens

**Observed examples:**

- Documents are simultaneously shown as `Missing` and `Approved`.
- Verified buddy interactions use red warning styling and a warning icon.
- Report copy says it is assembled from authoritative documents while the dependency table says none were found.
- Attendance entries say `Unknown verifier` even though they are presented as verified records.
- IGP analytics says `2 reports filed` and `of 0 closed programmes`, an unexplained ratio.

See [`06-documents.png`](./screenshots/06-documents.png), [`08-buddy-feedback.png`](./screenshots/08-buddy-feedback.png), [`10-complete-report.png`](./screenshots/10-complete-report.png), [`30-igp-analytics.png`](./screenshots/30-igp-analytics.png), and [`32-attendance.png`](./screenshots/32-attendance.png).

**Impact:** users cannot distinguish workflow approval, file availability, verification, publication, and completion.

**Required fix:** define a status model with separate named dimensions. At minimum: file availability, workflow state, review/approval state, publication state, and lifecycle state. Give each state one semantic label, icon, and color token. Do not style successful verification as danger. Rewrite report copy to match the actual dependency mode.

**Acceptance:** no record presents two apparently contradictory states without labels explaining the dimensions; automated fixtures cover combinations such as “approved metadata / file missing.”

### P0-05 — Mobile bottom navigation and safety banner obscure working content

**Observed:** the bottom navigation contains seven icons and remains fixed while the multi-line safety banner sits directly above it. Together they cover the lower part of project tables and actions. See all screenshots `49`–`54`.

**Required fix:** follow the design-system mobile navigation contract: four primary destinations plus Menu. Move secondary destinations into a labeled menu. Reserve bottom padding for navigation plus `env(safe-area-inset-bottom)`. Make the demo warning compact and non-overlapping.

**Acceptance:** the last interactive element on every mobile screen scrolls completely above the banner/navigation; no bottom navigation has more than five top-level items.

## P1 — cross-cutting major issues

### P1-01 — The shell still uses the retired desktop rail

The current left icon rail conflicts with the mandatory master design system, which calls for a 56 px sticky top bar and no desktop rail. The rail consumes width, hides labels until discovery, and creates a different information architecture from the public and auth shells.

Implement the authorized destinations in a labeled top bar with a clear current location, command trigger, notifications, and user menu. Preserve permission checks and destination URLs.

### P1-02 — Text hierarchy is too compressed

Micro labels, uppercase tracking, condensed headings, monospaced metadata, status chips, and body copy often share similar weight. Tables contain readable information at 100% zoom, but scanning requires too much effort. Body text and helper text should use semantic size/line-height tokens. Restrict uppercase condensed text to short labels and table headings. Do not use monospaced type for ordinary prose.

### P1-03 — Important text is truncated even when space exists

Project metadata, operating unit, audience, venue, task titles, task details, report names, operational requests, and public/report labels are ellipsized. See [`02-logistics-top.png`](./screenshots/02-logistics-top.png), [`44-icc-logistics.png`](./screenshots/44-icc-logistics.png), and [`46-icc-documents.png`](./screenshots/46-icc-documents.png).

Wrap primary text. Use truncation only for secondary content when a visible expansion or full accessible name is available. Never truncate the only visible copy of a title or required instruction.

### P1-04 — Inline editing controls make tables unreadable

Task, checklist, finance, document, buddy, contribution, feedback, and decision rows place a select, reason field, and Save button inside the same horizontal row. On desktop these collide with status chips; on phone they disappear off-canvas.

Use a read-first record row/card. Put the current state in the summary and expose “Review” or “Change status” to open an inline panel/dialog/fieldset with all required inputs. Preserve the existing form action, CSRF token, version field, and server validation.

### P1-05 — Legacy and current visual languages are mixed

Rounded white panels, native file inputs, flat blueprint tables, dark marketing tiles, form cards, and public empty states look like separate products. The master design system already defines the intended flat blueprint language. Apply its tokens and components consistently rather than introducing another redesign layer.

### P1-06 — Color contrast fails on dark campus/analytics tiles

Dark tile headings are rendered as near-black text over navy/green backgrounds. The computed heading color was `rgb(29, 31, 32)` on a navy tile background of `rgb(44, 69, 93)`. See [`20-analytics-hub.png`](./screenshots/20-analytics-hub.png) and [`28-campus-detail.png`](./screenshots/28-campus-detail.png).

Use an accessible light-on-dark foreground token for headings, supporting text, and actions. Verify WCAG AA contrast in automated and manual checks.

### P1-07 — Currency, dates, and numbers are inconsistent

Examples include `₹765000.00`, `INR 45000.00`, `480000`, `₹7.2L`, raw ISO dates, localized dates, and timestamps with microseconds. Use shared formatters: Indian grouping (`₹7,65,000`), stable precision by context, human dates with the timezone label where relevant, and no microseconds in UI copy. Keep raw values only in technical details/export data.

### P1-08 — Terminology changes across screens

`IGP` expands to “India Gateway Program” in project metadata but “International Guest Programmes” in campus navigation. `ICC` is described as “International Christite Community” in one place and “Institutional Collaboration Cell” in another. Routes mix project, programme, and event for the same entity. Establish a canonical glossary and apply it to headings, breadcrumbs, actions, helper text, and empty states without changing internal enum values.

### P1-09 — Heading structure is inconsistent

Administration uses level-5 headings for primary sections directly below an H1. The profile also uses H4/H5 as layout styling. Replace visual-level headings with semantic H2/H3 structure and style them through classes.

### P1-10 — Role context is invisible

Events Head, Media Head, and USC users see nearly identical project directories, and the UI does not state the current role/scope. Add role/scope context to the user menu or page header where it helps explain why records/actions are present. Do not expose unauthorized destinations.

### P1-11 — Empty and low-content screens waste most of the viewport

Alerts, campus list, public pages, analytics directories, reports, and the complete-report screen leave large blank areas without strengthening orientation. Use compact empty-state regions with a clear explanation and one permitted next action. A flexible page shell should keep the footer natural without artificially stretching cards.

### P1-12 — Forms do not consistently explain conditional fields

Reason fields remain visible when approving even though copy says they are only required for rejection/cancellation/waiver. “If Other” fields remain present when a standard option is selected. Reveal these fields conditionally and retain server-side validation. Use `aria-expanded`, focus management, and adjacent errors.

### P1-13 — Native upload controls do not match the product

Creation and import screens show unstyled native “Choose file” controls, duplicate “No file selected” messages, and very large full-width submit buttons. Build one accessible file-picker component around the native input with accepted types, size, selected filename(s), errors, and pending state.

### P1-14 — Fixed controls and overlays need collision rules

The demo warning, mobile nav, sticky attendance submit action, toasts, command palette, and page content can overlap. Define z-index layers and safe offsets centrally. Toasts should not cover the final table column or action.

## Screen-by-screen findings

### Authentication

- Login is visually cleaner than the application, but it looks like a different product and leaves most of the desktop viewport unused. See [`34-login.png`](./screenshots/34-login.png).
- “Create Command Account” is legacy language and does not match “Request access.” Rename the page to “Request access” or “Create account.” See [`35-register.png`](./screenshots/35-register.png).
- The volunteer form adds long fields below the fold without an explicit group label; group account, access request, and volunteer profile fields. See [`36-register-volunteer.png`](./screenshots/36-register-volunteer.png).
- Recovery lacks a visible route back to sign in. Add a secondary return link. See [`37-forgot-password.png`](./screenshots/37-forgot-password.png).

### Event/project directory

- The page title “Every event” conflicts with route/template language that calls records projects/programmes.
- Search uses a full-width field plus a distant Search button; make it one coherent search control and allow Enter submission.
- Filters are visually plain and the count is detached from results.
- At small result counts the single row does not provide enough visual structure to distinguish title, code, programme, campus, dates, and status. See [`01-project-directory.png`](./screenshots/01-project-directory.png).

### New event/project

- Four creation paths have equal emphasis even though they serve very different workflows. Identify the recommended path and progressively disclose the others.
- “Import ICC event summary” sends the user to another screen, while the other cards act in place. Make navigation vs direct action visually clear.
- Two nearly identical title/date forms appear side by side. Reduce duplication and explain the difference before fields.
- Icons and card styling feel like a marketing page inserted into the ERP. See [`18-new-event.png`](./screenshots/18-new-event.png) and [`19-new-event-details.png`](./screenshots/19-new-event-details.png).

### Project shell and Logistics

- The header compresses breadcrumbs, a long title, overdue state, blockers, Edit, and Report into one line.
- The project metadata definition list truncates the values most useful for orientation.
- Status chips collide visually with requirement flags; in some rows the flag appears attached to the word.
- Repeating reason fields and Save buttons for every settled task adds heavy interaction chrome.
- Schedule dates use multiple visual formats across setup and workspace.
- “Add a checklist” remains prominent even when a checklist already exists, with no explanation of whether duplicates are valid. See [`02-logistics-top.png`](./screenshots/02-logistics-top.png) and [`03-logistics-lower.png`](./screenshots/03-logistics-lower.png).

### Finance

- Budget summary, operational requests, and reimbursements need clear section-level totals and state summaries.
- The `Appr.` column heading is unexplained and mixes raw approved amounts with dashes.
- “Legacy value” is implementation language exposed repeatedly to users. Map legacy categories to a neutral display label or place provenance in technical details.
- Inline decision controls repeat the same responsive failures as tasks.
- The expanded budget form is clearer than row editing but its fields are still spread across one long line. Use a responsive grid with description taking the largest share. See [`04-finance.png`](./screenshots/04-finance.png), [`05-budget-form.png`](./screenshots/05-budget-form.png), and [`45-icc-finance.png`](./screenshots/45-icc-finance.png).

### Documents and reporting

- Availability and approval are mixed without explanation.
- Link columns display `—` even for document records, which makes “Missing” ambiguous: missing file, missing Drive link, or unavailable permission.
- Public disclosure, lifecycle transition, report approval, and closure summary are packed into one document tab despite serving distinct decisions.
- The complete report page uses two H1 headings and places the dependency table far below the CTA with a large blank gap.
- The report preview contains four sparse KPI cards and almost no report content, so “preview” overpromises what users can assess. See [`06-documents.png`](./screenshots/06-documents.png), [`10-complete-report.png`](./screenshots/10-complete-report.png), and [`11-report-snapshot.png`](./screenshots/11-report-snapshot.png).

### People, recruitment, buddy logs, contributions, and feedback

- The Team table repeats an empty registration number and extra dash columns for every row.
- Recruitment duplicates people already listed in Team without showing why a second section is useful.
- Buddy pairings flatten parent pairings and child logs into one table; the hierarchy is conveyed by a text arrow only.
- Multiple identical pending buddy logs require separate wide inline decision forms. Batch review may be useful if business rules allow it; otherwise use compact Review actions.
- Feedback moderation is embedded at the end of a very long People tab and can be missed.
- The phone layout drops labels and shows unexplained dashes. See [`07-people.png`](./screenshots/07-people.png), [`08-buddy-feedback.png`](./screenshots/08-buddy-feedback.png), [`47-icc-people.png`](./screenshots/47-icc-people.png), and [`54-mobile-people.png`](./screenshots/54-mobile-people.png).

### Project analytics

- KPI cards and the blockers list are useful, but the page duplicates information already shown in the project header.
- “Overdue 0 / 6 still block closure” needs wording that makes clear that blockers are not necessarily overdue.
- Charts require a visible accessible table fallback or named summary, not color alone.
- On phone, the four KPI cards dominate the first viewport while the action list is clipped. See [`09-project-analytics.png`](./screenshots/09-project-analytics.png) and [`48-icc-analytics.png`](./screenshots/48-icc-analytics.png).

### Six-step setup

- The stepper shows all steps as checked, including the current step, but does not distinguish complete, current, and revisitable.
- Team produces a very long table before the add-person controls; users must scroll past every member to act.
- Checklist allows adding another checklist even while saying one already exists.
- Buttons differ between “Save and continue,” “Add,” and a separate “Finish setup” link with no consistent footer action pattern.
- Existing rows are read-only here but editable elsewhere; tell users where edits are made when a step is complete. See screenshots [`12-edit-basics.png`](./screenshots/12-edit-basics.png) through [`17-setup-budget.png`](./screenshots/17-setup-budget.png).

### Attendance

- All 16 participants default visually to Present, including records that are “Not recorded.” This can be mistaken for saved attendance.
- Correction-reason fields are disabled but look nearly identical to enabled fields.
- `P/A/E/L` depends on abbreviations even though full labels are only visible inside each segmented control.
- Verification copy exposes version numbers and “Unknown verifier” as primary content.
- The sticky Save Attendance action competes with the bottom navigation and demo warning. See [`32-attendance.png`](./screenshots/32-attendance.png).

### Decision queue

- Twenty-three unrelated decision types are placed in one ungrouped table. Users must scan the Kind column to understand each action.
- Truncated titles and project descriptions make similar rows indistinguishable.
- Primary actions vary among Approve, Verify, Publish, Mark completed, Query, Hold, and Send back without grouped sections or filters.
- The `2 active` control is ambiguous and, given the analytics defect, must be verified against the same status definition.
- Group by urgency/type or provide filters while keeping an all-items view. Include enough context to make a safe decision. See [`43-decision-queue.png`](./screenshots/43-decision-queue.png).

### Administration

- The empty pending-registration panel is much taller than its message.
- Primary sections use H5 styling and the active-user table requires long vertical scanning.
- Expanding Edit inserts six controls into a full-width table row with no human-readable scope summary.
- Checkboxes such as Platform scope and Restricted references need concise explanations of their effect.
- Add a confirmation summary before updating permissions; keep the existing server authorization and audit behavior. See [`39-admin-users.png`](./screenshots/39-admin-users.png) and [`40-role-editor.png`](./screenshots/40-role-editor.png).

### Audit history

- Raw entity/action identifiers such as `Report Generate` and `ReportSnapshot` are primary copy.
- Timestamps expose inconsistent precision and no visible timezone.
- “Raw value,” “Record id,” and “Request id” disclosures do not communicate what the user will see.
- Use human labels in the row and retain raw payload/IDs in a clearly named technical-details disclosure with copy affordances. See [`41-audit-trail.png`](./screenshots/41-audit-trail.png).

### Imports

- The safety panel is useful but visually dominates the form.
- “Download a starter template” always points to the people template while the visible selector may be Attendance or another type.
- Template download and upload controls are separated, making it hard to understand which schema applies.
- The empty batch state is large and passive. Add brief next-step copy after the upload form. See [`21-imports.png`](./screenshots/21-imports.png).

### Alerts and preferences

- “1 records” is grammatically incorrect.
- Alert timestamps are raw and lack timezone/context.
- Alerts do not link to the affected record or decision.
- Preference copy says critical alerts always stay enabled, but the UI does not show which event types are critical.
- Use a compact preference form and actionable alert cards. See [`22-notifications.png`](./screenshots/22-notifications.png) and [`42-notification-preferences.png`](./screenshots/42-notification-preferences.png).

### Profile

- Username is presented as the main identity even when a person name may be available.
- Security, role assignments, projects, notifications, and navigation shortcuts use several unrelated card patterns.
- “Send a password reset link” is styled as a direct action but actually navigates to the recovery flow; label it “Change or reset password.”
- Recent notification has no date, status, or destination. See [`23-profile.png`](./screenshots/23-profile.png).

### Campus and analytics directories

- Dark division tiles fail contrast and contain decorative bar shapes that resemble charts without representing data.
- Empty ICC tiles still use a large, strongly colored surface.
- Campus list occupies only part of the available width and provides limited hierarchy beyond a basic table.
- The division screen places one small project card in a huge tinted canvas. Use a responsive project grid/list whose container follows content. See [`20-analytics-hub.png`](./screenshots/20-analytics-hub.png), [`27-campuses.png`](./screenshots/27-campuses.png), [`28-campus-detail.png`](./screenshots/28-campus-detail.png), and [`29-igp-division.png`](./screenshots/29-igp-division.png).

### Public site

- The public shell is structurally different from the ERP and auth shells, including another logo treatment and top navigation pattern.
- Empty events/reports are centered in small cards within very large blank pages.
- The landing page gives two zero KPIs and a “No published analytics yet” block, which feels like a dead end.
- Keep the public visual identity distinct only where intentional, but share typography, tokens, button language, and status/empty-state components. See [`24-published-reports.png`](./screenshots/24-published-reports.png), [`25-public-events.png`](./screenshots/25-public-events.png), and [`26-public-home.png`](./screenshots/26-public-home.png).

## Implementation order

1. Fix the home-route rate limit and KPI/filter mismatch.
2. Introduce shared semantic status, typography, currency/date, and responsive-layout primitives.
3. Replace the retired desktop rail and oversized mobile bottom navigation according to the master design system.
4. Rebuild project header, mobile section navigation, and action-heavy table rows.
5. Rework decision queue, attendance, and admin role editor because they carry the highest decision risk.
6. Normalize forms, file inputs, empty states, report surfaces, and public pages.
7. Remove exposed legacy/technical copy and complete accessibility, forced-colors, reduced-motion, zoom, print, and no-JavaScript verification.

## Required acceptance checks

- Test 375, 390, 768, 1024, and 1440 px widths plus 200% and 400% browser zoom.
- No page-level horizontal scrollbar at 375/390 px.
- Every record title and required action is visible without hover.
- Every fixed element reserves layout space; no banner, toast, sticky action, or navigation overlaps content.
- Keyboard-only users can open/close disclosures and dialogs, operate segmented controls, reach errors, and return focus correctly.
- All text/background pairs meet WCAG 2.2 AA; automated contrast checks must be enabled.
- All forms retain server actions, payload names, CSRF fields, optimistic-concurrency fields, permissions, and server validation.
- Every linked KPI has a fixture asserting that its destination contains the counted records.
- Every state uses text plus icon/shape; color is never the only signal.
- Tables that become cards retain explicit field labels and sensible reading order.
- Status/currency/date formatters are shared rather than duplicated in templates.
- Reports, audit, and summaries have usable print styles.
- The app remains usable with reduced motion and without JavaScript for server-rendered navigation/forms.
- Update Playwright visual baselines only after behavior and accessibility assertions pass.

## Definition of done

The work is complete when all P0 and P1 findings are resolved across both IGP and ICC fixtures, P2 screen findings are addressed or explicitly documented with rationale, responsive/accessibility checks pass, and the implementation visibly conforms to the existing master design system without changing authorization or workflow semantics.
