---
name: explicit-dependencies
when: Tasks have ordering dependencies.
---

# Task Dependencies Are Stated

When one task must land before another, the dependency is named in the
later task's entry. List position, alphabetical order, and unstated
"obvious" precedence do not count.

## Illustrations

**Bad — implicit ordering.** Task `t-3` builds on a module `t-1`
introduces, but its entry says nothing about `t-1`.
**Good:** `t-3`'s entry includes "Depends on: `t-1`."

**Bad — order-by-listing.** The `feature-tasks.md` author orders entries
chronologically and assumes readers will infer the order.
**Good:** Each task that depends on an earlier one names it explicitly;
order in the file is no longer load-bearing.
