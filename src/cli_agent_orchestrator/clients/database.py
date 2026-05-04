"""Minimal database client with terminal, inbox, monitoring, flow, and baton metadata."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, declarative_base, sessionmaker

from cli_agent_orchestrator.constants import DATABASE_URL, DB_DIR, DEFAULT_PROVIDER
from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonEventType, BatonStatus
from cli_agent_orchestrator.models.flow import Flow
from cli_agent_orchestrator.models.inbox import InboxMessage, MessageStatus

logger = logging.getLogger(__name__)

Base: Any = declarative_base()


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
    """SQLAlchemy model for inbox messages."""

    __tablename__ = "inbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String, nullable=False)
    receiver_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    status = Column(String, nullable=False)  # MessageStatus enum value
    created_at = Column(DateTime, default=datetime.now)


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
    _migrate_ensure_baton_tables()
    _migrate_add_allowed_tools()
    _migrate_drop_monitoring_session_peers()


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


def create_inbox_message(
    sender_id: str, receiver_id: str, message: str, db: Optional[Session] = None
) -> InboxMessage:
    """Create inbox message with status=MessageStatus.PENDING.

    When ``db`` is supplied, the message participates in the caller's
    transaction and is only flushed. Callers that omit ``db`` retain the
    historical self-contained commit behavior.
    """

    def _add_message(session: Session) -> InboxMessage:
        inbox_msg = InboxModel(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message,
            status=MessageStatus.PENDING.value,
        )
        session.add(inbox_msg)
        session.flush()
        session.refresh(inbox_msg)
        return InboxMessage(
            id=inbox_msg.id,
            sender_id=inbox_msg.sender_id,
            receiver_id=inbox_msg.receiver_id,
            message=inbox_msg.message,
            status=MessageStatus(inbox_msg.status),
            created_at=inbox_msg.created_at,
        )

    if db is not None:
        return _add_message(db)

    with SessionLocal() as session:
        inbox_message = _add_message(session)
        session.commit()
        return inbox_message


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
    with SessionLocal() as db:
        query = db.query(InboxModel).filter(InboxModel.receiver_id == receiver_id)

        if status is not None:
            query = query.filter(InboxModel.status == status.value)

        messages = query.order_by(InboxModel.created_at.asc()).limit(limit).all()

        return [
            InboxMessage(
                id=msg.id,
                sender_id=msg.sender_id,
                receiver_id=msg.receiver_id,
                message=msg.message,
                status=MessageStatus(msg.status),
                created_at=msg.created_at,
            )
            for msg in messages
        ]


def update_message_status(message_id: int, status: MessageStatus) -> bool:
    """Update message status to MessageStatus.DELIVERED or MessageStatus.FAILED."""
    with SessionLocal() as db:
        message = db.query(InboxModel).filter(InboxModel.id == message_id).first()
        if message:
            message.status = status.value
            db.commit()
            return True
        return False


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
