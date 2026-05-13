---
name: respect-standing-decisions
when: The feature has committed implementation decisions in force.
---

# Committed Decisions Are Respected

The Code Contract, Coding Implementation Plans, code, tests, and completion
reports must remain compatible with committed implementation decisions in
the feature area.

If a committed decision appears wrong or stale, escalate upstream before
contradicting it.

## Illustrations

**Bad - renamed settled concept.** A committed decision says outputs are
called artifacts; new code calls the same concept assets.
**Good:** New code uses artifact or escalates a vocabulary change.

**Bad - decision treated as background.** A task ignores a committed boundary
because the code would be easier without it.
**Good:** The plan names the decision and works within it.
