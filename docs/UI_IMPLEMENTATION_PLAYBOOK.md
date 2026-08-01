# ICC ERP UI Overhaul Implementation Playbook

Status: mandatory execution procedure  
Applies to: humans, coding agents, 21st.dev-generated code, and reviewers

## 1. Execution rules

1. Migrate a bounded vertical slice, never “restyle the entire app” in one change.
2. Capture the old route/form/data baseline before editing its template.
3. Read the master design system and page override before generating or coding UI.
4. Build from approved primitives; do not create page-local variants to save time.
5. Keep server-rendered critical HTML complete before mounting an island.
6. Run parity, accessibility, responsive and visual checks before moving to the next slice.
7. Do not update broad screenshot baselines to hide regressions.
8. Keep unrelated backend cleanup out of UI commits.

## 2. Required frontend architecture

### 2.1 Toolchain

Target versions are pinned in `package-lock.json` during Phase 1:

- Node.js 22 LTS.
- npm via the lockfile; CI uses `npm ci`.
- Vite with TypeScript.
- React and ReactDOM matching Framer Motion peer requirements.
- Framer Motion 12.x.
- Playwright and axe integration as development dependencies.
- Lucide icons as a local SVG build source and `lucide-react` dependency only where needed.

Do not add Tailwind to the production application merely because a 21st.dev component uses it. The UI lab may use Tailwind temporarily for evaluation; adopted components are converted to ICC tokens and scoped CSS or reviewed utilities.

### 2.2 Source and output structure

```text
frontend/
  src/
    entries/
      atmosphere.tsx
      command-palette.tsx
      feedback-center.tsx
      metric-motion.tsx
      workspace-navigator.tsx
      executive-story.tsx
    islands/
    components/
    motion/
    lib/
  ui-lab/
  vite.config.ts
app/static/ui/
  manifest.json
  assets/<content-hashed files>
app/templates/ui/
app/static/css/
tests/ui_contract/
tests/ui_e2e/
tests/ui_visual/
```

Production images never require Node at runtime. Docker/Cloud Build runs `npm ci && npm run build:ui` before packaging Flask static assets.

### 2.3 Vite contract

- One entry per island, no monolithic SPA entry.
- Emit content-hashed JS/CSS and `manifest.json` to `app/static/ui/`.
- Flask helper resolves logical entry names through the manifest and emits `type="module"` plus associated CSS.
- Only pages containing a mount point load that entry.
- Development uses Vite only behind an explicit development flag; production never references a dev server.
- Build fails on TypeScript errors, missing manifest entries, oversized chunks, or uncommitted generated assets when deployment expects them committed.

### 2.4 Island mount contract

Each island mount has:

```html
<div data-island="command-palette" data-props-id="command-palette-props">
  <!-- usable server fallback -->
</div>
<script id="command-palette-props" type="application/json">SAFE_JSON</script>
```

Rules:

- Use `createRoot`, not hydration, unless server markup is intentionally identical and tested.
- Before replacing fallback content, validate the prop schema and confirm the island initialized.
- Mount failure leaves fallback content untouched and reports a non-sensitive console error in development.
- Props contain only allowlisted fields already visible/authorized on the page.
- An island does not reach into unrelated DOM or attach global listeners without cleanup.
- Page unload/back-cache handling must not double-mount listeners.

## 3. Design-system retrieval workflow

Before implementing a page:

1. Read `design-system/icc-erp/MASTER.md` completely.
2. Read the applicable override:
   - `authentication.md`
   - `dashboard.md`
   - `project-workspace.md`
   - `reports-admin.md`
3. Read the relevant component sections in `docs/UI_DESIGN_SYSTEM.md`.
4. Read the route/state row in `docs/UI_PAGE_AND_STATE_MATRIX.md`.
5. Read the affected forms in `docs/UI_FUNCTIONAL_PARITY_CONTRACT.md`.
6. Run UI/UX Pro Max searches only for the unresolved component family; record accepted/rejected recommendations in the implementation note.

Page overrides may change arrangement and priority, not token values, component semantics, parity rules, or accessibility.

## 4. Controlled 21st.dev workflow

21st.dev code is candidate code, never an automatic dependency or design decision.

### 4.1 Before generation

Create a component brief containing:

- Component name and exact job.
- Target users and operational context.
- Required variants/states from `UI_DESIGN_SYSTEM.md`.
- Exact tokens from the master.
- Semantic HTML and keyboard contract.
- Reduced-motion behavior.
- Maximum dependency and bundle allowance.
- Explicitly prohibited behavior.
- Fixture data including empty, dense, long and error cases.

### 4.2 Magic prompt template

```text
Create [COMPONENT] for ICC ERP, a dense institutional operations platform.
Use the Institutional Aurora tokens supplied below; do not invent colors,
spacing, radii, shadows or motion. Provide [REQUIRED VARIANTS/STATES].
Use semantic HTML and full keyboard behavior. Respect prefers-reduced-motion,
forced-colors and 400% zoom. Critical content must be present without motion.
Do not add network calls, mock business logic, client authorization, new fields,
Tailwind-only abstractions, gradients outside the approved tokens, or unrelated
dependencies. Test with [FIXTURES]. Return a self-contained component plus a
state gallery and list all dependencies.
```

### 4.3 Evaluation

Generate at most three variants. For each, record:

- Magic prompt and output/reference URL.
- Author/source/license/provenance.
- Dependency list and estimated route cost.
- Semantic/keyboard/focus findings.
- Responsive, zoom, reduced-motion and forced-colors findings.
- Token deviations.
- Security/data-flow findings.
- Decision: reject, adapt to Jinja/CSS, or adopt as React island.

Reject a component if it:

- Depends on client authorization or invented API calls.
- Hides essential content without JavaScript.
- Uses inaccessible custom controls when native controls suffice.
- Adds broad UI frameworks or unmaintained dependencies.
- Cannot meet reduced-motion, forced-colors, zoom, CSP or bundle budgets without a rewrite.
- Duplicates an approved primitive.

### 4.4 Adaptation

- Replace all raw colors/spacing/radius/motion with ICC tokens.
- Remove mock data, invented actions, analytics and network calls.
- Replace Tailwind utility output with repo-native semantic classes unless the lab dependency has been separately approved for production.
- Convert form/data primitives to Jinja macros. Keep React only for approved islands.
- Add state-gallery, contract, E2E, accessibility and visual tests before production use.
- Store attribution/license notices required by the source.

### 4.5 Private ICC library

Publish only stabilized, reviewed React components to a private 21st library. Never publish ICC data, screenshots containing personal/restricted information, server routes, credentials, internal tokens, or unreviewed generated code.

## 5. Framer Motion implementation rules

- One `MotionConfig` per island tree using master duration/easing/reduced-motion configuration.
- Import only APIs needed by the island; route-split heavy animation code.
- Use transform/opacity; no width/height/top/left animation.
- Limit initial view animation to two focal groups. Lists stagger at most eight items.
- No stagger/entrance on tables, form rows, error lists, audit rows or notifications already present at load.
- Use `AnimatePresence` only when exit state has a real semantic lifecycle.
- User input interrupts motion immediately.
- Do not wait for animation before submitting, following a link, focusing an error, or displaying settled data.
- CSS provides equivalent static states before the island mounts.

## 6. Migration procedure per slice

### Step 1 — Freeze the baseline

- Seed a deterministic database fixture.
- Capture route response, role-visible links, forms/controls, screenshots and critical requests.
- Add missing parity tests before changing markup.
- Record current known defects separately; do not normalize them silently.

### Step 2 — Compose in the UI lab

- Use approved primitives and candidate 21st components.
- Populate every required page state from the state matrix.
- Obtain visual approval for desktop and mobile before backend integration.

### Step 3 — Implement server-first

- Build Jinja macros/markup with all data, links, forms, errors and fallbacks.
- Confirm the page works with CSS only and with JavaScript disabled.
- Do not mount Framer islands yet.

### Step 4 — Add styling and responsive behavior

- Apply tokens and shared components.
- Verify 375, 667×375, 768, 1024 and 1440 viewports plus 200/400% zoom.
- Exercise long, empty, dense, unknown and error fixtures.

### Step 5 — Add approved islands

- Add minimal allowlisted props and route-specific assets.
- Verify mount failure and reduced-motion fallbacks.
- Check that no sensitive or unauthorized data entered page source or source maps.

### Step 6 — Verify and remove legacy usage

- Run all gates in Section 11.
- Remove migrated inline styles/handlers and legacy classes for that slice.
- Do not remove shared Bootstrap/theme rules still used by unmigrated pages; track them in the legacy ledger.

### Step 7 — Review and record

- Complete the page acceptance record.
- Review screenshot diffs manually.
- Record approved copy-only differences and any deferred defect.
- Merge only a bounded, reversible slice.

## 7. Legacy compatibility ledger

Maintain [`docs/UI_LEGACY_LEDGER.md`](UI_LEGACY_LEDGER.md) during implementation with columns:

```text
Legacy class/script | templates still using it | replacement | owner/slice | removal test | status
```

Rules:

- New templates may not introduce legacy classes.
- Shared legacy CSS is deleted only when `rg` shows zero template/script use and the complete visual suite passes.
- Bootstrap CSS and JS are removed separately; utility, collapse, modal and offcanvas dependencies are enumerated first.
- Inline `onclick` and `style` are reduced to zero, excluding explicitly reviewed safe JSON/configuration blocks.

## 8. Browser, input and rendering support

Release support:

- Latest two stable versions of Chrome/Edge, Firefox and Safari.
- Current iOS Safari and Android Chrome used by stakeholder devices.
- CSS feature fallbacks for `backdrop-filter`, `100dvh`, container queries if introduced, and view transitions if introduced.
- Keyboard/mouse/touch supported; stylus behaves as touch.
- No dependence on hover, fine pointer, haptics, swipe, device orientation or WebGL.

Progressive enhancements may be absent in older browsers; forms, links, data and feedback must remain functional.

## 9. CSP, security and privacy

- Eliminate inline executable scripts and handlers. Use external hashed modules and safe JSON data blocks.
- Respect the application's CSP; do not add `unsafe-inline` or broad third-party origins for visual tooling.
- Self-host production fonts, icons and assets.
- 21st/Magic is never given real credentials, personal records, sensitive Drive references or production screenshots with identifiable data.
- Source maps are disabled in production or stored privately; they must not contain fixture secrets.
- No UI analytics, session replay, remote error tracking or CDN is added without separate privacy/security approval.
- Dependency audit and license review are release gates.

## 10. Performance budgets

Measure on representative mid-range mobile hardware/network after baseline. Initial hard budgets:

| Metric | Budget |
|---|---:|
| Initial route JS for pages without islands | 0 new application JS beyond shared progressive controller |
| Shared enhancement JS, compressed | ≤45 KB |
| Any normal island, compressed | ≤35 KB route cost |
| Executive scrollytelling island, compressed | ≤80 KB, lazy and below fold |
| Total initial CSS, compressed | ≤45 KB after legacy removal |
| LCP p75 target | ≤2.5 s |
| INP p75 target | ≤200 ms |
| CLS p75 target | ≤0.1 |
| Main-thread animation work | <16 ms/frame target; no long task >50 ms caused by decoration |
| Font payload | ≤160 KB total WOFF2 for critical UI/data faces |

Budgets are not loosened simply because a generated component exceeds them. Decorative 3D/scrollytelling is the first feature removed when budgets fail.

## 11. Test gates

### Per component

- Unit/state-gallery tests.
- Axe: zero serious/critical violations.
- Keyboard/focus manual pass.
- Reduced-motion and forced-colors snapshot.
- Visual snapshots at compact/default/mobile states.

### Per page

- Python route/template contract tests.
- Form request assertion for every mutation on the page.
- Applicable actor/role journeys.
- Empty, typical, dense, long, error and unknown-status fixtures.
- 375, 667×375, 768, 1024 and 1440 screenshots.
- 200/400% zoom; keyboard; no-JS; reduced motion; forced colors.
- Print for reports/audit/project summaries.

### Per slice/merge

```text
pytest full suite
coverage threshold already required by repository
npm typecheck
npm production build
Playwright functional/parity suite
Playwright visual suite
axe suite
dependency/license audit
bundle budget check
git diff --check
```

### Visual-diff policy

- Stable deterministic fixtures, time and animation.
- Pixel threshold starts at 0.2% changed pixels for stable components; antialiasing exceptions are documented by platform.
- Layout, clipping, focus, contrast and content changes always require human review regardless of pixel percentage.
- Update one page/component baseline at a time with reviewer name and reason.
- `--update-snapshots` across the whole suite is prohibited in implementation and CI handoff.

## 12. Edge-case execution checklist

For every applicable slice, explicitly test:

- Long names, email, URLs, descriptions, errors, codes, checksums and untranslated server values.
- Empty, one, dense, 50+, 200 and maximum server-limited collections.
- Zero versus null, invalid date range, future/past dates, timezone boundary and large numeric values.
- Double click, Enter submission, back/forward, refresh after POST redirect, slow response and interrupted download.
- Multiple simultaneous flashes; field error below fold; first/last control focus.
- Session expiration mid-form, CSRF rejection, 403/404/409/422/429/500 and network offline.
- Restricted item visible as metadata but value absent; whole record out of scope and absent.
- Unknown status/role/type; missing related campus/program/person/document.
- Mobile keyboard, password manager, autofill, landscape, safe area, browser zoom and high text scale.
- Screen reader landmarks/headings/live regions; keyboard-only; forced colors; reduced motion.
- Print page breaks, repeated table headers, visible provenance and hidden controls.

## 13. Rollout and rollback

### Feature switch

Use a server configuration switch such as `UI_V2_ENABLED` to select v2 base/templates during migration. It controls presentation only; routes and data loaders remain identical.

- Development: enabled per environment/user fixture.
- Pilot: enabled for designated non-production users/roles.
- Production: staged by approved deployment, not a client-side toggle.
- Do not expose both versions through user-controlled query parameters that could leak or confuse state.

### Rollback

- Rollback switches template/assets to the last approved version without database migration.
- Because mutations remain native and routes unchanged, no UI-specific data migration is required.
- Asset manifests are deployment-versioned so rollback never points to missing hashes.
- Monitor client errors, 4xx/5xx changes, task completion, form abandonment and accessibility feedback without recording sensitive field values.

### Legacy deletion

Keep rollback capability through the observation window. Delete old templates/theme only after:

- All roles complete pilot journeys.
- No unresolved severity-1/2 issue.
- Parity, accessibility and performance gates pass in the deployed environment.
- Stakeholder approval and recovery artifact are recorded.

## 14. Implementation sequence

| Slice | Scope | Primary proof |
|---|---|---|
| 0 | Baseline manifest, fixtures, screenshot harness | Trusted before/after oracle |
| 1 | Tokens, component gallery, Vite/island build | System quality and deployability |
| 2 | Auth shell and all account pages | Forms, errors, no-JS, autofill |
| 3 | Signed-in shell, navigation, command palette, feedback | Role visibility, islands, focus |
| 4 | ERP hub/projects and campus directory | Cards, lists, tables, responsive records |
| 5 | Notifications/imports/audit | Dense data, critical feedback, print |
| 6 | Faculty/ICC/IGP/volunteer dashboards | Role variants, charts, queues |
| 7 | ERP project detail | Versions, lifecycle, restricted data |
| 8 | Legacy campus project workspace one tab at a time | Twenty forms, dense responsive workflows |
| 9 | Reports and user administration | Exports, scope assignment, destructive actions |
| 10 | Optional 3D/scrollytelling polish | Performance-safe progressive enhancement |
| 11 | Bootstrap/theme removal, pilot and release | Zero legacy UI and reversible launch |

Do not combine Slices 7–9 into one implementation task.

## 15. Handoff packet required for each slice

- Scope and excluded routes.
- Baseline manifest/test fixture IDs.
- Master/page/component specs read.
- 21st component decisions and provenance, if used.
- Files changed and legacy ledger update.
- Before/after screenshots at all required viewports.
- Parity, accessibility, performance and no-JS results.
- Known limitations and rollback instruction.
- Reviewer and stakeholder sign-off.
