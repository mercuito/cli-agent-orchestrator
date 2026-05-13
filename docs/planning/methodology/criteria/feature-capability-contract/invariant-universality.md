---
name: invariant-universality
when: The capability contract declares invariants.
---

# Invariants Are Universal

An invariant is a property that must hold across the entire domain at all
times — not a property that holds only in specific scenarios. Scenario-bound
properties belong in the behavioral contract as constraints, not here.

If an invariant cannot be stated without "when X" or "during Y," it is a
constraint, not an invariant.

## Illustrations

**Bad — scenario-bound.** "When a user logs in, there is exactly one active
session for that user."
**Good — universal.** "There is never more than one active session per user."
The login scenario is one of many that this invariant covers; the invariant
itself does not name a scenario.

**Bad — implicit scope.** "Sessions cannot be reactivated."
**Good:** "A session that has entered the terminated state never returns to
the active state." Universal across the session lifecycle.

