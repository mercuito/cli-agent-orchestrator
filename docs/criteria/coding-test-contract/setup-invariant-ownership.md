---
name: setup-invariant-ownership
when: Tests require valid setup that is not the behavior under test.
---

# Setup Invariants Are Owned By Setup

Fixture validity checks must live with the setup that creates the fixture, not
as repeated behavior assertions in leaf tests. Leaf tests assert the behavior
under test; setup owners fail fast when preconditions are invalid.

This criterion does not allow setup to prove behavior.

## Illustrations

**Bad - repeated fixture guard.** Every leaf test asserts that the temp
workspace contains required base files before testing unrelated behavior.
**Good:** The workspace setup helper validates base files once and leaf tests
assert their behavior.

**Bad - behavior in setup.** Given verifies that the command output changed.
**Good:** Given verifies fixture validity; Then verifies command output.
