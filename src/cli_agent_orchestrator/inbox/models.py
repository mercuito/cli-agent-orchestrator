"""Public inbox models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from cli_agent_orchestrator.models.inbox import MessageStatus


class Notification(BaseModel):
    """Agent-to-agent inbox notification."""

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
    """Result of reading an inbox notification."""

    notification: Notification
    body: str
