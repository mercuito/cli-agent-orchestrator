"""Inbox notification models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageStatus(str, Enum):
    """Message status enumeration."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class InboxNotification(BaseModel):
    """Per-recipient agent-to-agent notification."""

    id: int = Field(..., description="Notification ID")
    sender_agent_id: str = Field(..., description="Sender agent ID")
    receiver_agent_id: str = Field(..., description="Recipient agent ID")
    body: str = Field(..., description="Agent-visible notification body")
    status: MessageStatus = Field(..., description="Delivery status")
    created_at: datetime = Field(..., description="Creation timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    failed_at: Optional[datetime] = Field(None, description="Failure timestamp")
    error_detail: Optional[str] = Field(None, description="Delivery failure detail")
