---
name: stable-code-clause-ids
when: Always.
---

# Stable Code Clause IDs

Every feature-level Code Contract clause has a stable ID of the form
`F-CC-<n>`. These IDs are the slice surface used by `tasks.md`, handoffs,
implementation plans, and Code Contract Defences.

Do not rely on headings, bullets, or prose position alone. A clause title
can be edited for clarity without changing which obligation a task owns.

## Illustrations

**Bad - title-only obligation.** "Public surface remains stable" has no
stable handle for task slicing.
**Good:** `F-CC-2`: "The CLI command surface for existing monitoring
commands remains available while the event publication internals move
behind the event service."

**Bad - grouped obligations under one ID.** `F-CC-1` requires both a new
service boundary and a migration strategy.
**Good:** Split them into separate `F-CC-<n>` clauses so tasks can own and
defend each obligation independently.
