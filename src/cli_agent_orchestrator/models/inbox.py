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


class InboxMessage(BaseModel):
    """Legacy-compatible inbox message view.

    During the inbox split, ``id`` is the compatibility delivery identifier
    exposed to older callers. New owner surfaces use ``InboxNotification.id``
    directly when an operation is about delivery state.
    """

    id: int = Field(..., description="Message ID")
    sender_id: str = Field(..., description="Sender terminal ID")
    receiver_id: str = Field(..., description="Receiver terminal ID")
    message: str = Field(..., description="Message content")
    source_kind: Optional[str] = Field(None, description="Provider-neutral source kind")
    source_id: Optional[str] = Field(None, description="Provider-neutral source ID")
    status: MessageStatus = Field(..., description="Message status")
    created_at: datetime = Field(..., description="Creation timestamp")


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
    route_kind: Optional[str] = Field(None, description="Hidden reply route kind")
    route_id: Optional[str] = Field(None, description="Hidden reply route ID")
    created_at: datetime = Field(..., description="Creation timestamp")


class InboxNotification(BaseModel):
    """Per-recipient delivery notification for one inbox message."""

    id: int = Field(..., description="Notification ID")
    message_id: int = Field(..., description="Durable message ID")
    receiver_id: str = Field(..., description="Recipient identity")
    status: MessageStatus = Field(..., description="Delivery status")
    created_at: datetime = Field(..., description="Creation timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    failed_at: Optional[datetime] = Field(None, description="Failure timestamp")
    error_detail: Optional[str] = Field(None, description="Delivery failure detail")
    legacy_inbox_id: Optional[int] = Field(
        None, description="Old inbox row ID reserved for compatibility wrappers"
    )


class InboxDelivery(BaseModel):
    """Joined notification-backed message ready for delivery or display."""

    message: InboxMessageRecord
    notification: InboxNotification
