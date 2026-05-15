---
name: given-when-then-test-structure
when: Always.
---

# Tests Are Structured As Given-When-Then

Tests must be structured in a clear Given-When-Then format. The Given section sets up the initial state and context, the When section performs the action being tested, and the Then section asserts the expected outcomes. This structure promotes clarity and maintainability in tests.

## Illustrations

### Clear Given-When-Then Sections

```markdown
plan.md
# Verify the supervisor records a heartbeat for a registered agent
- [ ] Test that `report_heartbeat` updates the agent's last-seen time
...
```

**Bad - unstructured test.** Setup, action, and assertion are interleaved
with no separation, forcing the reader to reconstruct intent.

```python
def test_heartbeat():
    sup = Supervisor()
    sup.report_heartbeat("a1")
    sup.register(Agent(id="a1"))
    assert sup.last_seen("a1") is not None
    sup.report_heartbeat("a1")
```

**Good:** The test reads top-down — setup, single action, then assertions.

```python
def test_heartbeat_updates_last_seen():
    # Given
    sup = Supervisor()
    sup.register(Agent(id="a1"))

    # When
    sup.report_heartbeat("a1")

    # Then
    assert sup.last_seen("a1") is not None
```

### One Action Per Test

**Bad - multiple actions blur what is verified.** Several operations run in
sequence and a mix of their effects is asserted, so a failure does not
point at a specific behavior.

```python
def test_session_lifecycle():
    store = SessionStore()
    store.create("s1")
    store.update("s1", state="running")
    store.delete("s1")
    assert store.get("s1") is None
```

**Good:** Each behavior is its own test with a single When step.

```python
def test_created_session_can_be_loaded():
    # Given
    store = SessionStore()

    # When
    store.create("s1")

    # Then
    assert store.get("s1") is not None

def test_deleted_session_is_removed():
    # Given
    store = SessionStore()
    store.create("s1")

    # When
    store.delete("s1")

    # Then
    assert store.get("s1") is None
```
