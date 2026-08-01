# ICC ERP UI Design System and Component Specifications

Status: implementation contract  
Visual source of truth: [`design-system/icc-erp/MASTER.md`](../design-system/icc-erp/MASTER.md)

This document specifies component behavior. The master file specifies tokens. A component is not production-ready until every applicable state below is implemented and tested.

## 1. Global component rules

Every primitive must:

- Accept caller-owned IDs, names, values, URLs, methods, ARIA attributes, data attributes, and test IDs without rewriting them.
- Use semantic native elements before custom roles.
- Render useful HTML before JavaScript mounts.
- Expose default, hover, pressed, focus-visible, disabled, busy, error, and high-contrast behavior where applicable.
- Support 200% zoom without lost content and 400% zoom without two-dimensional page scrolling.
- Tolerate a 60-character label, 120-character title, and 500-character error without overlap.
- Show unknown server values verbatim using a neutral variant.
- Avoid raw HTML injection; text is escaped unless the existing server contract marks trusted content.
- Avoid embedding authorization logic. Jinja/Flask decides whether a component is rendered.

## 2. Component inventory and APIs

### 2.1 `ui.button`

API:

```text
button(label, variant, size, type="button", href=None, icon=None,
       disabled=False, busy=False, busy_label=None, attrs={})
```

Variants: `primary`, `secondary`, `quiet`, `danger`, `success`, `link`. Sizes: `compact` 36px, `default` 44px, `touch` 48px.

Rules:

- If `href` exists, render `<a>`; otherwise render `<button>` and preserve `type` exactly.
- A disabled anchor uses `aria-disabled="true"`, is removed from tab order, and prevents activation without changing its URL.
- Busy state preserves button width, sets `aria-disabled`, shows an inline spinner, and changes visible text to `busy_label` when supplied.
- Busy enhancement prevents repeat activation, but server idempotency remains authoritative.
- Icon-only buttons are a separate `ui.icon_button` and require `aria-label`.
- Primary buttons may occur once per bounded view; repeating row actions use quiet/secondary variants.
- Destructive actions never appear adjacent to the primary action without at least 16px separation or a menu boundary.

### 2.2 `ui.icon_button`

API: `icon_button(icon, label, variant="quiet", pressed=None, badge=None, attrs={})`.

- Visual icon 18–20px inside a 44×44px minimum target.
- `label` becomes the accessible name. A hover/focus tooltip may repeat it after 500ms.
- Toggle buttons expose `aria-pressed`; menu controls expose `aria-expanded` and `aria-controls`.
- A notification badge exposes a readable count; `99+` is visual only while the accessible label uses the exact count.

### 2.3 `ui.field`

API:

```text
field(name, label, type="text", value=None, required=False,
      autocomplete=None, inputmode=None, helper=None, error=None,
      prefix=None, suffix=None, readonly=False, disabled=False, attrs={})
```

- Visible label always precedes the control. Placeholder is an example, never the label.
- Required fields show “Required” text or an asterisk with screen-reader explanation.
- Helper text is persistent. Error replaces or follows helper text and is connected via `aria-describedby`.
- Error state sets `aria-invalid="true"`; server value is retained unless security requires clearing it.
- Validate on blur only when client validation matches the server exactly. Server errors remain authoritative.
- Read-only and disabled are visually and semantically distinct.
- Use semantic `email`, `url`, `tel`, `number`, `date`, and password types where the existing payload permits.
- Input height is at least 44px. On screens below 768px, text inputs remain 16px to avoid browser zoom.
- Password fields provide show/hide without changing the field name/value or disabling password-manager support.

### 2.4 `ui.select`, checkbox and radio

- Native `<select>`, checkbox, and radio controls are preferred.
- Preserve option values exactly; visible labels may be styled but not renamed without product approval.
- Multi-option groups use `<fieldset><legend>`.
- Checkboxes never submit an invented false value unless the existing form contract already expects one.
- Selection state must remain visible in forced-colors mode.

### 2.5 `ui.form`

API: structural macro only; caller supplies form contents, `action`, `method`, encoding, and attributes.

- Do not intercept native submission by default.
- POST forms retain central CSRF injection and explicit hidden CSRF fields when present.
- Submit enhancement disables only the activated submitter and restores it on browser validation failure.
- Multiple-error response: focused error summary at the top with links to invalid fields; errors also remain adjacent to fields.
- GET filters submit normally and preserve unrelated query parameters using hidden fields where the existing page already does so.
- Unsaved-change warnings apply only to long forms and must not fire after successful submission.
- Enter-key behavior remains native: never trigger a destructive default action.

### 2.6 `ui.status_badge`

API: `status_badge(value, semantic=None, size="default", icon=True)`.

Canonical mapping:

| Values | Semantic |
|---|---|
| Approved, Completed, Active, Committed, Valid | success |
| Pending, Planned, Closing, In Progress | warning |
| Rejected, Failed, Error, Expired, Archived | danger |
| Submitted, Processing, Staged | information |
| Draft, Not Started, Inactive, Waived | neutral |
| Restricted | restricted |

The displayed value is never normalized away. `semantic` only determines styling. Add icon and text; do not rely on color.

### 2.7 `ui.surface` and cards

Variants: `work`, `raised`, `interactive`, `glass`, `danger`, `warning`.

- Work surfaces hold forms/tables and are opaque.
- Interactive cards render a real link/button covering the intended hit region without nesting interactive elements.
- Hover lift is prohibited. Interactive feedback uses border/surface color and at most a 1–2px transform.
- Glass is allowed only for shell navigation, command palette, popover, drawer, or transient summary overlay.
- Cards do not all need borders and shadows simultaneously; use the elevation table.

### 2.8 `ui.data_table`

API:

```text
data_table(caption, columns, rows, density="default",
           mobile="scroll|records|priority", sortable=False,
           empty=None, row_key=None)
```

- A descriptive caption is present, visibly or with `sr-only` treatment.
- Header cells use `scope="col"`; row headers use `scope="row"` where appropriate.
- Sort controls are buttons and update `aria-sort`; visual sorting does not invent backend sorting.
- Numeric data is right-aligned and uses tabular figures. Actions are aligned consistently at the end.
- Interactive forms inside rows preserve labels and must remain operable at 400% zoom.
- Sticky headers activate only in the main page scroll context; avoid nested vertical scroll containers.
- Empty state spans all columns and offers an action only when the role can perform it.
- Loading skeleton uses fixed row geometry and is only used for genuinely async content.
- Read-only tables with more than 50 client-rendered rows may virtualize only if a complete accessible/server fallback remains available.

Mobile policy:

- `scroll`: schedules, audit trails, immutable comparison tables. Keep first priority column sticky.
- `records`: tables containing row forms/actions, users, projects, reports, documents, tasks, checklist items.
- `priority`: compact KPI/ranking tables where two or three columns remain visible and the rest are disclosed per row.

### 2.9 Navigation shell

- Desktop rail contains labeled destinations grouped by Command, Reporting, and Administration.
- Collapsed rail retains tooltips and accessible labels; collapse choice persists locally but does not affect authorization.
- Mobile bottom navigation contains at most four top-level destinations plus Menu and uses icon + label.
- Destinations unavailable to a role are not serialized into client navigation data. If temporarily unavailable for state reasons, render disabled with explanation rather than silently hiding.
- Logout is spatially separated from normal navigation.
- Active location uses `aria-current="page"`, weight, and indicator—not color alone.
- Deep pages show breadcrumbs when hierarchy is at least three levels.

### 2.10 Tabs and disclosures

- Workspace tabs are real anchor links and preserve `?tab=`.
- The active link uses `aria-current="page"`; do not use ARIA tab roles unless content switches without navigation.
- Accordion buttons expose `aria-expanded`/`aria-controls`; headings remain in the document outline.
- Content is available immediately when expanded; animation does not delay focus or rendering.
- Mobile never requires horizontal swipe. Tabs may horizontally scroll with visible affordance or become a section selector.

### 2.11 Dialogs, drawers and popovers

- Dialog trigger is remembered; focus moves to heading/first meaningful field and returns on close.
- Escape and explicit Close dismiss unless a server operation is actively being submitted.
- Clicking the backdrop dismisses informational dialogs, not destructive confirmations or forms with unsaved data.
- Drawers are for navigation/secondary context, never the only home of a primary workflow.
- Popovers close on Escape and outside click and do not contain long forms.
- Background is inert while modal UI is open.

### 2.12 Alerts, flashes and toasts

- Server flash markup is the source of truth and remains in the DOM.
- Errors use `role="alert"`; success/info use `role="status"` or polite live regions.
- Toast enhancement may mirror or animate the message but must not duplicate screen-reader announcements.
- Success/info may auto-dismiss after five seconds; warning/error persists until dismissed.
- Multiple messages stack in source order, maximum three visible; the remainder is summarized with an expandable count.
- Messages longer than 240 characters render as inline alerts rather than transient toasts.

### 2.13 Empty, loading and error states

Empty state structure: icon, specific title, one-sentence explanation, and permitted next action. Never state that data does not exist when it may merely be outside the user's scope.

Loading:

- Native navigation uses browser loading; do not blank the old page.
- For enhanced actions taking >300ms, show busy feedback; >1s may show progress/skeleton.
- Never display a fake percentage.

Errors:

- State what failed, whether data was saved, and the next safe action.
- Preserve user input where safe.
- 403 differentiates “not permitted” without revealing protected record details.
- 404 offers a return destination.
- 409 shows stale-data conflict with Reload latest as the primary recovery and preserves the attempted value separately when safe.
- 500/request timeout offers Retry only when the action is safe/idempotent; otherwise directs the user to verify state first.

### 2.14 Command palette

- React/Framer Motion island enhanced from an accessible server-rendered dialog/search fallback.
- Receives only authorized label, category, URL, shortcut, and keywords from Jinja.
- Arrow keys move options; Enter activates; Escape closes; Tab remains trapped while open.
- Empty query shows frequent authorized destinations. No query results provides a close/rephrase instruction.
- Does not query sensitive project/person data unless a dedicated authorized server endpoint is later approved.

### 2.15 KPI and charts

- KPI always shows settled server value immediately, label, context period, and optional trend comparison.
- Never animate from zero because intermediate values are false.
- Chart frame includes title, one-sentence text insight, unit/timeframe, chart, legend, and data-table disclosure.
- Tooltip information is keyboard/tap reachable; legends can toggle series only when the same action is accessible by keyboard.
- Chart failure renders a text summary and retry if applicable; empty data never shows empty axes.

## 3. Motion contract by component

| Component | Default | Reduced motion | Prohibited |
|---|---|---|---|
| Button | 100ms press scale/background | background only | bounce, glow pulse |
| Navigation active item | 240ms shared indicator | immediate | moving whole rail |
| Drawer | 240ms translate+fade | 100ms fade | overshoot |
| Dialog | 240ms scale .98+fade | 100ms fade | spin/large zoom |
| Toast | 240ms 16px slide+fade | fade | repeated pulse |
| Disclosure | 160ms fade/4px translate | immediate/fade | animating measured height repeatedly |
| Page | one 240ms 8px entry | 100ms fade | replay on every tab/back restoration |
| Chart | 360ms max draw, values immediate | no draw | delayed numbers |
| 3D summary | pointer tilt ≤2 degrees | static | on forms/tables/mobile |
| Scrollytelling | 360ms section crossfade | static document | pinned blocking scroll |

## 4. Content rules

### Labels

- Page titles: noun or destination, e.g. “ERP operations”, not marketing slogans.
- Primary actions: verb + object, e.g. “Create project”, “Compile report”, “Apply transition”.
- Avoid “Submit” when a more specific verb exists.
- Destructive actions state the consequence, e.g. “Reject application”, not “Continue”.
- Status capitalization follows sentence case in new copy; server status values may remain as supplied.

### Feedback formula

- Success: object + completed action: “Project ICC-… was created in Draft.”
- Validation: cause + correction: “End date must be on or after start date.”
- Permission: “You do not have permission to approve this project.” Do not disclose hidden role/scope details.
- Conflict: “This record changed after you opened it. Reload the latest version before applying your decision.”
- Restricted: “Restricted reference. Named permission is required to view it.”

### Formatting

- Dates: `17 Jul 2026` in compact tables; `17 July 2026` in prose. Preserve date inputs as browser-native ISO values.
- Times: `09:30–11:00`, with timezone shown when ambiguity exists.
- Durations: `2 h 30 min`; never `2.5 hrs` in prose.
- Numbers: locale-aware Indian English grouping where applicable; use server semantics for exports.
- Percentages: 0 decimals for whole operational rates, 1 decimal only when it changes interpretation.
- Missing value: em dash plus accessible “Not provided” where context is unclear. Do not conflate zero with missing.
- Identifiers/checksums: data font, selectable, never altered; truncated visual forms provide full accessible/copy value.

## 5. Legacy-to-new mapping

| Existing implementation | Required replacement | Completion condition |
|---|---|---|
| `.sidebar`, `.topbar`, mobile offcanvas | New shell/navigation primitives | Same authorized destinations and active states |
| Bootstrap offcanvas/modal/collapse | New accessible drawer/dialog/disclosure | Keyboard, Escape, focus restore, no Bootstrap JS |
| `.card-control` and raw `.card` | `ui.surface` variants | No legacy card classes |
| `.btn-*`, `.btn-oia-*` | `ui.button`/`ui.icon_button` | Same element type and submit behavior |
| `.form-input-oia`, `.form-control`, `.form-select` | `ui.field`/native control macros | Same names, values, types and validation |
| `.badge-oia`, Bootstrap badges | `ui.status_badge`/`ui.meta_badge` | Canonical semantics and unknown fallback |
| `.table-oia`, raw Bootstrap tables | `ui.data_table` or documented semantic table | Same row forms and data |
| `.tabs-control`, `.tab-link` | Link-based section navigation | Query/history preservation |
| Inline flash alerts | Feedback component + optional toast island | One screen-reader announcement |
| Inline command palette | Authorized command island + fallback | Same navigation plus keyboard completion |
| CSS `.animate-fade-in` | Motion tokens/islands | Reduced-motion equivalent |
| Bootstrap Icons | Lucide local SVG masks/React icons | No mixed rendered icon family |
| Inline styles/onclick handlers | Component variants/controllers | Zero inline style/handler except safe serialized data |
| `theme.css` | tokens/base/layout/components bundles | Old file removed at final gate |

## 6. Required edge-case fixture set

Every component gallery and affected page must include applicable fixtures:

- Empty, one, typical, 50+, and 1,000+ records.
- 120-character names/titles, 500-character errors, long email/URL/file path/checksum.
- Zero, negative where valid, large integer, decimal, null, future unknown status, and future unknown role label.
- One and multiple flash messages; simultaneous warning and error.
- First field error, last field error below fold, and five-field error summary.
- Busy, disabled, read-only, expired session, CSRF failure, 403, 404, 409, 429, 500, timeout, and offline.
- Restricted metadata visible with value hidden; inaccessible record absent entirely.
- 375px portrait, 667×375 landscape, 768px, 1024px, 1440px, 200% and 400% zoom.
- Keyboard-only, screen reader, reduced motion, forced colors, increased contrast, disabled JavaScript, slow network, and print.
- Browser autofill, password manager overlay, mobile software keyboard, and back-navigation with preserved filters/scroll.

## 7. Component definition of done

- Component contract and variants are implemented with no one-off page CSS.
- Gallery covers states and edge fixtures.
- Axe reports no serious/critical issues.
- Keyboard, focus, forced-colors, reduced-motion, zoom, mobile and print checks pass where applicable.
- Visual regression is approved at required breakpoints.
- Functional contract tests prove caller-owned names/actions/values remain unchanged.
- Dependency, bundle and CSP review passes.
