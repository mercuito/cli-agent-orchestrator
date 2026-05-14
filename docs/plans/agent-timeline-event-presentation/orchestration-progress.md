# Orchestration Progress — Agent Timeline Event Presentation

## Task Status

| Task | Status | Notes |
|------|--------|-------|
| `t-1` — Typed Timeline Payload Surface And Fallback View | Pending | Reissued after architecture pivot from backend-owned presentation values to frontend typed event views. |
| `t-2` — Known Frontend Event Views | Pending | Depends on `t-1`. |
| `t-3` — Related View Continuity And Entity References | Pending | Depends on `t-1` and `t-2`. |

## Architecture Pivot

- The uncommitted backend-owned presentation implementation for prior
  `t-1`/`t-2` dispatches was intentionally discarded before commit.
- The canonical pending plan now keeps typed event presentation in the
  frontend. Backend timeline reads expose event envelope fields and typed
  `event_data`; frontend event views own rendering, fallback, and entity
  reference affordances.
- No task is currently implemented under the reissued architecture.
