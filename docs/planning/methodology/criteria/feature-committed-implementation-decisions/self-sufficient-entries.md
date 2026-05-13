---
name: self-sufficient-entries
when: Always.
---

# Entries Stand On Their Own

Each entry must let a future task know exactly what compatibility requires
and why it is required, from the entry text alone. The rationale carries
the binding reason — not the source task's defence or completion report.

Vague rationales ("for consistency", "to keep things simple") leave future
tasks unable to tell intentional violation from stylistic divergence.

## Illustrations

**Bad — vague rationale.** `cid-3 — All command handlers are pure.`
Rationale: "Cleaner that way."
**Good:** `cid-3 — All command handlers are pure.` Rationale: "Side effects
in handlers caused the t-2 retry-loop bug; purity makes handler retry safe."

**Bad — defers to source task.** Rationale: "See `t-5` defence."
**Good:** Rationale: "Two packages held overlapping API surface before t-5;
consolidating ownership in module X removed the duplication and broke the
dependency cycle."
