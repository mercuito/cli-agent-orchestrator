---
name: stable-capability-ids
when: Always.
---

# Stable Capability IDs

Every capability and invariant has a stable ID. Capabilities use `CAP-<n>`;
invariants use `INV-<n>`. IDs are part of the contract surface: later
artifacts reference them, and they must remain stable unless the capability
or invariant is removed or the feature contract is deliberately reissued.

Do not rely on headings alone. A title can be edited for clarity without
changing the identity of the capability or invariant.

## Illustrations

**Bad — title-only capability.** `### Restored Session` gives reviewers no
stable reference once the title changes.
**Good:** `### CAP-2 — Restored Session` lets the behavioral contract and
task list reference `CAP-2`.

**Bad — implicit invariant.** A paragraph says "sessions are always tied to
one workspace" without an ID.
**Good:** `### INV-1 — Session Workspace Ownership` names the invariant and
gives downstream artifacts a stable reference.
