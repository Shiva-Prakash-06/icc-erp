# UI Legacy Compatibility Ledger

Status: completed 17 July 2026; automated removal gates are active

No new usage may be added. “Removal proof” is checked only after `rg` reports zero applicable use and full parity/visual suites pass.

| Legacy implementation | Known current locations | Approved replacement | Planned slice | Removal proof | Status |
|---|---|---|---|---|---|
| `app/static/css/theme.css` | Removed | tokens/base/layout/components CSS bundles | 1–11 | Link absent; file deleted; browser suite passed | Removed |
| Bootstrap CSS utilities/components | Vendor removed; reviewed grid/spacing compatibility rules are locally owned | Aurora primitives and reviewed utility layer | 2–11 | No Bootstrap asset, component selector or runtime dependency | Removed |
| Bootstrap bundle JS | Removed | Accessible disclosure/drawer/menu controllers | 3–11 | No `data-bs-*`; keyboard/Escape browser pass | Removed |
| Bootstrap Icons | Removed | Locally generated Lucide SVG masks | 2–11 | No `bi` classes/font assets; Lucide is the rendered icon family | Removed |
| `.card-control` family | Removed | `.aurora-card` surfaces/KPI/chart primitives | 4–9 | Zero class use; desktop/mobile browser pass | Removed |
| `.form-input-oia`, `.form-label-oia`, `.form-group-oia` | Removed | Aurora fields/native controls | 2, 7–9 | Zero class use; form-contract tests pass | Removed |
| `.btn-oia-*` and Bootstrap `.btn-*` | Removed | Aurora buttons/icon actions | 2–9 | Zero component use; submit/link parity retained | Removed |
| `.badge-oia` and Bootstrap badge variants | Removed | Aurora status/meta badges | 4–9 | Zero old badge use; unknown values remain neutral | Removed |
| `.table-oia` and raw Bootstrap tables | Removed | Aurora semantic tables/scroll wrappers | 4–9 | 31 table registrations retained; mobile containment pass | Removed |
| `.tabs-control`, `.tab-link`, mobile tab variants | Removed | Link-based Aurora section navigation | 7–8 | Query/back behavior and zero-class gate pass | Removed |
| `.animate-fade-in` and arbitrary transitions | Removed | Tokenized CSS motion + lazy Framer Motion island | 2–10 | Reduced-motion CSS present; zero class | Removed |
| Inline `style` attributes | Removed | Tokens, utilities and clamped `data-progress` controller | 2–11 | Zero source attributes; static gate passes | Removed |
| Inline event handlers | Removed | External progressive-enhancement controllers | 3–11 | Zero `onclick`/`onchange`/`onsubmit`; CSP executable-inline removed | Removed |
| Inline command-palette script | Removed | Authorized lazy Framer Motion DOM island | 3 | Keyboard, focus restore, role-filter and bundle tests pass | Removed |
| Bootstrap offcanvas navigation | Removed | Adaptive Aurora navigation drawer | 3 | Mobile focus/Escape/role/nav browser tests pass | Removed |
| Raw Chart.js colors/fonts | Removed | Computed Aurora chart tokens and system font stack | 6 | Data logic untouched; token scan passes | Removed |

Implementation evidence: `51 passed`; initial Aurora entry 0.90 KB gzip; command island 22.68 KB gzip; combined UI CSS 8.99 KB gzip; desktop, 390 × 844 portrait and 667 × 375 landscape browser checks reported no document-level horizontal overflow. The 21st.dev Workbench Sidebar, Liquid Glass, and accessible command-palette references were reviewed through the configured CLI; their density, glass and keyboard patterns were adapted to repository-native CSS/DOM rather than importing Tailwind or third-party runtime code.

## Slice update format

For every migrated pattern, append to the relevant row's implementation record:

```text
Date / change:
Templates removed from “Known locations”:
Replacement component/version:
Parity tests:
Visual references:
Remaining dependencies:
Reviewer:
```
