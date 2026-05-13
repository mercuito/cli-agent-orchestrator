---
name: prefer-public-surfaces
when: Code consumes another package, module, subsystem, or boundary-owned surface.
---

# Cross-Boundary Use Goes Through Public Surfaces

Consumers must use supported public entrypoints and exported surfaces across
package, module, subsystem, and ownership boundaries. Deep internal imports
require an explicit note naming the missing public surface and a follow-up path
to add it.

Tests are not exempt when they are proving consumer-visible behavior.

## Illustrations

**Bad - deep import.** A route imports another subsystem's private parser helper
because it is convenient.
**Good:** The route uses the subsystem's exported parser surface, or records
the missing public API and files follow-up work.

**Bad - private helper reliance.** Tests depend on a private helper owned by
another subsystem.
**Good:** Tests exercise the owner surface or use a test helper owned by that
subsystem.
