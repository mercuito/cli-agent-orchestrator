---
name: system-code-locality
when: Always.
---

# System Code Is Near Each Other
Code that is part of a logical system must be near each other in the file system and must not be nested inside another system's private surface. If code is part of a logical system, it should be located in a directory owned by that system with a clear contract and public API as much as the architecture allows.


## Illustrations

### Keeping A System's Code Together

```markdown
plan.md
# Add a `flow` subsystem that schedules recurring agent runs
- [ ] Place flow code under a dedicated home with a clear public API
...
```

**Bad - scattered system.** Flow code is sprinkled across unrelated packages,
some of it nested inside the supervisor's private modules.

```
cao/
  supervisor/
    _flow_scheduler.py     # Bad: flow logic buried in supervisor internals
  cli/
    flow_command.py        # Bad: flow domain logic, not just CLI wiring
  events/
    flow_event_parser.py   # Bad: flow-specific parser inside generic events
```

**Good:** Flow has a single architectural home with a public surface; other
systems consume that surface.

```
cao/
  flow/
    __init__.py            # public API: schedule(), cancel(), list_runs()
    scheduler.py
    events.py
    storage.py
  cli/
    flow_command.py        # only CLI wiring, delegates to cao.flow
```

### Exception: Adapters Required To Live In A Fixed Location

Some host frameworks require their adapters in a fixed directory (e.g., MCP
tool registration, pytest plugins, entry-point hooks). When that happens, the
adapter lives where the host requires, but it stays a thin shim that delegates
to the owning system.

**Good:** A required-location adapter delegates back to its system.

```python
# cao/mcp/tools/flow_tool.py  (location dictated by the MCP framework)
from cao.flow import schedule, cancel  # delegate to the flow system

def register(server):
    server.tool("flow.schedule")(schedule)
    server.tool("flow.cancel")(cancel)
```

The implementation that the adapter wraps still lives under `cao/flow/`.
