---
name: given-when-then-test-structure
when: Tests prove multi-step behavior.
---

# Tests Expose Given When Then Phases

Tests that prove multi-step behavior must make setup, action, and assertion
phases identifiable. The behavior invocation belongs in When; behavior proof
belongs in Then; Given may establish and validate preconditions only.

Labels, helper names, or comments must name the concrete setup, operation, and
observable claim when the code is not self-explanatory.

## Illustrations

**Bad - hidden action.** A Given helper creates state and also runs the command
being tested.
**Good:** Given creates state, When runs the command, Then asserts the outcome.

**Bad - vague labels.** `when the operation runs` and `then it works`.
**Good:** `when the Linear provider config is loaded` and `then duplicate app
users are rejected with diagnostics`.
