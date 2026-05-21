---
id: 0005
status: ready
type: AFK
title: Plain agent-addressed inbox.send (tracer slice)
parent: 0003
blocked_by: [0004]
labels: [inbox-refactor]
github_origin: 5
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

The first tracer-bullet slice through the new `inbox/` package. After this slice merges:

- A new top-level package `inbox/` exists with:
  - `inbox/__init__.py` exposing `send` and `PlainSource`
  - `inbox/models.py` with `Notification`, `PlainSource`, `ProviderSource`, `ReadResult`, `Reply` Pydantic types
  - `inbox/store.py` (private) — SQLAlchemy model and persistence functions for `inbox_notifications`
  - `inbox/readiness.py` (private) — watchdog Observer + LogFileHandler, moved from `services/inbox_service.py`
- `inbox.send(receiver_agent_id, body, source=PlainSource(sender_agent_id))` writes a notification row, attempts immediate delivery if the receiver agent's terminal is idle, and returns a `Notification` object.
- HTTP route: `POST /agents/{agent_id}/inbox/messages` (old `POST /terminals/{receiver_id}/inbox/messages` route deleted).
- MCP `send_message(receiver_agent_id, body)` — parameter renamed from `receiver_id`.
- `services/inbox_service.send_message`-shaped public functions and `LogFileHandler` deleted; all old in-place callers route through `inbox.send`.

Note: read/reply for both plain and provider paths still live in `provider_conversations/inbox_access.py` and `reply_service.py` and are migrated in later slices.

Tracer test (real SQLite, fake tmux, real `CaoEventDispatcher`, no patching of inbox internals):

> Given agent A with a live terminal and agent B with a live idle terminal,
> when A's MCP `send_message(receiver_agent_id=B, body="hello")` is invoked,
> then within the test's wait window B's tmux session has received a `send_keys` call carrying "hello",
> and the `inbox_notifications` row for B is marked DELIVERED.

## Acceptance criteria

- [ ] New `inbox/` package exists with the files described.
- [ ] `inbox.send` works for `PlainSource`.
- [ ] HTTP route moved to `/agents/{agent_id}/inbox/messages`; old `/terminals/...` route deleted.
- [ ] MCP `send_message` parameter renamed to `receiver_agent_id`. (Agent prompts referencing the old shape are handled in [#0010](0010-cao-agent-id-env.md) — leave them for now.)
- [ ] `services/inbox_service.send_message`-shaped functions and `LogFileHandler` deleted.
- [ ] Tracer test as described passes.
- [ ] Patched-style tests retire as the tracer covers them (delete or rewrite at the interface level).
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#0004](0004-inbox-schema-cutover.md) — schema must be in place before the new package writes to it.
