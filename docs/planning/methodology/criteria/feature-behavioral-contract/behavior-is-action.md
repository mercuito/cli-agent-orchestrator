---
name: behavior-is-action
when: Always.
---

# Behaviors Are Actions

Every behavior must describe an actor or system action under concrete
preconditions and the observable outcome produced by that action. A behavior is
not a standing rule, invariant, admissibility table, data-shape requirement, or
other constraint written in Given/When/Then clothing.

If the clause is true across time, across many operations, or without a
specific action that changes or attempts to observe the system, it belongs as a
constraint under the relevant invariant instead of as a behavior.

## Illustrations

**Bad - invariant as behavior.** Given any saved record, when time passes, then
there is never more than one active record per user.
**Good:** Constraint: there is never more than one active record per user.

**Bad - rule without action.** Given a draft item, when validation is considered,
then required fields are present.
**Good:** Given a user submits a draft item missing a required field, when the
system validates it, then submission is rejected with a diagnostic naming the
missing field.
