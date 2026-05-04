"""Baton domain models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BatonStatus(str, Enum):
    """Lifecycle status for a baton."""

    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELED = "canceled"
    ORPHANED = "orphaned"


class BatonEventType(str, Enum):
    """Audit event types for baton state changes and operator actions."""

    CREATE = "create"
    PASS = "pass"
    RETURN = "return"
    COMPLETE = "complete"
    BLOCK = "block"
    CANCEL = "cancel"
    REASSIGN = "reassign"
    ORPHAN = "orphan"
    NUDGE = "nudge"


class Baton(BaseModel):
    """Tracked async control obligation between agents."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Unique baton identifier")
    title: str = Field(..., description="Human-readable baton title")
    status: BatonStatus = Field(..., description="Current baton status")
    originator_id: str = Field(..., description="Terminal that created the baton")
    current_holder_id: Optional[str] = Field(None, description="Terminal that owes the next move")
    return_stack: List[str] = Field(default_factory=list, description="LIFO return chain")
    expected_next_action: Optional[str] = Field(None, description="Hint for the current holder")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_nudged_at: Optional[datetime] = Field(None, description="Last watchdog nudge timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")


class BatonEvent(BaseModel):
    """Audit event emitted for a baton transition."""

    model_config = ConfigDict(use_enum_values=True)

    id: int = Field(..., description="Event identifier")
    baton_id: str = Field(..., description="Baton identifier")
    event_type: BatonEventType = Field(..., description="Event type")
    actor_id: str = Field(..., description="Terminal or operator that performed the action")
    from_holder_id: Optional[str] = Field(None, description="Previous holder, if any")
    to_holder_id: Optional[str] = Field(
        None, description="New holder or notification target, if any"
    )
    message: Optional[str] = Field(None, description="Transition message")
    created_at: datetime = Field(..., description="Creation timestamp")
