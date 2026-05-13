---
name: slice-acknowledgment-completeness
when: Always.
---

# Every Slice Section Is Named Or Explicitly Absent

Every contract slice section in a task entry — Behavioral, Code, Test —
must be either fully named (every assigned ID listed) or explicitly absent
with a one-line reason.

An empty section without acknowledgment is a defect.

## Illustrations

**Bad — silent omission.** A task entry lists Behavioral and Code slices
and omits the Test slice section.
**Good:** Test slice reads "no Test Contract slice for this task: pure
behavior, no shared proof obligations."

**Bad — empty bullet.** "Code slice:" with nothing after it.
**Good:** "Code slice: no Code Contract slice for this task: only test
fixtures change."
