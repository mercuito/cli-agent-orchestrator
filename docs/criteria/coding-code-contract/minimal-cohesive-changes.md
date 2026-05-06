---
name: minimal-cohesive-changes
when: A task changes code outside pure refactor work.
---

# Changes Stay Minimal And Cohesive

Implementation must stay within the assigned task and make the smallest
cohesive change that satisfies the in-force contracts. Related issues found
during implementation must be reported or escalated, not silently folded into
the task.

Necessary supporting changes are allowed when they are directly required to
complete the assigned slice.

## Illustrations

**Bad - quiet expansion.** A task adds a CLI flag and also rewires unrelated
config defaults discovered nearby.
**Good:** The flag work lands with only required support; the default issue is
reported separately.

**Bad - scattered cleanup.** Formatting and renames are applied across
unrelated modules.
**Good:** Cleanup stays within files required by the task.

