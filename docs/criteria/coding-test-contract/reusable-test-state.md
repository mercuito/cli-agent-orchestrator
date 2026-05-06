---
name: reusable-test-state
when: Tests repeat setup state across scenarios.
---

# Repeated Test State Is Named And Reused

Repeated worlds, filesystem scaffolds, fixture state, parsed artifacts, and
setup API calls must be captured in named reusable setup. Leaf tests refine
shared state with behavior-specific inputs instead of rebuilding the same
preconditions.

Reusable state must expose only the values the scenario needs and must not hide
the behavior invocation.

## Illustrations

**Bad - copied setup.** Several scenarios each create the same temp workspace,
provider config, and parsed registry state.
**Good:** A named setup creates that state once per scenario and returns the
focused handles each scenario needs.

**Bad - broad checkpoint.** `happyPathProvider()` hides the authored fixture
that explains the assertion.
**Good:** `linearConfigWithUnknownAgentReference()` names the state being
proven.
