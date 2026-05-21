"""Public inbox models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from cli_agent_orchestrator.models.inbox import MessageStatus


class PlainSource(BaseModel):
    """Agent-authored inbox source."""

    sender_agent_id: str = Field(..., description="Durable CAO agent that sent the message")

    def __init__(self, sender_agent_id: str | None = None, **data: Any) -> None:
        if sender_agent_id is not None:
            data["sender_agent_id"] = sender_agent_id
        super().__init__(**data)


class ProviderSource(BaseModel):
    """Provider-owned inbox source used by migrated provider paths."""

    source_kind: str = Field(..., description="Provider-neutral source kind")
    source_id: str = Field(..., description="Provider-neutral source ID")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Provider/system-owned notification metadata"
    )


class Notification(BaseModel):
    """Source-agnostic inbox notification."""

    id: int
    receiver_agent_id: str
    body: str
    source_kind: str
    source_id: str
    metadata: Optional[Dict[str, Any]] = None
    status: MessageStatus
    created_at: datetime
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    error_detail: Optional[str] = None


class ReadResult(BaseModel):
    """Result of reading an inbox notification."""

    notification: Notification
    body: str
    replyable: bool = False


class Reply(BaseModel):
    """Reply recorded through an inbox source route."""

    notification_id: int
    body: str
    created_at: datetime
