# Project Workspace Override

Inherits `MASTER.md`.

- Project identity, lifecycle status, closure blockers, and current contextual action remain visible before tab content.
- Tabs are real links preserving the existing `tab` query parameter and browser history.
- Mobile uses a section selector plus in-page headings; no swipe-only tabs.
- Forms remain server-rendered. Sticky action regions never obscure validation errors or the final field.
- Restricted references use explicit locked states; never render protected values into hidden DOM or React props.
- Long tables choose record-card mobile layouts for forms and priority-column scrolling for read-only schedules/audit data.
- No scrollytelling or 3D inside task, checklist, attendance, contribution, buddy, feedback, or document-entry regions.
