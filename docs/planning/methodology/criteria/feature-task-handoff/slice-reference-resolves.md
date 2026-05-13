---
name: slice-reference-resolves
when: Always.
---

# The Slice Reference Resolves To A Complete Entry

The handoff's slice reference must point at a real `tasks.md` entry whose
own slice acknowledgments are complete. A reference to a missing entry, a
typo'd ID, or an entry with empty/unacknowledged slices leaves the handoff
built on missing ground.

## Illustrations

**Bad — broken reference.** Handoff says "see `../tasks.md#t-7`" but
`tasks.md` has no `t-7` entry (only `t-1` through `t-6`).
**Good:** The slice reference resolves to an existing entry whose
Behavioral / Code / Test sections each carry IDs or explicit absence.

**Bad — references an incomplete entry.** `tasks.md#t-3` has empty Test
slice with no acknowledgment.
**Good:** `t-3`'s Test slice is filled in (or explicitly absent with a
reason) before the handoff is finalized.
