---
id: 0007
status: ready
type: AFK
title: Source registry + inbox.reply dispatch
parent: 0003
blocked_by: [0006]
labels: [inbox-refactor]
github_origin: 7
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

The source registry plus `inbox.reply` dispatch.

- `inbox/source_registry.py` — process-local map `source_kind → reply_handler`.
- `inbox/` registers `PlainSource`'s reply handler at module init. The plain handler takes `(notification, body, caller)` and calls `inbox.send(receiver_agent_id=notification.sender_agent_id, body=body, source=PlainSource(sender_agent_id=caller))`. A plain reply is just another plain send looped back.
- Linear's reply handler (today in `provider_conversations/reply_service.py`) becomes the registered handler for `source_kind="provider_conversation"`. Registered at Linear-package import time. Retains today's behavior: validate auth, call Linear API, record outbound message, return result.
- `inbox.reply(notification_id, body, caller_agent_id)` looks up the notification's source kind, dispatches via the registry. If no handler is registered, raises `NotReplyable`.
- MCP `reply_to_inbox_message(notification_id, body)` calls `inbox.reply`.
- Plain notification previews (the text pushed into the receiving terminal) now include the notification_id so plain replies have something to address. Use a minimal footer rather than a verbose header.
- `provider_conversations/reply_service.py` shrinks to the registered handler only; legacy public functions deleted.

Tracer tests:

> Given a provider notification was delivered to agent B,
> when an agent calls MCP `reply_to_inbox_message(notification_id, body)`,
> then the fake Linear API client records the expected create-comment call with `body`,
> and a downstream `ProviderConversationMessage` row is recorded.

> Given a plain notification was delivered from agent A to agent B,
> when agent B calls MCP `reply_to_inbox_message(notification_id, body)`,
> then agent A's tmux session receives a `send_keys` call carrying `body`.

> Given a notification with `source_kind="baton"` (no registered handler),
> when an agent calls `inbox.reply`,
> then `NotReplyable` is raised.

## Acceptance criteria

- [ ] `inbox/source_registry.py` exists.
- [ ] `PlainSource` reply handler registered by `inbox/`.
- [ ] `provider_conversation` reply handler registered by its owning package (current `provider_conversations/`; moves with [#0009](0009-move-linear-files.md)).
- [ ] `inbox.reply` dispatches via registry; raises `NotReplyable` for unhandled source kinds.
- [ ] Plain notification previews include `notification_id` as a small footer.
- [ ] All three tracer tests pass.
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#0006](0006-inbox-read.md) — read and reply are paired UX-wise; agents need to read before they can reply.
