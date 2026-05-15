---
name: properly-designed-shared-code
when: Code changes that uses shared code, helpers, fixtures, or abstractions.
---

# Shared Code Is Public

Shared code must be explicitly designed to be used by multiple consumers and must not be nested in a single consumer's private surface. If code is useful to multiple consumers, it should be moved to a shared location with a clear contract and public API.

## Illustrations

### Promoting Code Out Of A Consumer's Private Surface

```markdown
plan.md
# Both the supervisor and reviewer agents need to parse the same MCP event payload
- [ ] Share the event parser between the supervisor and reviewer
...
```

**Bad - shared code nested under one consumer.** The parser lives inside the
supervisor package, and the reviewer reaches into the supervisor's internals to
use it.

```python
# cao/supervisor/_event_parser.py
def parse_mcp_event(payload: dict) -> Event: ...

# cao/reviewer/run.py
# Bad: crosses a boundary to reach into the supervisor's private module
from cao.supervisor._event_parser import parse_mcp_event
```

**Good:** The parser is lifted to a shared package with a clear contract and
a public API. Both consumers import from the shared home.

```python
# cao/events/parser.py
def parse_mcp_event(payload: dict) -> Event:
    """Public: parse an MCP event payload into an Event."""

# cao/supervisor/run.py
from cao.events import parse_mcp_event

# cao/reviewer/run.py
from cao.events import parse_mcp_event
```
