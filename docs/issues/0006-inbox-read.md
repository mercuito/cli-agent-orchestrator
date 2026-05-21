---
id: 0006
status: ready
type: AFK
title: inbox.read replaces inbox_access.read_inbox_message
parent: 0003
blocked_by: [0005]
labels: [inbox-refactor]
github_origin: 6
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

`inbox.read` becomes the single read entry point.

- `inbox.read(notification_id, caller_agent_id) -> ReadResult` returns body + opaque metadata + `can_reply: bool` (derived from whether the source kind has a registered reply handler; the registry lands in [#0007](0007-inbox-source-registry-reply.md)).
- MCP `read_inbox_message(notification_id)` calls `inbox.read`.
- For `source_kind == "provider_conversation"`, the MCP tool layer ALSO calls a Linear-internal helper (`linear.get_message_context(source_id)`) to attach breadcrumb + work-item context to the response. This keeps Inbox provider-agnostic.
- `provider_conversations/inbox_access.py` deleted. Its source-agnostic read logic moves into `inbox/`. Linear-specific lookup (thread, work item) lives in a `linear.get_message_context` helper (still inside `provider_conversations/` until [#0009](0009-move-linear-files.md) moves it).
- Plain notifications: read returns body + empty metadata + `can_reply=True`. No external lookup.

Tracer tests:

> Given a provider notification was delivered to agent B for a Linear thread,
> when an agent calls MCP `read_inbox_message(notification_id)`,
> then the response includes the body, the Linear breadcrumb, and `replyable=True`.

> Given a plain notification was delivered to agent B from agent A,
> when an agent calls MCP `read_inbox_message(notification_id)`,
> then the response includes the body and `replyable=True`. ([#0007](0007-inbox-source-registry-reply.md) enforces the registry that makes this real.)

## Acceptance criteria

- [ ] `inbox.read` exposed from `inbox/`.
- [ ] MCP `read_inbox_message` uses `inbox.read`.
- [ ] Linear context helper is private to its owning package (`provider_conversations/` until [#0009](0009-move-linear-files.md); then `linear/`).
- [ ] `provider_conversations/inbox_access.py` deleted; no external callers remain.
- [ ] Both tracer tests pass.
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#0005](0005-inbox-plain-send.md) — `inbox/` package and persistence layer must exist before adding `read`.
