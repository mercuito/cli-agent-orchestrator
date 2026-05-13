---
name: given-when-then-verifiability
when: Always.
---

# Behaviors Use Verifiable Given/When/Then

Every behavior must state a concrete precondition, action, and observable
outcome in Given/When/Then form. A reader must be able to write a test from
the behavior without guessing what "correct" means.

Behaviors must use domain terms from the narrative vocabulary and must not
prescribe implementation mechanics.

## Illustrations

**Bad - vague outcome.** Given invalid config, when loading runs, then the
system handles it correctly.
**Good:** Given a config path that does not exist, when the service loads
configured inputs, then loading fails with a diagnostic naming the missing
path and no config entries are admitted.

**Bad - implementation body.** Then `ConfigLoader.parse()` throws.
**Good:** Then loading fails with the defined diagnostic outcome.

