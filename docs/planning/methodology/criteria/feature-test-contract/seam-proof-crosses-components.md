---
name: seam-proof-crosses-components
when: When a Test Contract clause names a seam between components, layers, or pipeline stages as the proof target.
---

# Seam Proof Crosses Both Sides

When a clause names a seam — the boundary between two components, two
layers, or two stages of a pipeline — the required proof exercises
both sides of the seam together in a single scenario. Per-component
unit tests that pass on either side independently do not satisfy a
seam clause, because seam failures show up only when the two sides
meet under real fixtures.

The clause names the seam and states that the proof crosses it; the
specific scenarios live in the Coding Test Contract per
`proof-shape-not-test-instance`.

## Illustrations

**Bad — seam clause satisfied by parallel unit tests.** Clause: "The
serializer-to-storage seam is proven." An implementer adds two unit
tests: one that serialize-deserializes in memory, one that writes and
reads SQL rows with hand-built payloads. Neither test crosses the
seam — a serializer change that drops a field passes both but breaks
real-row reconstruction.
**Good:** A scenario publishes a real event through the dispatcher,
persists it through the storage layer, reads it back through the
production read path, and asserts the reconstructed instance equals
the original. The seam is exercised end to end with the production
serializer and the production read path in the same run.

**Bad — seam clause split across tasks without a crossing scenario.**
Task A's Coding Test Contract proves the serializer in isolation.
Task B's Coding Test Contract proves the storage layer in isolation.
The seam is named in the feature-level clause but never traversed by a
single test.
**Good:** One of the tasks owns the seam scenario explicitly; the
feature-level clause's slice in `feature-tasks.md` names which task
carries it.
