import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const output = resolve(root, "app/static/ui");
const manifest = JSON.parse(readFileSync(resolve(output, "manifest.json"), "utf8"));
const entry = manifest["frontend/src/entries/aurora.tsx"];
const publicEntry = manifest["frontend/src/entries/public.ts"];
if (!entry) throw new Error("Aurora production entry is missing from the Vite manifest.");
if (!publicEntry) throw new Error("Public production entry is missing from the Vite manifest.");

const cssBytes = (entry.css || []).reduce((total, file) => total + statSync(resolve(output, file)).size, 0);
const publicCssBytes = (publicEntry.css || []).reduce((total, file) => total + statSync(resolve(output, file)).size, 0);
const jsFiles = readdirSync(resolve(output, "assets")).filter((file) => file.endsWith(".js"));
const jsSizes = jsFiles.map((file) => [file, statSync(resolve(output, "assets", file)).size]);
const sharedJsBytes = jsSizes.reduce((total, [, size]) => total + size, 0);
const islandFailures = jsSizes.filter(([file, size]) => !file.startsWith("aurora-") && size > 35 * 1024);

// The 45 KiB application-CSS ceiling was set when the shipped bundle was
// 46,026 B -- 54 bytes of headroom. The blueprint redesign adds real
// component surface (dense project rows, status filter chips, the facts
// list, the home decision table, roll-call controls and the tab overflow)
// and lands at ~49.5 KiB raw / 10.4 KiB gzip, up from ~9.8 KiB gzip. Raised
// to 52 KiB to restore a working margin; revisit if it is approached again.
//
// Revisited 2026-09-16 for the first-run onboarding surface (welcome modal,
// anchored spotlight tour, getting-started checklist -- the ".onb-*" block in
// components.css). ~3.2 KiB raw / ~0.7 KiB gzip of genuinely new components,
// landing at ~52.7 KiB raw. Raised to 55 KiB; the gzip figure users actually
// pay is ~11.2 KiB.
//
// Revisited 2026-09-17 for the Tile System (tiles.css): the rail and screen
// frame, the navigation tile in four states, the one-line work row, the
// filter bar, the event card, the tab strip and the analytics marks. That
// is the whole new presentation layer, and it arrived alongside the removal
// of the shell it replaced -- the top bar, mobile header, bottom nav,
// drawer, notification slide-over and the project workspace's context
// header, stat bar and tab furniture (~8 KiB of source deleted from
// layout.css and components.css). Net 53.9 -> 63.3 KiB raw, 11.2 -> 12.7
// KiB gzip. Raised to 66 KiB. The next raise should come with a deletion:
// the .aurora-table--cards responsive card-table block exists for
// multi-line record tables that the Tile System is replacing tab by tab.
//
// Revisited 2026-09-17 for the UI/UX audit fixes. Added: the labelled
// mobile record card and its column-name pseudo-elements (P0-02), the
// review disclosure that took the select/reason/Save stack off every row
// (P1-04), the phone Menu drawer that reduced a seven-icon bar to four
// plus Menu (P0-05), the branded error page (P0-01), the single search
// control and the screen-level empty state.
//
// The paired deletion is a purge-scope correction rather than a source
// deletion, and it is worth more: templates/public_site/ is no longer in
// the application bundle's PurgeCSS content globs. Those pages inline the
// separately purged public stylesheet and never link aurora.css, so every
// rule the app bundle was keeping purely because a public template
// mentioned the class -- .page-header, .page-title, .page-subtitle,
// .page-eyebrow, .content-grid, .kpi-card, .resource-list,
// .aurora-breadcrumb, .public-chart-frame -- was being shipped to every
// signed-in page for nothing. That is 2.7 KiB raw off the bundle.
//
// Net 63.3 -> 69.8 KiB raw, 12.7 -> 13.6 KiB gzip. Raised to 72 KiB.
// The .aurora-table--cards deletion is still owed: attendance, audit,
// campuses, the report preview and the admin directory are the five
// screens still using it, and each becomes a .ds-row list.
//
// Revisited 2026-09-17 for the paged section workspace. The event
// workspace stopped stacking every list a tab owned inside one scrolling
// column; it is now a strip of section tiles above one open section, paged
// on the server, with the sixteen "add/import/attach" forms moved into
// :target dialogs. That is six new component families -- .ds-work,
// .ds-sections/.ds-section, .ds-panel, .ds-pager, .ds-factgrid/.ds-fact
// and .ds-modal -- at 8.5 KiB raw.
//
// This raise is NOT paired with a deletion, and that is worth stating
// plainly: nothing the redesign replaced became dead CSS, because
// .ds-rows, .ds-rows__foot and .aurora-disclosure are all still carrying
// other screens (imports, notifications, the report preview, the queue
// chip bar, roll call, create project). The two deletions now owed are
// .aurora-table--cards, as above, and .ds-facts' key/value strip, which
// the fact cards left to the error page alone.
//
// Net 69.8 -> 78.3 KiB raw, 13.6 -> 14.9 KiB gzip. Raised to 82 KiB.
const failures = [];
if (cssBytes > 82 * 1024) failures.push(`application CSS ${cssBytes} B exceeds 82 KiB`);
if (publicCssBytes > 20 * 1024) failures.push(`public CSS ${publicCssBytes} B exceeds 20 KiB`);
if (sharedJsBytes > 45 * 1024) failures.push(`shared JavaScript ${sharedJsBytes} B exceeds 45 KiB`);
for (const [file, size] of islandFailures) failures.push(`${file} ${size} B exceeds 35 KiB`);
if (jsFiles.some((file) => file.startsWith("animate-"))) failures.push("obsolete shared animation chunk is present");

if (failures.length) throw new Error(failures.join("; "));
console.log(`asset budgets passed: application CSS=${cssBytes} B, public CSS=${publicCssBytes} B, shared JS=${sharedJsBytes} B`);
