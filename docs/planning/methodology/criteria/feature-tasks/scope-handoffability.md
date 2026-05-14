---
name: scope-handoffability
when: Always.
---

# Scope Sentence Supports Handoff Drafting

Each task's scope sentence, combined with the task's listed slices and the
feature-level contracts, must be enough to draft a Task Handoff
without consulting the planner again.

If the scope is too vague to answer "what does this task deliver?", the
entry is underspecified.

## Illustrations

**Bad — vague intent.** "Improve auth handling."
**Good:** "Replace the legacy password-reset flow with a token-link flow
covering the email-delivery and token-redemption events."

**Bad — solution sketch instead of scope.** "Refactor `AuthService` into
two classes."
**Good:** "Split session-establishment and session-validation into separate
services so they can be deployed independently."
