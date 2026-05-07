"""Minimal database client with terminal, inbox, monitoring, flow, and baton metadata."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, declarative_base, sessionmaker

from cli_agent_orchestrator.constants import DATABASE_URL, DB_DIR, DEFAULT_PROVIDER
from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonEventType, BatonStatus
from cli_agent_orchestrator.models.flow import Flow
from cli_agent_orchestrator.models.inbox import (
    InboxDelivery,
    InboxMessage,
    InboxMessageRecord,
    InboxNotification,
    MessageStatus,
)

logger = logging.getLogger(__name__)

Base: Any = declarative_base()


class EffectiveMessageSource(NamedTuple):
    """Source identity used for inbox batch selection."""

    kind: str
    id: str
    is_legacy_message: bool = False


class TerminalModel(Base):
    """SQLAlchemy model for terminal metadata only."""

    __tablename__ = "terminals"

    id = Column(String, primary_key=True)  # "abc123ef"
    tmux_session = Column(String, nullable=False)  # "cao-session-name"
    tmux_window = Column(String, nullable=False)  # "window-name"
    provider = Column(String, nullable=False)  # "q_cli", "claude_code"
    agent_profile = Column(String)  # "developer", "reviewer" (optional)
    allowed_tools = Column(String, nullable=True)  # JSON-encoded list of CAO tool names
    last_active = Column(DateTime, default=datetime.now)


class InboxModel(Base):
    """Legacy SQLAlchemy model for overloaded inbox rows."""

    __tablename__ = "inbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String, nullable=False)
    receiver_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    source_kind = Column(String, nullable=True)
    source_id = Column(String, nullable=True)
    status = Column(String, nullable=False)  # MessageStatus enum value
    created_at = Column(DateTime, default=datetime.now)


class InboxMessageModel(Base):
    """SQLAlchemy model for durable semantic inbox messages."""

    __tablename__ = "inbox_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    origin_json = Column(Text, nullable=True)
    route_kind = Column(String, nullable=True)
    route_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class InboxNotificationModel(Base):
    """SQLAlchemy model for per-recipient inbox delivery notifications."""

    __tablename__ = "inbox_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer, ForeignKey("inbox_messages.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    error_detail = Column(Text, nullable=True)
    legacy_inbox_id = Column(
        Integer, ForeignKey("inbox.id", ondelete="SET NULL"), nullable=True, unique=True
    )


class MonitoringSessionModel(Base):
    """A monitoring session is a recording window over the inbox table.

    Captures all inbox activity involving ``terminal_id`` within
    ``[started_at, ended_at]`` (or ``[started_at, now]`` while active). Peer
    and time-range filtering happens at query time on reads (see
    ``monitoring_service.get_session_messages``), not baked into the session
    record — one recording, many possible views.

    There is at most one active session per terminal at any given time (see
    ``create_session`` idempotency). Ended sessions remain in the table so
    their artifacts stay fetchable.
    """

    __tablename__ = "monitoring_sessions"

    id = Column(String, primary_key=True)
    terminal_id = Column(String, nullable=False)
    label = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class BatonModel(Base):
    """SQLAlchemy model for baton state."""

    __tablename__ = "batons"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False)
    originator_id = Column(String, nullable=False)
    current_holder_id = Column(String, nullable=True)
    return_stack_json = Column(String, nullable=False, default="[]")
    expected_next_action = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
    last_nudged_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class BatonEventModel(Base):
    """SQLAlchemy model for baton audit events."""

    __tablename__ = "baton_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    baton_id = Column(String, ForeignKey("batons.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String, nullable=False)
    actor_id = Column(String, nullable=False)
    from_holder_id = Column(String, nullable=True)
    to_holder_id = Column(String, nullable=True)
    message = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class FlowModel(Base):
    """SQLAlchemy model for flow metadata."""

    __tablename__ = "flows"

    name = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    schedule = Column(String, nullable=False)
    agent_profile = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    script = Column(String, nullable=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)


class PresenceWorkItemModel(Base):
    """Provider-neutral work item reference owned by an external presence system."""

    __tablename__ = "presence_work_items"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    external_url = Column(String, nullable=True)
    identifier = Column(String, nullable=True)
    title = Column(String, nullable=True)
    state = Column(String, nullable=True)
    raw_snapshot_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class PresenceThreadModel(Base):
    """Provider-neutral conversation surface owned by an external presence system."""

    __tablename__ = "presence_threads"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    external_url = Column(String, nullable=True)
    work_item_id = Column(
        Integer, ForeignKey("presence_work_items.id", ondelete="SET NULL"), nullable=True
    )
    kind = Column(String, nullable=False, default="conversation")
    state = Column(String, nullable=False, default="active")
    prompt_context = Column(Text, nullable=True)
    raw_snapshot_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class PresenceMessageModel(Base):
    """Provider-neutral message/activity inside an external conversation surface."""

    __tablename__ = "presence_messages"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(
        Integer, ForeignKey("presence_threads.id", ondelete="CASCADE"), nullable=False
    )
    provider = Column(String, nullable=False)
    external_id = Column(String, nullable=True)
    direction = Column(String, nullable=False, default="inbound")
    kind = Column(String, nullable=False, default="unknown")
    body = Column(Text, nullable=True)
    state = Column(String, nullable=False, default="received")
    raw_snapshot_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class ProcessedProviderEventModel(Base):
    """Provider event idempotency marker shared by webhook and polling paths."""

    __tablename__ = "processed_provider_events"
    __table_args__ = (UniqueConstraint("provider", "external_event_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    external_event_id = Column(String, nullable=False)
    event_type = Column(String, nullable=True)
    processed_at = Column(DateTime, nullable=False, default=datetime.now)
    metadata_json = Column(Text, nullable=True)


class PresenceInboxNotificationModel(Base):
    """Idempotency marker for bridged presence messages sent to terminal inboxes."""

    __tablename__ = "presence_inbox_notifications"
    __table_args__ = (UniqueConstraint("receiver_id", "presence_message_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    receiver_id = Column(String, nullable=False)
    presence_message_id = Column(
        Integer, ForeignKey("presence_messages.id", ondelete="CASCADE"), nullable=False
    )
    inbox_message_id = Column(Integer, ForeignKey("inbox.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class AgentRuntimeNotificationModel(Base):
    """Idempotency marker for provider notifications accepted by agent runtime handles."""

    __tablename__ = "agent_runtime_notifications"
    __table_args__ = (UniqueConstraint("agent_id", "source_kind", "source_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    inbox_message_id = Column(Integer, ForeignKey("inbox.id", ondelete="CASCADE"), nullable=True)
    inbox_notification_id = Column(
        Integer, ForeignKey("inbox_notifications.id", ondelete="CASCADE"), nullable=True
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)


# Module-level singletons
DB_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
    """SQLite does not enforce foreign keys by default. Enable them
    per-connection so any FK constraints (current or future) actually
    fire. Leaving this disabled would be a silent regression the moment
    the schema grows a CASCADE relationship."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database tables and apply schema migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate_ensure_semantic_inbox_tables()
    _migrate_add_inbox_source_fields()
    _migrate_ensure_baton_tables()
    _migrate_ensure_presence_tables()
    _migrate_ensure_agent_runtime_tables()
    _migrate_add_allowed_tools()
    _migrate_drop_monitoring_session_peers()


def _migrate_ensure_semantic_inbox_tables() -> None:
    """Create semantic inbox message/notification tables on existing databases."""
    try:
        InboxMessageModel.__table__.create(bind=engine, checkfirst=True)
        InboxNotificationModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for semantic inbox tables failed: {e}")


def _migrate_add_inbox_source_fields() -> None:
    """Add source identity columns to inbox table if missing."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        conn = sqlite3.connect(str(DATABASE_FILE))
        cursor = conn.execute("PRAGMA table_info(inbox)")
        columns = {row[1] for row in cursor.fetchall()}
        if "source_kind" not in columns:
            conn.execute("ALTER TABLE inbox ADD COLUMN source_kind TEXT")
            logger.info("Migration: added source_kind column to inbox table")
        if "source_id" not in columns:
            conn.execute("ALTER TABLE inbox ADD COLUMN source_id TEXT")
            logger.info("Migration: added source_id column to inbox table")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Migration check for inbox source fields failed: {e}")


def _migrate_ensure_baton_tables() -> None:
    """Create baton tables on existing databases.

    ``Base.metadata.create_all`` covers normal startup, but keeping this
    checkfirst migration hook makes the baton schema explicit and safely
    repeatable for databases initialized before batons existed.
    """
    try:
        BatonModel.__table__.create(bind=engine, checkfirst=True)
        BatonEventModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for baton tables failed: {e}")


def _migrate_ensure_presence_tables() -> None:
    """Create provider-neutral presence tables on existing databases."""
    try:
        PresenceWorkItemModel.__table__.create(bind=engine, checkfirst=True)
        PresenceThreadModel.__table__.create(bind=engine, checkfirst=True)
        PresenceMessageModel.__table__.create(bind=engine, checkfirst=True)
        ProcessedProviderEventModel.__table__.create(bind=engine, checkfirst=True)
        PresenceInboxNotificationModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for presence tables failed: {e}")


def _migrate_ensure_agent_runtime_tables() -> None:
    """Create CAO agent runtime contract tables on existing databases."""
    try:
        AgentRuntimeNotificationModel.__table__.create(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning(f"Migration check for agent runtime tables failed: {e}")
        return

    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        conn = sqlite3.connect(str(DATABASE_FILE))
        cursor = conn.execute("PRAGMA table_info(agent_runtime_notifications)")
        column_info = {row[1]: row for row in cursor.fetchall()}
        columns = set(column_info)
        inbox_message_column = column_info.get("inbox_message_id")
        if inbox_message_column is not None and inbox_message_column[3]:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("DROP TABLE IF EXISTS agent_runtime_notifications_old")
            conn.execute(
                "ALTER TABLE agent_runtime_notifications "
                "RENAME TO agent_runtime_notifications_old"
            )
            conn.execute("""
                CREATE TABLE agent_runtime_notifications (
                    id INTEGER NOT NULL,
                    agent_id VARCHAR NOT NULL,
                    source_kind VARCHAR NOT NULL,
                    source_id VARCHAR NOT NULL,
                    inbox_message_id INTEGER,
                    inbox_notification_id INTEGER,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (agent_id, source_kind, source_id),
                    FOREIGN KEY(inbox_message_id) REFERENCES inbox (id) ON DELETE CASCADE,
                    FOREIGN KEY(inbox_notification_id)
                        REFERENCES inbox_notifications (id) ON DELETE CASCADE
                )
            """)
            notification_expr = (
                "old.inbox_notification_id" if "inbox_notification_id" in columns else "NULL"
            )
            conn.execute(f"""
                INSERT INTO agent_runtime_notifications (
                    id,
                    agent_id,
                    source_kind,
                    source_id,
                    inbox_message_id,
                    inbox_notification_id,
                    created_at
                )
                SELECT
                    old.id,
                    old.agent_id,
                    old.source_kind,
                    old.source_id,
                    old.inbox_message_id,
                    COALESCE(
                        {notification_expr},
                        (
                            SELECT inbox_notifications.id
                            FROM inbox_notifications
                            WHERE inbox_notifications.legacy_inbox_id =
                                old.inbox_message_id
                        )
                    ),
                    old.created_at
                FROM agent_runtime_notifications_old AS old
            """)
            conn.execute("DROP TABLE agent_runtime_notifications_old")
            conn.execute("PRAGMA foreign_keys=ON")
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(agent_runtime_notifications)").fetchall()
            }
            logger.info(
                "Migration: rebuilt agent_runtime_notifications with nullable inbox_message_id"
            )
        if "inbox_notification_id" not in columns:
            conn.execute(
                "ALTER TABLE agent_runtime_notifications ADD COLUMN inbox_notification_id INTEGER"
            )
            logger.info(
                "Migration: added inbox_notification_id column to agent_runtime_notifications"
            )
        conn.execute("""
            UPDATE agent_runtime_notifications
            SET inbox_notification_id = (
                SELECT inbox_notifications.id
                FROM inbox_notifications
                WHERE inbox_notifications.legacy_inbox_id =
                    agent_runtime_notifications.inbox_message_id
            )
            WHERE inbox_notification_id IS NULL
              AND inbox_message_id IS NOT NULL
            """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Migration check for agent runtime notification ids failed: {e}")


def _migrate_drop_monitoring_session_peers() -> None:
    """Drop the obsolete ``monitoring_session_peers`` table.

    Session-level peer scoping was removed in favor of query-time peer
    filtering. Existing active sessions that had peer rows simply become
    unscoped (capture all) — which is the intended behavior under the new
    model. Dropping the table keeps the schema honest.
    """
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        conn = sqlite3.connect(str(DATABASE_FILE))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_session_peers'"
        )
        if cursor.fetchone():
            conn.execute("DROP TABLE monitoring_session_peers")
            conn.commit()
            logger.info("Migration: dropped obsolete monitoring_session_peers table")
        conn.close()
    except Exception as e:
        logger.warning(f"Migration check for monitoring_session_peers failed: {e}")


def _migrate_add_allowed_tools() -> None:
    """Add allowed_tools column to terminals table if missing (schema migration)."""
    import sqlite3

    from cli_agent_orchestrator.constants import DATABASE_FILE

    try:
        conn = sqlite3.connect(str(DATABASE_FILE))
        cursor = conn.execute("PRAGMA table_info(terminals)")
        columns = {row[1] for row in cursor.fetchall()}
        if "allowed_tools" not in columns:
            conn.execute("ALTER TABLE terminals ADD COLUMN allowed_tools TEXT")
            conn.commit()
            logger.info("Migration: added allowed_tools column to terminals table")
        conn.close()
    except Exception as e:
        logger.warning(f"Migration check for allowed_tools failed: {e}")


def create_terminal(
    terminal_id: str,
    tmux_session: str,
    tmux_window: str,
    provider: str,
    agent_profile: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create terminal metadata record."""
    import json as _json

    with SessionLocal() as db:
        terminal = TerminalModel(
            id=terminal_id,
            tmux_session=tmux_session,
            tmux_window=tmux_window,
            provider=provider,
            agent_profile=agent_profile,
            allowed_tools=_json.dumps(allowed_tools) if allowed_tools else None,
        )
        db.add(terminal)
        db.commit()
        return {
            "id": terminal.id,
            "tmux_session": terminal.tmux_session,
            "tmux_window": terminal.tmux_window,
            "provider": terminal.provider,
            "agent_profile": terminal.agent_profile,
            "allowed_tools": allowed_tools,
        }


def get_terminal_metadata(terminal_id: str) -> Optional[Dict[str, Any]]:
    """Get terminal metadata by ID."""
    import json as _json

    with SessionLocal() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if not terminal:
            logger.warning(f"Terminal metadata not found for terminal_id: {terminal_id}")
            return None
        logger.debug(
            f"Retrieved terminal metadata for {terminal_id}: provider={terminal.provider}, session={terminal.tmux_session}"
        )
        allowed_tools = _json.loads(terminal.allowed_tools) if terminal.allowed_tools else None
        return {
            "id": terminal.id,
            "tmux_session": terminal.tmux_session,
            "tmux_window": terminal.tmux_window,
            "provider": terminal.provider,
            "agent_profile": terminal.agent_profile,
            "allowed_tools": allowed_tools,
            "last_active": terminal.last_active,
        }


def list_terminals_by_session(tmux_session: str) -> List[Dict[str, Any]]:
    """List all terminals in a tmux session."""
    with SessionLocal() as db:
        terminals = db.query(TerminalModel).filter(TerminalModel.tmux_session == tmux_session).all()
        return [
            {
                "id": t.id,
                "tmux_session": t.tmux_session,
                "tmux_window": t.tmux_window,
                "provider": t.provider,
                "agent_profile": t.agent_profile,
                "last_active": t.last_active,
            }
            for t in terminals
        ]


def update_last_active(terminal_id: str) -> bool:
    """Update last active timestamp."""
    with SessionLocal() as db:
        terminal = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).first()
        if terminal:
            terminal.last_active = datetime.now()
            db.commit()
            return True
        return False


def list_all_terminals() -> List[Dict[str, Any]]:
    """List all terminals."""
    with SessionLocal() as db:
        terminals = db.query(TerminalModel).all()
        return [
            {
                "id": t.id,
                "tmux_session": t.tmux_session,
                "tmux_window": t.tmux_window,
                "provider": t.provider,
                "agent_profile": t.agent_profile,
                "last_active": t.last_active,
            }
            for t in terminals
        ]


def delete_terminal(terminal_id: str) -> bool:
    """Delete terminal metadata."""
    with SessionLocal() as db:
        deleted = db.query(TerminalModel).filter(TerminalModel.id == terminal_id).delete()
        db.commit()
        return deleted > 0


def delete_terminals_by_session(tmux_session: str) -> int:
    """Delete all terminals in a session."""
    with SessionLocal() as db:
        deleted = (
            db.query(TerminalModel).filter(TerminalModel.tmux_session == tmux_session).delete()
        )
        db.commit()
        return deleted


def _validate_complete_identity(
    kind: Optional[str], identity_id: Optional[str], label: str
) -> None:
    if (kind is None) != (identity_id is None):
        raise ValueError(f"{label}_kind and {label}_id must be provided together")


def _resolve_source_identity(
    sender_id: str, source_kind: Optional[str], source_id: Optional[str]
) -> Tuple[str, str]:
    _validate_complete_identity(source_kind, source_id, "source")
    if source_kind is None and source_id is None:
        return "terminal", sender_id
    assert source_kind is not None and source_id is not None
    return source_kind, source_id


def _serialize_origin(origin: Optional[Dict[str, Any]]) -> Optional[str]:
    if origin is None:
        return None
    return json.dumps(origin, sort_keys=True)


def _deserialize_origin(origin_json: Optional[str]) -> Optional[Dict[str, Any]]:
    if origin_json is None:
        return None
    value = json.loads(origin_json)
    return value if isinstance(value, dict) else None


def inbox_message_from_model(row: InboxModel) -> InboxMessage:
    """Convert an inbox database row to its typed domain model."""
    return InboxMessage(
        id=row.id,
        sender_id=row.sender_id,
        receiver_id=row.receiver_id,
        message=row.message,
        source_kind=row.source_kind,
        source_id=row.source_id,
        status=MessageStatus(row.status),
        created_at=row.created_at,
    )


def inbox_message_record_from_model(row: InboxMessageModel) -> InboxMessageRecord:
    """Convert a durable inbox message row to its domain model."""
    return InboxMessageRecord(
        id=row.id,
        sender_id=row.sender_id,
        body=row.body,
        source_kind=row.source_kind,
        source_id=row.source_id,
        origin=_deserialize_origin(row.origin_json),
        route_kind=row.route_kind,
        route_id=row.route_id,
        created_at=row.created_at,
    )


def inbox_notification_from_model(row: InboxNotificationModel) -> InboxNotification:
    """Convert an inbox notification row to its domain model."""
    return InboxNotification(
        id=row.id,
        message_id=row.message_id,
        receiver_id=row.receiver_id,
        status=MessageStatus(row.status),
        created_at=row.created_at,
        delivered_at=row.delivered_at,
        failed_at=row.failed_at,
        error_detail=row.error_detail,
        legacy_inbox_id=row.legacy_inbox_id,
    )


def inbox_delivery_from_models(
    message_row: InboxMessageModel, notification_row: InboxNotificationModel
) -> InboxDelivery:
    """Convert joined semantic inbox rows to their domain model."""
    return InboxDelivery(
        message=inbox_message_record_from_model(message_row),
        notification=inbox_notification_from_model(notification_row),
    )


def inbox_delivery_to_compat_message(
    delivery: InboxDelivery,
    *,
    compatibility_id: Optional[int] = None,
    legacy_row: Optional[InboxModel] = None,
) -> InboxMessage:
    """Render semantic message + notification as the legacy InboxMessage shape."""
    notification = delivery.notification
    message = delivery.message
    receiver_id = legacy_row.receiver_id if legacy_row is not None else notification.receiver_id
    created_at = legacy_row.created_at if legacy_row is not None else notification.created_at
    return InboxMessage(
        id=compatibility_id if compatibility_id is not None else notification.id,
        sender_id=message.sender_id,
        receiver_id=receiver_id,
        message=message.body,
        source_kind=message.source_kind,
        source_id=message.source_id,
        status=notification.status,
        created_at=created_at,
    )


def create_inbox_delivery(
    sender_id: str,
    receiver_id: str,
    message: str,
    *,
    source_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    origin: Optional[Dict[str, Any]] = None,
    route_kind: Optional[str] = None,
    route_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> InboxDelivery:
    """Create one durable inbox message and one delivery notification.

    New callers should use the returned notification id for delivery-state
    operations. Compatibility wrappers below keep old ``InboxMessage`` callers
    working without making the old table the authoritative message store.
    """
    effective_source_kind, effective_source_id = _resolve_source_identity(
        sender_id, source_kind, source_id
    )
    _validate_complete_identity(route_kind, route_id, "route")

    def _add_delivery(session: Session) -> InboxDelivery:
        message_row = InboxMessageModel(
            sender_id=sender_id,
            body=message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
            origin_json=_serialize_origin(origin),
            route_kind=route_kind,
            route_id=route_id,
        )
        session.add(message_row)
        session.flush()
        notification_row = InboxNotificationModel(
            message_id=message_row.id,
            receiver_id=receiver_id,
            status=MessageStatus.PENDING.value,
        )
        session.add(notification_row)
        session.flush()
        session.refresh(message_row)
        session.refresh(notification_row)
        return inbox_delivery_from_models(message_row, notification_row)

    if db is not None:
        return _add_delivery(db)

    with SessionLocal() as session:
        delivery = _add_delivery(session)
        session.commit()
        return delivery


def create_inbox_message_record(
    sender_id: str,
    message: str,
    *,
    source_kind: Optional[str] = None,
    source_id: Optional[str] = None,
    origin: Optional[Dict[str, Any]] = None,
    route_kind: Optional[str] = None,
    route_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> InboxMessageRecord:
    """Create a durable inbox message without creating delivery state."""
    effective_source_kind, effective_source_id = _resolve_source_identity(
        sender_id, source_kind, source_id
    )
    _validate_complete_identity(route_kind, route_id, "route")

    def _add_message(session: Session) -> InboxMessageRecord:
        message_row = InboxMessageModel(
            sender_id=sender_id,
            body=message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
            origin_json=_serialize_origin(origin),
            route_kind=route_kind,
            route_id=route_id,
        )
        session.add(message_row)
        session.flush()
        session.refresh(message_row)
        return inbox_message_record_from_model(message_row)

    if db is not None:
        return _add_message(db)

    with SessionLocal() as session:
        record = _add_message(session)
        session.commit()
        return record


def create_inbox_notification(
    message_id: int,
    receiver_id: str,
    *,
    status: MessageStatus = MessageStatus.PENDING,
    db: Optional[Session] = None,
) -> InboxNotification:
    """Create delivery state for an existing durable inbox message."""

    def _add_notification(session: Session) -> InboxNotification:
        if session.get(InboxMessageModel, message_id) is None:
            raise ValueError(f"Inbox message not found: {message_id}")
        notification_row = InboxNotificationModel(
            message_id=message_id,
            receiver_id=receiver_id,
            status=status.value,
        )
        session.add(notification_row)
        session.flush()
        session.refresh(notification_row)
        return inbox_notification_from_model(notification_row)

    if db is not None:
        return _add_notification(db)

    with SessionLocal() as session:
        notification = _add_notification(session)
        session.commit()
        return notification


def _get_delivery_by_notification_id(
    session: Session, notification_id: int
) -> Optional[InboxDelivery]:
    row = (
        session.query(InboxNotificationModel, InboxMessageModel)
        .join(InboxMessageModel, InboxNotificationModel.message_id == InboxMessageModel.id)
        .filter(InboxNotificationModel.id == notification_id)
        .first()
    )
    if row is None:
        return None
    notification_row, message_row = row
    return inbox_delivery_from_models(message_row, notification_row)


def get_inbox_delivery(
    notification_id: int, *, db: Optional[Session] = None
) -> Optional[InboxDelivery]:
    """Read one notification-backed inbox message by notification id."""
    if db is not None:
        return _get_delivery_by_notification_id(db, notification_id)
    with SessionLocal() as session:
        return _get_delivery_by_notification_id(session, notification_id)


def get_inbox_delivery_for_legacy_message(
    legacy_inbox_id: int, *, db: Optional[Session] = None
) -> Optional[InboxDelivery]:
    """Read semantic delivery state mapped to a legacy-readable inbox id."""

    def _read(session: Session) -> Optional[InboxDelivery]:
        row = (
            session.query(InboxNotificationModel, InboxMessageModel)
            .join(InboxMessageModel, InboxNotificationModel.message_id == InboxMessageModel.id)
            .filter(InboxNotificationModel.legacy_inbox_id == legacy_inbox_id)
            .first()
        )
        if row is None:
            return None
        notification_row, message_row = row
        return inbox_delivery_from_models(message_row, notification_row)

    if db is not None:
        return _read(db)
    with SessionLocal() as session:
        return _read(session)


def list_pending_inbox_notifications(receiver_id: str, limit: int = 10) -> List[InboxDelivery]:
    """List pending notification-backed messages for a receiver."""
    with SessionLocal() as db:
        rows = (
            db.query(InboxNotificationModel, InboxMessageModel)
            .join(InboxMessageModel, InboxNotificationModel.message_id == InboxMessageModel.id)
            .filter(
                InboxNotificationModel.receiver_id == receiver_id,
                InboxNotificationModel.status == MessageStatus.PENDING.value,
            )
            .order_by(InboxNotificationModel.created_at.asc(), InboxNotificationModel.id.asc())
            .limit(limit)
            .all()
        )
        return [
            inbox_delivery_from_models(message_row, notification_row)
            for notification_row, message_row in rows
        ]


def get_oldest_pending_inbox_delivery(receiver_id: str) -> Optional[InboxDelivery]:
    """Get the oldest pending semantic delivery notification for a receiver."""
    deliveries = list_pending_inbox_notifications(receiver_id, limit=1)
    return deliveries[0] if deliveries else None


def list_pending_inbox_deliveries_for_effective_source(
    receiver_id: str, source_delivery: InboxDelivery
) -> List[InboxDelivery]:
    """List pending deliveries for the same durable source as ``source_delivery``."""
    source_message = source_delivery.message
    with SessionLocal() as db:
        rows = (
            db.query(InboxNotificationModel, InboxMessageModel)
            .join(InboxMessageModel, InboxNotificationModel.message_id == InboxMessageModel.id)
            .filter(
                InboxNotificationModel.receiver_id == receiver_id,
                InboxNotificationModel.status == MessageStatus.PENDING.value,
                InboxMessageModel.source_kind == source_message.source_kind,
                InboxMessageModel.source_id == source_message.source_id,
            )
            .order_by(InboxNotificationModel.created_at.asc(), InboxNotificationModel.id.asc())
            .all()
        )
        return [
            inbox_delivery_from_models(message_row, notification_row)
            for notification_row, message_row in rows
        ]


def move_pending_inbox_notifications(
    current_receiver_id: str,
    new_receiver_id: str,
) -> int:
    """Move pending semantic delivery notifications to a new receiver id."""
    with SessionLocal() as db:
        updated = (
            db.query(InboxNotificationModel)
            .filter(
                InboxNotificationModel.receiver_id == current_receiver_id,
                InboxNotificationModel.status == MessageStatus.PENDING.value,
            )
            .update(
                {InboxNotificationModel.receiver_id: new_receiver_id},
                synchronize_session=False,
            )
        )
        db.commit()
        return int(updated or 0)


def update_inbox_notification_receiver(notification_id: int, receiver_id: str) -> bool:
    """Update one semantic notification recipient."""
    with SessionLocal() as db:
        row = db.get(InboxNotificationModel, notification_id)
        if row is None:
            return False
        row.receiver_id = receiver_id
        db.commit()
        return True


def _apply_notification_status(
    notification: InboxNotificationModel, status: MessageStatus, error_detail: Optional[str]
) -> None:
    notification.status = status.value
    if status == MessageStatus.DELIVERED:
        notification.delivered_at = datetime.now()
        notification.failed_at = None
        notification.error_detail = None
    elif status == MessageStatus.FAILED:
        notification.failed_at = datetime.now()
        notification.error_detail = error_detail
    else:
        notification.delivered_at = None
        notification.failed_at = None
        notification.error_detail = None


def update_inbox_notification_statuses(
    notification_ids: Sequence[int],
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> int:
    """Update delivery state for semantic inbox notifications."""
    if not notification_ids:
        return 0

    with SessionLocal() as db:
        rows = (
            db.query(InboxNotificationModel)
            .filter(InboxNotificationModel.id.in_(list(notification_ids)))
            .all()
        )
        for row in rows:
            _apply_notification_status(row, status, error_detail)
        db.commit()
        return len(rows)


def update_inbox_notification_status(
    notification_id: int,
    status: MessageStatus,
    *,
    error_detail: Optional[str] = None,
) -> bool:
    """Update one semantic inbox notification by notification id."""
    return (
        update_inbox_notification_statuses([notification_id], status, error_detail=error_detail) > 0
    )


def create_inbox_message(
    sender_id: str,
    receiver_id: str,
    message: str,
    db: Optional[Session] = None,
    source_kind: Optional[str] = None,
    source_id: Optional[str] = None,
) -> InboxMessage:
    """Create an inbox message through the legacy-compatible wrapper.

    When ``db`` is supplied, the message participates in the caller's
    transaction and is only flushed. Callers that omit ``db`` retain the
    historical self-contained commit behavior.
    """
    effective_source_kind, effective_source_id = _resolve_source_identity(
        sender_id, source_kind, source_id
    )

    def _add_message(session: Session) -> InboxMessage:
        message_row = InboxMessageModel(
            sender_id=sender_id,
            body=message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
        )
        session.add(message_row)
        session.flush()

        legacy_row = InboxModel(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message,
            source_kind=effective_source_kind,
            source_id=effective_source_id,
            status=MessageStatus.PENDING.value,
        )
        session.add(legacy_row)
        session.flush()

        notification_row = InboxNotificationModel(
            message_id=message_row.id,
            receiver_id=receiver_id,
            status=MessageStatus.PENDING.value,
            legacy_inbox_id=legacy_row.id,
        )
        session.add(notification_row)
        session.flush()
        session.refresh(message_row)
        session.refresh(notification_row)
        session.refresh(legacy_row)
        delivery = inbox_delivery_from_models(message_row, notification_row)
        return inbox_delivery_to_compat_message(
            delivery, compatibility_id=legacy_row.id, legacy_row=legacy_row
        )

    if db is not None:
        return _add_message(db)

    with SessionLocal() as session:
        inbox_message = _add_message(session)
        session.commit()
        return inbox_message


def get_inbox_message(message_id: int) -> Optional[InboxMessage]:
    """Get one inbox message through the compatibility read path."""
    with SessionLocal() as db:
        mapped_delivery = (
            db.query(InboxNotificationModel, InboxMessageModel, InboxModel)
            .join(InboxMessageModel, InboxNotificationModel.message_id == InboxMessageModel.id)
            .join(InboxModel, InboxNotificationModel.legacy_inbox_id == InboxModel.id)
            .filter(InboxNotificationModel.legacy_inbox_id == message_id)
            .first()
        )
        if mapped_delivery is not None:
            notification_row, message_row, legacy_row = mapped_delivery
            return inbox_delivery_to_compat_message(
                inbox_delivery_from_models(message_row, notification_row),
                compatibility_id=message_id,
                legacy_row=legacy_row,
            )

        legacy_row = db.query(InboxModel).filter(InboxModel.id == message_id).first()
        if legacy_row is not None:
            return inbox_message_from_model(legacy_row)
        return None


def get_pending_messages(receiver_id: str, limit: int = 1) -> List[InboxMessage]:
    """Get pending messages ordered by created_at ASC (oldest first)."""
    return get_inbox_messages(receiver_id, limit=limit, status=MessageStatus.PENDING)


def get_inbox_messages(
    receiver_id: str, limit: int = 10, status: Optional[MessageStatus] = None
) -> List[InboxMessage]:
    """Get inbox messages with optional status filter ordered by created_at ASC (oldest first).

    Args:
        receiver_id: Terminal ID to get messages for
        limit: Maximum number of messages to return (default: 10)
        status: Optional filter by message status (None = all statuses)

    Returns:
        List of inbox messages ordered by creation time (oldest first)
    """
    return _get_inbox_messages(receiver_id, limit=limit, status=status)


def _get_inbox_messages(
    receiver_id: str, *, limit: Optional[int], status: Optional[MessageStatus] = None
) -> List[InboxMessage]:
    with SessionLocal() as db:
        notification_query = (
            db.query(InboxNotificationModel, InboxMessageModel, InboxModel)
            .join(InboxMessageModel, InboxNotificationModel.message_id == InboxMessageModel.id)
            .join(InboxModel, InboxNotificationModel.legacy_inbox_id == InboxModel.id)
            .filter(InboxModel.receiver_id == receiver_id)
        )
        notification_rows = notification_query.all()

        mapped_legacy_ids = {
            notification_row.legacy_inbox_id
            for notification_row, _message_row, _legacy_row in notification_rows
            if notification_row.legacy_inbox_id is not None
        }
        messages = []
        for notification_row, message_row, legacy_row in notification_rows:
            compat_message = inbox_delivery_to_compat_message(
                inbox_delivery_from_models(message_row, notification_row),
                compatibility_id=notification_row.legacy_inbox_id,
                legacy_row=legacy_row,
            )
            if status is None or compat_message.status == status:
                messages.append(compat_message)

        legacy_query = db.query(InboxModel).filter(InboxModel.receiver_id == receiver_id)
        if status is not None:
            legacy_query = legacy_query.filter(InboxModel.status == status.value)
        legacy_rows = legacy_query.all()
        messages.extend(
            inbox_message_from_model(row) for row in legacy_rows if row.id not in mapped_legacy_ids
        )

        messages.sort(key=lambda item: (item.created_at, item.id))
        if limit is not None:
            return messages[:limit]
        return messages


def get_oldest_pending_message(receiver_id: str) -> Optional[InboxMessage]:
    """Get the oldest pending inbox message for a receiver."""
    rows = get_inbox_messages(receiver_id, limit=1, status=MessageStatus.PENDING)
    return rows[0] if rows else None


def get_effective_message_source(message: InboxMessage) -> EffectiveMessageSource:
    """Return the batching source for a message.

    Rows without a complete explicit source are treated as a unique per-message
    source so legacy messages remain deliverable without unexpected grouping.
    """
    if message.source_kind is not None and message.source_id is not None:
        return EffectiveMessageSource(message.source_kind, message.source_id)
    return EffectiveMessageSource("legacy_message", str(message.id), is_legacy_message=True)


def get_pending_messages_for_effective_source(
    receiver_id: str, source_message: InboxMessage
) -> List[InboxMessage]:
    """Get pending messages for the receiver and source selected by ``source_message``."""
    source = get_effective_message_source(source_message)
    pending_messages = _get_inbox_messages(receiver_id, limit=None, status=MessageStatus.PENDING)
    if source.is_legacy_message:
        return [message for message in pending_messages if message.id == int(source.id)]
    return [
        message
        for message in pending_messages
        if message.source_kind == source.kind and message.source_id == source.id
    ]


def update_message_statuses(message_ids: List[int], status: MessageStatus) -> int:
    """Update selected delivery statuses through the compatibility path."""
    if not message_ids:
        return 0

    with SessionLocal() as db:
        unique_ids = list(dict.fromkeys(message_ids))
        updated_requested_ids = set()
        updated_legacy_ids = set()

        mapped_notifications = (
            db.query(InboxNotificationModel)
            .filter(InboxNotificationModel.legacy_inbox_id.in_(unique_ids))
            .all()
        )
        for notification in mapped_notifications:
            _apply_notification_status(notification, status, None)
            if notification.legacy_inbox_id is not None:
                updated_legacy_ids.add(notification.legacy_inbox_id)
                updated_requested_ids.add(notification.legacy_inbox_id)
                legacy_row = db.get(InboxModel, notification.legacy_inbox_id)
                if legacy_row is not None:
                    legacy_row.status = status.value

        remaining_ids = [
            message_id for message_id in unique_ids if message_id not in updated_legacy_ids
        ]

        legacy_rows = db.query(InboxModel).filter(InboxModel.id.in_(remaining_ids)).all()
        for legacy_row in legacy_rows:
            legacy_row.status = status.value
            updated_legacy_ids.add(legacy_row.id)
            updated_requested_ids.add(legacy_row.id)

        db.commit()
        return len(updated_requested_ids)


def update_message_status(message_id: int, status: MessageStatus) -> bool:
    """Update message status to MessageStatus.DELIVERED or MessageStatus.FAILED."""
    return update_message_statuses([message_id], status) > 0


# Baton database functions


def baton_from_model(row: BatonModel) -> Baton:
    """Convert a SQLAlchemy baton row to its typed domain model."""
    return Baton(
        id=row.id,
        title=row.title,
        status=BatonStatus(row.status),
        originator_id=row.originator_id,
        current_holder_id=row.current_holder_id,
        return_stack=json.loads(row.return_stack_json or "[]"),
        expected_next_action=row.expected_next_action,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_nudged_at=row.last_nudged_at,
        completed_at=row.completed_at,
    )


def baton_event_from_model(row: BatonEventModel) -> BatonEvent:
    """Convert a SQLAlchemy baton event row to its typed domain model."""
    return BatonEvent(
        id=row.id,
        baton_id=row.baton_id,
        event_type=BatonEventType(row.event_type),
        actor_id=row.actor_id,
        from_holder_id=row.from_holder_id,
        to_holder_id=row.to_holder_id,
        message=row.message,
        created_at=row.created_at,
    )


def get_baton_record(baton_id: str) -> Optional[Baton]:
    """Get a baton by ID."""
    with SessionLocal() as db:
        row = db.query(BatonModel).filter(BatonModel.id == baton_id).first()
        if row is None:
            return None
        return baton_from_model(row)


def list_batons(
    *,
    status: Optional[BatonStatus] = None,
    holder_id: Optional[str] = None,
    originator_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Baton]:
    """List batons with operator-facing filters, newest update first."""
    with SessionLocal() as db:
        query = db.query(BatonModel)
        if status is not None:
            query = query.filter(BatonModel.status == status.value)
        if holder_id is not None:
            query = query.filter(BatonModel.current_holder_id == holder_id)
        if originator_id is not None:
            query = query.filter(BatonModel.originator_id == originator_id)

        rows = (
            query.order_by(BatonModel.updated_at.desc(), BatonModel.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [baton_from_model(row) for row in rows]


def list_batons_held_by(holder_id: str, status: Optional[BatonStatus] = None) -> List[Baton]:
    """List batons currently held by ``holder_id``, newest update first."""
    with SessionLocal() as db:
        query = db.query(BatonModel).filter(BatonModel.current_holder_id == holder_id)
        if status is not None:
            query = query.filter(BatonModel.status == status.value)
        rows = query.order_by(BatonModel.updated_at.desc(), BatonModel.created_at.desc()).all()
        return [baton_from_model(row) for row in rows]


def list_baton_events(baton_id: str) -> List[BatonEvent]:
    """List baton audit events ordered oldest first."""
    with SessionLocal() as db:
        rows = (
            db.query(BatonEventModel)
            .filter(BatonEventModel.baton_id == baton_id)
            .order_by(BatonEventModel.created_at.asc(), BatonEventModel.id.asc())
            .all()
        )
        return [baton_event_from_model(row) for row in rows]


# Flow database functions


def create_flow(
    name: str,
    file_path: str,
    schedule: str,
    agent_profile: str,
    provider: str,
    script: str,
    next_run: datetime,
) -> Flow:
    """Create flow record."""
    with SessionLocal() as db:
        flow = FlowModel(
            name=name,
            file_path=file_path,
            schedule=schedule,
            agent_profile=agent_profile,
            provider=provider,
            script=script,
            next_run=next_run,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        return Flow(
            name=flow.name,
            file_path=flow.file_path,
            schedule=flow.schedule,
            agent_profile=flow.agent_profile,
            provider=flow.provider,
            script=flow.script,
            last_run=flow.last_run,
            next_run=flow.next_run,
            enabled=flow.enabled,
        )


def get_flow(name: str) -> Optional[Flow]:
    """Get flow by name."""
    with SessionLocal() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if not flow:
            return None
        return Flow(
            name=flow.name,
            file_path=flow.file_path,
            schedule=flow.schedule,
            agent_profile=flow.agent_profile,
            provider=flow.provider,
            script=flow.script,
            last_run=flow.last_run,
            next_run=flow.next_run,
            enabled=flow.enabled,
        )


def list_flows() -> List[Flow]:
    """List all flows."""
    with SessionLocal() as db:
        flows = db.query(FlowModel).order_by(FlowModel.next_run).all()
        return [
            Flow(
                name=f.name,
                file_path=f.file_path,
                schedule=f.schedule,
                agent_profile=f.agent_profile,
                provider=f.provider,
                script=f.script,
                last_run=f.last_run,
                next_run=f.next_run,
                enabled=f.enabled,
            )
            for f in flows
        ]


def update_flow_run_times(name: str, last_run: datetime, next_run: datetime) -> bool:
    """Update flow run times after execution."""
    with SessionLocal() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if flow:
            flow.last_run = last_run
            flow.next_run = next_run
            db.commit()
            return True
        return False


def update_flow_enabled(name: str, enabled: bool, next_run: Optional[datetime] = None) -> bool:
    """Update flow enabled status and optionally next_run."""
    with SessionLocal() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if flow:
            flow.enabled = enabled
            if next_run is not None:
                flow.next_run = next_run
            db.commit()
            return True
        return False


def delete_flow(name: str) -> bool:
    """Delete flow."""
    with SessionLocal() as db:
        deleted = db.query(FlowModel).filter(FlowModel.name == name).delete()
        db.commit()
        return deleted > 0


def get_flows_to_run() -> List[Flow]:
    """Get enabled flows where next_run <= now."""
    with SessionLocal() as db:
        now = datetime.now()
        flows = (
            db.query(FlowModel).filter(FlowModel.enabled == True, FlowModel.next_run <= now).all()
        )
        return [
            Flow(
                name=f.name,
                file_path=f.file_path,
                schedule=f.schedule,
                agent_profile=f.agent_profile,
                provider=f.provider,
                script=f.script,
                last_run=f.last_run,
                next_run=f.next_run,
                enabled=f.enabled,
            )
            for f in flows
        ]
