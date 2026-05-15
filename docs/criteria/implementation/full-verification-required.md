---
name: full-verification-required
when: Any implementation task produces code changes.
---

# Verification Command Runs Before Completion

Before completion, the Verification Command named by the task definition
must run successfully. If the applicable command is unclear or unavailable,
the task blocks rather than reporting completion on guessed proof.

Focused checks may be used during development but do not replace the
Verification Command.

## Illustrations

**Bad - guessed proof.** A single focused unit test passes and the task is
reported complete without the Verification Command.
**Good:** The Verification Command named by the task definition runs and
its result is reported.

**Bad - skipped failures.** Failing checks are marked `.skip` to make the
command pass.
**Good:** Failures are fixed or escalated before completion.
