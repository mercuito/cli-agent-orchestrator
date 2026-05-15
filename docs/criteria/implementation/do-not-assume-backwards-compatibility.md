---
name: do-not-assume-backwards-compatibility
when: Always.
---

# Backwards Compatibility Requires Explicit Contract

The implementation must not preserve old call signatures, exports, file
formats, flags, behavior, or code paths unless explicitly allowed by the plan.

Deprecated code is removed rather than hidden behind aliases, overloads,
feature flags, or comments.

## Illustrations

### Renaming A Function

```markdown
plan.md
# Rename `spawn_agent` to `start_agent` for consistency with session vocabulary
- [ ] Rename `spawn_agent` to `start_agent`
- [ ] Update all callers to use the new name
...
```

**Bad - alias preserved.** A wrapper keeps the old name working so callers do
not have to be touched.

```python
def start_agent(config: AgentConfig) -> Agent:
    return _start(config)

# Bad: kept around to avoid touching old callers
def spawn_agent(config: AgentConfig) -> Agent:
    return start_agent(config)
```

**Good:** The old name is removed and all callers are migrated.

```python
def start_agent(config: AgentConfig) -> Agent:
    return _start(config)

# Every call site updated:
agent = start_agent(config)
```

### Removing A Deprecated Flag

```markdown
plan.md
# Drop the `--legacy-mode` flag — the new dispatcher replaces it
- [ ] Remove `--legacy-mode` from the CLI and the dispatcher branch behind it
...
```

**Bad - hidden behind a flag.** The flag is left in place "just in case" and
its branch is gated by a feature toggle.

```python
def dispatch(args):
    if args.legacy_mode:
        # Bad: deprecated path kept behind a flag instead of removed
        return _legacy_dispatch(args)
    return _dispatch(args)
```

**Good:** The flag and the legacy branch are deleted together.

```python
def dispatch(args):
    return _dispatch(args)
```
