# OIA Intelligence Hub — Design System Master

Status: mandatory source of truth  
Mode: light Tile System application UI; white high-contrast print output  
Density: enterprise dense 9/10  
Motion: restrained 4/10  
Last revised: 17 September 2026

This file governs the presentation layer only. Existing Flask routes, Jinja permission branches, form payloads, server validation, exports, offline snapshots, models, and workflows remain authoritative.

## What changed on 17 September 2026, and why this file changed with it

This document described the **flat blueprint**: a 56px sticky top bar, no desktop
rail, square corners everywhere and no elevation. That system was superseded the
same day by the **ICC ERP Tile System**, and the Flask application was migrated
to it (see the "Tile System migration" section of `docs/UI_LEGACY_LEDGER.md`).

The UI/UX audit in `docs/ui-ux-audit-2026-09-17/AUDIT.md` was written against
this file while the screenshots were taken of the migrated application, so two
of its findings — **P1-01** ("the shell still uses the retired desktop rail")
and the blueprint half of **P1-05** — asked for the migration to be reverted.
They are recorded as superseded in that document. Everything else the audit
found was real and has been fixed inside the Tile System.

The sections below now describe the shipped system. Neutrals, ink, hairlines,
the spacing scale and the three Barlow / IBM Plex Mono faces carried across from
the blueprint unchanged; radius, elevation, colour roles and layout are the
Tile System's.

## Product character

Precise, institutional, and quiet. The system reads as a technical drawing of the record: a flat ground, hairline rules, condensed uppercase labels, and registration marks at the corners of the things you act on. Nothing floats, nothing glows, and nothing is decorated. The ERP supplies every fact, action, state, and permission; the presentation layer's only job is to make the next decision obvious.

Three rules carry the whole system:

1. **The number is a link.** A count that cannot be opened is a dead end. Every counter that has a real destination navigates to the filtered list behind it; a counter with no destination is set as plain text rather than given a false affordance.
2. **Decide in place.** Approving is one click from the list it appears in. Sending something back opens the record, because every reject path requires a written reason.
3. **Nothing that blocks you is collapsed.** Closure blockers, the decision queue and a tab's primary content are never behind a disclosure. Disclosures hold provenance, settled records and secondary "add" forms.

## Foundation tokens

| Token | Value | Use |
|---|---:|---|
| `--color-canvas` | `#F2F2F3` | Application ground |
| `--color-surface-1` | `#FFFFFF` | Input and table surfaces |
| `--color-surface-2` | `#E9E9EA` | Hover and nested fills |
| `--color-surface-ink` | `#1D2D3D` | Inverse: avatars, toasts |
| `--color-primary` | `#5980A6` | Primary actions, active marks |
| `--color-primary-hover` | `#416180` | Primary hover/pressed |
| `--color-text` | `#1D1F20` | Primary text |
| `--color-text-secondary` | `#424244` | Secondary text |
| `--color-text-tertiary` | `#5D5D60` | Metadata, micro-labels |
| `--color-border` | `rgb(29 31 32 / 16%)` | Hairline rules |
| `--color-border-strong` | `rgb(29 31 32 / 30%)` | Inputs, buttons, popovers |
| `--color-focus` | `#2C455D` | Focus ring |
| `--color-success` | `#3D6B57` | Approved/completed |
| `--color-warning` | `#8A6329` | Pending/attention |
| `--color-danger` | `#8F3D38` | Errors/destructive actions |

Gradients of any kind are excluded. Status is never conveyed by color alone; retain its label and, where useful, a Lucide icon.

## Typography

- Headings, buttons, column heads, status words and micro-labels: Barlow Condensed, 500/600/700.
- Interface and body: Barlow, 400/500/600.
- Codes, dates, percentages, counts, and tabular data: IBM Plex Mono, 400/600.
- All fonts are self-hosted WOFF2 with `font-display: swap`; runtime font CDNs are forbidden.
- Body copy is 15px. Metadata may be 13px, and 12px when nonessential.
- Use sentence case for prose and headings. Uppercase with `.09em` tracking is the system's micro-label, used for column heads, field labels, eyebrows, status words and button text.
- Page titles are 40/42 desktop and 28/32 mobile.

## Geometry

- **The shell is a 72px rail**, down the left above 860px and along the bottom below it. The blueprint's top bar is gone. `.ds-app` is a named-area grid — `banner / rail / screen` — so the demo banner and the bottom navigation reserve layout space instead of floating over the record.
- **Two surfaces carry the product.** A *tile* (`--radius-tile`, filled with a family accent, lifts on hover) takes you somewhere; a *row* (44px, labelled cells) is a thing you act on. A screen is one or the other.
- **One screen, one viewport.** `.ds-app` is `overflow: hidden` at `100dvh`; a screen declares at most one `.ds-scroll`, and that is the only thing that moves. **The event workspace declares none** — see "A tab is a section strip and one open section" below.
- Radius encodes what a surface does: `--radius-chip` 4px, `--radius-control` 6px, `--radius-panel` 10px, `--radius-tile` 16px. The tile radius appears nowhere else — the corner *is* the signal that a surface drills down.
- Elevation belongs to navigational and floating surfaces only (`--shadow-tile`, `--shadow-tile-raised`). A work row never casts.
- Separation inside a work surface is a 1px hairline, never a shadow and never a fill.
- Controls are sized for density: 38px default, 30px compact, 34px segmented, 26px inside a row. Touch targets on the mobile bottom bar and the Menu drawer remain at least 44px.
- Spacing follows the 4, 8, 12, 16, 20, 24, 32, 40, 48, and 64px scale.

### A tab is a section strip and one open section

Revised 17 September 2026. Each of the event workspace's four work tabs used
to render every list it owned inside one `.ds-scroll`: Logistics stacked the
fact strip, the tasks, every checklist and the schedule; People stacked five
lists. The screen scrolled to hold it, and the reader met forty rows when the
decision in front of them concerned one.

A tab is now `.ds-work`, a two-track grid of **a section strip and one open
section**, and it declares no scroll container at all.

- **The strip** (`.ds-sections`) is one `.ds-section` tile per section,
  rotating through the three family accents *by position, not by meaning*.
  A closed tile is the accent's tint with ink on it; the open one is the solid
  accent with `--on-accent`. Each tile carries the section's name, its total,
  and how many items in it still need somebody — so the counts that used to
  justify scrolling the whole tab are readable without opening anything. The
  strip is the one element allowed to overflow sideways; it is a control, not
  a page.
- **The open section** (`.ds-panel`) is three fixed tracks: a 48px head
  carrying the title, the count and the section's actions; a
  `minmax(0, 1fr)` body at `overflow: hidden`; and a 40px pager pinned to the
  bottom, so the pager is in the same place whether a page holds eight rows
  or one.
- **A page is `paging.PAGE_SIZE` rows**, currently 8. That is the count that
  fits the shortest supported viewport between the fixed tracks, not a taste
  setting: it is paired with the `--row-height` track, and changing one means
  recomputing the other.
- **Paging is a query argument** resolved on the server (`?section=`,
  `?page=`, `?focus=`). The URL map is frozen and query arguments are not part
  of it, exactly as `tab` already was. The pager is therefore ordinary links:
  no JavaScript, keyboard operable for free, and a page can be bookmarked.
- **Reachability is the contract pagination must not break.** `?focus=<id>`
  resolves a record to the section *and the page* that hold it, and every
  deep link that names a record (the decision queue, a closure blocker, a
  post-decision redirect) carries it. Every form inside a panel posts `next`,
  which `_redirect_to_tab` already honoured, so a verdict returns to the
  section and page it was taken on.
- **Reference facts are a section, not a header.** The record's own attributes
  are `.ds-fact` cards in a `.ds-factgrid`, taking the same three tints. They
  are reference, never items, and they are one click away rather than
  permanently above the work.
- **Two exceptions scroll, and both are correct.** Below 860px a row becomes a
  labelled record card several lines tall and under 720px of height the fixed
  tracks alone use most of the screen; in those two cases `.ds-panel__body`
  scrolls, and it is still the only thing on the screen that does. The other
  is `.ds-forms` — Public disclosure is three blocking forms and no pager.

### A tab is a tile

Revised 17 September 2026. The tab strip was five words in
`--color-text-tertiary` on transparent, marked only by a 2px underline on the
active one. On the `--color-canvas` ground the resting tabs read as page
furniture rather than as controls — the reader could not see where the strip
began or ended.

Each tab now carries a fill at 32px with `--radius-control`, and the underline
is gone: a filled tab needs no second marker. **The hue is the record's own
family** — pine for an ICC event, indigo for an IGP programme, set once on
`.ds-tabs` as `--tab-accent` / `--tab-tint`. That keeps colour inside its one
permitted job, identity, instead of handing five tabs five decorative hues,
and it is the hue the reader clicked through from the division tile to get
here. Resting tabs take the tint with ink on it; the open one takes the solid
accent with `--on-accent`, named explicitly on the count as well as the tab.

The bare `.ds-tabs` fallback (brand blue) is declared **before** the two family
modifiers. They are all one class, so at equal specificity the later rule wins:
declared after, it would repaint every strip brand blue whatever family it
carries.

### Dialogs

`.ds-modal` is a `:target` dialog: the trigger is a link to the dialog's id,
`:target` shows it, and the scrim and close control are links back to `#`.
No JavaScript, so it survives the no-JS contract, and no inline handler, which
CSP would kill and `tests/ui_contract_test.py` forbids. It carries `role="dialog"`
and `aria-labelledby` but **not** `aria-modal`: the page behind is still
reachable by tab, and claiming otherwise would be a lie to assistive
technology. A dialog is rendered only when its own trigger is, so a reader
without the permission carries no hidden form.

Every "add", "import", "attach" and "open a form" of the workspace lives in
one — sixteen of them, each three to six fields tall when open, which was most
of the reason a tab could not fit its viewport. The dialog's body is the one
place an internal scroll is right: it belongs to the dialog, not to the screen
behind it.

### Mobile navigation contract

Below 860px the rail becomes a bottom bar of **four primary destinations plus
Menu**, and nothing else. `navigation.MAX_BOTTOM_NAV_ITEMS` is the ceiling and
is asserted by `tests/ui_audit_regression_test.py`; eleven 48px targets do not
fit 375px. Everything the bar drops — alerts, the account, imports, audit,
administration, sign-out — lives in the labelled `.ds-menu__drawer`, a native
`<details>` that needs no JavaScript, together with the reader's role and scope.
The bar reserves `56px + env(safe-area-inset-bottom)`.

### A record row on a phone

A `.ds-row` folds into a labelled record card below 860px: each cell prints its
own column name from `data-label`, the title wraps rather than clipping, and the
actions sit inside the card. Row actions are never positioned off-canvas.

## Depth

There is no glass: `.aurora-card--glass` and the `--color-surface-glass*` tokens are gone. Work surfaces are opaque and flat. Elevation is carried by navigational tiles and by the four things that genuinely float above the record — the toast, the command dialog, the row's review panel, and the Menu drawer — and is a plain ink shadow, never a colour glow.

The blueprint registration mark (`.blueprint` plus four empty `<i class="corner">` elements) survives on the sign-in action and the first-run cards. It is decorative and invisible to the accessibility tree.

No cursor spotlight, no perspective, no tilt, no parallax.

## Foreground on an accent ground

`--tile-pine`, `--tile-indigo` and `--tile-brass` are dark grounds, and anything
drawn on them takes `--on-accent` (white, 6.33–9.92:1) or `--on-accent-muted`
(white at 88%, 5.33–8.14:1). **A heading must name the token explicitly.**
`base.css` sets `h1..h6 { color: var(--color-text) }`, which is specificity
(0,0,1) and beats the tile's *inherited* white however specific the tile's own
selector is — that is how every dark tile heading came to render at 1.67:1
(audit P1-06). `tests/ui_audit_regression_test.py` measures every pair.

## The two divisions

Revised 17 September 2026. **IGP is "India Gateway Program" and ICC is
"International Christite Community"** — the offices' own names. One expansion
each, everywhere: `services/glossary.DIVISION_NAMES`, `hierarchy.DIVISIONS`,
the seeded operating units and the public landing copy were changed together,
because the bug audit P1-08 was raised to fix is a canonical name that
disagrees with another screen. Stored `operating_units.name` rows are left
alone and mapped at render time; renaming that column on a populated database
would be a data migration to fix a caption.

The record noun is unchanged: the interface says "event" for ICC, "programme"
for IGP, and "record" where it must cover both, while routes and the model
keep saying `project`.

## Status

Status has **five named dimensions**, defined once in `app/services/status.py`:
`availability` (is the file there), `workflow`, `review` (what an approver
decided), `publication` and `lifecycle`. A chip carries its dimension, so
"File: No file" beside "Review: Approved" reads as two facts about one record
rather than as a contradiction (audit P0-04).

- **The label is the stored word.** The vocabulary is not rewritten for style:
  `Pending` and `Submitted` are distinct states in different workflows and must
  not be collapsed. The explanation lives in the chip's hint.
- **An unknown value degrades to neutral, never to danger.** The hand-written
  ternaries this replaced used `else` as a synonym for "bad", which is how a
  *verified* buddy interaction came to be painted in danger red under a warning
  triangle.
- **Tone describes the reader's next action, not sentiment.** `attention` means
  somebody has to do something; `critical` means something is wrong. A waived
  requirement is a decision, not a failure.
- Every state renders a word, an icon and a colour. Colour is never the only
  carrier.

## Numbers, money and dates

Shared formatters in `app/services/formatting.py`, registered as Jinja filters,
are the only way a number reaches a template. Indian digit grouping
(`₹7,65,000`); trailing `.00` dropped unless the value has paise; `short_money`
(`₹7.2L`) only where the exact figure sits beside it or one click away;
`pluralise` for every count. Dates and times go through `timeutil`'s
`localdate` / `localtime` / `localdatetime`, which render campus-local and label
the zone. Raw values stay raw in exports, the API and the audit payload.

## Icons

Lucide is the only visual icon language. React islands use `lucide-react`; server-rendered templates receive locally generated Lucide SVG masks from `icons.css`. Historical `ph-*` class names are compatibility hooks only and no longer load the Phosphor font.

## Motion

- Typical duration: 160–300ms. Use transform and opacity; progress uses `scaleX`.
- Two keyframes exist: `rise` and `fade`, for the toast, the command dialog and the sign-in column.
- Numeric data renders its true value immediately. No fake count-up or simulated workflow progress.
- Tables, forms, validation errors, audit rows, and notification lists do not stagger.
- Below-fold dashboard sections may reveal once; there is no scroll-jacking or pinned storytelling.
- `prefers-reduced-motion` removes perspective, parallax, stagger, count transitions, cursor spotlight, and large transforms.
- Framer Motion is progressive enhancement only. Navigation, forms, content, feedback, and exports must remain usable without JavaScript.

## Accessibility

- WCAG 2.2 AA is the release floor for structure, naming, focus and keyboard operation, verified by axe on every page state.
- **Target size is a deliberate exception.** The blanket 44×44px floor was dropped for this design: it is the AAA criterion, it is touch-oriented, and enforcing it on pointer devices is what previously forced the Home counters to be non-clickable. Desktop controls are sized for density; the mobile bottom nav and drawer keep 44px.
- **Colour contrast is not gated by axe in CI**, because the palette's muted metadata tone sits near the 4.5:1 boundary. It is gated another way: `tests/ui_audit_regression_test.py` measures every accent ground against its foreground token, and `e2e/accessibility-responsive.spec.ts` measures every rendered tile in the browser. Both require 4.5:1.
- **Forms reveal conditional fields with CSS `:has()`, never JavaScript.** The rule *hides*, so a browser without `:has()` drops the selector and the field stays visible — the behaviour before the rule existed, never a field the reader cannot reach. The input keeps its name, its label and the server's validation either way.
- Every control has a visible label or accessible name and a visible `:focus-visible` treatment.
- No hover-only behavior. Touch, keyboard, and pointer paths receive the same functionality.
- Server validation remains adjacent to its field and connected through `aria-describedby`/`aria-invalid` where available.
- Mobile data tables become record cards/definition lists when row actions would otherwise become inaccessible; read-only ledgers may scroll priority columns.
- Forced-colors retains native affordances, borders, focus, and status text.

## Print

Reports, audit views, and structured project summaries print on white without shell, glass, ambient backgrounds, or motion. Table headers repeat where supported; record blocks avoid page breaks; interactive-only controls are hidden.

**The one-screen frame must be unclamped for print.** `.ds-app`, `.ds-screen`,
`.ds-screen__body` and `.ds-scroll` are all reset to `display: block; height:
auto; overflow: visible`, or a report prints the rail plus exactly one viewport
and silently drops everything below the fold. Disclosures print open —
provenance and settled records are what a printed ledger is for — and a record
row prints as a labelled block rather than as a seven-column grid.

## Architecture and functional invariants

- Flask/Jinja owns content, navigation, permission branches, forms, errors, and links.
- React/Framer Motion islands mount only over usable server-rendered fallbacks and accept minimal allowlisted props.
- Tailwind, TanStack Router, Radix, shadcn, React Query, and Recharts are not production dependencies.
- Chart.js remains the chart implementation.
- Local storage is unused. `oia.ui.rail-collapsed` went away with the rail.
- Route count and URL-map hash may not change without a deliberate, documented and re-baselined update (`scripts/regen_ui_baseline.py`) recorded in `docs/UI_LEGACY_LEDGER.md`. Form actions/methods/field names, CSRF/version fields, and role navigation may not change. **Redirect endpoint and HTTP status may not change; the `tab` query argument on a project workspace redirect is presentation and may be re-pointed** (e.g. the `operations` → `delivery`/`contributions`/`finance` tab split), since query arguments are not part of the URL map. Downloads and offline behavior may not change.
- Prototype mock data, fictional actions, appearance settings, synthetic system health, and simulated report progress are forbidden.

## Explicit anti-patterns

- Dark legacy surfaces, purple/pink gradients, neon effects, particles, autoplay media, or decorative tickers.
- Blur, gradients, glow, rounded cards, drop shadows on work surfaces, or hover lift.
- A count that is not a link when a destination for it exists.
- **A counter whose destination does not contain the records it counted.** A counter links to the `state` filter, which reproduces `event_state`, and never to `status`, which matches the stored column that no counter counts.
- A decision that requires leaving the list to take it, when the decision needs no reason.
- A select, a free-text reason and a verb wedged into a record row. The row reads; `Review` opens the form.
- Truncating the only visible copy of a title, a required instruction or a fact.
- Primary content behind a disclosure.
- Color-only status, placeholder-only labels, or icon-only primary navigation.
- Client-side permission filtering or sensitive records serialized for hidden island state.
- New business functionality introduced during visual migration.
