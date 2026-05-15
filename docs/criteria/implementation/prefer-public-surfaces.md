---
name: prefer-public-surfaces
when: Code consumes another package, module, subsystem, or boundary-owned surface.
---

# Cross-Boundary Use Goes Through Public Surfaces

Consumers must use supported public entrypoints and exported surfaces across
package, module, subsystem, and ownership boundaries. Deep internal imports
require an explicit note naming the missing public surface and a follow-up path
to add it.

## Illustrations

### Importing Through The Package's Public API

```markdown
plan.md
# The dispatcher needs to look up a session by id
- [ ] Use the session package's lookup API from the dispatcher
...
```

**Bad - deep internal import.** The dispatcher reaches into the session
package's internal module.

```python
# dispatcher.py
# Bad: imports a private module across a package boundary
from cao.session._store import SessionStoreImpl

store = SessionStoreImpl.load()
record = store._records_by_id[session_id]
```

**Good:** The dispatcher consumes the session package's documented public
surface.

```python
# dispatcher.py
from cao.session import get_session

record = get_session(session_id)
```

### Naming The Missing Surface When You Must Reach In

**Bad - silent deep import.** A consumer imports an internal helper without
acknowledgement.

```python
from cao.tmux._panes import find_pane_by_title  # internal
```

**Good:** If no suitable public API exists, the deep import is annotated and a
follow-up is filed to add the missing public surface.

```python
# TODO(cao-tmux): no public API for "find pane by title"; tracked in #1234.
# Replace with `cao.tmux.find_pane(title=...)` once that lands.
from cao.tmux._panes import find_pane_by_title
```
