---
name: proof-shape-not-test-instance
when: When the feature-level Test Contract carries clauses describing cross-task proof obligations.
---

# Test Contract Clauses Name Proof Shape, Not Proof Instances

Each clause in the feature-level Test Contract describes a proof
shape — the harness, scenario type, fixture pattern, or seam the proof
must exercise. It does not enumerate the specific tests that must
exist. What gets tested is implied by the behavioral contract (for
behavior-changing work) or by the preservation baseline (for refactor
work); the feature-level Test Contract shapes how that proof is
constructed across tasks. Specific test instances are a task-level
concern recorded in the Coding Test Contract.

## Illustrations

**Bad — clause prescribes a single test instance.** "A backend test
inspects `app.openapi()` and asserts the response schema is a `oneOf`
keyed by `kind`." The clause names one test that must exist; nothing
about the shape transfers to a second proof at the same boundary.
**Good:** "Cross-task proof of the registered-event ↔ API-schema seam
requires an assertion at the boundary between event registration and
OpenAPI emission, exercising every registered event in one scenario
rather than per-event unit assertions."

**Bad — instance disguised as shape.** "A test demonstrates that
post-migration rows reconstruct via `get_cao_event`." A reader cannot
tell whether the obligation is "one such test exists" or "this kind of
proof must exist over the migration."
**Good:** "Post-migration reconstruction proof has the shape:
fixture-loaded pre-migration rows are migrated by the production
migration path, then read back through `get_cao_event` and equality-
asserted against the originals. Per-task Coding Test Contracts decide
the specific scenarios."
