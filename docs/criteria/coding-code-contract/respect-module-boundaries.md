---
name: respect-module-boundaries
when: Code is added, moved, or restructured across files, modules, or packages.
---

# Module Boundaries Stay Coherent

Changed modules must preserve or improve coherent ownership boundaries. A file
must not become a bucket of unrelated concerns unless the Code Contract
explicitly allows that co-location.

When separable concerns begin to grow, extract a coherent module instead of
adding more unrelated logic.

## Illustrations

**Bad - responsibility bucket.** A command file grows parsing, validation,
filesystem mutation, and reporting logic.
**Good:** The command delegates to focused owner modules.

**Bad - unexplained co-location.** Two unrelated helpers are added to an
existing module because it was nearby.
**Good:** Each helper goes to its owner, or co-location is justified.
