# ICC ERP UI Functional-Parity Contract

Status: release-blocking contract  
Rule: visual migration may change markup and styling, never observable ERP behavior

## 1. Parity definition

For the same database fixture, session, role/scope, URL, query string, and user action, the upgraded interface must produce:

- The same reachable route and HTTP method.
- The same submitted field names and semantic values.
- The same authorization outcome and protected-data exposure.
- The same validation/audit/business operation.
- The same redirect destination, status class, and materially equivalent feedback.
- The same persisted records, versions, reports, files, and offline/security side effects.

DOM structure, CSS classes, visual hierarchy, copy improvements, and progressive enhancement may change only within those boundaries.

## 2. Files outside presentation scope

UI work must not modify these without a separately approved functional change:

- `app/models/**`
- `app/services/**`
- `migrations/**`
- Database schema or seed/import normalization
- Authorization role/permission maps
- API request/response schemas
- Lifecycle transitions and closure blockers
- Report calculations/export content
- Password, CSRF, session, audit, Drive, notification, and offline security rules

Blueprint/template-call edits are allowed only when needed to pass presentation data safely, select a v2 template, or include versioned assets. They may not broaden queries, permissions, or mutation behavior.

## 3. Frozen baseline manifest

Implementation baseline: `tests/ui_contract/baseline.json`. Its route fingerprint, form names, navigation authority, outcome classes, sensitive-data exclusions and shared runtime references are enforced by `tests/ui_contract_test.py`.

The machine-readable baseline contains:

- Flask URL map: endpoint, rule, methods and parameter converters.
- Template route mapping.
- Per-page form action, method, encoding, named successful controls, fixed option values, hidden inputs and submitter values.
- Authorized navigation destinations for each test identity.
- Status code, redirect and flash fixtures for success and failure journeys.
- Sensitive-data absence assertions.
- Current service-worker, manifest and shared-script references.

The manifest is reviewed once and thereafter changed only with explicit product approval. UI migrations consume it; they do not regenerate it from the new UI.

## 4. Global browser contracts

### 4.1 Forms

- Preserve `action`, `method`, and encoding.
- Preserve every successful control `name`; do not rename to suit React conventions.
- Preserve option/submitter `value` strings including capitalization and spacing.
- Preserve native omission behavior for unchecked checkboxes and disabled controls.
- Preserve hidden `version`, scope identifiers and any explicit `csrf_token`.
- Central CSRF injection in `app.js` remains effective for every POST form until replaced by an equivalently tested mechanism.
- A visual loading state may prevent duplicate clicks but may not replace server idempotency or silently convert POST to `fetch`.
- Native validation may become more helpful, but it must not accept input the server rejects or block input the server accepts without an approved rule change.
- Do not nest forms or move a row submitter outside its form without an explicit `form` attribute and parity test.

### 4.2 Links and navigation

- Keep real `href` values for all destinations and exports.
- Do not use click handlers as the only navigation mechanism.
- Preserve query strings such as `academic_year_id` and `tab` and fragment identifiers where present.
- Browser Back/Forward must restore the same logical location. Enhancements preserve filter values and scroll when feasible but never rewrite history unexpectedly.
- External Drive references retain `target`, `rel`, permission checks and audited redirect behavior.

### 4.3 Role and scope visibility

- Server/Jinja remains the only authority deciding whether protected content/action/navigation renders.
- Hidden CSS, disabled buttons, encrypted props or client filtering are not substitutes for server omission.
- React-island props may contain only data already permitted and visible in server HTML for that user.
- Sensitive Drive URLs, person records, unrestricted option lists, hidden project IDs and unauthorized command destinations must not be serialized “for convenience”.
- Unknown future roles receive current server/default behavior; the frontend must not infer extra permission.

### 4.4 Feedback and focus

- Flash category meaning remains: error maps to danger; success/warning/info remain distinct.
- Toast enhancement must not consume/remove the source message before assistive technology can announce it.
- After server error, focus the error summary or H1 without bypassing native page load.
- After 409 or validation error, preserve safe user-entered values when the existing server returns them; never retain passwords, tokens or restricted references in client storage.

### 4.5 Charts and data

- Chart transformations are presentation-only. Labels, series values, grouping and time period must match server data.
- Replacing chart type requires the same analytical meaning and visible numeric fallback.
- Never round stored/displayed values differently from existing business/report semantics without explicit approval.

### 4.6 PWA/offline

- `/static/sw.js`, manifest registration and online behavior remain intact.
- `ICCOffline.refresh/read/purge` semantics remain unchanged.
- Logout continues to purge the session key and IndexedDB snapshots.
- Offline UI is read-only and must not queue mutations unless a new product/security contract is separately approved.

## 5. Form payload contracts

The lists below are minimum named-control contracts from current templates. Dynamic row-specific names and submitter values must also be captured in the baseline manifest.

### Authentication

| Route | Method | Named controls |
|---|---|---|
| `/login` | POST | `username`, `password`, injected/explicit `csrf_token` |
| `/register` | POST | `username`, `email`, `password`, `confirm_password`, `preferred_role`, `campus_id`, `skills`, `interests`, CSRF |
| `/reset-password` | POST | `new_password`, `confirm_password`, CSRF |
| `/forgot-password` | POST | `identifier`, CSRF |
| `/recover-password/<token>` | POST | `new_password`, `confirm_password`, CSRF; token remains only in action URL |

Password fields must never be reflected into HTML, logs, React props, analytics or local/session storage.

### Dashboard and administration

| Action family | Required names/values |
|---|---|
| Academic-year filtering | GET `academic_year_id` |
| Contribution/buddy decisions | POST `action` with current server-approved values; IDs stay in route parameters |
| User approval | POST `role`, and applicable `campus_public_id`, `academic_year_public_id`, `wing_public_id`, `project_public_id`, `platform_scope`, `can_view_sensitive_links` |
| User rejection | Existing action route and CSRF; do not invent deletion semantics |
| Modify role | Same role/scope names as approval |

Conditional scope fields may be visually hidden only when irrelevant; disabled/omitted submission behavior must match the current handler expectations.

### Legacy campus project workspace

Retain current action URLs and applicable names:

- Participants: `user_id`, `participant_type`, nationality/identity fields currently present.
- Attendance: `date`, dynamic `status_<user-id>` and/or `user_ids` exactly as current template submits.
- Contributions: `activity_type`, `activity_date`, `duration_hours`, `description`, `division`, `submission_type`; decision `action`.
- Buddy assignment/logs: `buddy_user_id`, `exchange_student_id`, `buddy_assignment_id`, `date`, `duration_hours`, `activity_type`, `comments`; decision `action`.
- Feedback: `rating`, `comments`, `suggestions`.
- Documents: `title`, `document_type`, `google_drive_link`, `description`.
- Report shortcuts/filters: current `report_type`, date, campus/program/project identifiers.

The upgrade must capture the exact successful-control set per each of the 20 existing forms before migration because conditional sections can change which controls submit.

### ERP projects and decisions

| Route/action family | Required names |
|---|---|
| Create project | `title`, `description`, `project_type`, `category`, `campus_public_id`, `program_type_public_id`, `academic_year_public_id`, `wing_public_id`, `start_date`, `end_date`, `venue`, `target_audience` |
| Lifecycle transition | `version`, `target_status`, `reason` |
| Add task | `title`, `priority`, `mandatory_for_closure` |
| Update task | `version`, `status`, `comment` |
| Update checklist item | `version`, `status`, `comment` |
| Stage import | `import_type` |
| Notification preference | `event_type`, `email_enabled`, `in_app_enabled` |

`version` is mandatory UI state even where the server currently defaults it. Never replace it with a client timestamp or cached object version.

### Reports

`/reports/generate` POST retains `report_type`, `title`, `description`, `campus_id`, `program_type_id`, `project_id`, `start_date`, and `end_date`.

Excel/PDF exports remain normal GET downloads and must not be fetched into client memory merely to show progress.

## 6. Mutation outcome matrix

Every mutation journey needs tests for authorized success, validation failure, unauthorized actor, missing target, repeat/double submission, and server error where feasible.

| Mutation | Success oracle | Critical failure oracle |
|---|---|---|
| Login | Session established; correct redirect | Invalid generic error; 429 lock; no account enumeration |
| Register | Pending user/profile as applicable | No partial user on validation/duplicate failure |
| Password reset/recovery | Version rotation, audit and token/session semantics | Password absent from output/storage; expired token rejected |
| User approval/role change | Same role assignment, scope and audit | Invalid cross-scope grant rejected; self-change prohibited |
| Contribution/buddy decision | Same status and feedback/audit | Unauthorized/out-of-scope decision rejected |
| Project create | Same project fields/code/status Draft and audit | Invalid date/unit/wing rejected; no partial record |
| Task/checklist update | Version increment and immutable event | 409/stale or reason rule unchanged |
| Lifecycle transition | Same transition/audit/blocker enforcement | Unsupported transition/closure blockers unchanged |
| Import stage/commit | Same checksum/idempotency/reconciliation | Error batch not committed; repeat safe |
| Notification read/preference | Own record only; critical behavior retained | Other user's notification not discoverable |
| Report generation/export | Same snapshot/data/file | Scope enforcement and human-approval semantics retained |
| Document open | Audited redirect only when authorized | Restricted URL absent and 403 without named permission |

## 7. HTTP and error contracts

- Redirect-vs-render behavior remains unchanged for successful/failed authentication and forms unless an approved test updates it.
- 403 pages/messages must not disclose record title, sensitive classification, user membership or valid IDs.
- 404 does not distinguish nonexistent from unauthorized where the server intentionally avoids disclosure.
- 409 conflict is not presented as success; a client may explain it but cannot auto-overwrite/retry with a new version.
- 422 remains distinguishable from 500 for malformed/required values where the route uses it.
- 429 retains retry-later semantics and does not auto-resubmit.
- 500/timeout UI must distinguish known failure from uncertain mutation outcome.

## 8. Client-storage and serialization contract

Allowed local persistence:

- Non-sensitive presentation preferences such as collapsed rail.
- Existing encrypted offline snapshot and ephemeral key behavior.

Prohibited:

- Passwords, reset tokens, CSRF tokens outside current DOM/session mechanisms.
- Sensitive links, form drafts containing personal/restricted data, full user lists, approval payloads, project authorization maps.
- Server flash content retained after its intended session/page lifecycle.
- React state persisted merely to survive navigation when the URL/server is the source of truth.

Island props use `<script type="application/json">` with safe JSON escaping, a minimal allowlist, and no HTML interpolation. CSP nonces/hashes are used if policy requires them.

## 9. Automated parity tests

### Static contract tests

For every rendered fixture:

- Extract forms and compare action/method/names/fixed values with baseline.
- Extract authorized links and ensure required destinations exist and forbidden destinations/identifiers do not.
- Assert one H1, unique IDs, associated labels, CSRF presence, version presence and no nested forms.
- Assert no restricted sentinel values appear in HTML, attributes, JSON props or source maps.

### E2E request assertions

Playwright records the submitted request for each critical form and compares URL, method and form-data keys/values with the baseline fixture before allowing the response assertion.

### Database/audit assertions

After each mutation, existing model/service tests plus UI journeys assert the same database fields, version increments, audit event types, notification behavior and redirect/flash outcome.

### No-JavaScript assertions

Critical journeys—authentication, project creation, task/checklist/lifecycle decisions, imports, notifications, user approval, reports and legacy workspace forms—must complete with JavaScript disabled where they currently do.

## 10. Change-control rule

When implementation exposes an apparent functional defect or desirable UX change:

1. Stop that slice.
2. Record it as a separate functional-change proposal.
3. Complete or test the visual migration against current behavior.
4. Implement the functional change only after explicit approval, separate tests and audit/security review.

UI polish is never used to smuggle in altered business behavior.

## 11. Parity sign-off

A page is parity-approved only when:

- Baseline form/link/role assertions pass.
- Success and failure journeys pass for applicable actors.
- Sensitive-data absence passes.
- No-JS critical behavior passes.
- Existing Python suite remains green.
- Reviewer records the baseline ID, new screenshot ID, test run and any approved copy-only differences.
