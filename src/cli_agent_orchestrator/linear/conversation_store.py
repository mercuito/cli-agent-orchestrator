"""Linear-owned conversation/work-item persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from cli_agent_orchestrator.clients.database_core import Base


class ProviderWorkItemModel(Base):
    """Work item reference cached from Linear."""

    __tablename__ = "provider_work_items"
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


class ProviderConversationThreadModel(Base):
    """Conversation surface cached from Linear."""

    __tablename__ = "provider_conversation_threads"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    external_url = Column(String, nullable=True)
    work_item_id = Column(
        Integer, ForeignKey("provider_work_items.id", ondelete="SET NULL"), nullable=True
    )
    kind = Column(String, nullable=False, default="conversation")
    state = Column(String, nullable=False, default="active")
    prompt_context = Column(Text, nullable=True)
    raw_snapshot_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)


class ProviderConversationMessageModel(Base):
    """Message or activity inside a cached Linear conversation surface."""

    __tablename__ = "provider_conversation_messages"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(
        Integer, ForeignKey("provider_conversation_threads.id", ondelete="CASCADE"), nullable=False
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
    """Linear event idempotency marker shared by webhook and polling paths."""

    __tablename__ = "processed_provider_events"
    __table_args__ = (UniqueConstraint("provider", "external_event_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    external_event_id = Column(String, nullable=False)
    event_type = Column(String, nullable=True)
    processed_at = Column(DateTime, nullable=False, default=datetime.now)
    metadata_json = Column(Text, nullable=True)
