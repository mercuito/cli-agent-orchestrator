---
name: stable-test-clause-ids
when: Always.
---

# Stable Test Clause IDs

Every feature-level Test Contract clause has a stable ID of the form
`F-TC-<n>`. These IDs are the slice surface used by `feature-tasks.md`, handoffs,
implementation plans, and Test Contract Defences.

Do not rely on headings, bullets, or prose position alone. A clause title
can be edited for clarity without changing which proof obligation a task
owns.

## Illustrations

**Bad - title-only proof shape.** "Migration proof" has no stable handle
for task slicing.
**Good:** `F-TC-1`: "The migration proof preserves preexisting sessions and
shows new event-log tables are available after startup."

**Bad - multiple proof obligations under one ID.** `F-TC-2` requires both
API proof and migration proof.
**Good:** Split them into separate `F-TC-<n>` clauses so tasks can own and
defend each proof obligation independently.
