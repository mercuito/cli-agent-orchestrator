---
name: seams-must-be-tested
when: Always.
---

# Seams Must Be Tested
Seams, which are the points of interaction between different components or subsystems, must be covered by tests. This includes integration points, side effects, and interactions with external dependencies. Testing seams ensures that the system behaves correctly in real-world scenarios and that all critical interactions are validated.

## Illustrations

### Persistence Seam

```markdown
plan.md
# Persist session records so the supervisor survives a restart
- [ ] Implement `SessionStore` backed by SQLite
...
```

**Bad - the store seam is mocked.** The test substitutes an in-memory dict
for the real store, so a broken schema, a missing column, or a misnamed
table is never caught.

```python
def test_session_is_saved(mocker):
    fake_store = {}
    mocker.patch("cao.sessions.SessionStore", return_value=fake_store)

    save_session(Session(id="s1"))

    assert "s1" in fake_store  # only verifies the mock
```

**Good:** The test writes through the real store (against a scoped
database) and reads the row back, proving the seam works end-to-end.

```python
def test_session_is_saved(tmp_db):
    store = SessionStore(tmp_db)

    store.save(Session(id="s1", workspace="main"))

    row = store.get("s1")
    assert row.workspace == "main"
```

### Subprocess Seam

**Bad - subprocess invocation is mocked.** The test verifies the call
shape but never proves the process actually runs or that stdout is wired
up correctly.

```python
def test_spawn_calls_popen(mocker):
    popen = mocker.patch("subprocess.Popen")

    spawn_agent(["echo", "hi"])

    popen.assert_called_once()
```

**Good:** A small real process runs; the test asserts on its observable
output.

```python
def test_spawned_agent_streams_output(tmp_log):
    spawn_agent(["printf", "hello\n"], log=tmp_log)

    assert tmp_log.read_lines() == ["hello"]
```
