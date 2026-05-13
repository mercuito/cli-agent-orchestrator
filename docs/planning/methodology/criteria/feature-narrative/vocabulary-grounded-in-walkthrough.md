---
name: vocabulary-grounded-in-walkthrough
when: Always.
---

# Vocabulary Is Grounded In The Walkthrough

Every term in the narrative's Domain Vocabulary section is used by the
walkthrough or by a downstream contract. Orphan definitions — terms
defined but never referenced — do not belong here.

Conversely, every domain noun used in the walkthrough or a downstream
contract that is not common English must have a vocabulary definition.
Undefined domain terms force readers to guess.

## Illustrations

**Bad — orphan definition.** Vocabulary defines `AuditLog` even though
neither the walkthrough nor any contract uses the term.
**Good:** Cut the orphan, or extend the walkthrough/contracts to use it
deliberately.

**Bad — undefined term used.** The walkthrough refers to a quorum, but no
vocabulary entry defines what a quorum is in this domain.
**Good:** Add a vocabulary entry for `quorum` that fixes its meaning for
this feature.

