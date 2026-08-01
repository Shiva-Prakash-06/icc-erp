# ICC ERP Complete UI/UX Overhaul — Implementation Plan

Status: implementation contract — specification set v2  
Date: 17 July 2026  
Scope: presentation and interaction layer only

## Governing specification set

This plan defines sequencing and outcomes. Implementation is governed by the following companion contracts:

1. [`design-system/icc-erp/MASTER.md`](../design-system/icc-erp/MASTER.md) — exact visual, responsive, motion, accessibility and print tokens, with page overrides in `design-system/icc-erp/pages/`.
2. [`UI_DESIGN_SYSTEM.md`](UI_DESIGN_SYSTEM.md) — component APIs, states, content rules, legacy mappings and edge fixtures.
3. [`UI_PAGE_AND_STATE_MATRIX.md`](UI_PAGE_AND_STATE_MATRIX.md) — route-, role-, page-, workspace- and state-level requirements.
4. [`UI_FUNCTIONAL_PARITY_CONTRACT.md`](UI_FUNCTIONAL_PARITY_CONTRACT.md) — forms, payloads, links, permissions, protected data, browser behavior and parity tests.
5. [`UI_IMPLEMENTATION_PLAYBOOK.md`](UI_IMPLEMENTATION_PLAYBOOK.md) — toolchain, 21st.dev process, Framer Motion rules, migration steps, budgets, test gates and rollback.
6. [`UI_LEGACY_LEDGER.md`](UI_LEGACY_LEDGER.md) — removal inventory and proof that no old visual component family survives the final release.

When documents appear to conflict, functional/security behavior follows the parity contract and current server tests; accessibility/component behavior follows the design system; execution follows the playbook. No implementer may resolve a conflict by silently changing ERP behavior.

## 1. Outcome

Replace the current visual interface with a coherent, accessible, futuristic enterprise design system while preserving the ERP's behavior exactly.

This plan interprets “complete overhaul” to mean that current visual component implementations are not carried forward into the finished interface. Existing backend and browser contracts do carry forward: routes, permissions, forms, field names, request methods, CSRF protection, optimistic-concurrency versions, query parameters, data visibility, exports, offline behavior, and audit semantics.

The finished product should feel like a purpose-built operations platform rather than a themed Bootstrap application. Futuristic effects are permitted only when they improve hierarchy, orientation, feedback, or perceived continuity. Operational clarity wins over spectacle.

## 2. Non-negotiable invariants

The redesign must not change:

- Flask route URLs, HTTP methods, redirects, or response semantics.
- Authorization decisions, role-based visibility, scope rules, or sensitive-reference redaction.
- Form actions, field `name` values, submitted values, validation rules, or required hidden fields.
- CSRF injection and validation.
- Optimistic-concurrency `version` fields and conflict behavior.
- Project lifecycle transitions, task/checklist decisions, approval rules, or audit history.
- Import staging/commit behavior, report generation/export, document links, notifications, or account flows.
- Chart data meaning, report calculations, or server-provided template context.
- The encrypted offline snapshot, logout purge behavior, service worker, and PWA manifest.
- Deep links, browser back behavior, or meaningful query parameters such as project workspace tabs.

No redesign task is complete when it merely looks correct. It is complete only after the old and new interfaces produce the same requests and outcomes for the same user, role, data, and action.

## 3. Current-state findings

The application is Flask/Jinja with local Bootstrap, Bootstrap Icons, Chart.js, one 1,271-line theme stylesheet, and a 340-line shared JavaScript controller. The repository currently contains:

- 27 Jinja templates.
- 70 forms across 16 templates.
- 31 tables across 15 templates.
- Two Chart.js canvases plus several charts created by shared JavaScript.
- Large role-specific dashboards and a 1,442-line project workspace.
- Extensive inline styles and inline event handlers.
- Two partially competing visual languages: custom `*-oia` components and raw Bootstrap components/utilities.
- Existing glass blur, glow, hover transforms, and entrance animation, but without a unified token, accessibility, or reduced-motion strategy.

Framer Motion is installed, but the production UI is not React. Framer Motion therefore cannot simply animate the existing Jinja DOM. The implementation needs a small frontend build and isolated React enhancement islands; it must not turn the ERP into a client-rendered single-page application.

## 4. Design principles

### 4.1 Operational clarity first

- Every page has one obvious primary action.
- Status, ownership, deadlines, and blockers are more prominent than decorative copy.
- Dense data remains dense but becomes easier to scan through grouping, alignment, tabular figures, sticky headers, and progressive disclosure.
- Color never carries meaning alone; use label, icon, and color together.

### 4.2 Consistency before novelty

- One shell, type scale, spacing scale, radius scale, elevation scale, icon family, and motion language.
- One implementation per primitive: button, field, select, badge, card, table, empty state, alert, dialog, drawer, tabs, and page header.
- Page-specific styling is expressed through documented variants, not one-off CSS.

### 4.3 Progressive enhancement

- The server-rendered page is complete, navigable, and submittable before React mounts.
- React/Framer Motion may enhance presentation or feedback but must not own critical request construction.
- Enhancement failure must not remove content, controls, or success/error messages.

### 4.4 Accessibility is part of the component API

- WCAG 2.2 AA target: at least 4.5:1 normal-text contrast and 3:1 large-text/UI contrast.
- Visible `:focus-visible` treatment, logical tab order, skip link, sequential headings, landmarks, and correct labels.
- Minimum 44×44 px touch targets with at least 8 px separation where controls are adjacent.
- Keyboard-operable command palette, tabs, dialogs, drawers, tables, and chart alternatives.
- `prefers-reduced-motion`, `prefers-contrast`, browser zoom, and system text scaling are respected.

### 4.5 Motion explains state

- Motion establishes cause and effect, hierarchy, and continuity; it never delays access to data.
- Micro-interactions use 150–250 ms; complex transitions remain at or below 400 ms.
- Animate opacity and transforms, not layout dimensions.
- Exits are faster than entrances, interactions are interruptible, and content is usable during animation.

## 5. Target visual direction: Institutional Aurora

A restrained “institutional futurism” language is approved: calm, precise, layered, and contemporary rather than cyberpunk.

### Foundation

- Deep ink/blue-black application canvas, not pure black.
- Opaque high-contrast work surfaces for tables and forms.
- Translucent glass only for navigation, command surfaces, overlays, and non-critical summary layers.
- Teal/cyan as the primary navigational accent, indigo as the secondary dimensional accent, and amber as the attention/CTA accent.
- Semantic green, amber, red, and blue statuses, each paired with text and iconography.
- Subtle ambient gradients and fine grid/noise texture in large empty background areas; never behind dense reading content.

### Typography

- Primary UI family: self-hosted Inter Variable with the fallback stack defined in the master.
- Data/identifier family: IBM Plex Mono or system monospace for codes, timestamps, checksums, and tabular operational figures.
- Type scale: 12, 14, 16, 18, 24, 32, and 40 px, with 16 px minimum for mobile body/input text.
- The playful education-font recommendation returned by the UI/UX Pro Max database is intentionally rejected as a poor fit for a professional ERP.

### Layout

- Mobile-first layouts verified at 375, 768, 1024, and 1440 px.
- A 12-column desktop grid with dense 8–16 px internal component spacing and 24–32 px section rhythm.
- Adaptive navigation: compact bottom/top navigation on small screens and a persistent, collapsible rail on large screens.
- No page-level horizontal scroll. Wide data tables get an explicit scroll container, sticky priority columns, or a purpose-designed mobile record view.

### Iconography

- Replace mixed Bootstrap icon usage with the Lucide SVG family, using locally generated assets for Jinja and `lucide-react` for islands.
- Standardize size, stroke, alignment, accessible label behavior, and status-icon mapping.

## 6. Component architecture

### 6.1 New repo-native component system

Create a presentation system independent of backend services:

```text
app/
  templates/
    ui/                    # Jinja macros and structural primitives
      button.html
      field.html
      badge.html
      card.html
      data_table.html
      page_header.html
      empty_state.html
      feedback.html
      navigation.html
  static/
    css/
      tokens.css           # primitive and semantic tokens
      base.css             # reset, typography, accessibility
      components.css       # production component styles
      layouts.css          # shell and responsive layouts
      utilities.css        # deliberately small utility set
    ui/                    # built React/Framer Motion assets
frontend/
  src/
    motion/                # tokens, reduced-motion helpers
    islands/               # independently mounted enhancements
    components/            # reviewed 21st-derived React components
    entries/               # per-island build entry points
```

The playbook's source/output structure is authoritative. Generated assets land in `app/static/ui/`, and Flask remains deployable without a Node runtime in production.

### 6.2 Jinja remains the functional source of truth

Use Jinja macros for controls that submit or expose protected data. Macros must preserve caller-supplied `action`, `method`, `name`, `value`, `id`, `aria-*`, hidden inputs, conditional rendering, and server errors.

Recommended primitives:

- Application shell, sidebar/rail, top bar, mobile navigation, breadcrumbs.
- Page header, section header, contextual action bar, and filter bar.
- Button/link button, icon button, split action, and destructive action.
- Text field, text area, select, checkbox, radio, fieldset, helper text, and error summary.
- Status badge, role badge, metadata chip, and count badge.
- KPI card, work surface, record card, chart frame, and callout.
- Data table, responsive record list, sorting header, empty/loading/error row, and pagination.
- Tabs, accordion/disclosure, drawer, dialog, toast/alert, skeleton, and empty state.
- Timeline, progress indicator, stepper, task row, and checklist row.

### 6.3 React/Framer Motion islands

Use React only where it adds meaningful interaction or visual continuity:

- `MotionAtmosphere`: non-interactive ambient gradient/mesh layer.
- `CommandPalette`: accessible keyboard search and grouped navigation, using server-provided URLs.
- `FeedbackCenter`: animated toast stack that mirrors server flash messages while retaining the underlying live region.
- `MetricMotion`: optional number/trend transitions on read-only KPI summaries.
- `WorkspaceNavigator`: enhanced visual tab/section indicator that preserves real links and query parameters.
- `ExecutiveStory`: lazy-loaded scrollytelling for dashboard/report overview only.

Do not use React to take ownership of login, registration, approvals, task/checklist decisions, attendance, contributions, imports, lifecycle transitions, report generation, or other critical forms. These may receive motion wrappers and enhanced feedback while remaining native forms.

### 6.4 Bootstrap exit strategy

The finished interface should not depend on old Bootstrap visual components. Migration may temporarily retain Bootstrap utilities and behavior behind a compatibility layer, but completion requires:

- All production primitives rendered by the new system.
- No remaining `card-control`, `form-input-oia`, `table-oia`, or equivalent legacy component markup.
- No raw Bootstrap card/table/form styling used as a page's visual implementation.
- Bootstrap CSS/JS removed after collapse, drawer, modal, and utility dependencies are replaced and parity-tested.
- `theme.css` removed or reduced to a temporary forwarding file, then deleted at the final cleanup gate.

## 7. Framer Motion strategy

Define motion centrally rather than adding animation page by page.

### Tokens

- Durations: instant 100 ms, fast 160 ms, standard 240 ms, deliberate 360 ms.
- Easing: standard enter, faster exit, and one restrained spring preset.
- Distance: 4, 8, 16, and 24 px; no arbitrary movement values.
- Stagger: 30–45 ms, capped so large lists do not produce long cascades.

### Approved motion patterns

- Press feedback: scale to 0.98 and restore immediately.
- Page content: subtle 8–12 px fade/translate on first entry, not on every back-navigation restoration.
- Drawers/dialogs: motion originates from the trigger direction and restores focus on close.
- Disclosure: content crossfade/transform with semantic expanded state available immediately.
- Data updates: brief highlight/crossfade; never hide the final value behind a count-up.
- Navigation: shared active indicator and spatially consistent forward/back cues.

### Reduced-motion mode

`MotionConfig` and CSS media queries must disable parallax, 3D tilt, large translation, stagger, and count-up behavior. State changes use an immediate update or short crossfade. No information is conveyed only through motion.

## 8. 3D, glassmorphism, and scrollytelling boundaries

### 3D

Use CSS perspective plus Framer Motion for lightweight depth in the dashboard hero, project health constellation, or campus/program overview. Do not add WebGL/Three.js initially. Reconsider true 3D only after performance measurements show sufficient budget and a real information-design benefit.

3D elements must be decorative/read-only, pointer-optional, keyboard-neutral, lazy-loaded, and removable without information loss.

### Glassmorphism

Use blur to communicate layered context: top bar, command palette, drawer, modal, floating filter bar, or summary overlay. Tables, forms, body copy, and critical alerts use opaque surfaces for contrast and performance.

Every glass surface needs an opaque fallback for reduced transparency, unsupported browsers, print, and low-power/mobile modes.

### Scrollytelling

Use only on read-oriented overview surfaces:

- Mission Control executive narrative.
- Project overview showing lifecycle, risks, reach, tasks, and closure readiness.
- Report preview presenting the story behind operational figures.

Do not use scrollytelling in data entry, approvals, imports, user administration, or audit tables. Scrolling must never be required to trigger data loading or make an action available.

## 9. How each tool is used

### UI/UX Pro Max

1. Persist a project master design system in `design-system/icc-erp/MASTER.md` after stakeholder approval.
2. Create overrides for shell, authentication, dashboards, project workspace, reports, and administration.
3. Query accessibility, forms, navigation, chart, icon, responsive, and React performance guidance before each component family.
4. Record accepted recommendations and deliberate overrides; database output is input to design review, not an automatic decision.
5. Run the skill's pre-delivery checklist for each release slice.

### 21st.dev and Magic MCP

21st.dev is a React/Tailwind component ecosystem, so it should be used through a controlled adaptation workflow:

1. Generate/search for a small component family, not an entire ERP page: shell, command palette, KPI card, data table, form field, dialog, empty state, timeline, or chart frame.
2. Give Magic the approved ICC tokens, density rules, accessibility contract, and a screenshot/DOM description of the target state.
3. Generate two or three variants in an isolated Vite UI lab.
4. Review keyboard behavior, responsive behavior, dependency cost, licensing/provenance, semantic markup, and reduced-motion behavior.
5. Either:
   - adopt the reviewed component as a React island when it is genuinely interactive; or
   - translate its visual structure into a Jinja macro and repo-native CSS for server-rendered controls.
6. Strip unused dependencies and Tailwind assumptions. No generated component is copied blindly into production.
7. Once the ICC component set stabilizes, publish it to a private 21st component library so later generation reuses approved primitives instead of inventing variants.

21st-generated changes are restricted to the frontend lab/component directories until their parity gate passes. They must not edit Flask blueprints, models, services, migrations, or security configuration.

### Framer Motion

Framer Motion implements the approved motion tokens and React enhancement islands. It is not a reason to migrate the application to React and is not used to replace native HTML form behavior.

## 10. Migration phases and gates

### Phase 0 — Baseline and contract freeze

Deliverables:

- Route/page/role matrix covering anonymous, pending, faculty/admin, ICC core, IGP core, volunteer/buddy, and restricted-data cases.
- Inventory of every form action, method, named field, hidden version, CSRF expectation, table, chart, flash state, tab parameter, modal/disclosure, and empty state.
- Baseline screenshots at 375, 768, 1024, and 1440 px for representative seeded data.
- Baseline request traces for critical workflows.
- Current automated test run captured before UI changes.

Gate: the contract inventory is reviewed and no protected workflow is missing.

### Phase 1 — Design system and frontend foundation

Deliverables:

- Approved Institutional Aurora master system and page overrides.
- Semantic color, typography, spacing, radius, elevation, z-index, breakpoint, and motion tokens.
- Vite + TypeScript build that emits hashed assets to `app/static/ui/`.
- Explicit React, ReactDOM, Framer Motion, and build dependencies with production Node-free serving.
- UI lab for 21st component evaluation.
- Global accessibility base: skip link, focus style, landmarks, live regions, reduced motion, and font loading.

Gate: a static component gallery passes contrast, keyboard, responsive, and reduced-motion checks.

### Phase 2 — New shell and authentication

Rebuild:

- Desktop rail, top bar, mobile navigation, drawer, breadcrumbs, academic-year context, user menu, logout placement, command palette, flash/toast system.
- Login, registration, pending approval, reset, forgot-password, and recovery screens.

Keep the same links, route-aware active states, role visibility, form actions, and field payloads.

Gate: anonymous and every role can reach exactly the same destinations as before; all account flows pass automated tests without JavaScript.

### Phase 3 — Core primitives and low-risk directories

Rebuild campus directory, campus/program detail, ERP hub, project list, notifications, imports, and audit using the new page header, cards, tables, forms, badges, empty states, and filters.

Gate: responsive data behavior, keyboard sorting/disclosure, import commit safeguards, notification actions, and audit readability pass parity tests.

### Phase 4 — Role dashboards

Rebuild Mission Control and the faculty, ICC core, IGP core, volunteer/buddy, and profile variants.

- Define a stable dashboard grid and KPI hierarchy.
- Preserve role-specific datasets, decisions, filters, and action forms.
- Restyle Chart.js via tokens and add accessible summaries/data alternatives.
- Add restrained motion, ambient depth, and the optional executive scrollytelling layer.

Gate: screenshot and E2E coverage for each role; data values and available actions match the baseline exactly.

### Phase 5 — Project workspace

Treat the 1,442-line project detail template as its own program of work. Migrate one workspace section at a time:

1. Overview, metadata, lifecycle, and closure blockers.
2. Participants and attendance.
3. Contributions and verification.
4. Buddy assignment and interaction logs.
5. Feedback submission and moderation.
6. Documents and restricted references.
7. Tasks, checklists, schedules, team, and evidence.

Keep real URLs/query parameters for section navigation. Use sticky contextual actions and progressive disclosure, but never hide blockers or required decisions behind decorative interaction.

Gate after every section: identical GET visibility, identical POST payload, identical redirect/flash result, identical authorization outcome, and a keyboard/mobile usability check.

### Phase 6 — Reports and administration

Rebuild report list, compile form, report detail/preview, export actions, and user approval/role management. Apply the highest caution to destructive/reject actions and scope assignment fields.

Gate: generated reports and exported files are byte/semantic-equivalent where expected; role and scope mutations create the same audit records.

### Phase 7 — Futuristic polish and performance

- Add approved Framer Motion choreography, CSS 3D summaries, glass layers, and read-only scrollytelling.
- Lazy-load non-critical islands.
- Remove decorative effects from low-power and reduced-motion paths.
- Tune Chart.js, font loading, CSS, and bundle splitting.
- Test real datasets, long names, zero states, error states, timeouts, and high-density tables.

Gate: interaction remains responsive; no new layout shift; animations stay within frame budget; no workflow depends on an effect.

### Phase 8 — Legacy removal and release

- Remove legacy component markup, inline styles/handlers, obsolete theme rules, Bootstrap presentation dependencies, and temporary compatibility adapters.
- Run the full Python, security, UI contract, E2E, visual regression, accessibility, and performance suites.
- Complete stakeholder review with faculty/admin, ICC, IGP, and volunteer/buddy views.
- Release behind a reversible configuration switch, then remove the old theme only after an agreed observation window.

Gate: all acceptance criteria below pass and the visual inventory confirms no legacy component family remains.

## 11. Verification strategy

### Existing regression suite

Run the repository's full pytest/unittest/coverage checks on every migration slice. Backend failures block UI work from merging.

### New contract tests

- Pytest + HTML parsing assertions for form action, method, named fields, hidden CSRF/version values, links, and role-conditional content.
- Route smoke tests for every protected page and representative role.
- POST contract tests comparing payloads and resulting redirects/flashes.
- Explicit tests for restricted document visibility and sensitive data not appearing in markup or client props.

### Browser E2E tests

Add Playwright journeys for:

- Login/reset/recovery.
- Faculty/admin approval and role assignment.
- ICC and IGP dashboard decisions.
- Volunteer contribution and buddy logs.
- Project task/checklist updates including version conflict.
- Attendance, feedback, document indexing, import staging/commit, notifications, report generation, and exports.
- Keyboard-only navigation, focus restoration, command palette, drawers/dialogs, and reduced-motion mode.
- JavaScript-disabled critical workflows.

### Visual regression

Capture stable seeded screenshots for every page family, role, required breakpoint, empty/loading/error state, long-content case, forced-colors state, and reduced-motion state. The application ships the approved light sky-blue theme plus a white high-contrast print treatment; no interactive theme selector is part of this overhaul. Review diffs per component migration rather than accepting broad baseline replacements.

### Accessibility

- Automated axe checks with zero critical/serious violations.
- Manual keyboard and screen-reader smoke pass.
- Contrast validation for all token pairs and chart colors.
- 200% zoom, forced colors/high contrast, reduced motion, and touch target checks.

### Performance budgets

Proposed starting budgets, refined after baseline measurement:

- No JavaScript required for initial content or critical form submission.
- React/Framer initial enhancement payload kept route-aware and split by island.
- No avoidable layout shift from fonts, charts, or motion.
- 60 fps target for interaction animation on representative mid-range hardware.
- Decorative background/3D effects disabled when they threaten input latency or scrolling.

## 12. Definition of done

The overhaul is complete only when:

- Every current user-visible page and state has a new design-system implementation.
- Every current workflow and role boundary passes functional parity tests.
- No legacy visual component class or raw Bootstrap component remains in production templates.
- No critical action depends on React, animation, hover, gesture, or scroll position.
- The design is coherent across desktop, tablet, mobile, dense data, empty states, errors, and long content.
- WCAG 2.2 AA checks and manual keyboard validation pass.
- Reduced-motion and opaque glass fallbacks are complete.
- Frontend assets are versioned, reproducible, CSP-compatible, and served locally.
- Full Python tests, contract tests, E2E journeys, and approved visual diffs pass.
- Product stakeholders sign off on faculty/admin, ICC, IGP, volunteer/buddy, and anonymous/account experiences.

## 13. Out of scope

- Changing business rules, backend services, data models, API schemas, or database migrations for visual convenience.
- Converting the ERP into a React SPA.
- Replacing server authorization with client-side gating.
- New ERP capabilities disguised as interface polish.
- Adding WebGL, video backgrounds, or heavy shader effects before a measured need and explicit approval.

## 14. Recommended first implementation slice

Start with Phase 0 and Phase 1, then build one complete vertical slice consisting of the new shell, flash/toast feedback, login screen, ERP hub, project list, and one read-only project overview. This proves tokens, Jinja macros, 21st adaptation, Framer Motion islands, role-aware navigation, responsive data surfaces, and test strategy before touching the highest-risk workspace forms.

Do not start by restyling the 1,442-line project workspace in place. Its migration should begin only after the component system and parity harness have already succeeded on the smaller slice.

## 15. Tooling references

- [21st.dev documentation](https://help.21st.dev/)
- [21st.dev component catalogue](https://21st.dev/)
- [21st.dev Magic MCP source and setup](https://github.com/21st-dev/magic-mcp)
- [21st.dev component libraries workflow](https://21st.dev/blog/component-libraries)
