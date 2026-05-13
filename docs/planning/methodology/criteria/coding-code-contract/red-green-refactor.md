---
name: red-green-refactor
when: A task adds or changes testable behavior.
---

# Behavior Changes Start With Failing Proof

For testable behavior changes, focused proof must be written or updated
before implementation and observed failing for the intended reason. Then
the smallest change that makes it pass is implemented, and refactoring
happens after the proof is green.

If test-first is skipped, the completion report must name the contracted
exception.

## Illustrations

**Bad - tests after code.** A caching layer is implemented first, then tests
are written to match it.
**Good:** A failing cache invalidation test is written before implementation.

**Bad - no semantic proof.** A test asserts only "does not throw."
**Good:** The test asserts the behavior the contract requires.

