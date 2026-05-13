---
name: named-registration-collision
when: Consumers register entities under supplied identifiers.
---

# Named Registration Defines Collision Behavior

The behavioral contract must define what happens when a registration uses an
identifier that is already registered. The rule must be consistent for the
registration surface unless the contract explicitly defines narrower cases.

Allowed rules include reject, replace, or idempotent no-op for equivalent
entities. If collisions cannot occur in the slice, the contract must state why.

## Illustrations

**Bad - silent default.** The contract says registration succeeds but does not
say whether a duplicate name replaces or rejects the prior entity.
**Good:** A duplicate name rejects with a collision outcome and leaves the
existing registration in force.

**Bad - implicit out of scope.** The designer says "we only call it once" but
the contract is silent.
**Good:** The contract scopes out collision because the slice performs exactly
one hardcoded registration.

