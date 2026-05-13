---
name: vocabulary-grounded-in-event-timeline
when: Always.
---

# Vocabulary Is Grounded In The Event Timeline

Every term in the narrative's Domain Vocabulary section is used by the
event timeline or by a downstream contract. Orphan definitions — terms
defined but never referenced — do not belong here.

Conversely, every domain noun used in the event timeline or a downstream
contract that is not common English must have a vocabulary definition.
Undefined domain terms force readers to guess.

## Illustrations

**Bad — orphan definition.** Vocabulary defines `AuditLog` even though
neither the event timeline nor any contract uses the term.
**Good:** Cut the orphan, or extend the event timeline/contracts to use it
deliberately.

**Bad — undefined term used.** The event timeline refers to a quorum, but no
vocabulary entry defines what a quorum is in this domain.
**Good:** Add a vocabulary entry for `quorum` that fixes its meaning for
this feature.
