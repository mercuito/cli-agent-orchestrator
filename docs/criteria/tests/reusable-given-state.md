---
name: reusable-given-state
when: Tests repeat setup state across scenarios.
---

# Repeated Test State Is Named And Reused

Tests with the same given state must be able to be constructed once and reused across scenarios. If multiple tests require the same setup, that setup must be extracted into a named helper or fixture that can be reused to ensure consistency and reduce duplication.

## Illustrations

### Extracting Shared Setup

```markdown
plan.md
# Verify the supervisor's status output for each agent state
- [ ] Test running, stopped, and failed states
...
```

**Bad - copy-pasted setup.** Three tests duplicate the same registration
boilerplate; a future change to `register` ripples into every test.

```python
def test_running_agent_shows_in_status():
    sup = Supervisor(config=test_config())
    sup.register(Agent(id="a1", kind="reviewer"))
    sup.set_state("a1", "running")
    assert "running" in sup.status_for("a1")

def test_stopped_agent_shows_in_status():
    sup = Supervisor(config=test_config())
    sup.register(Agent(id="a1", kind="reviewer"))
    sup.set_state("a1", "stopped")
    assert "stopped" in sup.status_for("a1")

def test_failed_agent_shows_in_status():
    sup = Supervisor(config=test_config())
    sup.register(Agent(id="a1", kind="reviewer"))
    sup.set_state("a1", "failed")
    assert "failed" in sup.status_for("a1")
```

**Good:** The shared setup lives in a named fixture; each scenario names
only what differs.

```python
@pytest.fixture
def supervisor_with_agent():
    sup = Supervisor(config=test_config())
    sup.register(Agent(id="a1", kind="reviewer"))
    return sup

@pytest.mark.parametrize("state", ["running", "stopped", "failed"])
def test_state_shows_in_status(supervisor_with_agent, state):
    # Given
    supervisor_with_agent.set_state("a1", state)

    # When
    status = supervisor_with_agent.status_for("a1")

    # Then
    assert state in status
```
