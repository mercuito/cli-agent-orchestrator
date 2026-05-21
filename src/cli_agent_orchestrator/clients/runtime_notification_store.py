"""Monitoring/runtime notification persistence models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from cli_agent_orchestrator.clients.database_core import Base


class MonitoringSessionModel(Base):
    """A monitoring session is a recording window over agent inbox activity."""

    __tablename__ = "monitoring_sessions"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False)
    label = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class AgentRuntimeNotificationModel(Base):
    """Idempotency marker for notifications accepted by agent runtime handles."""

    __tablename__ = "agent_runtime_notifications"
    __table_args__ = (UniqueConstraint("agent_id", "idempotency_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    inbox_notification_id = Column(
        Integer, ForeignKey("inbox_notifications.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now)
