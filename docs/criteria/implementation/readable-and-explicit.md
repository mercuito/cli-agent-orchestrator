---
name: readable-and-explicit
when: Always.
---

# Code Makes Behavior Explicit

Names, types, control flow, and sparse comments must make behavior and limits
understandable without reconstructing hidden assumptions. Non-obvious side
effects, filtering, dropping, mutation, or transformation must be visible in
the name, type, or a short comment.

Comments clarify intent or constraints, not obvious code.

## Illustrations

### Naming Reveals Hidden Filtering

```markdown
plan.md
# The supervisor lists active agents
- [ ] Add `list_agents` to the agent registry
...
```

**Bad - hidden filtering.** The function is named `list_agents` but silently
drops agents in `stopped` and `failed` states.

```python
def list_agents() -> list[Agent]:
    # Bad: drops non-running agents with no signal in the name or signature
    return [a for a in _agents if a.state == "running"]
```

**Good:** The name (or signature) makes the filter visible.

```python
def list_running_agents() -> list[Agent]:
    return [a for a in _agents if a.state == "running"]

# or, if both are needed:
def list_agents(states: set[AgentState] | None = None) -> list[Agent]:
    if states is None:
        return list(_agents)
    return [a for a in _agents if a.state in states]
```

### Comments Clarify Intent, Not The Obvious

**Bad - noise comment.** The comment restates what the code already says.

```python
# Bad: tells the reader nothing the code doesn't
# Increment the counter by one
counter += 1
```

**Good:** The comment captures a non-obvious constraint or reason.

```python
# tmux pane indexes are 1-based; the registry stores them 0-based
counter += 1
```

### Side Effects Are Visible

**Bad - mutation hidden in a "getter".** `get_session` looks like a pure
lookup, but it also persists the access timestamp.

```python
def get_session(session_id: str) -> Session:
    session = _store[session_id]
    # Bad: side effect hidden behind a read-shaped name
    session.last_accessed = now()
    _store.save(session)
    return session
```

**Good:** The name reflects the mutation, or the mutation is split out.

```python
def get_session(session_id: str) -> Session:
    return _store[session_id]

def touch_session(session_id: str) -> Session:
    session = _store[session_id]
    session.last_accessed = now()
    _store.save(session)
    return session
```
