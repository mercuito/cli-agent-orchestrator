---
name: system-definitions-are-localized
when: Creating/designing a service or subsystem, or substantially reshaping an existing one.
---

# System Definitions Are Localized
The definition of a service or subsystem must be localized in a clear architectural home and not scattered across the codebase. The system's API/configuration should be defined in one logical place as much as the architecture allows.

## Illustrations

### One Architectural Home For A Service

```markdown
plan.md
# Design the new `sessions` service that owns session lifecycle and storage
- [ ] Define the sessions service API and config in a single architectural home
...
```

**Bad - scattered definition.** The sessions service's API, config schema, and
storage contract are spread across unrelated packages, so understanding the
service requires reading several directories.

```
cao/
  cli/
    session_args.py        # Bad: session config schema lives in CLI
  events/
    session_events.py      # Bad: session API surface defined in events
  storage/
    session_table.py       # Bad: session storage contract defined under storage
```

**Good:** The sessions service has one home that declares its API, its config,
and its storage contract. Other systems import from that home.

```
cao/
  sessions/
    __init__.py            # public API: start_session, get_session, list_sessions
    config.py              # SessionConfig schema
    storage.py             # SessionStore contract
    events.py              # SessionEvent types
```

### Consumers Reference The Localized Definition

**Bad - re-declared config.** A consumer re-declares the session config shape
locally to avoid importing from the service's home.

```python
# cao/cli/start.py
@dataclass
class SessionConfig:        # Bad: shadow definition
    workspace: str
    kind: str
```

**Good:** The consumer imports the canonical definition.

```python
# cao/cli/start.py
from cao.sessions import SessionConfig, start_session
```

