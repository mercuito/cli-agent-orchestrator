---
name: promotion-draft-durability
when: The defence proposes committed-decision promotions.
---

# Proposed Promotions Are Durable Cross-Task Facts

Each entry in the Committed-Decision Promotion Draft must name a fact
future tasks should actually inherit. Task-local notes, ephemeral
implementation details, and "we did X this time" observations do not
earn committed-decision authority.

If no entry warrants promotion, the section says so explicitly with a
one-line reason rather than being omitted.

## Illustrations

**Bad — task-local note.** Promotion draft: "`cid-?` — t-3 used a `Map`
instead of an array for the handler registry."
**Good:** Either omit (it's a local choice) or promote the durable
constraint behind it: "`cid-?` — Handler registry lookup is O(1)."

**Bad — restatement of contract.** Promotion draft: "`cid-?` — Auth
module owns session API." (already a Code Contract clause).
**Good:** Promote a fact the contract didn't already settle, or state
"no promotion warranted: this task only validated existing contract
clauses."
