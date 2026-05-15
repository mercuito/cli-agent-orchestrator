---
name: migration-discipline
when: Refactoring - an existing code moves to a new service, API, or architecture.
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

### Adapting Callers To A New API Shape

```markdown
plan.md
# Move the session API from flat string IDs to structured SessionId objects
- [ ] Update `start_session` to accept `SessionId(workspace, name)`
- [ ] Migrate existing callers to construct `SessionId`
...
```

**Bad - service bent to old caller.** The new API accepts structured IDs, but
an adapter is added so old flat string IDs still work.

```python
def start_session(session_id: SessionId | str):
    # Bad: new surface widened to accept the old shape
    if isinstance(session_id, str):
        session_id = SessionId.parse(session_id)
    return _start(session_id)
```

**Good:** Old callers are migrated to construct the structured ID; the new
surface only accepts the new shape.

```python
def start_session(session_id: SessionId):
    return _start(session_id)

# At each call site
start_session(SessionId(workspace="main", name="run-1"))
```

### Shape Mismatches Are Escalated, Not Silently Bridged

```markdown
plan.md
# Switch `get_active_runs` to return a list instead of a single run
- [ ] Update `get_active_runs` to return `list[Run]`
- [ ] Update callers to handle multiple runs
...
```

**Bad - hidden bridge.** Old code expects one item while the new model returns
a list, so the implementation silently chooses the first item.

```python
def render_status():
    runs = get_active_runs()
    # Bad: silently collapses the new shape to the old one
    return format_run(runs[0])
```

**Good:** The mismatch is escalated unless the plan defines selection
semantics; callers are updated to handle the list.

```python
def render_status():
    runs = get_active_runs()
    return "\n".join(format_run(r) for r in runs)
```

### SQLite Rebuilds Update Dependent Schema Objects

```markdown
plan.md
# Rebuild the `messages` table to add a NOT NULL `kind` column
- [ ] Rename `messages` to `messages_old`, create new `messages`, copy rows
- [ ] Ensure foreign keys from `attachments` still reference `messages`
...
```

**Bad - dangling SQLite dependency.** The migration rebuilds `messages` by
renaming it to `messages_old`, creating a new `messages`, and copying rows, but
dependent tables still have foreign keys pointing at `messages_old`.

```sql
-- Bad: attachments.message_id now points at the orphaned messages_old
ALTER TABLE messages RENAME TO messages_old;
CREATE TABLE messages (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, body TEXT);
INSERT INTO messages (id, kind, body) SELECT id, 'text', body FROM messages_old;
```

**Good:** The migration checks dependent foreign keys and rebuilds affected
tables so they reference the final `messages` table.

```sql
ALTER TABLE messages RENAME TO messages_old;
CREATE TABLE messages (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, body TEXT);
INSERT INTO messages (id, kind, body) SELECT id, 'text', body FROM messages_old;

-- Rebuild dependents so FKs reference the new messages table
ALTER TABLE attachments RENAME TO attachments_old;
CREATE TABLE attachments (
    id INTEGER PRIMARY KEY,
    message_id INTEGER REFERENCES messages(id)
);
INSERT INTO attachments SELECT * FROM attachments_old;
DROP TABLE attachments_old;
DROP TABLE messages_old;
```
