---
name: test-through-owner-surfaces
when: A test depends on behavior owned by another system.
---

# Tests Use Owner Surfaces For Owned Behavior

When setup, behavior, state, parsing, persistence, discovery, or side effects
belong to another subsystem, tests must use that subsystem's public owner
surface instead of duplicating its internals via helper/mocks. Baking in assumptions this way can cause test drift that makes refactors more difficult and hides important interactions. Tests must go through the owner surface to ensure they validate the actual behavior of the system under test and maintain consistency across the codebase.

Exceptions inlude external dependencies/libraries and cases where the owner surface is unavailable or impractical to use, which must be explicitly noted and defensed.

## Illustrations

### Setup Through The Owner

```markdown
plan.md
# Verify the supervisor reports the count of active sessions
- [ ] Test `active_session_count()` after sessions are started
...
```

**Bad - reaching into another system's storage.** The supervisor test
seeds sessions by writing directly to the sessions package's SQLite table,
bypassing the sessions API. A schema change in `cao.sessions` silently
breaks this test.

```python
def test_active_session_count(tmp_db):
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "INSERT INTO sessions (id, state) VALUES (?, ?)", ("s1", "running")
    )
    conn.commit()

    sup = Supervisor(db=tmp_db)
    assert sup.active_session_count() == 1
```

**Good:** Setup goes through `start_session`, the sessions package's
public owner surface. The test then asserts on the supervisor's behavior.

```python
def test_active_session_count(tmp_db):
    start_session(SessionConfig(id="s1", workspace="main"), db=tmp_db)

    sup = Supervisor(db=tmp_db)

    assert sup.active_session_count() == 1
```

### Documented Exception When No Owner Surface Exists

**Good:** When the owner has no suitable public surface, the deep access
is annotated and a follow-up is filed.

```python
# TODO(cao-sessions): no public surface to seed historical sessions;
# tracked in #1789. Switch to `seed_session(...)` once it lands.
def test_active_session_count(tmp_db):
    _seed_session_row(tmp_db, id="s1", state="running")  # internal

    sup = Supervisor(db=tmp_db)
    assert sup.active_session_count() == 1
```