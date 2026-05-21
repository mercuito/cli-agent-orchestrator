---
id: 0003
status: ready
type: HITL
title: Collapse inbox onto polymorphic notification table (supersede CAO-42 implementation)
blocked_by: []
labels: [inbox-refactor, umbrella]
github_origin: 3
---

## Goal

Restructure CAO's inbox so the agent-to-agent path and the provider-routed path share one deep module — `inbox/` — exposed as a minimal `send · read · reply` interface, and addressed by `agent_id` end-to-end.

This work is the implementation of candidate #1 in `docs/architecture-review-2026-05-20.html` ("Give the Inbox concept a deep home"). It supersedes the implementation shape laid down in [Linear CAO-42 "Clarify CAO inbox notification and message contracts"](https://linear.app/yards-framework/issue/CAO-42).

## Relationship to CAO-42

CAO-42 set principles we are **keeping**:

- The smartphone model: notification = "look here", with optional readable content behind it.
- Notification ≠ has-Message. A notification can be a pure attention event (e.g., a baton-idle nudge).
- No object-specific nullable FKs on the notification table.
- Reply via CAO is a quick-route convenience, not the only way to respond in a workspace.
- Provider-authored breadcrumb stays opaque to CAO.

CAO-42 prescribed a two-table implementation (`inbox_messages` + `inbox_notification_targets` with `target_kind`/`target_id`/`role`). This issue **supersedes that implementation** for these reasons:

- The `inbox_messages` table existed to support broadcast and rehome. Broadcast was never wired. Rehome dies with agent-id addressing (no more terminal-id swaps).
- The `inbox_notification_targets` table's only `target_kind` in use today is `"inbox_message"`. Multi-target with roles was never load-bearing.
- The codebase already has `provider_conversation_inbox_notifications` — a Linear-specific join table that is exactly the "object-specific FK" anti-pattern CAO-42 warned against, just disguised. CAO-42's own implementation didn't survive contact with the second provider it was meant to anticipate.

The new implementation honors CAO-42's principles via polymorphic `source_kind`/`source_id` columns on `inbox_notifications` and a runtime source registry. No per-target-type nullable FKs grow.

## Target model

```
inbox/
  __init__.py         # exposes send, read, reply, source registry
  models.py           # Pydantic types (Notification, Source variants, ReadResult)
  store.py            # private: SQLAlchemy + SQL
  readiness.py        # private: watchdog + AgentReady subscriber
  source_registry.py  # source_kind → reply_handler

linear/
  ... + the former provider_conversations/ files (bridge, authorization, read_presentation, reply_handler)
  ... + the provider-conversation cache models (ProviderWorkItem etc.)
```

Inbox interface:

```python
inbox.send(receiver_agent_id, body, source) -> Notification
inbox.read(notification_id, caller) -> ReadResult  # body + opaque metadata + can_reply
inbox.reply(notification_id, body, caller) -> Reply  # dispatches via source registry
```

Source kinds:

- `PlainSource(sender_agent_id)` — agent-to-agent, registered by `inbox/`
- `ProviderSource(source_kind, source_id, sender_label, metadata)` — providers register at app init (Linear registers `"provider_conversation"`)
- Future: `"baton"`, etc. — no schema change required

Schema after migration (one table):

```sql
inbox_notifications
  id                 integer pk
  receiver_agent_id  text not null
  sender_agent_id    text             -- nullable; provider sources may not have one
  body               text not null
  source_kind        text not null
  source_id          text not null
  metadata_json      text
  status             text not null
  created_at         timestamp not null
  delivered_at       timestamp
  failed_at          timestamp
  error_detail       text
```

Dropped: `inbox_messages`, `inbox_notification_targets`, `provider_conversation_inbox_notifications`.

## Slices

- [#0004](0004-inbox-schema-cutover.md) — 1/7: Schema cutover + all current callers migrated in-place (HITL)
- [#0005](0005-inbox-plain-send.md) — 2/7: Plain agent-addressed `inbox.send` (tracer slice; blocked by 0004)
- [#0006](0006-inbox-read.md) — 3/7: `inbox.read` replaces `inbox_access.read_inbox_message` (blocked by 0005)
- [#0007](0007-inbox-source-registry-reply.md) — 4/7: Source registry + `inbox.reply` dispatch (blocked by 0006)
- [#0008](0008-agent-ready-event.md) — 5/7: `AgentReady` event drives delivery (blocked by 0004; parallel with 0005–0007)
- [#0009](0009-move-linear-files.md) — 6/7: Move Linear-owned files into `linear/`; delete `provider_conversations/` (blocked by 0007)
- [#0010](0010-cao-agent-id-env.md) — 7/7: `CAO_TERMINAL_ID` → `CAO_AGENT_ID` (blocked by 0005)

Dependency graph: `0004 → 0005 → 0006 → 0007 → 0009`, `0004 → 0008`, `0005 → 0010`.

## Required Review Workflow

Per CAO-42's "Required Review Workflow" section: each slice ships via a GitHub draft PR with sparse orientation comments; reviewer findings stay as PR review comments; the implementer addresses or replies before final landing.

## Design references

- `docs/architecture-review-2026-05-20.html` — candidate #1
- `CONTEXT.md` — glossary for Inbox, Source, Notification, AgentReady, Source registry, Replyability
- `docs/adr/0001-inbox-one-agnostic-concept.md`
- `docs/adr/0002-inbox-addresses-agents.md`
- `docs/adr/0003-aggressive-inbox-schema-collapse.md`
- `docs/adr/0004-provider-conversation-cache-owned-by-linear.md`
- [Linear CAO-42](https://linear.app/yards-framework/issue/CAO-42/clarify-cao-inbox-notification-and-message-contracts) — predecessor; principles inherited, implementation superseded

## Acceptance criteria

- [ ] All 7 slice issues merged via the Required Review Workflow.
- [ ] At final landing: `provider_conversations/` package is deleted; `inbox/` exposes only `send · read · reply` externally; addressing is by `agent_id` across HTTP/MCP/env; ADR-0003's schema is in effect; agent prompts use `CAO_AGENT_ID`.
- [ ] All criteria from `docs/criteria/` applied per CAO-42's "Implementation Notes".

## Review Gate

After implementing this task, run a review loop. The reviewer compares the landed implementation against each item in Acceptance criteria above plus all applicable entries in the `docs/criteria` catalog (run `uv run python scripts/catalog_criteria.py` and load any criterion whose `when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the review loop restarts with a fresh reviewer. For every review finding that requires an implementation change, the implementer updates [../completion-report.md](../completion-report.md) under this task's heading, recording what the reviewer found, why it was accepted as valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero valid findings for this task, and those two clean review passes are recorded in the completion report.

## Blocked by

None — umbrella tracker; individual slices have their own blockers.
