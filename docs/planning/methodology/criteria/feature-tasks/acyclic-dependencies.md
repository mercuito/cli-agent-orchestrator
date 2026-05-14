---
name: acyclic-dependencies
when: Tasks have ordering dependencies.
---

# Task Dependencies Are Acyclic

Task dependencies must be acyclic, including dependencies implied by assigned slices. A task must not own a slice whose satisfaction depends on another task that directly or indirectly depends on it.

## Illustrations

**Bad — hidden circular slice dependency.** `t-1` is scoped to build the
generic presentation registry and fallback renderer, owns behavioral slice
`B-1`, and has no dependencies. `t-2` is scoped to add Linear mention and
runtime delivery presenters and explicitly depends on `t-1`. But `B-1`
requires known event kinds to render as distinct presentations, so `t-1`
cannot satisfy its assigned slice until `t-2` lands. The visible
dependency is `t-2 -> t-1`, but the slice creates a hidden reverse
dependency: `t-1 -> t-2`.

**Good:** `t-1` owns only the generic framework and fallback slices, such
as `B-9`, `C-1`, and `C-4`, with no dependency on later presenter work.
`t-2` owns the known-presenter slices, such as `B-1`, `B-2`, and `B-3`,
and depends on `t-1`. The task graph stays acyclic because every slice can
be satisfied by the task that owns it after its declared dependencies
land.
