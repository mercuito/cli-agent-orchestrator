---
name: events-have-observable-outcomes
when: Always.
---

# Events Show Observable Consequences

Every significant event in the narrative shows what changes observably as a
result. The consequence belongs in the event prose, not in a separate
`Outcome` field. An event whose consequence is not visible is too vague to
ground capability derivation.

Events whose outcome is purely internal (no domain-observable change) do not
belong in the narrative.

## Illustrations

**Bad — consequence implicit.** "The user submits the login form."
**Good:** "The user submits the login form, and the system either grants a
session or rejects the attempt with a reason the user can read."

**Bad — internal-only event.** "The auth service hashes the password."
**Good:** Cut. The user does not observe hashing; this belongs in the
Code Contract, not the narrative.
