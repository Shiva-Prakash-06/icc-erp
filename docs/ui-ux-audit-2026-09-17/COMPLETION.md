# Audit completion evidence — 17 September 2026

Finding-by-finding record for [`AUDIT.md`](./AUDIT.md). Every entry names what
was wrong, what was changed, and how it is held.

## A note on the visual target

The audit names `design-system/icc-erp/MASTER.md` as the source of truth. That
file described the **flat blueprint**, which was superseded on the same date by
the **ICC ERP Tile System**; the audit's own screenshots show the Tile System
shell. The conflict was raised with the product owner before any code changed,
and the decision was to **keep the Tile System** and fix the audit's substance
inside it. `MASTER.md` has been rewritten so it now describes the shipped
system rather than the one it replaced.

Two findings are therefore recorded as **superseded** rather than fixed. Both
are noted in place below.

---

## P0 — release blockers

### P0-01 — the authenticated home route returned a raw, unstyled 429 · **Fixed**

Two separate defects behind one symptom.

**Why it 429'd.** `app/database.py` declared
`Limiter(key_func=get_remote_address, default_limits=["300 per hour"])`.
Flask-Limiter's default limits are **one bucket shared across every endpoint**,
not per route — verified empirically — so a single campus behind one NAT shared
five requests a minute for the whole institution, and `/`, the destination of
every sign-in redirect, is simply the route most likely to be hit when the
budget runs out.

- The key is now the **account** for signed-in traffic and the address only for
  anonymous traffic (`rate_limit_key`), so one shared NAT no longer pools an
  allowance.
- The ceiling moved to `1200 per hour; 120 per minute`, configurable through
  `RATELIMIT_DEFAULT`. The tight explicit limits on sign-in, registration,
  password recovery and the write API are untouched — those are the abuse
  surface.

**Why the page was bare.** Every non-API error handler returned a plain string.
All of them — 403, 404, CSRF, 429, 500 — now render `app/templates/error.html`
inside the application shell, with an H1, an explanation, recovery guidance, a
safe destination, a technical-details disclosure carrying the request id, and
`Retry-After` on a 429. `/api/v1/` keeps its RFC 7807 JSON.

A third defect surfaced while testing the fix: Flask-Limiter's `before_request`
hook runs **before** the one that populates `g.user`, so a rate-limited signed-in
reader was handed the anonymous auth shell — losing exactly the identity and
navigation this finding asks the error page to keep. `_error_page` now re-reads
the session on the error path.

*Held by* `tests/ui_audit_regression_test.py::HomeRouteRateLimitTestCase` (four
tests: the key is per account, the allowance clears interactive use, a 429 keeps
the shell and its heading and offers a route out, and the API keeps
problem+json).

### P0-02 — phone layouts clipped titles, tabs and row actions · **Fixed**

- `.ds-screen__head` becomes a two-row grid below 860px: identity (breadcrumb +
  title, wrapping to two lines) above actions, which scroll horizontally rather
  than clipping.
- `.ds-row` folds into a labelled record card. Each cell prints its own column
  name from `data-label`, taken from that table's own `ds-rows__head`; the title
  wraps; actions sit inside the card at full width.
- `.ds-review__panel` becomes static and full-width on a phone — an anchored
  popover has nothing to anchor to in a 390px card.
- The grid's seven columns no longer reserve 336px for a form on every row (see
  P1-04), which is what pushed the action cell off-canvas in the first place.

*Held by* `e2e/accessibility-responsive.spec.ts` — "no row action is clipped or
off-canvas on a phone" (measures every action box against the viewport at 390px)
and "the record title is fully readable at 375 and 390 px" (asserts the title
element is not clipping its own content). Plus
`MobileActionClippingTestCase::test_every_row_cell_carries_its_column_name_for_the_card_layout`.

### P0-03 — analytics drill-down linked to the wrong filtered state · **Fixed**

The KPI counted `states["active"] + states["overdue"]`, which is
`event_state`-based and includes `Closing` and anything past its end date. Its
`href` was `/erp/projects?status=Active`, which matches the **stored column
exactly**. A `Closing` programme was therefore counted and then excluded.

- `erp.projects` accepts a **`state`** query argument filtered through
  `matches_filter`, alongside the existing `status`. Both are query arguments,
  so the frozen URL map is untouched.
- Every counter links to `state`, never to `status`.
- The label says what it counts: "Programmes in flight", not "Active
  programmes". "Reports filed · 2 of 0 closed programmes" became "0 of 1
  programmes closed", where both halves describe the same population.
- The directory screen was rebuilt on the same four reserved states, so its
  facets and the dashboard's counters cannot disagree.

*Held by* `KpiDrilldownTestCase` — four tests, including one that proves the
fixture still reproduces the original defect (`?status=Active` genuinely
excludes the `Closing` record) — and the e2e test "every linked analytics
counter opens a list containing its records", which walks every linked tile on
the dashboard and asserts the destination holds exactly the counted number.

### P0-04 — status semantics conflicted across screens · **Fixed**

`app/services/status.py` defines five named dimensions — availability,
workflow, review, publication, lifecycle — each with one vocabulary, one tone,
one icon and a sentence explaining what the dimension measures. Chips carry
their dimension, visibly on a card and in the accessibility tree everywhere.

Each reported contradiction:

| Reported | Cause | Now |
|---|---|---|
| Documents read `Missing` **and** `Approved` | two dimensions in one unlabelled voice | "File: No file" beside "Review: Submitted" |
| Verified buddy interactions in danger red under a warning triangle | `'complete' if x == 'Approved' else 'overdue'` — and the seed writes `status="Verified"`, which is not one of the three documented values, so it fell to `else` | `review_state()` maps by meaning; an unknown value degrades to **neutral**, never to danger |
| Report copy claimed authoritative sources while its own table said none were found | the sentence was unconditional | three branches on `preflight.has_authoritative_report` |
| Attendance said `Unknown verifier` | a failed name lookup printed as a fact | "Recorded during import"; the revision number moved into a technical-details disclosure |
| `2 reports filed` over `of 0 closed programmes` | two unrelated numbers presented as a ratio | both halves now count the same population |

The stored vocabulary is **not** rewritten. An early revision relabelled
`Pending` and `Submitted` both to "Awaiting review"; that collapsed two states
the records genuinely distinguish and was reverted. The dimension name and the
hint carry the explanation instead.

*Held by* `StatusContradictionTestCase` (five tests, including a rendered
`Verified` buddy log asserting no danger chip),
`report_routes_test.py::test_preview_copy_matches_the_real_dependency_mode`,
and the e2e test "no record shows two contradictory states without naming the
dimensions".

### P0-05 — mobile bottom navigation and safety banner obscured content · **Fixed**

The bar carried seven icons plus a sign-out. It now carries **four destinations
plus Menu**, capped by `navigation.MAX_BOTTOM_NAV_ITEMS`. Alerts, the account,
imports, audit, administration and sign-out moved into `.ds-menu__drawer`, a
native `<details>` that opens without JavaScript and also states the reader's
role and scope (P1-10).

The demo banner was `position: fixed` above the bar, covering the last rows of
every table. `.ds-app` is now a named-area grid (`banner / rail / screen`), so
the banner is a 24px strip that reserves its own space and covers nothing. The
bar reserves `56px + env(safe-area-inset-bottom)`, and the flash stack and
first-run aside offset from one shared `--mobile-nav-clearance`.

*Held by* `MobileActionClippingTestCase::test_the_phone_bottom_bar_carries_four_destinations_plus_menu`,
`::test_fixed_shell_furniture_reserves_layout_space`, and the e2e test "the
phone bar holds four destinations plus Menu, and covers nothing", which scrolls
each screen to its end and asserts the last element clears the bar.

---

## P1 — cross-cutting

### P1-01 — "the shell still uses the retired desktop rail" · **Superseded**

This finding asks for the rail to be replaced by the blueprint's 56px top bar.
The rail is the Tile System's deliberate choice, adopted the same day and
shipped in the build the audit screenshotted. Reverting it would undo that
decision. Confirmed with the product owner; `MASTER.md` now documents the rail.

The substance behind the finding was real and is fixed: the rail was icon-only
with no visible labels until hover, and it said nothing about who you were. It
now carries labels, and a role-and-scope line (P1-10).

### P1-02 — text hierarchy too compressed · **Fixed**

Row titles are 14/20 and wrap to two lines; card titles 15/21. Monospace is
confined to codes, dates, amounts and counts — the audit trail's prose, the
attendance verification line and the alert bodies were moved off it. Uppercase
`.09em` tracking is restricted to column heads, field labels and status words.

### P1-03 — important text truncated where space existed · **Fixed**

`.ds-row__title` wraps to two lines instead of ellipsising; `.ds-facts dd` wraps
entirely (it held operating unit, venue, audience and the date range, every one
of them the only visible copy of that fact). `.ds-row__desc` still clamps at two
or three lines, because the row links to the record that holds all of it.

The action column shrinking from 336px to 84px (P1-04) is what returned the
space to the text columns.

### P1-04 — inline editing controls made tables unreadable · **Fixed**

Ten in-row decision forms — task, checklist, budget, operational request,
reimbursement, document, recruitment, contribution, buddy log and feedback —
are now read-first rows with a `Review` disclosure. **The form inside is
byte-for-byte the one that was there**: same action, method, field names,
CSRF token, version field and server validation. It is a native `<details>`, so
it opens and closes with no JavaScript.

*Held by* `MobileActionClippingTestCase::test_a_row_decision_is_a_disclosure_not_a_form_wedged_into_a_cell`
and the e2e test "a row decision opens in place and keeps its exact payload",
which reads the rendered form's method, action and every field name.

### P1-05 — legacy and current visual languages mixed · **Fixed (within the Tile System)**

The blueprint half of this finding is superseded with P1-01. The real problem —
screens that had not been migrated — is fixed: the event directory, alerts,
imports, the complete-report page and the decision queue were rebuilt on
`.ds-rows` / `.ds-row` / `.ds-empty--block` / `.ds-chipbar`, and the native file
inputs were replaced by one shared picker (P1-13).

### P1-06 — colour contrast failed on dark tiles · **Fixed**

The cause is specificity, not a missing rule. `base.css` declares
`h1..h6 { color: var(--color-text) }` at (0,0,1); an element selector's
*explicit* colour beats an *inherited* one however specific the ancestor, so
`.ds-tile--indigo { color: #fff }` never reached its own heading. Measured
1.67:1 on indigo, 2.21:1 on pine, 2.61:1 on brass.

`--on-accent` (white) and `--on-accent-muted` (white at 88%, raised from 82% for
headroom on brass) are now named explicitly on the title and code. Measured
white 6.33–9.92:1, muted 5.33–8.14:1. `.ds-tile__code` also lost an
`opacity: .72` that multiplied against the accent rule.

*Held by* `DarkTileContrastTestCase` — four tests, one of which asserts that ink
on navy *would* still fail, so the guard cannot quietly stop guarding — and the
e2e test that measures every rendered tile's computed colours in the browser,
compositing translucent foregrounds before taking the ratio.

### P1-07 — currency, dates and numbers inconsistent · **Fixed**

`app/services/formatting.py` provides `money`, `money_exact`, `short_money`,
`number`, `percent` and `pluralise` as Jinja filters. Indian digit grouping;
trailing `.00` dropped unless the value has paise. `₹765000.00`, `INR 45000.00`
and `480000` all became `₹7,65,000`. Dates go through the existing
`localdate`/`localdatetime`; the audit trail states its timezone once in the
header instead of suffixing every row. `analytics._lakh` was retired in favour
of the shared `short_money`.

### P1-08 — terminology changed across screens · **Fixed**

`app/services/glossary.py` maps division code to display name at render time:
IGP is "International Guest Programmes", ICC is "Institutional Collaboration
Cell". The differing strings live in `operating_units.name`, seeded years ago
and referenced by imports, so the **rows are unchanged** and only the caption
moves. The sign-in lockup said "International Christite Community" under the
university wordmark — that is the ICC division, not the university — and now
says "Office of International Affairs". New installations seed the canonical
names. The interface calls a record an "event".

### P1-09 — heading structure inconsistent · **Fixed**

Administration and the profile used `<h5>` directly under the page H1 as pure
styling; those are `<h2>` regions now, styled by `.aurora-card__heading`. The
complete-report page carried its own `<h1 class="h2">` on top of the shell's
title and shipped two level-one headings; it has one. The error page takes the
same care — the body supplies an H1 only when signed out, where there is no
screen head.

### P1-10 — role context invisible · **Fixed**

`roles.role_context()` returns one line per active assignment: the role title
and what it covers, resolved from the assignment's own scope columns. It appears
as a compact badge at the foot of the desktop rail (full text in `title` and for
assistive tech) and in full at the head of the phone Menu drawer.

### P1-11 — empty and low-content screens wasted the viewport · **Fixed**

`.ds-empty--block` is a compact bounded region — icon, heading, one sentence,
one permitted action — that follows its content instead of stretching. Applied
to the event directory, alerts, imports and the report sources list.

### P1-12 — conditional fields not explained · **Fixed**

Every "If Other, specify" input and every reason-on-reject field is revealed by
CSS `:has()` on the live selection. **The rule hides**, so a browser without
`:has()` drops the selector and both fields stay visible — the behaviour before
the change, never a field the reader cannot reach. No JavaScript is involved,
which the no-JS contract requires. The inputs keep their names, labels and
server validation; a hidden field submits empty exactly as an untouched one did.

The task and checklist "Reason or comment" fields are deliberately **not**
conditional: that field is a comment, useful on every status and required on
none.

`aria-expanded` is not applied, because there is no disclosure widget — the
field appears and disappears with the select's value, and the select is the
labelled control. This is a stated deviation from the finding's wording, not an
oversight.

### P1-13 — native upload controls did not match the product · **Fixed**

One `file_picker` macro covers all ten file inputs. It keeps the **native**
`<input type="file">` and styles it in place — including
`::file-selector-button` — rather than hiding it behind a fake button, so the OS
picker, drag-and-drop, keyboard operation, forced-colors and no-JS submission
all keep working. Accepted types and the size limit are stated and wired through
`aria-describedby`; the duplicated "No file selected" readout is gone (the
native control already says it); the full-width submit buttons beside pickers
are sized to their content.

`tests/ui_contract_test.py::test_frozen_form_names_remain_in_server_templates`
was **strengthened** rather than relaxed to accommodate this: it used to grep
template source for a literal `name="source_files"`, which the macro no longer
contains. It now renders the macro and asserts against the HTML the server
actually sends, so a name misspelled inside the macro fails where it would
previously have passed.

### P1-14 — fixed controls and overlays needed collision rules · **Fixed**

The demo banner moved into the shell grid (P0-05). One
`--mobile-nav-clearance` token offsets the flash stack and the first-run aside.
The z-index scale in `tokens.css` is unchanged and now actually used by the
review panel and the Menu drawer.

**The print stylesheet was broken and is rewritten.** Every selector in it named
the pre-Tile shell — `.app-rail`, `.app-topbar`, `.mobile-bottom-nav`,
`.app-shell`, `.app-content` — none of which exists. Because `.ds-app` is
`height: 100dvh; overflow: hidden` with a single inner scroller, a report
printed the navigation rail and exactly one viewport, silently dropping
everything below the fold. The audit's acceptance check "reports, audit and
summaries have usable print styles" could not have passed. The frame is now
unclamped for print, disclosures print open, rows print as labelled blocks, and
external links print their target.

---

## Screen-specific findings

| Screen | Status |
|---|---|
| Authentication | Lockup wording fixed (P1-08). **Deferred:** the "Create Command Account" rename, the volunteer field grouping and the recovery back-link — copy and form-grouping changes on screens the audit rated cleanest. |
| Event directory | Rebuilt: state facets with counts, one search control with Enter submission and a Clear affordance, wrapping card titles, compact empty state, glossary-correct division names. |
| New event | **Deferred.** Four equally-weighted creation paths and the marketing-styled cards remain; the file inputs on it were migrated to the shared picker. |
| Project shell / Logistics | Header rebuilt for mobile; metadata wraps; rows read-first; dates humanised. **Deferred:** "Add a checklist" still shows when one exists. |
| Finance | `Appr.` renamed to `Approved` and formatted like its neighbour; amounts through the shared formatter; decisions behind Review. **Deferred:** section-level totals, and the "Legacy value" provenance wording. |
| Documents and reporting | File and review are separate named dimensions; the complete-report page rewritten with copy that matches the real dependency mode, one H1, and the dependency table directly under the claim it qualifies. **Deferred:** splitting the four decisions in the Documents tab into separate regions, and the thin report preview. |
| People, buddy, feedback | Verified logs no longer painted as failures; cells labelled for the card layout. **Deferred:** the Team table's empty columns, the Recruitment/Team duplication, batch buddy review, and surfacing feedback moderation earlier in the tab. |
| Project analytics | KPI wording fixed; charts already carry an accessible `aria-label` naming every figure and a named legend. **Deferred:** a visible data-table fallback. |
| Six-step setup | Conditional "If Other" fields fixed. **Deferred:** stepper complete/current/revisitable states, the long team table before the add control, and the footer action pattern. |
| Attendance | Segments show the whole word, not `P/A/E/L`; unsaved rows say "Not recorded yet" beside the control that defaults to Present; disabled correction fields are visibly disabled; verification says who and when, with the revision number demoted. |
| Decision queue | Filter by kind, plain links with counts, all-items view kept as the default. The ambiguous "2 active" control now reads "2 events in flight" and links to the `state` filter. **Deferred:** grouping by urgency. |
| Administration | Section headings are semantic H2. **Deferred:** the tall empty pending panel, the scope summary in the role editor, checkbox explanations and the confirmation summary. |
| Audit history | Rewritten as When / Who / What happened, with human verb phrases and entity nouns from the glossary, timezone stated once, and all identifiers in one "Identifiers and raw values" disclosure. |
| Imports | Each template names itself and links to its own file beside the selector that uses it — the "Download a starter template" link always fetched the people template regardless of the choice. Safety note demoted below the form; batches are rows with a Provenance disclosure; a stray CSRF input outside any form was removed. |
| Alerts and preferences | "1 records" fixed; alerts link to the affected record; timestamps humanised; the preference copy names which alerts are critical. |
| Profile | Person name is the identity when one exists; "Send a password reset link" is now "Change or reset password"; recent notifications carry a date, a read state and a destination. |
| Campus and analytics directories | Dark tile contrast fixed (P1-06). **Deferred:** the decorative bar shapes that resemble charts, and the large tinted canvas around a single project card. |
| Public site | Glossary wording fixed on the landing page. **Deferred:** sharing shell components with the ERP — the public site is a separately purged bundle and the change is larger than the finding implies. |

## Verification

```
.venv/bin/python -m pytest -q          356 passed
npx playwright test                    231 passed, 1 pre-existing failure
npm run typecheck                      clean
npm run build:ui && npm run check:assets   passed
```

Playwright projects: desktop Chromium, Firefox, WebKit; Pixel 7; iPhone 13;
JavaScript disabled; reduced motion; forced colors; 200% zoom; visual.

### Pre-existing failure, unrelated to this work

`e2e/platform-matrix.spec.ts:42` — "protected workflow resources reject generic
PATCH and return RFC 7807 errors" expects 405 and receives 400. The acceptance
server runs with `WTF_CSRF_ENABLED=true`; a `PATCH` to an unrouted method has no
matched endpoint, so CSRFProtect cannot find the blueprint's exemption and
rejects with 400 before routing can raise 405. **Confirmed to fail identically
with this branch's application changes stashed.** It is an API/CSRF contract
question rather than a UI/UX one, so it is reported rather than changed here.

### Asset budget

Application CSS moved from 63.3 KiB to 71.5 KiB raw (12.7 → 14.0 KiB gzip) and
the budget was raised to 72 KiB, with the rationale recorded in
`scripts/check-asset-budgets.mjs`. The paired deletion is a purge-scope
correction worth 2.7 KiB: `templates/public_site/` is no longer in the
application bundle's PurgeCSS globs, because those pages inline a separately
purged stylesheet and never link `aurora.css` — every rule the app bundle kept
only because a public template mentioned the class was being shipped to every
signed-in page for nothing.

### Visual baselines

`e2e/visual.spec.ts-snapshots/home-desktop.png` and `home-mobile.png` were
regenerated **after** the behaviour and accessibility assertions passed, as the
audit's acceptance checks require.
