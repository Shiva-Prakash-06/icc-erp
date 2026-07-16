# Three-Day Demonstrator Script

1. Confirm the yellow **Demonstrator—Not Production** banner is visible.
2. Sign in with an explicitly bootstrapped local demonstrator account.
3. Open **ERP Operations** and verify 9 projects, 31 people, and 3 current import batches in a fresh run.
4. Open **Coffee Meet & Greet**:
   - verify 31 team assignments;
   - verify 9 source actions;
   - verify the eight programme segments and overall session;
   - verify actual reach 175 and the document index;
   - show that unresolved tasks block closure.
5. Open **International Summer School 2026**:
   - verify all 50 requirements;
   - show that the passport/visa/C-Form item is marked restricted;
   - reject an item without a reason and confirm it is refused;
   - add a reason or approved waiver and confirm an audit event is created.
6. Open **Staged Imports** and show checksums, valid/error/committed counts, and zero reconciliation differences.
7. Show scoped-role tests: an ICC head cannot approve IGP work, a participant exists without an account, and sensitive links are redacted without named permission.
8. Generate a project report preview and explain that human approval is mandatory for narrative publication.
9. Close with [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md) and the four-approver production gate.
