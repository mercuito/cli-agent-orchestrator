"""Inbox message and notification models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MessageStatus(str, Enum):
    """Message status enumeration."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class InboxMessageRecord(BaseModel):
    """Durable communicated inbox message."""

    id: int = Field(..., description="Durable message ID")
    sender_id: str = Field(..., description="Sender/source identity")
    body: str = Field(..., description="Agent-visible message body")
    source_kind: str = Field(..., description="Provider-neutral source kind")
    source_id: str = Field(..., description="Provider-neutral source ID")
    origin: Optional[Dict[str, Any]] = Field(
        None, description="Provider-owned origin/breadcrumb metadata"
    )
    route_kind: Optional[str] = Field(
        None, description="Optional CAO quick-reply route kind, not provider-native ownership"
    )
    route_id: Optional[str] = Field(
        None, description="Optional CAO quick-reply route ID, not provider-native ownership"
    )
    created_at: datetime = Field(..., description="Creation timestamp")


class InboxNotification(BaseModel):
    """Per-recipient attention notification.

    Notifications own the agent-visible display body and may optionally point
    at a durable inbox message for read/reply flows.
    """

    id: int = Field(..., description="Notification ID")
    message_id: Optional[int] = Field(None, description="Optional durable message ID")
    receiver_id: str = Field(..., description="Recipient identity")
    body: str = Field(..., description="Agent-visible notification body")
    source_kind: str = Field(..., description="Provider-neutral notification source kind")
    source_id: str = Field(..., description="Provider-neutral notification source ID")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Provider/system-owned notification metadata"
    )
    status: MessageStatus = Field(..., description="Delivery status")
    created_at: datetime = Field(..., description="Creation timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    failed_at: Optional[datetime] = Field(None, description="Failure timestamp")
    error_detail: Optional[str] = Field(None, description="Delivery failure detail")


class InboxDelivery(BaseModel):
    """Notification with its optional durable message ready for delivery or display."""

    message: Optional[InboxMessageRecord]
    notification: InboxNotification
