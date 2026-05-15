---
name: test-validity-preserved
when: Always.
---

# Tests Continue To Validate Their Target Behavior

Tests must validate the target behavior of the system under test, even as the implementation evolves. When changes are made to the codebase, tests should be updated to reflect any changes in behavior or contracts, but they must not be modified in a way that undermines their ability to validate the intended behavior. This ensures that tests remain effective at catching regressions and verifying that the system continues to meet its requirements.

## Illustrations

### Updating A Test To Match A New Contract

```markdown
plan.md
# `start_session` now returns a `Session` object instead of an id string
- [ ] Update callers and tests for the new return shape
...
```

**Bad - test weakened to keep passing.** The implementation changed and
the original assertion was replaced with a truthiness check, so the test
still passes but no longer validates the target behavior.

```python
def test_start_session_returns_session():
    result = start_session(SessionConfig(workspace="main"))

    # Bad: originally asserted result.id == expected_id; now just truthy
    assert result
```

**Good:** The test is updated to the new contract while still validating
the behavior it was written to cover.

```python
def test_start_session_returns_session():
    result = start_session(SessionConfig(workspace="main"))

    assert isinstance(result, Session)
    assert result.workspace == "main"
    assert result.id  # generated, non-empty
```

### Removing An Assertion Instead Of Investigating

**Bad - silenced assertion.** A test fails after an implementation change;
the assertion is deleted to make the suite green, without confirming the
new behavior is the intended one.

```python
def test_failed_agent_is_reaped():
    sup = supervisor_with_agent("a1")
    sup.fail("a1")
    sup.tick()

    # Bad: previously asserted "a1" not in sup.active_ids()
    # Deleted because the new tick logic delays reaping by one cycle
    pass
```

**Good:** The test reflects the actual new behavior (here, the explicit
grace tick) — or, if the change wasn't intended, the regression is
escalated. Either way, the test still proves something.

```python
def test_failed_agent_is_reaped_after_grace_tick():
    sup = supervisor_with_agent("a1")
    sup.fail("a1")
    sup.tick()  # grace tick
    sup.tick()  # reaping tick

    assert "a1" not in sup.active_ids()
```
