---
name: behavior-outcome-titles
when: Always.
---

# Behaviors Have Outcome Titles

Every behavior must have a short title beside its identifier. The title names
the observable outcome established by the behavior. The Given/When/Then body
remains authoritative.

Titles must be concise, unique within the contract, domain-level, and
implementation-neutral.

## Illustrations

**Bad - trigger title.** `B3 - Calling load after save` names the setup and
trigger.
**Good:** `B3 - Load returns saved data` names the outcome.

**Bad - implementation title.** `B4 - Calls saveData synchronously` names a
mechanism.
**Good:** `B4 - Save persists data for later load` names visible behavior.

