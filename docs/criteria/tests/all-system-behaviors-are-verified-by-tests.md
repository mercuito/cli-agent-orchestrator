---
name: all-system-interactions-are-verified-by-tests
when: Always.
---

# All System Interactions Are Verified By Tests
Tests must verify all interactions of the system under test. The seams that unity tests alone cannot cover, such as integration points, side effects, and interactions with external dependencies, must be covered by integration or end-to-end tests. This ensures that the system behaves as expected in real-world scenarios and that all critical interactions are validated.

## Illustrations

### Event Persistence

```markdown
plan.md
# Persist agent events so the monitor can replay a session
- [ ] Add `record_event(session_id, event)` that writes to the event store
- [ ] Add `load_events(session_id)` that returns events in order
...
```

**Bad - only the pure shape is tested.** Unit tests cover serialization in
isolation, but no test exercises `record_event` and `load_events` together
against the real store, so the storage seam is unverified.

```python
def test_event_serializes_to_dict():
    event = AgentEvent(kind="message", payload={"text": "hi"})
    assert event.to_dict() == {"kind": "message", "payload": {"text": "hi"}}
```

**Good:** An integration test writes through `record_event` and reads back
through `load_events`, proving the seam between the API and the store.

```python
def test_recorded_events_can_be_loaded_in_order(tmp_store):
    record_event(session_id="s1", event=AgentEvent(kind="start"))
    record_event(session_id="s1", event=AgentEvent(kind="message", payload={"text": "hi"}))

    events = load_events("s1")

    assert [e.kind for e in events] == ["start", "message"]
    assert events[1].payload == {"text": "hi"}
```

### Spawning A Subprocess

```markdown
plan.md
# Launch a CLI agent process and stream its stdout into the session log
- [ ] Add `spawn_agent(command)` that starts the process and pipes output
- [ ] Append each stdout line to the session log
...
```

**Bad - the subprocess seam is mocked away.** The test patches `subprocess.Popen`
and asserts the call shape, so a broken command, a missing binary, or a stdout
pipe wired up wrong would never be caught.

```python
def test_spawn_agent_invokes_popen(mocker):
    popen = mocker.patch("subprocess.Popen")
    spawn_agent(["echo", "hi"])
    popen.assert_called_once_with(["echo", "hi"], stdout=subprocess.PIPE)
```

**Good:** An integration test actually launches a small real process and
asserts the log captured its output, verifying the end-to-end interaction.

```python
def test_spawned_agent_output_is_logged(tmp_log):
    session = spawn_agent(["printf", "hello\nworld\n"])
    session.wait()

    assert tmp_log.read_lines() == ["hello", "world"]
```
