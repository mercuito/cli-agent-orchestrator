---
name: readable-and-explicit
when: Any implementation task.
---

# Code Makes Behavior Explicit

Names, types, control flow, and sparse comments must make behavior and limits
understandable without reconstructing hidden assumptions. Non-obvious side
effects, filtering, dropping, mutation, or transformation must be visible in
the name, type, or a short comment.

Comments clarify intent or constraints, not obvious code.

## Illustrations

**Bad - hidden drop.** `normalizeEntries()` silently removes invalid entries.
**Good:** `filterValidEntries()` or a short comment states that invalid entries
are dropped.

**Bad - unexplained side effect.** `getConfig()` creates directories.
**Good:** Rename or document the side effect at the boundary.

