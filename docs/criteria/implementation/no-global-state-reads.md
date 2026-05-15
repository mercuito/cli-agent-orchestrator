---
name: no-global-state-reads
when: Code reads environment variables or global runtime state.
---

# Global State Reads Stay At The Boundary

Global runtime state (env variables, mutable global variables) must be read at an
application or test boundary, captured into an explicit context/config object,
and passed inward. Leaf services, utilities, helpers, and module initializers
must not read `os.environ` or equivalent globals directly.


## Illustrations

### Environment Variables

```markdown
plan.md
# We need to read the API key from the environment in our service
- [ ] Read `API_KEY` from the environment in the service
...
```

**Bad - leaf read.** A deep utility or parser helper reads `os.environ["CAO_MODE"]` 
to determine its behavior.

```python
def get_api_client():
    # Bad: Direct environment read inside a leaf function
    api_key = os.environ.get("API_KEY")
    return Client(api_key)
```

**Good:** The CLI entrypoint or a dedicated configuration loader reads the 
environment once at the host boundary and injects the required values.

```python
def get_api_client(config: RuntimeContext):
    # Good: Value is passed in from the boundary context
    return Client(config.api_key)

# At the boundary (e.g., main.py)
config = RuntimeContext(api_key=os.environ.get("API_KEY"))
client = get_api_client(config)
```

### Parallel Test Execution

```markdown
plan.md
# Test multiple scenarios for our service
- [ ] Test service behavior when `CAO_MODE=fast` and `CAO_MODE=slow`
...
```

**Bad - global mutation.** Tests mutate `os.environ` to change behavior, making
parallel execution impossible or flaky.

```python
def test_fast_mode():
    os.environ["CAO_MODE"] = "fast"
    assert run_logic() == "fast_result"
```

**Good:** Tests pass configuration objects or use dependency injection, allowing
different settings to coexist in the same process.

```python
def test_fast_mode():
    config = RuntimeContext(mode="fast")
    assert run_logic(config) == "fast_result"
```
