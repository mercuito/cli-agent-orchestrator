---
name: active-exercise-grounding
when: A capability is mapped to narrative events.
---

# Capability Grounding Uses Active Exercise

A capability may map only to narrative events where the capability is actively
exercised and the narrative explicitly describes the action, produced entity,
or user-visible outcome. Prior effects, hidden implementation requirements,
and reader inference do not ground a capability.

If an expected capability has no explicit active event, either expand the
narrative so the exercise is observable or leave that capability out of the
slice.

## Illustrations

**Bad - lingering effect.** A view-registration capability maps to every event
where the registered view is later visible.
**Good:** Map it to the activation event that registers the view.

**Bad - inferred exercise.** A capability maps to activation because
registration must happen there, but the narrative only says "the plugin
activates."
**Good:** Expand the activation event to name the registered surface, or do
not map the capability to that event.

