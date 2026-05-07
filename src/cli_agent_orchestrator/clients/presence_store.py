"""Provider presence persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from cli_agent_orchestrator.clients.database_core import Base


class MonitoringSessionModel(Base):
    """A monitoring session is a recording window over terminal inbox activity."""

    __tablename__ = "monitoring_sessions"

    id = Column(String, primary_key=True)
    terminal_id = Column(String, nullable=False)
    label = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)


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
    inbox_notification_id = Column(
        Integer, ForeignKey("inbox_notifications.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class AgentRuntimeNotificationModel(Base):
    """Idempotency marker for provider notifications accepted by agent runtime handles."""

    __tablename__ = "agent_runtime_notifications"
    __table_args__ = (UniqueConstraint("agent_id", "source_kind", "source_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    inbox_notification_id = Column(
        Integer, ForeignKey("inbox_notifications.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)
