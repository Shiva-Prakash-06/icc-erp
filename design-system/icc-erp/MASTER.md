# OIA Intelligence Hub — Design System Master

Status: mandatory source of truth  
Mode: light sky-blue application UI; white high-contrast print output  
Density: enterprise dense 8/10  
Motion: restrained 6/10

This file governs the presentation layer only. Existing Flask routes, Jinja permission branches, form payloads, server validation, exports, offline snapshots, models, and workflows remain authoritative.

## Product character

Precise, optimistic, institutional, and calm. The OIA prototype supplies the geometry, bento composition, typography, icon weight, glass depth, and motion language. The ERP supplies every fact, action, state, and permission.

## Foundation tokens

| Token | Value | Use |
|---|---:|---|
| `--color-canvas` | `#F0F9FF` | Application canvas |
| `--color-surface` | `#FFFFFF` | Solid work surfaces |
| `--color-surface-frosted` | `rgba(255,255,255,.78)` | Navigation and elevated glass |
| `--color-surface-muted` | `#E0F2FE` | Selected and nested surfaces |
| `--color-primary` | `#0369A1` | Primary actions |
| `--color-primary-hover` | `#075985` | Primary hover/pressed |
| `--color-sky` | `#0EA5E9` | Decorative aurora and charts |
| `--color-blue` | `#2563EB` | Secondary data series |
| `--color-text` | `#0F172A` | Primary text |
| `--color-text-secondary` | `#334155` | Secondary text |
| `--color-text-muted` | `#475569` | Metadata |
| `--color-border` | `#BAE6FD` | Default borders |
| `--color-border-strong` | `#7DD3FC` | Hover/emphasized borders |
| `--color-focus` | `#0284C7` | Focus ring |
| `--color-success` | `#047857` | Approved/completed |
| `--color-warning` | `#B45309` | Pending/attention |
| `--color-danger` | `#B91C1C` | Errors/destructive actions |

Purple and pink decorative gradients are excluded. Status is never conveyed by color alone; retain its label and, where useful, a Lucide icon.

## Typography

- Headings: Space Grotesk, 500/700.
- Interface and body: Inter, 400/600.
- Codes, dates, percentages, counts, and tabular data: IBM Plex Mono, 400/600.
- All fonts are self-hosted WOFF2 with `font-display: swap`; runtime font CDNs are forbidden.
- Page titles are 32/40 desktop and 24/32 mobile. Body copy is at least 14px desktop and 16px mobile. Metadata may be 12px when nonessential.
- Use sentence case. Uppercase is limited to compact metadata eyebrows with tracking.

## Geometry

- Desktop rail: 248px expanded, 76px collapsed.
- Top bar: 56px.
- Content: fluid to 1600px; 32px desktop padding and 16px mobile padding.
- Bento layout: twelve columns with 16px gaps; collapse to one column on mobile.
- Primary cards: 16px radius; nested surfaces: 12px; buttons and inputs: 8px.
- Controls and interactive icon hit areas are at least 44×44px where applicable.
- Spacing follows the 4, 8, 12, 16, 20, 24, 32, 40, 48, and 64px scale.
- Labelled page regions (`.page-section`) are separated by 40px desktop / 32px mobile; a region's heading block sits 24px above its content. Bento gaps remain 16px column / 20px row.

## Glass and depth

Work surfaces (tables, forms, list/KPI cards -- `.aurora-card`) are opaque, not translucent: this is a floor, not a suggestion. Glass is opt-in via `.aurora-card--glass` and is reserved for navigation-adjacent shell surfaces (rail, topbar, notification panel, command dialog). Frosted surfaces use translucent white, 12–18px blur, a sky-tinted border, a subtle top highlight, and restrained blue shadows. The no-`backdrop-filter` fallback is opaque white. Glass may frame navigation and cards but must not reduce form, table, or long-text legibility.

Cursor spotlight and shallow perspective are limited to KPI cards on fine-pointer desktop devices. No WebGL dependency is permitted. Forms, tables, alerts, dialogs, and destructive controls do not tilt.

## Icons

Lucide is the only visual icon language. React islands use `lucide-react`; server-rendered templates receive locally generated Lucide SVG masks from `icons.css`. Historical `ph-*` class names are compatibility hooks only and no longer load the Phosphor font.

## Motion

- Typical duration: 160–300ms. Use transform and opacity; progress uses `scaleX`.
- Spring motion is limited to drawers, active navigation, and view selectors.
- Numeric data renders its true value immediately. No fake count-up or simulated workflow progress.
- Tables, forms, validation errors, audit rows, and notification lists do not stagger.
- Below-fold dashboard sections may reveal once; there is no scroll-jacking or pinned storytelling.
- `prefers-reduced-motion` removes perspective, parallax, stagger, count transitions, cursor spotlight, and large transforms.
- Framer Motion is progressive enhancement only. Navigation, forms, content, feedback, and exports must remain usable without JavaScript.

## Accessibility

- WCAG 2.2 AA is the release floor.
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
- Local storage is restricted to `oia.ui.rail-collapsed` and `oia.ui.projects-view` (the latter reserved/unused — no view-switcher currently exists; do not remove the reservation without also removing this line).
- Route count and URL-map hash may not change without a deliberate, documented and re-baselined update (`scripts/regen_ui_baseline.py`) recorded in `docs/UI_LEGACY_LEDGER.md`. Form actions/methods/field names, CSRF/version fields, and role navigation may not change. **Redirect endpoint and HTTP status may not change; the `tab` query argument on a project workspace redirect is presentation and may be re-pointed** (e.g. the `operations` → `delivery`/`contributions`/`finance` tab split), since query arguments are not part of the URL map. Downloads and offline behavior may not change.
- Prototype mock data, fictional actions, appearance settings, synthetic system health, and simulated report progress are forbidden.

## Explicit anti-patterns

- Dark legacy surfaces, purple/pink gradients, neon effects, particles, autoplay media, or decorative tickers.
- Blur on every surface, hover lift everywhere, or cursor-follow effects outside KPI cards.
- Color-only status, placeholder-only labels, or icon-only primary navigation.
- Client-side permission filtering or sensitive records serialized for hidden island state.
- New business functionality introduced during visual migration.
