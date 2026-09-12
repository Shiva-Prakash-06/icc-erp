# OIA Intelligence Hub — Design System Master

Status: mandatory source of truth  
Mode: light blueprint application UI; white high-contrast print output  
Density: enterprise dense 9/10  
Motion: restrained 4/10

This file governs the presentation layer only. Existing Flask routes, Jinja permission branches, form payloads, server validation, exports, offline snapshots, models, and workflows remain authoritative.

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

- There is no desktop rail. One sticky top bar, 56px, carries the brand, the five destinations, search, alerts and the user chip.
- Content: fluid to 1440px; 28px desktop padding and 16px mobile padding.
- Working layout is a 2.2fr/1fr split -- the list that needs deciding, and the facts beside it -- collapsing to one column at 1023px.
- Everything is square. Radii are 0, with 2px reserved for nested chips and 4px as the maximum anywhere.
- Separation is a 1px hairline, never a shadow and never a fill.
- Controls are sized for density: 38px default, 30px compact, 34px segmented. Touch targets on the mobile bottom nav and drawer remain at least 44px.
- Spacing follows the 4, 8, 12, 16, 20, 24, 32, 40, 48, and 64px scale.
- Labelled page regions (`.page-section`) are separated by 40px desktop / 32px mobile; a region's heading block sits 24px above its content. Bento gaps remain 16px column / 20px row.

## Depth

There is no glass: `.aurora-card--glass` and the `--color-surface-glass*` tokens are gone. Work surfaces are opaque and flat. Elevation is reserved for the three things that genuinely float above the record -- the toast, the command dialog, and the tab overflow popover -- and is a plain ink shadow, never a colour glow.

The system's one ornament is the blueprint registration mark: four corner ticks drawn just outside a box, applied to primary actions, counter tiles and framed panels via `.blueprint` plus four empty `<i class="corner">` elements. They are decorative and invisible to the accessibility tree.

No cursor spotlight, no perspective, no tilt, no parallax.

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
- **Colour contrast is not gated in CI.** The palette's muted metadata tone sits near the 4.5:1 boundary. Re-enable the axe `color-contrast` rule if the palette is retuned.
- Every control has a visible label or accessible name and a visible `:focus-visible` treatment.
- No hover-only behavior. Touch, keyboard, and pointer paths receive the same functionality.
- Server validation remains adjacent to its field and connected through `aria-describedby`/`aria-invalid` where available.
- Mobile data tables become record cards/definition lists when row actions would otherwise become inaccessible; read-only ledgers may scroll priority columns.
- Forced-colors retains native affordances, borders, focus, and status text.

## Print

Reports, audit views, and structured project summaries print on white without shell, glass, ambient backgrounds, or motion. Table headers repeat where supported; record blocks avoid page breaks; interactive-only controls are hidden.

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
- A decision that requires leaving the list to take it, when the decision needs no reason.
- Primary content behind a disclosure.
- Color-only status, placeholder-only labels, or icon-only primary navigation.
- Client-side permission filtering or sensitive records serialized for hidden island state.
- New business functionality introduced during visual migration.
