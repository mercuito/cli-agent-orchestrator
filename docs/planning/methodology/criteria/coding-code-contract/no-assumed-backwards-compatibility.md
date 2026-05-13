---
name: no-assumed-backwards-compatibility
when: Old callers or shapes could be preserved without an explicit contract requirement.
---

# Backwards Compatibility Requires Explicit Contract

The implementation must not preserve old call signatures, exports, file
formats, flags, behavior, or code paths unless the in-force plan or contract
requires compatibility or a deprecation period.

Deprecated code is removed rather than hidden behind aliases, overloads,
feature flags, or comments.

## Illustrations

**Bad - alias kept.** A rename from `getConfig` to `loadConfiguration` leaves
`getConfig` exported as an alias.
**Good:** Callers are migrated and the old export is removed unless a
deprecation plan requires it.

**Bad - old argument shape.** A new options object API also accepts positional
arguments.
**Good:** Positional callers are migrated to the options object.

