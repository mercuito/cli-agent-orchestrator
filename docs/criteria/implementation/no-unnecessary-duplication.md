---
name: no-unnecessary-duplication
when: Any implementation task adds code, helpers, fixtures, or abstractions.
---

# Existing Suitable Code Is Reused

Existing code must be reused when it is suitable for the new need. If reusable code exists but is behind an unsuitable interface, a refactor must be done to make the shared code suitable for both use cases.

## Illustrations

### Reusing Existing Helpers

```markdown
plan.md
# Add a `cao list-agents` command that prints active agents
- [ ] Implement the command and format the output the same way as `cao status`
...
```

**Bad - reimplemented formatter.** The new command writes its own table
formatter even though `cao status` already has one.

```python
# commands/list_agents.py
def render(agents: list[Agent]) -> str:
    # Bad: duplicates the formatter already in commands/status.py
    rows = [f"{a.id:<20} {a.kind:<10} {a.state}" for a in agents]
    return "\n".join(rows)
```

**Good:** The existing formatter is reused. If its interface is too narrow, it
is refactored to serve both commands.

```python
# shared/agent_table.py  (lifted from commands/status.py)
def format_agent_table(agents: list[Agent]) -> str: ...

# commands/list_agents.py
from shared.agent_table import format_agent_table
print(format_agent_table(agents))
```

### Refactoring When The Interface Doesn't Fit

**Bad - copy-paste with a tweak.** The existing helper returns a string; the
new caller needs a list of rows, so the helper is copied and modified.

```python
def format_agent_table(agents) -> str: ...

# Bad: near-duplicate forked because the return shape didn't match
def format_agent_rows(agents) -> list[str]: ...
```

**Good:** The shared helper is refactored so both callers use it.

```python
def agent_rows(agents) -> list[str]: ...

def format_agent_table(agents) -> str:
    return "\n".join(agent_rows(agents))
```
