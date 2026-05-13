---
name: stable-behavior-ids
when: Always.
---

# Stable Behavior IDs

Every behavior and constraint has a stable ID. Behaviors use `B-<n>`;
constraints use `C-<n>`. Parent headings reference the capability or
invariant ID from the Capability Contract, such as `CAP-1` or `INV-2`.

IDs are part of the slice surface. `tasks.md`, handoffs, defences, and
reviews use them to identify exact obligations without restating clause
text.

## Illustrations

**Bad — title-only behavior.** `### Behavior: Login succeeds` cannot be
referenced safely if the title changes.
**Good:** `### B-3 — Login Grants A Session` gives the task list and defence
a stable behavior ID.

**Bad — unanchored parent.** `## Capability: Login` does not prove which
capability is being decomposed.
**Good:** `## Capability: CAP-1 — Login` links the behavior group to the
capability contract.
