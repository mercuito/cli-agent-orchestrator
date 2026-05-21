---
name: deep-systems
when: Always.
---

# Decompose Into Deep Systems

Every problem worth solving gets broken into subsystems — at any scale. But each system must be **deep**: its interface narrower than its implementation, hiding real complexity that would otherwise spread to callers.

In this codebase, a [[System]] is anything with an interface and an implementation — a function, a class, a package, or a feature-area service. The principle scales. A deep function and a deep service are the same idea applied at different sizes.

"Simple" doesn't mean "small" or "few pieces." It means **leverage at the interface** — a caller learns a little and gets a lot. A chain of five thin pass-through systems is not simpler than one system with a small interface that does the same work; it's the same complexity spread across more files, where every caller has to learn five interfaces instead of one.

Decomposition and depth are independent axes. Both matter; neither replaces the other:

|              | Deep                                                | Shallow                                |
|--------------|-----------------------------------------------------|----------------------------------------|
| Decomposed   | what to aim for                                     | bouncing between thin systems          |
| Monolithic   | god system — has leverage, no internal locality     | just messy                             |

## The Deletion Test

For any system — at any scale — imagine deleting it. If the complexity vanishes, it was a pass-through; fold it into its caller. If the complexity re-appears across N callers, the system was earning its keep. Apply this recursively: subsystems within a system, smaller systems within a subsystem.

## Illustrations

### Avoid Premature Abstraction

```markdown
plan.md
# Add a `cao notify` command that sends a message to a single agent
- [ ] Implement `cao notify` that delivers a message to one agent by id
```

**Bad — speculative complexity.** The implementation introduces a pluggable
`NotificationStrategy` interface with multiple backends, queueing, and retry
policies — none of which the task requires. The seam is hypothetical; no
second adapter exists to justify it.

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
added later, when a real second adapter exists.

```python
def notify(agent_id: str, message: str) -> None:
    pane = find_pane_for_agent(agent_id)
    pane.send(message)
```

### Decompose By Responsibility, Not By Layer

When breaking down a system, the failure mode is to split along **layer**
lines — parsing, I/O, persistence, rendering — producing a chain of thin
systems where each one's interface is nearly as wide as its body. The
orchestrator has to learn every interface to do anything useful; the pieces
don't hide complexity, they just relocate it.

```python
# Bad — five shallow systems. Each is a thin wrapper around its library.
# The runtime has to learn all five interfaces to do anything.
# cao/cli/parse.py        — argparse setup
# cao/tmux/panes.py       — tmux subprocess calls
# cao/events/stream.py    — MCP socket reader
# cao/sessions/store.py   — sqlite read/write
# cao/cli/status.py       — print formatting

def run(argv):
    args = parse(argv)
    pane = panes.open(args.session)
    events.stream(pane, store=sessions.store)
    panes.close(pane)
    status.render(sessions.store)
```

Split by **responsibility** instead. An `Agent` system owns the live-agent
concept — its pane, its event stream, its state — behind a small interface.
Parsing and rendering stay separate because they're genuinely different
concerns, but the runtime no longer has to know about tmux subprocesses, MCP
sockets, or sqlite. Tmux/MCP/sqlite become **internal seams** inside `Agent`,
not part of its external interface.

```python
# Good — Agent is deep: it hides pane lifecycle, event streaming, and
# persistence behind a two-method interface. The runtime learns Agent.run()
# and Agent.status(), not five separate APIs.

class Agent:
    def __init__(self, session_id: str): ...
    def run(self) -> None: ...           # streams events until done
    def status(self) -> AgentStatus: ...

def run(argv):
    args = parse(argv)
    agent = Agent(args.session)
    agent.run()
    print(format_status(agent.status()))
```

Apply the deletion test to confirm: delete `Agent` and the runtime must
suddenly know about tmux, MCP, and sqlite — complexity concentrates, so
`Agent` earned its keep. Delete a layer-split `cao/cli/status.py` and the
runtime gains one line of print code — complexity vanished, so it did not.
