---
name: simple-systems
when: Always.
---

# Simple Systems Are Preferred

Systems must be designed to be as simple as possible, with minimal internal complexity and clear boundaries. Simple systems are easier to understand, maintain, and evolve. Complex systems should be composed of simpler subsystems with well-defined interactions.

## Illustrations

### Avoid Premature Abstraction

```markdown
plan.md
# Add a `cao notify` command that sends a message to a single agent
- [ ] Implement `cao notify` that delivers a message to one agent by id
...
```

**Bad - speculative complexity.** The implementation introduces a pluggable
`NotificationStrategy` interface with multiple backends, queueing, and retry
policies — none of which the task requires.

```python
class NotificationStrategy(Protocol):
    def deliver(self, target: str, message: str) -> None: ...

class TmuxStrategy: ...
class MCPStrategy: ...
class QueuedStrategy: ...

class Notifier:
    def __init__(self, strategies: list[NotificationStrategy], retry: RetryPolicy):
        ...
```

**Good:** The smallest thing that satisfies the task. Extension points are
added later, when a real second consumer exists.

```python
def notify(agent_id: str, message: str) -> None:
    pane = find_pane_for_agent(agent_id)
    pane.send(message)
```

### Compose Simple Subsystems Instead Of One Big One

**Bad - one module owns everything.** `agent_runtime.py` parses CLI args,
spawns tmux panes, reads MCP events, persists state, and renders status.

**Good:** Each responsibility lives in a small subsystem with a clear contract;
the runtime composes them.

```python
# cao/cli/parse.py        — argument parsing
# cao/tmux/panes.py       — pane lifecycle
# cao/events/stream.py    — MCP event reader
# cao/sessions/store.py   — persistence
# cao/cli/status.py       — rendering

def run(argv: list[str]) -> int:
    args = parse(argv)
    with panes.open(args.session) as pane:
        events.stream(pane, store=sessions.store)
    status.render(sessions.store)
```
