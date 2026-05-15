---
name: minimal-cohesive-changes
when: A task changes code outside pure refactor work.
---

# Changes Stay Minimal And Cohesive

Implementation must stay within the assigned task and make the smallest
cohesive change that satisfies the in-force contracts. Related issues found
during implementation must be reported or escalated, not silently folded into
the task.

Necessary supporting changes are allowed when they are directly required to
complete the assigned slice.

## Illustrations

### Staying Within The Assigned Slice

```markdown
plan.md
# Add a `--workspace` flag to `cao start` so the session is scoped to a workspace
- [ ] Add `--workspace` to the `start` command and thread it through to the session factory
...
```

**Bad - scope creep.** While adding the flag, the implementer also reformats
the unrelated `stop` command and renames an internal helper used elsewhere.

```python
# Bad: also rewrites unrelated commands in the same change
def start(workspace: str): ...
def stop(): ...           # reformatted, no behavior change
def _resolve_session():   # renamed from _find_session, ripples through callers
    ...
```

**Good:** The change is limited to what the task requires. Unrelated cleanups
are reported separately.

```python
def start(workspace: str):
    session = session_factory(workspace=workspace)
    ...
```

### Necessary Supporting Changes

```markdown
plan.md
# Add a `kind` field to `SessionRecord` so the supervisor can filter by agent type
- [ ] Add `kind` to `SessionRecord` and persist it
...
```

**Bad - silently folded in.** The implementer notices an unrelated bug in
`SessionStore.delete` and fixes it in the same change without mention.

**Good:** The required schema and store changes ship together; the unrelated
bug is escalated as a separate task.

```python
@dataclass
class SessionRecord:
    id: str
    workspace: str
    kind: str  # required by the new filter

class SessionStore:
    def insert(self, record: SessionRecord) -> None: ...
    # delete() left untouched; bug reported separately
```
