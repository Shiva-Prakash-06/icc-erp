# ICC ERP UI Page and State Matrix

Status: implementation contract  
Purpose: remove page-level ambiguity before visual implementation

## 1. Actors and test identities

Every page family must be exercised with the applicable representative identities below. “Role” refers to current server behavior; the redesign must not reinterpret it.

| Fixture | Representative role/state | Expected shell |
|---|---|---|
| A0 | Anonymous | Authentication shell only |
| A1 | Pending account | Pending shell; no ERP navigation |
| A2 | Rejected/archived account | Authentication feedback; no ERP content |
| A3 | Faculty / OIA faculty administrator | Full authorized navigation and administrative actions |
| A4 | ICC core/head | ICC-scoped dashboard/actions |
| A5 | IGP core/head | IGP-scoped dashboard/actions |
| A6 | Volunteer/ICC associate | Personal/assigned dashboard and project actions only |
| A7 | Buddy | Personal/assigned dashboard plus buddy workflows only |
| A8 | Participant/exchange student | Personal/assigned read access only |
| A9 | Auditor/read-only | Reports/audit only according to active scope |
| A10 | Approved user lacking target scope | 403 or absent record/action, exactly as current server decides |
| A11 | Named sensitive permission | Restricted-reference affordance available within scope |

## 2. Global states required on every applicable page

| State | Required behavior |
|---|---|
| Initial | H1, location, primary content and primary action render server-side |
| Empty | Specific explanation; action only if authorized; never imply out-of-scope data does not exist |
| Typical | Representative demonstrator data |
| Dense | Long text and at least 50 rows/items where the view can contain them |
| Flash success/info/warning/error | Correct live-region behavior; long error remains inline |
| 403 | No protected record details or unauthorized navigation serialized |
| 404 | Clear return destination; no guessed record information |
| 409/stale version | Reload-latest recovery and preservation of safe attempted input |
| 429 | Rate-limit message and retry-later guidance; fields remain safe |
| 500/timeout | State uncertainty explained; no unsafe blind retry |
| Offline | Existing cached read-only behavior identified; mutation attempts are not presented as saved |
| Reduced motion | No parallax, stagger, count-up, large transform or perspective tilt |
| No JavaScript | Navigation, content, forms, flashes and exports remain usable |
| Mobile/zoom | 375px, landscape phone, 200% and 400% zoom without lost actions/content |
| Print | Reports/audit/project summaries only; shell/actions removed, status meaning retained |

## 3. Authentication pages

| Route/template | Actors | Primary UI and actions | Mandatory states and edge cases |
|---|---|---|---|
| `GET/POST /login` · `auth/login.html` | A0, A2 | Username/email, password, Sign in; Register and Forgot password links | Invalid credentials without account disclosure; five-failure lock; locked response 429; pending redirect; forced-reset redirect; password-manager/autofill; long error; return from logout |
| `GET/POST /register` · `auth/register.html` | A0 | Username, email, password/confirmation, preferred role, campus, conditional skills/interests; Create account | Missing fields; mismatch; weak/breached password service failure; duplicate username/email; volunteer/buddy conditional fields; no campus; rate limit; retained non-password values; pending redirect |
| `GET /pending-approval` · `auth/pending.html` | A1 | Pending explanation and Log out | Anonymous redirect; approved user redirect; long username; no false ETA; no ERP nav |
| `GET/POST /reset-password` · `auth/reset_password.html` | Signed-in forced-reset user | New password/confirmation, Reset password, Log out | Policy error; mismatch; session-version rotation; pending vs approved success destination; password-manager; form not shown when reset unnecessary |
| `GET/POST /forgot-password` · `auth/forgot_password.html` | A0 | Identifier and Send recovery link | Same generic success for existing/non-existing/ineligible account; rate limit; email delivery failure does not disclose account |
| `GET/POST /recover-password/<token>` · `auth/recover_password.html` | Valid token holder | New password/confirmation and Set password | Invalid/expired/used token; mismatch; policy error; successful invalidation and sign-in destination; token never exposed to analytics/client props |

## 4. Application shell

Source: `base.html`, shared by every signed-in page.

| Region | Desktop | Mobile | Contract |
|---|---|---|---|
| Demonstrator banner | Top, non-dismissible | Top, wraps | Exact warning retained and announced once |
| Primary navigation | Expanded/collapsible 248/76px rail | Four top destinations plus Menu; role-aware | Same authorized destinations as current Jinja conditions; `aria-current`; no unauthorized URLs in command data |
| Top bar | Context title, academic year, command trigger, user actions | 56px title/back/menu; safe-area aware | Predictable back destination; no hard-coded record IDs; academic-year label remains informational unless page exposes a filter |
| Main | Offset from rail/top; max 1600px | Bottom padding includes nav and safe area | Skip target, one H1, flashed feedback before page content |
| Command palette | Keyboard-accessible island + fallback | Full-width dialog | `Ctrl/Cmd+K`, arrows, Enter, Escape; authorized static destinations only |
| Logout | Separated in user footer/menu | Separated in menu | Existing GET route and offline purge listener preserved until backend contract changes separately |

Shell states: expanded/collapsed rail, long username/role, no campus, active deep route, multiple flashes, command no results, 400% zoom, software keyboard, landscape phone, JS mount failure.

## 5. Dashboard pages

All use `GET /?academic_year_id=<id>`. The query parameter, default-year fallback, and server-selected dataset remain unchanged.

| Template/actor | First-viewport priority | Actions/data that must persist | Required edge states |
|---|---|---|---|
| `dashboard/index.html` · A3 | Pending decisions, global KPIs, active projects | Academic-year filter; campus drill-down; user approve/reject forms; contribution and buddy verification forms; active/upcoming projects; recent activity; current charts | No years; no pending actions; all queues dense; zero chart data; stale decision; missing campus; long project titles; mixed flash results |
| `dashboard/icc_core.html` · A4 | Scoped pending contributions, ICC KPIs/projects | Academic-year filter; scoped approvals; campus/project links; recent activity; upcoming events | Missing user campus fallback; no ICC program type; empty scoped queues; attempted out-of-scope project; dense pending contributions |
| `dashboard/igp_core.html` · A5 | Contributions and buddy-log decisions | Academic-year filter; contribution/buddy verification; scoped projects/activity/events | Same as ICC plus no buddy assignments/logs; dense dual queues; identical-looking users/projects; long interaction notes |
| `dashboard/volunteer.html` · A6/A7/A8/default approved role | Personal pending work and assigned projects | Academic-year filter; approved/pending contributions; buddy logs; attendance; enrolled projects; assignments | No assignments; participant with no user activity; buddy with no logs; zero hours vs missing hours; out-of-scope deep link; long personal history |
| `dashboard/profile.html` · signed-in | Identity, role/scope and personal performance | Existing profile data, contribution/buddy/attendance history and project links | No person profile; no volunteer profile; missing campus; unknown role; long email/skills/interests; empty history |

Dashboard composition:

- At 1440px: 12-column grid; KPI row, primary chart/operational queue, activity/upcoming regions.
- At 768–1023px: 8-column grid; queue before secondary charts.
- Below 768px: single column; blockers/pending actions before charts; secondary KPIs in disclosure.
- Scrollytelling, when enabled, begins after all current actionable content and duplicates no unique information or controls.

## 6. Administration

| Route/template | Actors | Actions | Required states |
|---|---|---|---|
| `GET/POST /admin/users` · `dashboard/users.html` | `manage_users` only | Review pending; approve with role/scope; reject; modify approved-user role/scope | No pending users; no approved users besides self; invalid role; required year/wing/project absent; out-of-unit wing/project; sensitive permission disallowed; self-role change prohibited; concurrent update; long identity fields |

Rules:

- Scope fields progressively disclose based on selected role but remain standard named controls.
- Before approval/role change, show a plain-language scope summary derived from visible selections; the server remains authoritative.
- Reject/destructive action is visually separated and confirmed with username/email but must submit the same form payload.
- Existing server flashes and audit creation are the outcome oracle.

## 7. Campus hierarchy

| Route/template | Actors | Content/actions | Required states/mobile treatment |
|---|---|---|---|
| `GET /campuses` · `campus/list.html` | Non-volunteer roles under current legacy check | Campus cards and summary counts | Zero/one/many campuses; long campus name; missing codes/counts; unauthorized volunteer 403; cards become one-column list mobile |
| `GET /campuses/<id>` · `campus/campus_detail.html` | Same | Campus summary and ICC/IGP program destinations | Missing campus 404; no program types; zero metrics; program cards stack mobile |
| `GET /campuses/<id>/program/<name>` · `campus/program_detail.html` | Same | Project directory and project summaries | Unknown program/campus 404; no projects; dense/long titles; read-only table becomes record cards mobile |
| `GET /campuses/<campus>/projects/<project>?tab=` · `campus/project_detail.html` | User passing `has_contributed_to_project` | Legacy project workspace with tabs `overview`, `people`, `operations`, `insights`, `resources`, `attendance` | Invalid tab falls back to overview; mismatched campus redirects to canonical project campus; unauthorized 403; 20 forms/7 tables; section state matrix below |

### Legacy campus project workspace sections

| Tab | Server content/actions to preserve | Empty/error/dense/mobile requirements |
|---|---|---|
| Overview | Project identity, dates/status, progress, core analytics, report link | Missing venue/audience; no activity; long description; lifecycle/status unknown; summary stacks without hidden data |
| People | Participants; Add participant | No available users; duplicate attempt; many participants; role/type labels; form and participant table become record layout |
| Operations | Contributions, buddy assignments/logs; Log and verify actions | No assignments; pending/approved/rejected; missing project buddy/student; invalid duration/date; dense row forms; mobile action sheets remain native forms |
| Insights | Feedback analytics and feedback submission/review | No feedback; zero ratings; long feedback; rating boundary; chart text/table fallback |
| Resources | Document index; Add document | Invalid/long URL, missing description, restricted-looking content, inaccessible external reference; mobile records with visible type/status |
| Attendance | Attendance records; Mark attendance | No participants, no records, duplicate/correction behavior, long session/date set; mobile record forms; not a horizontally compressed grid |

Forms in this workspace retain current actions for add participant, attendance, contributions, contribution decisions, buddy assignment/log/decision, feedback, and documents. They are never converted into speculative client API calls.

## 8. ERP operations

| Route/template | Actors | Content/actions | Required states |
|---|---|---|---|
| `GET /erp` · `erp/hub.html` | Signed-in; data filtered by `can_view_project` | Stats, recent eight visible projects, Projects/Imports links when authorized | No visible projects; hidden people/import stats; dense titles; unknown status; no unauthorized counts |
| `GET/POST /erp/projects` · `erp/projects.html` | Visible list for signed-in; create requires `manage_projects` | Project list; create form with title, description, type/category, campus, program, year, wing, dates, venue, audience | Missing required; end before start; invalid unit/wing; out-of-scope new project 403; no reference data; no projects; mobile records |
| `GET /erp/projects/<public_id>` · `erp/project_detail.html` | `can_view_project` | Project metadata, sessions, tasks, checklists, team, documents, lifecycle, report preview | Missing/403; zero sections; closure blockers; long task/checklist text; restricted reference redaction; stale versions; rejected/waived reason requirements; tables with row forms become records mobile |
| `GET /erp/projects/<id>/report-preview` · `erp/report_preview.html` | `report` permission in project | Generated snapshot/provenance | 403; generation failure; large snapshot; missing values; print; no mutation controls |
| `GET /erp/imports` · `erp/imports.html` | `manage_imports` | Stage source; view checksum/counts; commit error-free uncommitted batch | No batches; missing source; stage validation errors; already committed; invalid/error count; concurrent/repeated commit; long source path/checksum; mobile records |
| `GET /erp/audit` · `erp/audit.html` | `audit` | Latest 200 immutable events | No events; exactly 200; long action/entity/request IDs; missing actor; mobile priority scroll; print |
| `GET /erp/notifications` · `erp/notifications.html` | Signed-in user | Own latest 200; mark read; change event preference | No notifications; all unread/read; critical preference cannot be disabled semantically; missing event type 422; 200 long messages; read action remains user-scoped |

### ERP project decision states

- Task/checklist: Not Started, In Progress, Blocked, Submitted, Approved, Rejected, Waived, Completed, plus unknown neutral fallback.
- `version` remains a hidden field for every update and transition.
- Rejected and waived states require the same server comment/reason rules.
- Restricted document value is absent when permission is absent—not blurred, CSS-hidden, or sent to React.
- Lifecycle region shows only server-provided transitions. No client-generated transition possibilities.
- Closure blockers are visible before/adjacent to lifecycle action and remain readable without animation.

## 9. Reports

| Route/template | Actors | Content/actions | Required states |
|---|---|---|---|
| `GET /reports` · `reports/list.html` | Signed-in; volunteer results filtered by contribution | Saved report directory; Compile report for eligible role; view report | No accessible reports; dense list; long title/type/date; report inaccessible by scope; mobile records |
| `GET/POST /reports/generate` · `reports/generate.html` | Faculty, ICC Core Committee, IGP Core, ICC Events Core, ICC Cultural Core, ICC Media Core | Report type/title/description, scope, dates; save configuration | Missing title; no campuses/programs/projects; optional scope; end-before-start behavior as server; long description; repeat submit; role 403/redirect behavior |
| `GET /reports/view/<id>` · `reports/view.html` | `has_contributed_to_report` | Summary, project details, Excel/PDF exports | 403; missing report; no projects; large report; export links; print; long narrative; null metrics |
| Export routes | Authorized viewer | Download Excel/PDF | Generation error, slow response, interrupted download, repeated click, filename safety; no React interception |

## 10. Page acceptance record

Each migrated page receives a checked record:

```text
Route/template:
Applicable actors:
Reference screenshot IDs:
Server-rendered regions:
React islands:
Forms and payload fixture IDs:
Empty/dense/error fixtures exercised:
Keyboard and focus result:
375/768/1024/1440 result:
200/400% zoom result:
Reduced-motion/forced-colors result:
No-JS result:
Print result if applicable:
Visual diff approved by:
Functional parity approved by:
```

No page may be marked complete with blank applicable fields.

## 11. Required reference-screen register

Phase 1 must produce and approve the following reference compositions before their implementation slice begins. Each ID requires 1440px and 375px variants; `D` adds dense data and `E` adds error/edge state.

| ID | Reference composition | Required variants |
|---|---|---|
| REF-01 | Authentication/login | Default, validation error, locked 429, password-manager/autofill |
| REF-02 | Signed-in shell | Faculty expanded/collapsed; volunteer mobile; deep breadcrumb; command palette |
| REF-03 | Faculty Mission Control | Typical, empty queues, dense queues, zero chart data |
| REF-04 | ICC/IGP scoped dashboard | ICC typical; IGP dual-queue dense; missing-campus fallback |
| REF-05 | Volunteer/buddy personal dashboard | Assigned typical; completely empty; long history |
| REF-06 | Campus/program/project directory | Typical cards; no projects; long titles; mobile records |
| REF-07 | ERP hub/project directory/create | Read-only role; manager create; validation error; dense projects |
| REF-08 | ERP project detail | Blocked lifecycle; editable task/checklist; restricted reference; 409 conflict |
| REF-09 | Legacy project workspace | One reference per six tabs, including form-heavy mobile states |
| REF-10 | Imports/notifications/audit | Empty and 200-row dense; import error; critical notification preference |
| REF-11 | Reports | List, compile, view, export/print and no-data report |
| REF-12 | User administration | Pending approval, role scope disclosure, rejection confirmation and invalid scope |

Reference approval covers hierarchy, density, component selection and responsive behavior. It does not authorize changes to server copy, payloads or functionality.
