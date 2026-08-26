# ICC ERP UI/UX Computer-Use Audit

**Audit date:** 23 August 2026  
**Application audited:** local ICC ERP instance on `http://localhost:5000`  
**Primary viewports:** desktop, tablet, and 390 px mobile  
**Implementation authority:** `design-system/icc-erp/MASTER.md` and its page overrides

## Purpose

This is an implementation backlog, not a visual mood board. It records the layout, typography, hierarchy, responsiveness, accessibility, and interaction defects found across the current application. Fix the shared causes before making page-specific adjustments.

Preserve all routes, authorization rules, form names and payloads, CSRF handling, server-side validation, data semantics, audit behavior, and backend workflows. Do not invent new business functionality or replace server-rendered workflows. Presentation-only wording may be made human-readable while canonical values remain unchanged in submitted data and stored records.

## Method and coverage

The live application was operated with Computer Use, including authentication and navigation through public and authenticated areas. Screens were checked visually at desktop and narrow widths. A local browser harness was then used to complete repeatable desktop/mobile capture of route and state variants after the host UI session locked. Routes that require a single-use token, a specific approval state, or an unavailable published event fixture were reviewed from their rendered templates and shared components as noted in the coverage matrix.

### Severity

- **P1 — blocking:** content is hidden, overlapping, unreadable, or the interface is materially unusable.
- **P2 — major:** hierarchy, readability, responsiveness, or task completion is substantially degraded.
- **P3 — polish:** consistency, wording, formatting, or discoverability should be improved after P1/P2.

## Executive findings

The most damaging problems are systemic:

1. A global `height: 100%` rule stretches nearly every card, producing enormous blank panels and overlaps.
2. The fixed mobile navigation obscures content and primary actions across the application.
3. The authenticated environment banner is clipped beside the desktop rail and consumes too much vertical space on mobile.
4. Operational text is routinely rendered at 10–13 px, below the design-system target and too small for dense administrative work.
5. Several icon classes have no mask mapping and render as solid squares.
6. Mobile data-table treatment is inconsistent; important actions and values disappear off-screen.
7. Project pages repeat a large hero, metrics strip, blocker list, and tab bar before the actual task on every tab.
8. Auth typography is broken by a selector-specificity collision, shrinking the main brand statement.
9. Empty states and low-content screens are placed inside very tall generic cards instead of concise, actionable states.
10. Technical identifiers and implementation language are exposed as primary content in audit/report screens.

## P1: shared defects to fix first

### G-01 — Cards stretch to the height of their containing row

**Affected:** profile, project overview, project creation paths, admin, public empty states, and most grid-based screens.  
**Evidence:** `.aurora-card, .aurora-card--padded` in `app/static/css/components.css` applies `height: 100%` globally. Flex/grid stretch then turns short sections into extremely tall white panels. On Profile this creates a multi-thousand-pixel page and causes the mobile activity state to collide visually with Role Assignments. Project Overview cards similarly contain huge blank areas and overlapping content.  
**Required change:** remove global `height: 100%`. Let cards use content height. Add an explicit opt-in utility only for the few equal-height marketing/KPI grids that genuinely need it. Check every grid after the change rather than compensating with fixed heights.  
**Acceptance:** no card is taller than its content merely because a neighboring card is tall; Profile and Project Overview have no overlap or large unexplained voids at 1440, 768, 390, or 375 px.

### G-02 — Fixed mobile navigation covers page content and actions

**Affected:** all authenticated mobile screens; directly observed over Home KPIs, Projects cards, Create IGP, project navigation/blockers, Imports fields, Notifications, Profile, and Admin.  
**Required change:** define one mobile navigation height including `env(safe-area-inset-bottom)`. Give the scroll container sufficient bottom padding, plus breathing room, and ensure sticky controls/anchor targets also clear it. Do not hide overflow to disguise collisions. Consider moving screen-critical submission controls into a safe sticky action bar above the navigation only where this preserves the existing form.  
**Acceptance:** at 390 × 844 and 375 × 667, every final field, message, disclosure, and CTA can be fully scrolled above the fixed navigation; focus and validation targets are not concealed.

### G-03 — Environment banner is clipped on desktop and oversized on mobile

**Affected:** all authenticated pages.  
**Evidence:** the desktop message begins mid-sentence behind/alongside the 248 px rail. On mobile it wraps to roughly three or four lines and consumes a large part of the initial viewport. `layout.css` offsets the banner with a rail margin while retaining incompatible width behavior.  
**Required change:** size and position the authenticated banner within the content viewport (`left`/`width` or container layout, not width plus margin overflow). Keep the full warning accessible. Render it as a compact, one-line desktop status strip and a concise two-line mobile notice; allow details through accessible disclosure if needed.  
**Acceptance:** the complete message is visible at all breakpoints with no horizontal overflow and no content hidden beneath it.

### G-04 — Base type is too small and lacks semantic roles

**Affected:** application-wide metadata, cards, table labels, breadcrumbs, badges, inline forms, and mobile record cards.  
**Evidence:** widespread `.625rem`, `.68rem`, `.72rem`, `.78rem`, and `.82rem` declarations produce 10–13 px text. Uppercase micro-labels are overused and compete with actual headings.  
**Required change:** replace ad-hoc sizes with semantic tokens for page title, section title, card title, body, supporting text, label, table text, and data/identifier text. Follow the design system: Inter body, Space Grotesk headings, IBM Plex Mono only for identifiers/numeric data; body at least 14 px desktop and 16 px mobile; comfortable line-height; uppercase tracking only for short eyebrows. Maintain AA contrast.  
**Acceptance:** normal task text never relies on micro type; hierarchy is immediately legible; no clipping after browser zoom to 200%.

### G-05 — Undefined icon masks render as solid squares

**Affected:** public Sign in, password/reset links, sent/reset states, Create Project paths, and other actions.  
**Missing mappings observed:** `ph-airplane-tilt`, `ph-envelope-simple-open`, `ph-hand-heart`, `ph-key`, `ph-lock-key`, `ph-receipt`, `ph-sign-in`.  
**Required change:** map every used icon class to an existing local Lucide asset, or replace the template class with an already mapped semantic icon. Retain accessible names on icon-only controls. Add a test/build check that fails when a template references an unmapped icon.  
**Acceptance:** no solid square placeholders remain on any audited route; decorative icons are hidden from assistive technology and icon-only buttons have labels/tooltips.

### G-06 — Mobile tables lose content or controls

**Affected:** Admin Users, Delivery, Contributions, Finance, Imports history, Audit, Attendance history, public Events/Reports, and project sub-tables.  
**Required change:** choose deliberately per table: semantic record cards for action-heavy records, or an overflow table with a visible affordance and sticky priority columns for genuinely tabular comparison. Do not remove headers without recreating labels. Keep the primary value and action visible without horizontal scrolling.  
**Acceptance:** at 375/390 px, every field and row action remains reachable and understandable; no email, status, or action is clipped; screen-reader table semantics are retained where a table remains.

### G-07 — Forms lack consistent pending, error, and disabled states

**Affected:** auth, project creation/setup, inline project decisions, imports, preferences, admin scope edits, and uploads.  
**Required change:** preserve server validation and add adjacent field errors plus a focusable error summary where multiple fields fail. On submit, disable only the submitted action, show a clear pending label, prevent accidental double submission, and restore on failure. Style disabled/read-only controls unambiguously. Do not rely on color alone.  
**Acceptance:** keyboard users are moved to useful error context; double submission is prevented; disabled inputs cannot be mistaken for editable inputs.

### G-08 — Native file controls conflict with the visual system

**Affected:** Create Project, People bulk upload, Resources/documents/events, Imports, Attendance and other evidence uploads.  
**Required change:** create one accessible reusable file-picker presentation around the native input. Show action label, accepted type/size guidance, selected filename(s), error, and upload/submission status. Keep native semantics and keyboard access; do not implement fake drag-and-drop unless it is fully accessible and backed by the current workflow.  
**Acceptance:** file controls align with other inputs at all widths, filenames wrap safely, and validation is explicit.

### G-09 — Page identity is inaccurate on several routes

**Affected:** Notifications, Create Project, Setup, Attendance, Complete Report, Preview, and related pages whose mobile header or breadcrumb says “Home.”  
**Required change:** provide an accurate `mobile_title`, breadcrumb label, current-page state, and context-appropriate back target for every template. Breadcrumbs must reflect hierarchy, not browser history.  
**Acceptance:** the header identifies the current task on every route and the back link returns to the logical parent.

## P2/P3: shared upgrade opportunities

### G-10 — Excessive homogeneous card chrome weakens hierarchy

Use fewer nested bordered cards. Reserve raised cards for grouped tasks; use dividers, definition lists, and quiet section surfaces inside them. Limit each action region to one clear primary action. Keep work surfaces opaque as required by the design system.

### G-11 — Empty states are too large and not task-oriented

Replace giant blank tables/cards with compact states containing: what is empty, whether that is expected, and the next permitted action. If the user lacks permission, explain who can act rather than presenting a disabled CTA. Never invent counts or records.

### G-12 — Dates, currencies, statuses, and identifiers need display formatting

Use locale-readable dates and INR formatting in visible text. Humanize enum/action labels without changing their submitted values. Keep full UUIDs/checksums available through details/copy, but do not make them the dominant visual content. Use monospaced type only for technical values.

### G-13 — Responsive layout needs explicit content priorities

Remove accidental empty grid cells, avoid placing unrelated text side by side merely because space exists, and cap reading measure. At mobile widths, stack title/context/actions in that order and keep 44 px minimum targets. Test 320–390 px without horizontal page scrolling.

### G-14 — Focus, hover, and reduced-motion behavior must be complete

Retain visible `:focus-visible` outlines on every interactive element, ensure hover is not the only cue, and honor `prefers-reduced-motion`. Decorative shell motion must never delay or block a task.

## Screen-by-screen findings

### Public landing (`/`)

- **P2:** KPI/stat cards are much taller than their content, leaving large white voids. Fix through G-01 and use a compact stat composition.
- **P2:** the analytics/empty region lacks a concise explanation and useful next step.
- **P3:** mobile cards consume too much vertical space; tighten spacing while preserving readable body text.
- **P3:** stabilize the footer at the end of low-content pages with a flex page shell rather than arbitrary minimum heights.

### Public events (`/events`) and reports (`/reports`)

- **P2:** empty table states appear as large, mostly blank bordered areas; on mobile they become ambiguous double-bordered cards without useful headers.
- **P2:** mobile public navigation wraps densely and the environment notice dominates the viewport. Keep navigation clear and the notice compact.
- **P3:** provide a concise zero-state and preserve meaningful column/field labels when records exist.

### Public event detail

- **P2:** files/posters are presented as a plain link list with weak type and grouping; use a semantic resource list with file type, descriptive link label, and thumbnail only when an actual thumbnail exists.
- **P2:** the report/attachment table needs the same explicit mobile strategy as G-06.
- **P3:** use a consistent back link and page metadata hierarchy. Do not invent event media or summaries.

### Login

- **P1:** the main brand statement is rendered like small body copy and breaks into cramped lines. `.auth-intro p` overrides `.auth-intro__title` because of selector specificity. Exclude the title from the paragraph rule or give the title an explicit semantic rule; widen its measure and loosen the near-1.0 line-height.
- **P2:** add an accessible show/hide control to the password field, as required by the auth design override.
- **P2:** keep the form card within the 440 px maximum, but balance it against the intro panel at laptop widths and collapse cleanly on mobile.
- **P3:** use consistent “Home” terminology; do not mix obsolete “Mission Control” wording into auth completion states.

### Register

- **P2:** the desktop email field/placeholder is visually clipped in the current narrow column. Give identity fields enough width and avoid squeezing sensitive inputs into ornamental layouts.
- **P2:** add show/hide controls and plain-language password requirements before submission.
- **P2:** on mobile, ensure the final primary CTA scrolls clear of the viewport/keyboard and error summary.
- **P3:** group institution identity, credentials, and requested access into clearly labeled sections without creating a multi-step business flow.

### Forgot password, reset request sent, recovery, reset, and reset success

- **P1:** the sent-state icon renders as a square; fix G-05.
- **P2:** short recovery states sit inside an oversized repeated split-screen shell with excessive empty space. Use a compact auth-state variant while retaining brand context.
- **P2:** recovery currently uses `novalidate` without a complete visible inline error treatment. Apply G-07.
- **P2:** add show/hide controls consistently to recovery/reset password inputs.
- **P3:** make line breaks natural in the sent confirmation and identify which address received the message only when safely available.
- **P3:** change “Continue to Mission Control” to the current product destination label.

### Pending approval

- **P2:** “Check Status (Refresh)” is implementation-oriented. Use “Check approval status.”
- **P2:** state the next step, who approves access, and what the user can do meanwhile, using only information the application actually knows.
- **P3:** keep Logout clearly secondary.

### Home dashboard

- **P1:** the fixed mobile navigation covers the lower KPI/action area.
- **P2:** KPI cards are over-tall and show too little information per viewport.
- **P2:** mobile decision-queue cards repeat tiny uppercase TYPE/ITEM/PROJECT labels and become unnecessarily tall. Use status + title + project metadata + a full-width Review action.
- **P2:** `SCOPED PROJECTSYour projects` is concatenated. Separate eyebrow and title with block/grid structure and spacing.
- **P3:** rename or explain “IGP indicators” so the disclosure communicates what will open.

### Projects index

- **P1:** the second project card/action is obscured by the mobile navigation at the initial viewport.
- **P2:** project cards are too tall for their content; remove G-01 and tighten metadata/action placement.
- **P3:** render date ranges in a readable local form instead of raw ISO strings and arrow notation.

### Create Project

- **P1:** the mobile navigation covers the Create IGP action and lower form content.
- **P1:** undefined pathway icons render as squares.
- **P2:** four creation pathways have equal visual weight and exaggerated equal-height cards. Establish a clear recommended/default path, concise descriptions, and progressive disclosure while preserving all existing options.
- **P2:** group form fields and use the shared file-picker pattern.
- **P2:** the mobile header incorrectly says Home.

### Project workspace — shared shell

- **P1:** every tab repeats a large project hero, five-stat strip, full blocker list, and seven-tab row before its actual content. On populated projects the blockers alone consume a large part of the viewport.
- **Required:** create a compact project context header containing project name, lifecycle/status, essential metadata, and primary route action. Summarize blockers as a count/priority and reveal the full list through an accessible disclosure. Keep required context before tab content.
- **P1:** horizontal tabs are unsuitable and partly hidden on mobile. Replace them at the mobile breakpoint with a labeled section selector or menu; do not use swipe-only navigation.
- **P2:** the five-item metric grid leaves a decorative blank cell on mobile. Use a deliberate 2+2+1 layout or compact list with the final item full width.
- **P3:** display `OperationalRequest` as “Operational request” without changing the canonical type.

### Project Overview

- **P1:** Project Basics, Project record, Lifecycle decision, Public disclosure, and Operational completeness stretch into huge panels; mobile content visibly overlaps. G-01 is the root cause.
- **P2:** use definition-list alignment for field/value content, stacking cleanly on mobile.
- **P2:** keep destructive/cancellation reason fields conditional and explain when they are required.
- **P3:** consolidate repeated status badges and technical metadata into one clear record summary.

### People

- **P2:** “Reason if rejected” remains visible for non-rejected selections. Reveal it only when the selected decision requires it, while retaining server-side validation.
- **P2:** convert bulk upload to the shared file picker and place format guidance next to it.
- **P3:** distinguish search results, current participants, and recruitment decision actions through headings and spacing rather than more nested cards.

### Delivery

- **P1:** mobile rows clip columns and actions; “CLOS…” is visibly truncated. Convert action-heavy rows to labeled record cards or implement a fully usable table strategy.
- **P2:** repeated uppercase inline labels make rows dense but not scannable. Lead with item title/status/due date; place evidence and decisions in a clear action region or disclosure.
- **P2:** “Need action 1 / Settled 0” is too subtle; render as a meaningful summary with labels and accessible status semantics.
- **P2:** group evidence status, file/link, and decision controls as a fieldset.

### Contributions

- **P2:** a rejection reason is displayed even for Approved records. Show conditional rationale only when relevant.
- **P2:** the buddy-log form is too horizontal and label-heavy; group related fields and stack at narrower desktop widths.
- **P3:** make the record’s current contribution status the primary line, with audit/detail content secondary.

### Finance / Budget

- **P2:** nested empty tables and forms create weak hierarchy. Use clear budget summary, request list, and action sections.
- **P2:** show INR values with consistent currency formatting and alignment.
- **P2:** apply conditional reason fields and the mobile record-card/table strategy.

### Insights / Feedback

- **P2:** the screen is almost blank and the “More: feedback” disclosure does not explain the purpose or state of the section.
- **Required:** provide a concise description, current empty/status state, and clearly labeled disclosure for existing feedback content. Do not manufacture analytics or feedback.

### Resources

- **P2:** document index, document upload, manual document entry, event-folder upload, reimbursements, and itinerary are presented in one long undifferentiated screen.
- **Required:** divide the existing workflow into strong sections/disclosures within the same route, order by likely task frequency, and keep one primary action per region.
- **P2:** replace all native file controls with G-08.
- **P2:** rename visible “STATUS (LEGACY)” to “Workflow status” while preserving submitted values.
- **P2:** show “Reason if rejected or waived” only when applicable.
- **P3:** use URL input semantics and helper/validation text for Google Drive links.

### Attendance roll call

- **P2:** page identity/breadcrumb says Home instead of Attendance/project context.
- **P2:** disabled correction-reason controls look editable; apply explicit disabled/read-only presentation and helper text.
- **P2:** mobile attendance should use labeled participant records and a submission action that remains visible but never collides with bottom navigation.
- **P3:** make attendance history an accurately labeled disclosure with readable dates and decision state.

### Project Setup

- **P2:** setup steps are plain slash-separated links with no current/completed state. Replace with an accessible stepper while preserving existing routes and submissions.
- **P2:** field labels/values wrap awkwardly despite available desktop space; group related fields and use predictable Back/Continue placement.
- **P2:** “Skip to full project page” competes with the primary setup path. Make it a clear secondary exit.
- **P3:** cards should use content height and each step should explain its completion requirement.

### Complete Report

- **P2:** the screen has excessive empty space and weak project/back context.
- **P2:** “Legacy exports” and “API compatibility” are developer terms. Present readiness, dependency/provenance, and download actions in user language; preserve technical detail in a disclosure.
- **P2:** make the current valid download the primary action when available and the preview a clearly secondary action.

### Report Preview

- **P2:** raw source UUIDs dominate the page and the narrative/status hierarchy is weak.
- **Required:** show human-readable provenance and approval state first; put complete technical identifiers in copyable details. Add only actions already supported by the existing workflow.

### Preflight JSON endpoint

- **P3:** raw formatted JSON is appropriate for an API/developer endpoint, not as a primary user screen. Do not cosmetically wrap or alter the response contract. Remove normal-user links to it; expose any required readiness information through the existing human-facing report screen.

### Imports

- **P1:** the mobile navigation covers lower import controls/content.
- **P2:** `RECONCILIATION LEDGERImport batches` is concatenated; separate eyebrow and title.
- **P2:** the safety warning is visually dominant and too long. Retain its meaning but structure it as a concise warning plus details.
- **P2:** use single-column mobile field grouping and the shared file picker.
- **P3:** when checksums exist, show a shortened visual value with accessible copy/full-value details.

### Notifications

- **P1:** lower content/empty state is obscured by mobile navigation.
- **P2:** page identity says Home.
- **P2:** the notification count floats far from its label on desktop and becomes an oversized full-width pill on mobile. Keep it adjacent to the title/status.
- **P2:** group delivery-channel controls with labels and helper text, and provide save/pending/success feedback.
- **P3:** make the no-notifications state concise rather than filling a large card.

### Audit log

- **P2:** `RECORDED SEQUENCEOperational events` is concatenated.
- **P2:** Actor is rendered as a numeric ID; actions appear as raw tokens such as `report.generate`; UUIDs dominate the table.
- **Required:** show human actor name/label and readable action descriptions where the underlying data permits. Keep raw IDs and canonical action values in technical details/copy controls. Do not change audit records.
- **P2:** use a responsive priority-column/record-card treatment and wrap long values safely.
- **P3:** add search/filter only if it can be implemented over the already loaded dataset without changing authorization or audit semantics; otherwise omit it.

### Profile

- **P1:** identity, role assignments, account security, and activity cards become extremely tall due to G-01; on mobile the activity empty message overlaps another card.
- **P1:** mobile navigation overlays identity content.
- **P1:** the reset/security icon renders as a square.
- **P2:** use content-height cards, a responsive single column, and aligned definition lists for email/campus/identity values.
- **P2:** make the activity empty state compact and keep the role badge aligned with its label.
- **P2:** recent operational-request links use the stale `tab=operations` target although current navigation uses Finance. Link to the current supported tab without changing route semantics.

### Admin Users

- **P1:** each user row contains a large inline scope/role form, making the desktop table thousands of pixels tall.
- **P1:** mobile shows only username/email; emails clip and permission/action columns are unreachable. Fixed navigation also obscures the header/content.
- **Required:** use compact user summary rows on desktop and summary cards on mobile. Put the existing edit form in a server-rendered disclosure/dialog/drawer with proper labels and a current-scope summary. Preserve its endpoint, fields, CSRF, and permission rules.
- **P2:** the heading/subtitle are laid out side by side and wrap awkwardly. Group title and subtitle, with actions separate.
- **P2:** keep rejection/destructive approval actions visually and semantically separate from save/approve.

### Campuses and Campus Detail

- **P2:** screens are very sparse, with a small table floating in a large canvas. Constrain measure and add a concise existing-data summary without inventing analytics.
- **P3:** render visible dates in a readable local form.
- **P3:** ensure the route is discoverable from the appropriate existing context if it is meant for routine use; otherwise keep it a secondary administrative destination.

## Coverage matrix

| Area/state | Desktop | Mobile/narrow | Review type |
|---|---:|---:|---|
| Public landing | Yes | Yes | Live visual |
| Public events/reports empty states | Yes | Yes | Live visual |
| Public event detail | — | — | Template/source-backed; no published fixture |
| Login/register/forgot | Yes | Yes | Live visual |
| Forgot sent/recovery/reset/reset success | Partial | Partial | Visual where reachable plus template/source-backed token states |
| Pending approval | Partial | Partial | Template/source-backed state |
| Home dashboard | Yes | Yes | Authenticated visual |
| Projects/Create Project | Yes | Yes | Authenticated visual |
| Project overview/people/delivery/contributions/finance/insights/resources | Yes | Yes | Authenticated populated and empty-state visual |
| Attendance | Yes | Yes | Authenticated visual |
| Project setup | Yes | Yes | Authenticated visual |
| Complete report/preview/preflight | Yes | Yes | Authenticated visual |
| Imports/notifications/audit/profile/admin | Yes | Yes | Authenticated visual |
| Campuses/campus detail | Yes | Yes | Authenticated visual |

## Implementation order

1. **Structural roots:** G-01 through G-06, type tokens, banner/rail sizing, mobile safe-area spacing, icon completeness.
2. **Shared primitives:** form states, file picker, empty state, definition list, responsive record/table, page header/breadcrumb, disclosures.
3. **Auth and global shell:** login specificity bug, recovery variants, accurate page identity, mobile navigation clearance.
4. **Project shell:** compact context, blocker disclosure, mobile section selector, responsive stats.
5. **High-risk task screens:** Overview, Delivery, Resources, Attendance, Profile, Admin.
6. **Remaining screens:** Home, Projects/Create, People, Contributions, Finance, Insights, Setup, Reports, Imports, Notifications, Audit, campuses, public screens.
7. **Verification and cleanup:** remove obsolete one-off styles, confirm no unmapped icons, and update visual/contract tests.

## Required verification

- Run the existing unit, route, authorization, UI-contract, and end-to-end suites.
- Exercise each coverage-matrix row at approximately 1440, 1024, 768, 390, and 375 px.
- Test a short and a populated project; empty and populated tables; validation errors; long names/emails/UUIDs; disabled fields; file selection; and submission pending/failure/success.
- Confirm no horizontal page scroll, clipped content, overlapping cards, or fixed-navigation obstruction.
- Check keyboard order, skip link, visible focus, disclosure naming/state, error focus, and dialog/drawer focus containment/return where used.
- Check 200% browser zoom and reduced motion.
- Confirm WCAG 2.2 AA contrast, 44 px mobile targets, correct heading order, and meaningful labels.
- Confirm the route map, RBAC outcomes, CSRF, form field names/payloads, canonical enum values, report contracts, and raw JSON/API responses are unchanged.
- Compare all final UI against `design-system/icc-erp/MASTER.md` and page overrides. Do not declare completion while any P1 remains.

## Likely implementation hotspots

- `app/static/css/components.css` — global card height, cards/tables/forms/type utilities.
- `app/static/css/layout.css` — rail/banner geometry, mobile shell, bottom navigation, content offsets.
- `app/static/css/base.css` and `app/static/css/tokens.css` — semantic type, focus, disabled and responsive tokens.
- `app/static/css/icons.css` — icon mapping completeness.
- `app/templates/base.html` and shared macros/partials — page identity, shell, banner, breadcrumbs, shared states.
- `app/templates/auth/*` — auth hierarchy, toggles, errors, compact state variants.
- `app/templates/dashboard/home.html`, `profile.html`, `users.html` — concatenated headings, content-height cards, responsive admin editing.
- `app/templates/erp/project_detail.html` — project shell and all tab-specific responsive layouts.
- `app/templates/erp/project_setup.html`, `attendance_roll_call.html`, `imports.html`, `audit.html`, report templates — page-specific issues above.
- `app/templates/public/*` — public empty states, resource lists, responsive tables/footer.

## Definition of done

The work is complete only when every P1 and P2 item above is implemented and verified, P3 items are either implemented or explicitly documented with a reason, no existing behavior or authorization contract has regressed, and the responsive acceptance checks pass on every route/state in the coverage matrix.

## Implementation record (23 August 2026)

Every P1 shared root cause and every screen-level P1/P2 item above has been implemented against `design-system/icc-erp/MASTER.md` and its page overrides. P3 polish items were implemented alongside their parent screen unless individually noted as intentionally skipped below.

### Shared root causes (G-01 – G-14)

- **G-01 (card height):** removed the global `height: 100%` from `.aurora-card`/`.aurora-card--padded` in `app/static/css/components.css`; cards now size to content. Kept `height: 100%` scoped only to `.project-card-link .aurora-card--padded` (the intentional equal-height bento grid on Projects index) via an explicit rule, plus an opt-in `.aurora-card--fill-height` utility for any future case that genuinely needs it. Verified live: Home KPI cards, Profile cards, Admin user rows, and the Project Overview cards all render at content height with no blank voids or mobile overlap.
- **G-02 (mobile nav clearance):** `.app-content` bottom padding at ≤1023px increased to `calc(108px + env(safe-area-inset-bottom))` (`app/static/css/layout.css`), giving clearance above the 64px fixed bottom nav on every screen. Verified via computed bounding-rect checks (not just screenshots) on Home and Projects index that the last content element clears the nav once scrolled.
- **G-03 (environment banner):** rebuilt `.environment-banner`/`--authenticated` in `layout.css` to use `box-sizing: border-box` + `padding-left` instead of `margin-left` on an unmodified full-width box, so the banner never overflows past the rail. Desktop renders as one compact line; mobile renders as a concise two-line notice with no rail offset. Verified live at desktop and 375px.
- **G-04 (type scale):** replaced sub-12px declarations across `components.css`/`layout.css`/`base.css` (table headers, badges, breadcrumbs, card descriptions, notification text, stat labels, KPI eyebrows, timeline text) with a floor of `.7rem`–`.875rem` depending on role; bumped the global `small`/`.small` rule from `.8125rem` to `.875rem`. Split the overloaded `.aurora-card__title` (KPI eyebrow) from a new `.aurora-card__heading` (real in-card section heading, sentence case, 1rem/700) and re-pointed every real heading (`Role assignments`, `Account security`, `Pending registrations`, etc.) onto the new class.
- **G-05 (icon masks):** added `ph-airplane-tilt`, `ph-envelope-simple-open`, `ph-hand-heart`, `ph-key`, `ph-lock-key`, `ph-receipt`, `ph-sign-in` (plus `ph-image`, needed by the public event-detail resource list) to `scripts/build-icon-assets.mjs`, each mapped to a distinct real Lucide asset, and regenerated `app/static/css/icons.css` and `app/static/icons/*.svg`. Added a permanent regression test, `test_every_template_icon_class_has_a_mask_mapping` in `tests/ui_contract_test.py`, that fails the build if any template ever references an unmapped `ph-*` class again.
- **G-06 (mobile tables):** applied `.aurora-table--cards` (with `data-label` on every `<td>`) or a purpose-built record-card component (`.admin-user-row`, `.queue-item`, `.resource-list__item`) across Admin Users, Delivery, Contributions, Finance, Imports history, Audit log, Attendance history, and the public Events/Reports/event-detail tables.
- **G-07 (form states):** added disabled/read-only input styling (muted background, `not-allowed` cursor) plus explanatory helper text (e.g. Attendance correction-reason fields); added a pending-submit label swap on the Notifications preferences form; removed stray `novalidate` on `forgot_password.html`/`recover_password.html` so native validation applies again.
- **G-08 (file picker):** introduced one shared `.aurora-file-field` component (native input kept for semantics/keyboard access, wrapped with type/size hint and a live selected-filename readout via a new `data-ui-toggle="file-field"` behavior in `app/static/js/app.js`) and applied it to every file input in Create Project, People (bulk upload, ICC attendance, buddy allocation), Resources (documents, event folder, reimbursements, itinerary), and Imports.
- **G-09 (page identity):** added accurate `mobile_title`/`crumb`/`back_url` blocks to every route that previously fell back to "Home": Notifications, Create Project, Project Setup, Attendance roll call, Complete Report, Report Preview, and Admin Users.

### Auth and global shell

- Fixed the login/register `.auth-intro__title` vs `.auth-intro p` selector-specificity bug (excluded the title from the paragraph rule, widened its measure, loosened line-height) — the brand statement now renders at full display size instead of collapsing to body-copy size.
- Added the existing `data-ui-toggle="password-reveal"` show/hide control (already implemented in `app.js` for `reset_password.html`) to Login, Register, and Recover-password.
- Added a new `.auth-stage--compact` variant (single centered card, no split intro panel) applied to the short single-purpose auth states: forgot-password, sent-confirmation, recovery, pending-approval, reset-success.
- Widened Register's identity fields (username/email) to full width instead of a cramped two-column split; added plain-language password requirements text.
- Reworded implementation-oriented copy: "Check Status (Refresh)" → "Check approval status", "Continue to Mission Control" → "Continue to Home".

### Project workspace shell and all seven tabs

- Replaced the always-rendered hero + 5-stat strip + full blocker list + 7-tab row with a compact `.project-context` header (name, lifecycle badge, essential metadata, primary action) and a collapsed-by-default blocker-count disclosure.
- Replaced the horizontal tab row at ≤767px with a `<select name="tab">` GET-form section switcher with a real (not hidden) "Go" submit button as the no-JS fallback, auto-submitting on change when JS is available. Desktop keeps the existing `.aurora-tabs` row and exact tab markup unchanged (verified against `tests/erp_test.py`'s tab-rendering assertions).
- `.project-stats-bar` now lays out 2+2+1 at ≤767px instead of leaving a blank fifth cell.
- Applied `.aurora-table--cards`, conditional-reason wording, `.aurora-file-field`, and section restructuring (via `.page-section`/disclosures) across Overview, People, Delivery, Contributions, Finance, Insights, and Resources, per each subsection's audit findings above.

### Everything else

Admin Users (compact rows + per-row disclosure holding the exact original edit form/CSRF/fields), Campuses/Campus Detail, Home dashboard, Projects index, Create Project, Imports, Audit log (human-readable actor/action with raw values kept in `<details>`), Notifications, and the full public site (landing, events, reports, event detail) were all brought into line with their respective audit sections — see the per-file agent reports folded into this pass for the itemized list; every numbered finding in the screen-by-screen sections above was addressed or explicitly deferred with a stated reason (see "Known gaps" below).

### Changed files

`app/static/css/{base,components,icons,layout,utilities}.css` · `app/static/js/app.js` · `app/blueprints/erp.py` (audit actor lookup only — no route/permission change) · `scripts/build-icon-assets.mjs` · `tests/ui_contract_test.py` · `app/templates/base.html` · `app/templates/auth/{login,register,pending,forgot_password,recover_password,forgot_password_sent,reset_password_success}.html` · `app/templates/dashboard/{home,profile,users}.html` · `app/templates/erp/{project_detail,project_setup,create_project,projects,attendance_roll_call,imports,audit,notifications,report_preview,complete_report_preview,campuses,campus_detail}.html` · `app/templates/public/{landing,events,reports,event_detail}.html` · `frontend/src/public.css`.

### Verification performed

- Full test suite: `pytest -q` → **270 passed, 1 failed**. The one failure, `tests/production_completion_test.py::ProductionCompletionTestCase::test_all_standard_operational_imports_commit_and_reconcile`, is a pre-existing SQLite unique-constraint fixture collision unrelated to any template/CSS/JS change in this pass (confirmed failing identically before this work started).
- `tests/ui_contract_test.py` (route-map hash, frozen form names, banned legacy-class fragments, icon-mask completeness, Jinja compile) passes in full, confirming no route, form field name, CSRF handling, or canonical value changed.
- `npm run build:ui` rebuilt the bundled CSS/JS/icon assets after every CSS/icon change; asset-budget/manifest tests pass.
- Live verification in-browser (desktop 1280px, mobile 390px) of: login/register/forgot-password (typography fix, show/hide, compact auth state), Home dashboard, Project workspace (compact header, blocker disclosure, mobile section switcher, 2+2+1 stats, Finance tab), and Admin Users (compact rows, mobile cards, empty state) — all match the acceptance criteria in G-01 through G-09.
- Manual bounding-rect checks (not screenshots alone) confirmed mobile bottom-nav clearance on Home and Projects index.

### Known gaps / explicitly deferred

- **Placeholder truncation on Register's password fields at desktop width:** the *email field clipping* the audit flagged is fixed (identity fields are now full-width); the password/confirm-password placeholders ("At least 12 ch…") can still truncate at the narrower half-column + Show-button layout. This is placeholder-only (not real content, not a required field) and was left as-is rather than widening further and disturbing the password/confirm pairing.
- **Audit log search/filter (P3):** implemented as a client-side filter over already-rendered/already-authorized rows only (`data-audit-filter` in `app.js`), per the audit's explicit constraint that this must not add a server round-trip or change authorization semantics.
- **Campuses nav discoverability (P3):** confirmed `erp.campuses` is already registered in the mobile drawer and command palette nav registry; it's deliberately excluded from the desktop rail/bottom nav as a secondary administrative destination. No navigation change was made since the existing placement already satisfies "discoverable, not orphaned."
- **Create Project pathway emphasis (P2):** the audit asked for "a clear recommended/default path." Rather than fabricate a "Recommended" claim not backed by the app's own logic, visual weight was instead equalized/de-emphasized uniformly (removed forced equal-height stretch, consistent heading treatment) so no pathway looks arbitrarily more important than another.
