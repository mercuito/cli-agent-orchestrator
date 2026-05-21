---
id: 0009
status: ready
type: AFK
title: Move Linear-owned files into linear/; delete provider_conversations/
parent: 0003
blocked_by: [0007]
labels: [inbox-refactor]
github_origin: 9
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

A near-pure file-move slice. After this slice, `provider_conversations/` no longer exists.

Moves:

- `clients/provider_conversation_store.py` Linear-specific models (`ProviderWorkItemModel`, `ProviderConversationThreadModel`, `ProviderConversationMessageModel`, `ProcessedProviderEventModel`) → under `linear/`.
- `provider_conversations/inbox_bridge.py` → `linear/inbox_bridge.py`.
- `provider_conversations/inbox_authorization.py` → `linear/inbox_authorization.py`.
- `provider_conversations/inbox_read_presentation.py` → `linear/inbox_read_presentation.py` (or fold into Linear's helpers if trivial).
- `provider_conversations/reply_service.py` → `linear/reply_handler.py` (the registered handler from [#0007](0007-inbox-source-registry-reply.md)).
- `provider_conversations/persistence.py` → `linear/persistence.py`.
- `provider_conversations/models.py` → `linear/models.py`.
- `provider_conversations/` package deleted entirely.
- `clients/provider_conversation_store.py` either deleted (Linear models moved) or retained with non-Linear leftovers (`MonitoringSessionModel`, `AgentRuntimeNotificationModel`). Only the four Linear-specific models move.

Also:

- Linear's source-kind registration (from [#0007](0007-inbox-source-registry-reply.md)) updated to its new location.
- All imports across the codebase updated.
- No behavior changes.

Tracer:

> The end-to-end test from [#0007](0007-inbox-source-registry-reply.md) (provider reply via `inbox.reply` round-trips to the fake Linear API client) continues to pass with no test changes, only import-path updates.

## Acceptance criteria

- [ ] `provider_conversations/` package deleted.
- [ ] Linear-specific cache models live under `linear/`.
- [ ] Inbox bridge, authorization, read-presentation, reply handler all under `linear/`.
- [ ] No file outside `linear/` imports from a `provider_conversations.*` path.
- [ ] [#0007](0007-inbox-source-registry-reply.md) tracer test still passes after import-only changes.
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments highlighting the package move.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

- [#0007](0007-inbox-source-registry-reply.md) — Linear's reply handler must be registered via the source registry before its files can move cleanly.
