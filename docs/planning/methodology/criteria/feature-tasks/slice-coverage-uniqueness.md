---
name: slice-coverage-uniqueness
when: Always.
---

# Every Feature Clause Has Exactly One Owning Task

Across all task entries, every clause from every feature-level contract
(Behavioral, Code, Test) appears in exactly one task's slice. Universally
binding criteria (e.g. `test-validity-preserved`) are excluded; they bind
every task by construction.

A clause owned by no task is unimplemented; a clause owned by two tasks
is double-assigned.

## Illustrations

**Bad — orphan clause.** Feature Code Contract clause `F-CC-3` is not
referenced by any task entry.
**Good:** `F-CC-3` appears in exactly one task's Code slice.

**Bad — double-assigned.** Both `t-2` and `t-5` list behavior `B-7` in
their Behavioral slices.
**Good:** `B-7` appears in one task's slice; the other task references
different IDs.
