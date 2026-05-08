---
name: migration-discipline
when: Existing code moves to a new service, API, or architecture.
---

# Migrations Move Callers To The New Shape

Migration work must adapt existing callers and tests to the new authoritative
shape. It must not widen the new surface, preserve obsolete names, or invent
bridge behavior unless the plan explicitly requires a compatibility period.

Replaced legacy surfaces must be removed in the same task or named as
temporarily retained by the plan.

When a SQLite migration rebuilds a table, the migration must account for
dependent schema objects that reference that table. If foreign keys, indexes,
triggers, marker tables, or other persisted relationships can be affected, the
migration must either preserve them through the rebuild or explicitly rebuild
the dependent objects so they reference the final schema, not a temporary
migration table.

## Illustrations

**Bad - service bent to old caller.** A new API accepts structured IDs, but an
adapter is added so old flat string IDs still work.
**Good:** Old callers are migrated to construct the structured ID.

**Bad - hidden bridge.** Old code expects one item while the new model returns
a list, so the implementation silently chooses the first item.
**Good:** The mismatch is escalated unless the plan defines selection
semantics.

**Bad - dangling SQLite dependency.** A migration rebuilds `messages` by
renaming it to `messages_old`, creating a new `messages`, and copying rows, but
dependent tables still have foreign keys pointing at `messages_old`.
**Good:** The migration checks dependent foreign keys and rebuilds affected
tables so they reference the final `messages` table.
