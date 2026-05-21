---
id: 0004
status: ready
type: HITL
title: Schema cutover + all current callers migrated in-place
parent: 0003
blocked_by: []
labels: [inbox-refactor]
github_origin: 4
---

## Parent

[#0003](0003-inbox-collapse-umbrella.md)

## What to build

The atomic schema migration that underpins the deep Inbox refactor. After this slice the new schema is live and all existing inbox callers compile and pass tests against it — but the `inbox/` package is NOT yet created and no external API shape changes. Subsequent slices build on this foundation.

Migration:

- Rename `inbox_notifications.receiver_id` (currently a terminal_id) to `receiver_agent_id`. Backfill by joining `terminals.agent_id`. Enforce NOT NULL after backfill.
- Drop tables: `inbox_messages`, `inbox_notification_targets`, `provider_conversation_inbox_notifications`.
- Migration script lives under the existing migrations infrastructure (`clients/database_migrations.py`, `clients/sqlite_migrations.py`).

All current callers updated in-place to use the new schema:

- `clients/inbox_store.py` — delete `InboxMessageModel` and `InboxNotificationTargetModel`. Update `InboxNotificationModel` (column rename). Persistence helpers no longer hop through messages/targets — body, source_kind, source_id are already on the notification row.
- `provider_conversations/inbox_bridge.py` — instead of creating message row + target row + provider_conversation_inbox_notifications row, create a single notification with `source_kind="provider_conversation"` and `source_id=str(provider_message_id)`. Metadata blob retains breadcrumb/context as today.
- `provider_conversations/inbox_access.py` — read flow stops following the targets table and the provider-conversation join; reads the notification row directly. For provider-conversation source, query `ProviderConversationMessage` by source_id to attach context.
- `provider_conversations/reply_service.py` — same pattern: look up the provider message via source_id, not via the dropped join.
- `services/inbox_service.py` — `format_message_batch` and `check_and_send_pending_messages` already operate on notification rows; ensure body-on-notification is the only source.
- `runtime/agent.py` — any inbox_message lookups become notification lookups.
- `services/monitoring_service.py` — adjust any inbox row queries.
- Tests across `test/services/`, `test/api/`, `test/provider_conversations/`, `test/runtime/` updated to match.

No external HTTP/MCP shape changes in this slice. No `inbox/` package. No agent prompts touched.

## Acceptance criteria

- [ ] Migration script renames `receiver_id` → `receiver_agent_id` on `inbox_notifications`, backfilled from `terminals.agent_id`.
- [ ] Migration script drops `inbox_messages`, `inbox_notification_targets`, `provider_conversation_inbox_notifications`.
- [ ] All in-place callers updated to read/write the new schema; no dead references to dropped tables.
- [ ] Full test suite passes.
- [ ] No backwards-compat columns or shims left in code (per CAO-42 "Implementation Notes": no legacy compatibility paths).
- [ ] All applicable criteria from `docs/criteria/` applied.
- [ ] PR opens as draft with sparse orientation comments on the migration and on each major migrated caller.

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

None — can start immediately.
