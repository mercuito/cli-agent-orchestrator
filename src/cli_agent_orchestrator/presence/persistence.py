"""Provider-neutral persistence helpers for external presence systems."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.presence.models import (
    ConversationMessageRecord,
    ConversationThreadRecord,
    PersistedPresenceEvent,
    PresenceEvent,
    ProcessedProviderEventRecord,
    WorkItemRecord,
)


def _dumps(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def _loads(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    return json.loads(value)


def _work_item_from_row(row: db_module.PresenceWorkItemModel) -> WorkItemRecord:
    return WorkItemRecord(
        id=row.id,
        provider=row.provider,
        external_id=row.external_id,
        external_url=row.external_url,
        identifier=row.identifier,
        title=row.title,
        state=row.state,
        raw_snapshot=_loads(row.raw_snapshot_json),
        metadata=_loads(row.metadata_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _thread_from_row(row: db_module.PresenceThreadModel) -> ConversationThreadRecord:
    return ConversationThreadRecord(
        id=row.id,
        provider=row.provider,
        external_id=row.external_id,
        external_url=row.external_url,
        work_item_id=row.work_item_id,
        kind=row.kind,
        state=row.state,
        prompt_context=row.prompt_context,
        raw_snapshot=_loads(row.raw_snapshot_json),
        metadata=_loads(row.metadata_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_from_row(row: db_module.PresenceMessageModel) -> ConversationMessageRecord:
    return ConversationMessageRecord(
        id=row.id,
        thread_id=row.thread_id,
        provider=row.provider,
        external_id=row.external_id,
        direction=row.direction,
        kind=row.kind,
        body=row.body,
        state=row.state,
        raw_snapshot=_loads(row.raw_snapshot_json),
        metadata=_loads(row.metadata_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _processed_event_from_row(
    row: db_module.ProcessedProviderEventModel,
) -> ProcessedProviderEventRecord:
    return ProcessedProviderEventRecord(
        id=row.id,
        provider=row.provider,
        external_event_id=row.external_event_id,
        event_type=row.event_type,
        processed_at=row.processed_at,
        metadata=_loads(row.metadata_json),
    )


def _require_ref(provider: str, external_id: str) -> None:
    if not provider:
        raise ValueError("provider is required")
    if not external_id:
        raise ValueError("external_id is required")


def _insert_unique_ref_if_missing(
    session: Session,
    model: Any,
    *,
    external_id_field: str,
    values: Dict[str, Any],
) -> bool:
    """Insert an opaque provider ref, letting the database resolve duplicate races."""

    result = session.execute(
        sqlite_insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["provider", external_id_field])
    )
    return result.rowcount == 1


def upsert_work_item(
    *,
    provider: str,
    external_id: str,
    external_url: Optional[str] = None,
    identifier: Optional[str] = None,
    title: Optional[str] = None,
    state: Optional[str] = None,
    raw_snapshot: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> WorkItemRecord:
    """Create or update a provider-owned work item by opaque provider ref."""

    def _upsert(session: Session) -> WorkItemRecord:
        _require_ref(provider, external_id)
        now = datetime.now()
        _insert_unique_ref_if_missing(
            session,
            db_module.PresenceWorkItemModel,
            external_id_field="external_id",
            values={
                "provider": provider,
                "external_id": external_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = (
            session.query(db_module.PresenceWorkItemModel)
            .filter(
                db_module.PresenceWorkItemModel.provider == provider,
                db_module.PresenceWorkItemModel.external_id == external_id,
            )
            .first()
        )
        if row is None:
            raise RuntimeError("presence work item insert did not create or find a row")

        row.external_url = external_url
        row.identifier = identifier
        row.title = title
        row.state = state
        row.raw_snapshot_json = _dumps(raw_snapshot)
        row.metadata_json = _dumps(metadata)
        row.updated_at = now
        session.flush()
        session.refresh(row)
        return _work_item_from_row(row)

    if db is not None:
        return _upsert(db)

    with db_module.SessionLocal() as session:
        record = _upsert(session)
        session.commit()
        return record


def get_work_item(
    provider: str, external_id: str, *, db: Optional[Session] = None
) -> Optional[WorkItemRecord]:
    """Read a work item by provider-owned ref."""

    def _get(session: Session) -> Optional[WorkItemRecord]:
        _require_ref(provider, external_id)
        row = (
            session.query(db_module.PresenceWorkItemModel)
            .filter(
                db_module.PresenceWorkItemModel.provider == provider,
                db_module.PresenceWorkItemModel.external_id == external_id,
            )
            .first()
        )
        return _work_item_from_row(row) if row is not None else None

    if db is not None:
        return _get(db)

    with db_module.SessionLocal() as session:
        return _get(session)


def upsert_thread(
    *,
    provider: str,
    external_id: str,
    external_url: Optional[str] = None,
    work_item_id: Optional[int] = None,
    kind: str = "conversation",
    state: str = "active",
    prompt_context: Optional[str] = None,
    raw_snapshot: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> ConversationThreadRecord:
    """Create or update a provider-owned conversation thread by opaque ref."""

    def _upsert(session: Session) -> ConversationThreadRecord:
        _require_ref(provider, external_id)
        now = datetime.now()
        _insert_unique_ref_if_missing(
            session,
            db_module.PresenceThreadModel,
            external_id_field="external_id",
            values={
                "provider": provider,
                "external_id": external_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = (
            session.query(db_module.PresenceThreadModel)
            .filter(
                db_module.PresenceThreadModel.provider == provider,
                db_module.PresenceThreadModel.external_id == external_id,
            )
            .first()
        )
        if row is None:
            raise RuntimeError("presence thread insert did not create or find a row")

        row.external_url = external_url
        row.work_item_id = work_item_id
        row.kind = kind
        row.state = state
        row.prompt_context = prompt_context
        row.raw_snapshot_json = _dumps(raw_snapshot)
        row.metadata_json = _dumps(metadata)
        row.updated_at = now
        session.flush()
        session.refresh(row)
        return _thread_from_row(row)

    if db is not None:
        return _upsert(db)

    with db_module.SessionLocal() as session:
        record = _upsert(session)
        session.commit()
        return record


def get_thread(
    provider: str, external_id: str, *, db: Optional[Session] = None
) -> Optional[ConversationThreadRecord]:
    """Read a conversation thread by provider-owned ref."""

    def _get(session: Session) -> Optional[ConversationThreadRecord]:
        _require_ref(provider, external_id)
        row = (
            session.query(db_module.PresenceThreadModel)
            .filter(
                db_module.PresenceThreadModel.provider == provider,
                db_module.PresenceThreadModel.external_id == external_id,
            )
            .first()
        )
        return _thread_from_row(row) if row is not None else None

    if db is not None:
        return _get(db)

    with db_module.SessionLocal() as session:
        return _get(session)


def upsert_message(
    *,
    thread_id: int,
    provider: str,
    external_id: Optional[str] = None,
    direction: str = "inbound",
    kind: str = "unknown",
    body: Optional[str] = None,
    state: str = "received",
    raw_snapshot: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> ConversationMessageRecord:
    """Create or update a message/activity, deduping on provider external_id when present."""

    def _upsert(session: Session) -> ConversationMessageRecord:
        if not provider:
            raise ValueError("provider is required")
        now = datetime.now()
        row = None
        if external_id is not None:
            _insert_unique_ref_if_missing(
                session,
                db_module.PresenceMessageModel,
                external_id_field="external_id",
                values={
                    "thread_id": thread_id,
                    "provider": provider,
                    "external_id": external_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            row = (
                session.query(db_module.PresenceMessageModel)
                .filter(
                    db_module.PresenceMessageModel.provider == provider,
                    db_module.PresenceMessageModel.external_id == external_id,
                )
                .first()
            )
        if row is None:
            if external_id is not None:
                raise RuntimeError("presence message insert did not create or find a row")
            row = db_module.PresenceMessageModel(
                thread_id=thread_id,
                provider=provider,
                external_id=external_id,
                created_at=now,
            )
            session.add(row)

        row.thread_id = thread_id
        row.direction = direction
        row.kind = kind
        row.body = body
        row.state = state
        row.raw_snapshot_json = _dumps(raw_snapshot)
        row.metadata_json = _dumps(metadata)
        row.updated_at = now
        session.flush()
        session.refresh(row)
        return _message_from_row(row)

    if db is not None:
        return _upsert(db)

    with db_module.SessionLocal() as session:
        record = _upsert(session)
        session.commit()
        return record


def get_message(
    provider: str, external_id: str, *, db: Optional[Session] = None
) -> Optional[ConversationMessageRecord]:
    """Read a message/activity by provider-owned ref."""

    def _get(session: Session) -> Optional[ConversationMessageRecord]:
        _require_ref(provider, external_id)
        row = (
            session.query(db_module.PresenceMessageModel)
            .filter(
                db_module.PresenceMessageModel.provider == provider,
                db_module.PresenceMessageModel.external_id == external_id,
            )
            .first()
        )
        return _message_from_row(row) if row is not None else None

    if db is not None:
        return _get(db)

    with db_module.SessionLocal() as session:
        return _get(session)


def list_messages(
    thread_id: int, *, db: Optional[Session] = None
) -> List[ConversationMessageRecord]:
    """List durable messages for a conversation thread oldest first."""

    def _list(session: Session) -> List[ConversationMessageRecord]:
        rows = (
            session.query(db_module.PresenceMessageModel)
            .filter(db_module.PresenceMessageModel.thread_id == thread_id)
            .order_by(
                db_module.PresenceMessageModel.created_at.asc(),
                db_module.PresenceMessageModel.id.asc(),
            )
            .all()
        )
        return [_message_from_row(row) for row in rows]

    if db is not None:
        return _list(db)

    with db_module.SessionLocal() as session:
        return _list(session)


def upsert_processed_event(
    *,
    provider: str,
    external_event_id: str,
    event_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> ProcessedProviderEventRecord:
    """Create or read/update a provider event idempotency marker."""

    def _upsert(session: Session) -> Tuple[ProcessedProviderEventRecord, bool]:
        _require_ref(provider, external_event_id)
        now = datetime.now()
        created = _insert_unique_ref_if_missing(
            session,
            db_module.ProcessedProviderEventModel,
            external_id_field="external_event_id",
            values={
                "provider": provider,
                "external_event_id": external_event_id,
                "event_type": event_type,
                "processed_at": now,
                "metadata_json": _dumps(metadata),
            },
        )
        row = (
            session.query(db_module.ProcessedProviderEventModel)
            .filter(
                db_module.ProcessedProviderEventModel.provider == provider,
                db_module.ProcessedProviderEventModel.external_event_id == external_event_id,
            )
            .first()
        )
        if row is None:
            raise RuntimeError("processed provider event insert did not create or find a row")

        row.event_type = event_type
        row.metadata_json = _dumps(metadata)
        session.flush()
        session.refresh(row)
        return _processed_event_from_row(row), created

    if db is not None:
        return _upsert(db)[0]

    with db_module.SessionLocal() as session:
        record, _ = _upsert(session)
        session.commit()
        return record


def get_processed_event(
    provider: str, external_event_id: str, *, db: Optional[Session] = None
) -> Optional[ProcessedProviderEventRecord]:
    """Read a provider event idempotency marker."""

    def _get(session: Session) -> Optional[ProcessedProviderEventRecord]:
        _require_ref(provider, external_event_id)
        row = (
            session.query(db_module.ProcessedProviderEventModel)
            .filter(
                db_module.ProcessedProviderEventModel.provider == provider,
                db_module.ProcessedProviderEventModel.external_event_id == external_event_id,
            )
            .first()
        )
        return _processed_event_from_row(row) if row is not None else None

    if db is not None:
        return _get(db)

    with db_module.SessionLocal() as session:
        return _get(session)


def mark_processed_event(
    *,
    provider: str,
    external_event_id: str,
    event_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> Tuple[ProcessedProviderEventRecord, bool]:
    """Mark an event processed and report whether this call created the marker."""

    def _mark(session: Session) -> Tuple[ProcessedProviderEventRecord, bool]:
        _require_ref(provider, external_event_id)
        now = datetime.now()
        created = _insert_unique_ref_if_missing(
            session,
            db_module.ProcessedProviderEventModel,
            external_id_field="external_event_id",
            values={
                "provider": provider,
                "external_event_id": external_event_id,
                "event_type": event_type,
                "processed_at": now,
                "metadata_json": _dumps(metadata),
            },
        )
        row = (
            session.query(db_module.ProcessedProviderEventModel)
            .filter(
                db_module.ProcessedProviderEventModel.provider == provider,
                db_module.ProcessedProviderEventModel.external_event_id == external_event_id,
            )
            .first()
        )
        if row is None:
            raise RuntimeError("processed provider event insert did not create or find a row")
        row.event_type = event_type
        row.metadata_json = _dumps(metadata)
        session.flush()
        session.refresh(row)
        return _processed_event_from_row(row), created

    if db is not None:
        return _mark(db)

    with db_module.SessionLocal() as session:
        result = _mark(session)
        session.commit()
        return result


def persist_presence_event(event: PresenceEvent) -> PersistedPresenceEvent:
    """Persist a normalized provider event without invoking any provider behavior."""

    with db_module.SessionLocal() as session:
        processed_event = None
        if event.delivery_id:
            processed_event, created = mark_processed_event(
                provider=event.provider,
                external_event_id=event.delivery_id,
                event_type=event.event_type,
                metadata={"action": event.action} if event.action else None,
                db=session,
            )
            if not created:
                session.commit()
                return PersistedPresenceEvent(
                    processed_event=processed_event,
                    work_item=None,
                    thread=None,
                    message=None,
                )

        work_item = None
        thread = None
        message = None
        if event.thread is not None:
            if event.thread.work_item is not None:
                ref = event.thread.work_item.ref
                work_item = upsert_work_item(
                    provider=ref.provider,
                    external_id=ref.id,
                    external_url=ref.url,
                    identifier=event.thread.work_item.identifier,
                    title=event.thread.work_item.title,
                    state=event.thread.work_item.state,
                    raw_snapshot=event.raw_payload,
                    db=session,
                )

            thread_ref = event.thread.ref
            thread = upsert_thread(
                provider=thread_ref.provider,
                external_id=thread_ref.id,
                external_url=thread_ref.url,
                work_item_id=work_item.id if work_item is not None else None,
                kind=event.thread.kind,
                state=event.thread.state,
                prompt_context=event.thread.prompt_context,
                raw_snapshot=event.raw_payload,
                db=session,
            )

        if thread is not None and event.message is not None:
            message_ref = event.message.ref
            message = upsert_message(
                thread_id=thread.id,
                provider=message_ref.provider if message_ref is not None else event.provider,
                external_id=message_ref.id if message_ref is not None else None,
                direction=event.message.direction,
                kind=event.message.kind,
                body=event.message.body,
                state=event.message.state,
                raw_snapshot=event.raw_payload,
                db=session,
            )

        session.commit()
        return PersistedPresenceEvent(
            processed_event=processed_event,
            work_item=work_item,
            thread=thread,
            message=message,
        )
