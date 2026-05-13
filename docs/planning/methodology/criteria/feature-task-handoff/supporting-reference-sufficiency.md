---
name: supporting-reference-sufficiency
when: Task entry says supporting references are required.
---

# Supporting References Are Concrete And Inspectable

When a task entry says supporting references are required, the handoff
provides concrete references that the implementer can inspect during
research before drafting the Coding Implementation Plan.

Each reference states what it is and how it applies to the task. Acceptable
references include UI designs, screenshots, Figma frames, Storybook
stories, routes, component files, product notes, domain examples, existing
implementation patterns, or other project material.

If a required reference is unavailable, the handoff explains the missing
reference and why the task can still proceed or why it is blocked.

## Illustrations

**Bad - vague design instruction.** "Follow the design."
**Good:** "`docs/designs/timeline-empty-state.png`: target empty-state
layout, spacing, and visible controls for the timeline view."

**Bad - unqualified code reference.** "`web/src/components/Timeline.tsx`."
**Good:** "`web/src/components/Timeline.tsx`: existing row density,
timestamp treatment, and keyboard navigation pattern to preserve."

**Bad - missing required reference.** The task entry says UI references are
required, but the handoff has no Supporting References section.
**Good:** The handoff lists the available design and product references, or
states that the missing Figma frame blocks implementation planning.
