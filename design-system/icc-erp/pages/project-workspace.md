# Project Workspace Override

Inherits `MASTER.md`.

- The identity bar is sticky: code, status, title and the lifecycle actions stay on screen while a long workspace scrolls. It goes static below 767px.
- **Closure blockers open the Overview tab, uncollapsed, each with a Resolve link to the record that clears it.** They decide whether the project can close; they are never an accordion.
- The sidebar is one `.facts-list` "Record" panel — the facts, not forms. The two definition lists it replaced are gone.
- Four sections sit in the tab bar (Overview, Delivery, People, Budget); Contributions, Insights and Resources sit behind "More". Every one of the seven links stays in the DOM and keeps its existing `tab` query value, so no-JS navigation and emailed deep links keep working.
- Tabs are real links preserving browser history. Mobile uses a section selector plus in-page headings; no swipe-only tabs.
- A tab's primary content is never behind a disclosure. Disclosures hold settled records, provenance, and secondary "add" forms.
- A deep link to a record inside a disclosure opens that disclosure (`revealFragmentTarget` in `app.js`) so the link always lands on something visible.
- Forms remain server-rendered. Sticky regions never obscure validation errors or the final field.
- Restricted references use explicit locked states; never render protected values into hidden DOM or island props.
- Roll call is a segmented radio control per person, posting the same `status_<person_id>` field the server already reads.
