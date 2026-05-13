---
name: events-have-observable-outcomes
when: Always.
---

# Events Have Observable Outcomes

Every significant event in the narrative states what changes observably as a
result. An event without a stated outcome is unverifiable and cannot ground
a behavior.

Events whose outcome is purely internal (no domain-observable change) do not
belong in the narrative.

## Illustrations

**Bad — outcome implicit.** "The user submits the login form."
**Good:** "The user submits the login form, and the system either grants a
session or rejects the attempt with a reason the user can read."

**Bad — internal-only event.** "The auth service hashes the password."
**Good:** Cut. The user does not observe hashing; this belongs in the
Code Contract, not the narrative.

