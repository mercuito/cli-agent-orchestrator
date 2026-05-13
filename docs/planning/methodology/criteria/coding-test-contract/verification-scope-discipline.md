---
name: verification-scope-discipline
when: A task needs focused proof and a broader verification surface.
---

# Verification Scope Is Explicit

The Test Contract must name the focused proof that demonstrates the task's
local behavior and the Verification Command required before completion.
These are separate obligations.

If the Verification Command is unavailable or too broad to run, the task
definition or Test Contract must name the substitute and escalation.

## Illustrations

**Bad - focused only.** A task reports one new unit test but never names the
Verification Command.
**Good:** The contract names the focused test and the task definition names the
Verification Command.

**Bad - broad only.** A full repo command passes, but no focused proof shows
the changed behavior.
**Good:** Local behavior proof and broader verification are both named.
