---
name: scenario-grounding
when: Always.
---

# Scenario Grounding

The narrative is grounded in a concrete, plausible scenario with named
domain actors, systems, consumers, providers, agents, workspaces, messages,
or other representative objects. It reads like a sequence of things
happening in the domain, not an abstract inventory of capabilities or
requirements.

Representative examples may be invented, but they must be specific enough
to show the feature in motion. The scenario makes clear what starts the
sequence, what moves through the system, who or what observes it later, and
how later events follow from or branch from earlier events.

## Illustrations

**Bad — abstract inventory.** "A CAO event is recognized. A CAO event is
recorded. A consumer queries events." This lists capabilities without a
running scenario.
**Good:** "A Linear webhook reports that an agent was mentioned in an issue.
CAO publishes the mention as a CAO event and records it in the durable event
log. Later, the timeline viewer asks for events involving that agent."

**Bad — disconnected beats.** `E1` is about login, `E2` is about exports,
and `E3` is about billing with no shared scenario or explicit branch.
**Good:** Each event follows one running scenario or clearly branches from
an earlier event.
