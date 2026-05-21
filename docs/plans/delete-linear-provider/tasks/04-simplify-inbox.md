# Task 04 — Collapse the Inbox to Agent-to-Agent Only

## Goal

Rewrite the `cli_agent_orchestrator/inbox/` package so it represents a pure
agent-to-agent message queue. Every concept tied to "this notification came
from somewhere other than an agent" goes away: `source_kind`, `source_id`,
`metadata_json`, `PlainSource`, `ProviderSource`, the reply registry, and
the `can_reply` flag.

After this task, an inbox notification carries exactly: an id, a
`sender_agent_id`, a `receiver_agent_id`, a body, a status, and lifecycle
timestamps. Nothing else.

## Preconditions

- Tasks 01–03 complete. The branch imports cleanly and the test suite
  passes on the pre-collapse inbox shape.

## Target Shape

`inbox/models.py`:

```python
class Notification(BaseModel):
    id: int
    sender_agent_id: str
    receiver_agent_id: str
    body: str
    status: MessageStatus
    created_at: datetime
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_detail: Optional[str] = None


class ReadResult(BaseModel):
    notification: Notification
    body: str
```

No `PlainSource`, no `ProviderSource`, no `Reply`. Drop them all.

`inbox/store.py`:

```python
class InboxNotificationModel(Base):
    __tablename__ = "inbox_notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_agent_id = Column(String, nullable=False)
    receiver_agent_id = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    error_detail = Column(Text, nullable=True)
```

Drop `source_kind`, `source_id`, `metadata_json` columns from the model.
Task 05 writes the migration that drops them from the DB; this task just
removes the columns from the model so the model and DB will be in sync
after Task 05 runs.

`inbox/__init__.py`:

```python
def send(receiver_agent_id: str, body: str, *, sender_agent_id: str) -> Notification: ...
def read(notification_id: int, caller_agent_id: str) -> ReadResult: ...
```

No `reply`. No `dispatch_reply`. No `register_reply_handler`. No
`NotReplyable`. No `InboxReplyError`. Drop all of them.

`inbox/source_registry.py`: delete the file entirely.

`inbox/readiness.py`: keep terminal delivery, drop source-kind batching.
`format_message_batch` no longer needs a `_source_label` helper; the batch
header should reference the sender agent id directly. Single-message
deliveries should still include the `notification_id=<id>` footer so the
receiving agent can call `read_inbox_message` if they want history.

## Scope

1. Edit `inbox/models.py` to the target shape above.
2. Edit `inbox/store.py`:
   - Update `InboxNotificationModel` columns.
   - Rewrite `create_inbox_delivery` / `create_inbox_notification_event` to
     accept a `sender_agent_id` and `receiver_agent_id`, no source parameters.
     Pick one canonical writer name; delete the redundant one. Recommend:
     keep `create_inbox_notification` and drop the legacy `create_inbox_delivery`
     wrapper.
   - Drop `_resolve_source_agent`, `_validate_complete_agent` (renamed
     argument labels if needed), `_serialize_notification_metadata`,
     `_deserialize_metadata`, `_synthetic_message_from_notification`.
   - `inbox_notification_from_model` / `inbox_delivery_from_model` collapse
     to a single function that returns a `Notification`. The notion of
     "delivery vs notification" has no remaining distinction.
   - `list_pending_inbox_deliveries_for_effective_source` becomes
     `list_pending_inbox_notifications` (already exists with a different
     signature; consolidate).
3. Edit `inbox/__init__.py`:
   - Public API: `send`, `read`, the exception classes (`InboxReadError`,
     `InboxReadNotFoundError`), and the public models.
   - `send` signature: `send(receiver_agent_id, body, *, sender_agent_id)`.
   - Drop `register_reply_handler` and the bottom-of-file
     `register_reply_handler("plain", _reply_to_plain_source)` call.
   - `__all__` reflects the new surface.
4. Delete `inbox/source_registry.py`.
5. Edit `inbox/readiness.py`:
   - `_source_label` removed.
   - `_format_delivery_body` always includes the footer
     `notification_id=<id>` (no source_kind check).
   - `format_message_batch` uses the sender agent id (resolved from the
     notification) for the header, not a `source_kind:source_id` label.
   - Drop `list_pending_inbox_deliveries_for_effective_source` and the
     batching by `(source_kind, source_id)`. Batch by
     `(sender_agent_id, receiver_agent_id)` instead, oldest-first.
6. Update every caller of the inbox in `src/` and `test/`:
   - `mcp_server/server.py` — `send_message` MCP tool: pass
     `sender_agent_id=<caller>` explicitly. `read_inbox_message`: already
     simplified in Task 01; update the `from` field to come from
     `notification.sender_agent_id`.
   - `api/main.py` — `send_inbox_message` calls now use the new signature.
   - Anywhere else `PlainSource` or `ProviderSource` was imported.
7. Update existing inbox tests (`test/inbox/test_*.py`) to use the new
   contracts. Apply `test-validity-preserved` rigorously.
8. The `models.InboxDelivery`, `InboxMessageRecord` types in
   `cli_agent_orchestrator/models/inbox.py` need review — they may be
   simplifiable or partly redundant after this collapse. Trim where safe.

## Out of Scope

- The SQLite migration to drop the obsolete columns is Task 05.
- UI changes are Task 06.
- ADR work is Task 07.

## Acceptance Criteria

1. `grep -rn "source_kind\|source_id\|notification_metadata\|PlainSource\|ProviderSource\|register_reply_handler\|dispatch_reply\|can_reply\|NotReplyable\|InboxReplyError" src/cli_agent_orchestrator/inbox/ src/cli_agent_orchestrator/mcp_server/ src/cli_agent_orchestrator/api/` returns no matches.
2. `inbox/source_registry.py` no longer exists.
3. `inbox/__init__.py` public surface is `send`, `read`, `InboxReadError`,
   `InboxReadNotFoundError`, `Notification`, `ReadResult`, `MessageStatus`.
4. `uv run pytest -q test/inbox/` passes.
5. `uv run pytest -q` passes (full suite, since callers were updated).
6. The deletion test from `deep-systems`: deleting the inbox package would
   make every caller suddenly need to talk to SQLAlchemy directly, manage
   terminal liveness, and format delivery batches. The interface is narrow;
   the implementation hides real complexity. Confirm.

## Criteria to Consult

- `do-not-assume-backwards-compatibility` — Always. No `PlainSource` shim;
  no aliases.
- `system-definitions-are-localized` — The inbox subsystem is being
  substantially reshaped. Its API and storage must live in `inbox/` only.
- `deep-systems` — Apply the deletion test on the final shape.
- `readable-and-explicit` — `sender_agent_id` / `receiver_agent_id` over
  any "source" framing. No leftover comments referencing removed concepts.
- `minimal-cohesive-changes` — Stay in the inbox files and their callers.
- `test-validity-preserved` — Always.
- `target-behavior-must-not-be-mocked` — Inbox tests hit the real store.
- `test-through-owner-surfaces` — Inbox tests go through `send` / `read`,
  not through `inbox.store` private helpers.

After implementation, re-evaluate against the catalog.

## Notes for the Implementing Agent

- The `inbox/readiness.py` batching uses `list_pending_inbox_deliveries_for_effective_source`
  with a per-source batch. The new batching is per-sender. Sender already
  groups naturally — a single sender's queued messages to one receiver are
  the "batch" and should arrive together when the receiver is idle.
- `models/inbox.py` has `InboxDelivery`, `InboxNotification`,
  `InboxMessageRecord`. After the collapse, the only meaningful concept is
  the notification. Audit and trim. If `InboxDelivery` becomes a one-field
  wrapper around `InboxNotification`, fold it.
- When you rebatch by `(sender_agent_id, receiver_agent_id)`, preserve the
  invariant that batches arrive in created-at order. Two sequential
  messages from agent A to agent B should arrive as a single bundled
  notification in the terminal, not interleaved with messages from agent C.
- The `_format_delivery_body` footer (`notification_id=<id>`) was previously
  only emitted for `source_kind == "plain"`. Make it unconditional — every
  delivered batch should let the receiver follow up with
  `read_inbox_message`.
