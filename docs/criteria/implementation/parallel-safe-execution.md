---
name: parallel-safe-execution
when: Always.
---

# Code Is Safe For Parallel Execution

Code and its tests must allow multiple concurrent invocations to run in the
same process or on the same machine without interference. Implementations must
not rely on fixed filesystem paths, fixed ports, shared module-level mutable
state, or any other process-wide resource that a second concurrent invocation
would collide with.

Resources that vary per invocation — working directories, sockets, registries —
must be supplied as parameters or constructed per call, so production wiring
and test wiring can each pick their own.

## Illustrations

### Fixed Filesystem Paths

```markdown
plan.md
# Cache reviewer results to disk so repeated reviews are fast
- [ ] Persist reviewer cache entries to disk
...
```

**Bad - hardcoded shared path.** The cache writes to a single location every
process shares, so two concurrent runs (or two parallel tests) clobber each
other.

```python
CACHE_DIR = Path("/tmp/cao-reviewer-cache")  # Bad: shared across all runs

def save_result(key: str, value: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(value))
```

**Good:** The cache location is supplied per invocation. Production picks one
location at the boundary; tests scope theirs to the test's temp directory.

```python
def save_result(cache_dir: Path, key: str, value: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(json.dumps(value))

# Production wiring
save_result(config.cache_dir, "abc", value)

# Test wiring
save_result(tmp_path, "abc", value)
```

### Fixed Network Ports

```markdown
plan.md
# Stand up a local control server for the supervisor to talk to
- [ ] Implement `start_server` and bind a local port
...
```

**Bad - hardcoded port.** The server binds the same port every run, so two
instances or two parallel tests collide on `EADDRINUSE`.

```python
def start_server() -> Server:
    return Server.bind("127.0.0.1", 8765)  # Bad: same port every time
```

**Good:** The port is supplied, or the OS picks a free one (port 0). The
caller learns which port was chosen and propagates it to clients.

```python
def start_server(host: str = "127.0.0.1", port: int = 0) -> Server:
    # port=0 → OS-assigned ephemeral port; read server.port after bind
    return Server.bind(host, port)
```

### Module-Level Mutable State

```markdown
plan.md
# Track running agents so the supervisor can look them up by id
- [ ] Add an agent registry with `register` and `lookup`
...
```

**Bad - shared registry.** A module-level dict holds state for the whole
process; two concurrent callers overwrite each other, and tests cannot be
isolated without resetting the global between cases.

```python
_AGENT_REGISTRY: dict[str, Agent] = {}  # Bad: process-wide mutable state

def register(agent: Agent) -> None:
    _AGENT_REGISTRY[agent.id] = agent

def lookup(agent_id: str) -> Agent:
    return _AGENT_REGISTRY[agent_id]
```

**Good:** State lives in an explicit object callers pass around. Each
caller — including each test — gets its own instance, so concurrent use does
not interfere.

```python
class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.id] = agent

    def lookup(self, agent_id: str) -> Agent:
        return self._agents[agent_id]
```
