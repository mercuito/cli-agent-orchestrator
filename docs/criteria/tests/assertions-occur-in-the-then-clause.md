
---
name: assertions-occur-in-the-then-clause
when: Always.
---

# Assertions Occur In The Then Clause
Tests must place all assertions in the Then clause. The Given and When clauses must not contain any assertions, as they are meant for setup and action, respectively. This separation ensures that tests are structured clearly and that the expected outcomes are explicitly stated in the Then clause.

## Illustrations

### Asserting Setup In The Given Clause

```markdown
plan.md
# Verify `start_session` returns a record with the configured workspace
- [ ] Add a test that creates a session and checks the returned record
...
```

**Bad - assertion in Given.** The setup verifies its own fixture, so a
failure there points at the test rather than the system under test.

```python
def test_start_session_returns_record():
    # Given
    config = SessionConfig(workspace="main", kind="agent")
    assert config.workspace == "main"  # Bad: asserting fixture state

    # When
    session = start_session(config)

    # Then
    assert session.id
```

**Good:** The Given clause only builds state; the Then clause carries all
assertions about the system's outcome.

```python
def test_start_session_returns_record():
    # Given
    config = SessionConfig(workspace="main", kind="agent")

    # When
    session = start_session(config)

    # Then
    assert session.id
    assert session.workspace == "main"
```

### Asserting Inside The When Clause

**Bad - assertions scattered through the action.** The test interleaves
checks with steps, so it isn't clear what behavior is actually being
verified.

```python
def test_event_pipeline():
    # Given
    pipeline = EventPipeline()

    # When
    pipeline.start()
    assert pipeline.is_running()  # Bad: assertion inside When
    pipeline.emit("hello")
    assert pipeline.queue_size() == 1  # Bad: assertion inside When
    pipeline.stop()

    # Then
    assert pipeline.events_processed() == 1
```

**Good:** The action runs as one block; outcomes are asserted at the end.

```python
def test_event_pipeline_processes_emitted_events():
    # Given
    pipeline = EventPipeline()

    # When
    pipeline.start()
    pipeline.emit("hello")
    pipeline.stop()

    # Then
    assert pipeline.events_processed() == 1
```
