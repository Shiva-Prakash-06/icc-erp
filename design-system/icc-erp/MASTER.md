# ICC — Design System Master

Status: mandatory source of truth
Mode: calm, task-first; light; white high-contrast print output
Density: low. Whitespace is a feature, not waste.
Motion: restrained
Last revised: 30 October 2026

This file governs the presentation layer: what a screen shows, in what words,
and how it is laid out. Flask routes, permission checks, form payloads,
server validation, exports and models stay authoritative.

## Why this file changed on 30 October 2026

It used to describe an "enterprise dense 9/10" ERP: a Tile System of campus
and division tiles, seven-column work rows, a tab with a strip of section
tiles, sixteen modal dialogs and five status dimensions. People could not
find their own work in it. The application was rebuilt in four phases
(recorded in `docs/UI_LEGACY_LEDGER.md`) around one idea — **each person
opens the app and sees their own list of things to do** — and this file now
describes that.

Who the screens are for: Faculty, the USC, the ICC Events, Media and
Culturals heads, the IGP head, and volunteers. **Assume every reader reads
like a twelve-year-old.** Data entry comes first; seeing your work comes
second.

## The eight rules

1. **One screen, one job.** At most one primary button per screen. If a
   screen needs two, it is two screens or a folded card.
2. **Show five, hide the rest.** Lists show at most five rows, then
   "Show all 12". Finished things fold into one line, such as "✓ 12 done".
   Groups (Today / This week / Later) start folded except the first.
3. **Plain words only.** Short sentences, sentence case, no uppercase
   micro-labels, no record codes (`ICC-2026-CEN-001`) shown to people. The
   banned words and their replacements are `glossary.PLAIN_WORDS`, and
   `tests/plain_language_test.py` fails the build if one reaches a page or a
   message. Say "money", not "reimbursement"; "skip", not "waive"; "file",
   not "evidence"; "check" and "save", not "stage" and "commit".
4. **Big and calm.** Body text 16–17px. Every control at least 44px tall
   (48px on a phone). At least `--space-6` between blocks. White sections on
   the grey canvas. Colour only where it means something: late, done, needs
   an OK.
5. **Defaults everywhere.** Dates default to the event's date or today; a
   venue to the event's venue; the program is picked when there is only one
   to pick; "Who?" defaults to you; a head's year to the current one.
6. **Everything can be fixed.** Every saved row can be changed or removed.
   Removing shows a ten-second **Undo** and keeps the row (soft delete).
7. **Stay where you are.** After saving, come back to the same card with
   "Saved ✓" — never bounce to another step. A form posted from My work
   returns to My work (`next`).
8. **Phone first on the event day.** Roll call, ticking a to-do, adding a
   photo or a bill all work one-handed at 375px.

## Where things are

**The rail** (`app/services/navigation.py`) is four places and a Menu, and a
phone's bottom bar is exactly that:

| Slot | Who | Goes to |
|---|---|---|
| My work | everyone (volunteers see "My activities") | `/` |
| Events | everyone but volunteers | `/erp/projects` |
| + New event | people who run events | `/erp/projects/new` |
| Reports, or Account | Reports for Faculty and the USC; Account for everyone else | `/reports` · `/profile` |

The Menu holds Alerts, Account, People (Faculty), Upload a sheet, Who
changed what, "Show me around again" and Log out.

**My work** (`dashboard/home.html`) is one sentence, then — only when they
have something in them — Needs your OK (Faculty), To do (Today / This week /
Later), Today's event (Take attendance) and Your events (three at most). The
circle ticks an item in one press; an item about a poster, photos, a report
or a bill shows **Add file**, which sends the file and ticks it.

**An event** (`erp/event.html`) is its to-do list, then folded cards: Schedule,
People, Money, Files, Buddies (IGP), Feedback, Applications, Event details,
Finish. Each card shows one line until opened. Rarely used actions on a row
sit behind its "⋯".

## Click budget

Measured from My work by `e2e/click-budget.spec.ts`; a change that breaks one
of these is a regression.

| Task | Presses |
|---|---|
| See my work | 0 |
| Tick a to-do | 1 |
| Approve money (Faculty) | 1 |
| Hand in a poster against a Media item | 2 |
| Take attendance on the event day | 2 |
| Create an event | 2 (plus typing) |
| Ask for money | 3 (plus typing) |

## Building blocks

The calm classes are `cv-*` in `app/static/css/calm.css`:

- `cv-page` — one centred column, 820px at most.
- `cv-lede` — the one sentence at the top of a screen.
- `cv-section` — a white block with a heading (`cv-section__title`) and an
  optional count (`cv-count`) or link (`cv-section__link`).
- `cv-card` — a `<details>` that folds: a title and a one-line summary
  (`cv-card__sum`) until opened. Works without JavaScript.
- `cv-list` / `cv-item` — a row: `cv-item__main` (title and one meta line)
  and `cv-item__act` (its buttons). `cv-item__meta--late` for overdue.
- `cv-tick` — the round one-press "done" button.
- `cv-menu` — the "⋯" for skip, remove, change.
- `cv-group` — Today / This week / Later.
- `cv-form`, `cv-field`, `cv-row`, `cv-chips` / `cv-chip` (big radio
  buttons), `cv-check`, `cv-roll` (roll call), `cv-sticky` (a save bar).
- `cv-btn` (`--primary`, `--quiet`, `--danger`, `--big`, `--full`),
  `cv-more` ("Show all"), `cv-done` (a folded "✓ N done").
- `cv-stats` / `cv-stat` — the few big numbers on Reports.

A class built in a template string (`cv-tag--{{ status }}`,
`cv-stage--{{ stage }}`) must be safelisted in `postcss.config.cjs` or
PurgeCSS removes it.

## Foundation tokens

Unchanged from the Tile System and defined in `app/static/css/tokens.css`:

| Token | Value | Use |
|---|---:|---|
| `--color-canvas` | `#F2F2F3` | Page ground |
| `--color-surface-1` | `#FFFFFF` | Sections, cards, inputs |
| `--color-surface-2` | `#E9E9EA` | Hover |
| `--color-primary` | `#5980A6` | The one primary button, links |
| `--color-text` | `#1D1F20` | Text |
| `--color-text-secondary` | `#424244` | Labels |
| `--color-text-tertiary` | `#5D5D60` | One meta line under a title |
| `--color-border-strong` | `rgb(29 31 32 / 30%)` | Inputs and buttons |
| `--color-focus` | `#2C455D` | Focus ring |
| `--color-success` | `#3D6B57` | Done, happening now |
| `--color-warning` | `#8A6329` | Asked, waiting for Faculty |
| `--color-danger` | `#8F3D38` | Late, needs finishing, remove |

No gradients, glass, glow or tilt.

## Words

- An event's stage comes from its dates and reads: Coming up, Happening
  now, Needs finishing, Waiting for Faculty, Finished, Cancelled
  (`app/services/stage.py`).
- Money reads: Asked, Approved, Paid, Not approved.
- A to-do is done, skipped (with a reason), or still to do.
- Role names are plain: Faculty, USC, Events head, Media head, Culturals
  head, IGP head, Volunteer.
- IGP is "India Gateway Program" and ICC is "International Christite
  Community" (`glossary.DIVISION_NAMES`). The interface says "event" for both.
- The history page (`/erp/audit`) reads as sentences — "Asha took
  attendance" — from `glossary.AUDIT_ACTIONS`; raw identifiers sit behind
  its "⋯".

## Numbers, money and dates

Shared formatters in `app/services/formatting.py` are the only way a number
reaches a template: Indian digit grouping (`₹7,65,000`), `.00` dropped
unless there are paise, `pluralise` for every count. Dates and times go
through `localdate` / `localtime` / `localdatetime` and are campus-local.

## Icons

Lucide masks in `icons.css`, reached through historical `ph-*` class names.
A `ph-*` name with no mask draws as a solid square, so
`tests/ui_contract_test.py` checks every template and
`tests/my_work_test.py` checks every rail icon.

## Accessibility

- WCAG 2.2 AA is the floor, checked by axe on every page in
  `e2e/platform-matrix.spec.ts` and `e2e/accessibility-responsive.spec.ts`.
- Targets are 44px everywhere and 48px on a phone.
- A scrolling region must contain something focusable, or axe fails it.
- Folding is a native `<details>`, so it opens and closes with JavaScript
  off. "Add file" falls back to a Send button that appears once a file is
  chosen (CSS `:has()`).
- Every control has a visible label; no placeholder-only labels; no
  hover-only behaviour; status is never colour alone.

## Print

Reports print on white without the rail. The one-screen frame
(`.ds-app`, `.ds-screen`, `.ds-screen__body`) is unclamped for print, and
folded cards print open.

## Architecture invariants

- Flask/Jinja owns content, navigation, permission branches and forms.
  Every screen works with JavaScript off.
- The route count and URL-map hash change only with a re-baselined
  `tests/ui_contract/baseline.json` (`scripts/regen_ui_baseline.py`) and an
  entry in `docs/UI_LEGACY_LEDGER.md`. Old addresses that are retired
  redirect rather than 404.
- Local storage is unused.

## Anti-patterns

- A screen that opens on anything other than the reader's own work.
- More than one primary button on a screen.
- A list longer than five rows with no "Show all".
- A record code, an uppercase micro-label or a word from
  `glossary.PLAIN_WORDS` on a page.
- A form that sends you somewhere else after saving.
- A required field that could have had a default.
- Removing something with no Undo.
- An approval for anything other than money, finishing an event, or the
  public website — and an approver other than Faculty.
- Colour-only status, placeholder-only labels, icon-only navigation.
