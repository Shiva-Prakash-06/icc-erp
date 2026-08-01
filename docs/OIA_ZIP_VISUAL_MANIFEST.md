# OIA ZIP → ICC ERP visual implementation manifest

## Authority boundary

The OIA prototype is the visual reference. The Flask ERP remains the only functional source of truth. No prototype route, data fixture, permission decision, fake progress state, synthetic health metric, or unsupported control is shipped.

## Translation decisions

| Prototype characteristic | ERP implementation |
|---|---|
| Dark translucent shell | Light sky-blue canvas with translucent white rail/top bar |
| Purple/pink ambient fields | Sky, cyan, and blue radial fields only |
| Dense collapsible navigation | Existing server-authorized destinations in a 248/76px rail |
| Bento dashboard | Existing role data in shared KPI, chart, queue, project, and activity surfaces |
| Project card/board/table selector | Presentation-only views over the same server-rendered project links; no drag-and-drop |
| Project hero/timeline/panels | Existing project lifecycle, sessions, people, tasks, documents, feedback, and report actions |
| Animated drawers/selectors | Progressive Framer Motion enhancement over native controls and fallback content |
| Prototype icon language | Locally generated Lucide SVG masks and `lucide-react` |
| Tailwind/shadcn components | Semantic repository-native CSS and Jinja macros/classes |

## Route family mapping

| Design family | Existing route ownership | Deliberate omissions |
|---|---|---|
| Shell and command | Shared signed-in base | No client-derived navigation or permission filtering |
| Dashboard | Faculty, ICC, IGP, volunteer dashboards | No invented KPI, leaderboard, or health telemetry |
| Projects | ERP projects, campus programs | Board is read-only; lifecycle actions remain on existing routes |
| Project workspace | ERP detail and campus project detail | No new tabs, state transitions, or facade routes |
| Attendance, buddies, feedback, documents | Existing project sections | No new top-level modules |
| Reports and analytics | Existing list/generate/view/preview pages | No simulated generation progress or unsupported filters |
| Administration | Existing users, imports, audit, notification routes | No fictional permissions, appearance editor, or 2FA UI |
| Authentication | Existing login/register/recovery/reset/pending routes | New composition only; authentication behavior unchanged |

## Geometry and type

- Rail: 248px expanded / 76px collapsed; top bar: 56px.
- Content: 32px desktop and 16px mobile, fluid to 1600px.
- Grid: twelve columns, 16px gap; cards 16px radius, nested surfaces 12px, controls 8px.
- Space Grotesk headings, Inter interface text, IBM Plex Mono operational data; all self-hosted WOFF2.
- Lucide is the rendered icon family. Legacy `ph-*` class names remain only as nonvisual compatibility selectors while template migration is completed.

## 21st.dev review record

21st.dev was searched for gaps in light glass authentication, dense project data presentation, and enterprise tables. Candidate families included Glassmorphism Navigation, Data Card Display, and Project Data Table. Their code was not imported because the candidates depended on Tailwind/shadcn conventions and carried mock behavior that conflicts with the server-first architecture. The useful composition ideas—editorial authentication split, compact data cards, and responsive record-table hierarchy—were translated into repository-native Jinja and semantic CSS.

## Progressive enhancement inventory

- Rail collapse: native button + local presentation preference; shell remains navigable without JavaScript.
- Command palette: server-derived destination allowlist with direct-link fallback navigation.
- Notification preview: server-authorized latest records only; full notification history and forms remain server routes.
- Project view selector: cards/board/table presentational preference; every record remains a native link.
- KPI spotlight and tilt: fine-pointer decoration only; disabled for reduced motion.
- Progress reveal: transforms the true server percentage with `scaleX`; the numeric value is immediately truthful.

## Verification gates

- Route contract: 89 routes and URL hash `aa36632192705fe035a0d16779d86c2ff68655ca7e58878a02a9d614533e853b`.
- No database, API, route, form-payload, authorization, export, or offline contract changes.
- JavaScript-disabled workflows remain server-submitted and accessible.
- Shared compressed JavaScript, per-island JavaScript, CSS, and font budgets are measured in the release check.
- Chrome visual checks cover authentication, dashboard, ERP hub, projects, and reports; responsive behavior is also covered by CSS breakpoints and contract tests.
