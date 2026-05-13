---
name: broad-claim-coverage
when: A behavior depends on merge, composition, ordering, visibility, inheritance, selection, or partitioning semantics.
---

# Broad Claims Carry Non-Happy-Path Evidence

When a claim covers behavior that depends on merge, composition, ordering,
visibility, inheritance, selection, or partitioning semantics, the
evidence must include at least one non-happy-path or composition case.

A single happy-path example does not support a general behavior claim.

## Illustrations

**Bad — happy path only.** Claim: "Config files merge correctly across
layers." Evidence: one test where two non-overlapping configs merge.
**Good:** Evidence covers an overlap case (later layer wins) and a
deletion case (later layer removes a key).

**Bad — no ordering case.** Claim: "Handlers run in registration order."
Evidence: a single handler runs successfully.
**Good:** Evidence shows two handlers register and run in the order they
were registered, plus a case proving the order is not coincidental.
