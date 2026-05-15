---
name: no-test-only-production-seams
when: Always.
---

# Production Seams Serve Production Needs

Production constructors, options, hooks, adapters, exports, and helpers may be
added or widened only for a production behavior or contracted architecture.
They must not exist solely to make tests easier. Production code must be designed to be testable without test-only seams.

## Illustrations

### Test-Only Constructor Arguments

```markdown
plan.md
# Make the dispatcher easier to unit test
- [ ] Allow tests to inject a fake clock and a fake session store
...
```

**Bad - test-only parameters on a production class.** The production
constructor grows optional `clock` and `store` parameters that only tests pass.

```python
class Dispatcher:
    def __init__(
        self,
        config: Config,
        clock: Clock | None = None,   # Bad: only tests set this
        store: SessionStore | None = None,  # Bad: only tests set this
    ):
        self._clock = clock or SystemClock()
        self._store = store or SessionStore.from_config(config)
```

**Good:** `Dispatcher` takes its real collaborators by interface, and the
production composition root wires them. Tests construct the dispatcher with
test doubles through the same interface — no extra production parameters.

```python
class Dispatcher:
    def __init__(self, clock: Clock, store: SessionStore):
        self._clock = clock
        self._store = store

# Production wiring
dispatcher = Dispatcher(clock=SystemClock(), store=SessionStore.from_config(config))

# Test wiring
dispatcher = Dispatcher(clock=FakeClock(), store=InMemorySessionStore())
```

### Widening Visibility For Tests

**Bad - exposing an internal helper.** A private function is made public so a
test can call it directly.

```python
# session_manager.py
def _normalize_session_name(name: str) -> str:  # was private
    ...

# Bad: re-exported only so a test can import it
normalize_session_name = _normalize_session_name
```

**Good:** The behavior is tested through the public surface that exercises it
(e.g., `start_session`), so the helper remains private.
