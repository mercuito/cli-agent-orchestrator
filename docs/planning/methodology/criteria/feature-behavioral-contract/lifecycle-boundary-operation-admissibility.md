---
name: lifecycle-boundary-operation-admissibility
when: A lifecycle state controls whether operations are valid.
---

# Lifecycle Boundaries Define Operation Admissibility

The behavioral contract must define which operations are valid in each relevant
lifecycle state and what happens when an operation is invoked outside its
valid state.

If in-flight operations can overlap with lifecycle transitions, the contract
must define whether they complete, cancel, fail, or are ignored.

## Illustrations

**Bad - ready path only.** The contract defines calls after activation but says
nothing about calls before activation or after deactivation.
**Good:** The contract states that pre-activation calls fail with a not-ready
outcome and post-deactivation calls fail without mutation.

**Bad - transition ambiguity.** Shutdown starts while a save is running, with
no required outcome.
**Good:** The contract states whether the save completes or is rejected and
what state remains afterward.

