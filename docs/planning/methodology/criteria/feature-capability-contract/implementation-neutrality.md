---
name: implementation-neutrality
when: Always.
---

# Implementation Neutrality

The capability contract uses domain entities only. No implementation-side
artifacts may appear in capabilities, invariants, or domain graphs — no
class names, module names, function names, file paths, payload shapes,
library names, or framework concepts.

A box labeled `Session` is a domain concept. A box labeled `SessionManager`
is an implementation artifact and does not belong here.

## Illustrations

**Bad — implementation entity in graph.** A diagram shows `AuthHandler →
SessionStore → Database`.
**Good:** The diagram shows `User → Session → Audit Log`.

**Bad — implementation entity in invariant.** "The `SessionStore` retains
exactly one active record per user."
**Good:** "There is never more than one active Session per User."

