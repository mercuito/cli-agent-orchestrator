---
name: operational-self-sufficiency
when: Always.
---

# The Handoff Carries Everything Needed To Start

A complete handoff carries all four operational pointers: the slice
reference into `tasks.md`, the committed-implementation-decisions
reference, the Verification Command, and the coding-level artifact paths.
None of these may be omitted on the assumption a reader will go find them.

If any of the four is missing, the task is blocked.

## Illustrations

**Bad — missing Verification Command.** The handoff has the slice
reference, committed-decisions reference, and coding-level paths, but
omits the Verification Command.
**Good:** All four pointers are present; the Verification Command is named
verbatim.

**Bad — coding-level paths implied.** The handoff says "create the coding
contracts in the usual location."
**Good:** The handoff names the exact paths
`docs/plans/<feature>/tasks/t-<n>/coding-code-contract.md` and
`coding-test-contract.md`.
