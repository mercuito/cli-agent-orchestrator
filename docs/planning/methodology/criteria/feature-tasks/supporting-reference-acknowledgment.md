---
name: supporting-reference-acknowledgment
when: Always.
---

# Supporting Reference Need Is Acknowledged

Each task entry states whether its handoff needs supporting references for
implementation research. This includes UI designs, screenshots, Figma
frames, Storybook stories, routes, component files, product notes, domain
examples, existing implementation patterns, or other material the
implementer should inspect before drafting the Coding Implementation Plan.

If references are required, the task entry names the reason at a high
level. The concrete references live in the Feature Task Handoff, not in
`feature-tasks.md`.

If no references are required, the task entry says so with a short reason.

## Illustrations

**Bad - silent UI dependency.** The task says "Build the timeline view"
but does not say whether design references are required.
**Good:** "Supporting references: required for timeline layout, empty
state, and interaction details."

**Bad - dumping references into `feature-tasks.md`.** The task entry lists five
screenshots and component paths.
**Good:** The task entry says references are required; the handoff carries
the screenshot and component list.

**Bad - unexplained none.** "Supporting references: none."
**Good:** "Supporting references: no supporting references required:
backend-only migration with no UI, product, domain, or prior-pattern
reference dependency."
