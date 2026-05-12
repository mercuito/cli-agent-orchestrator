"""Provider-owned conversation and work-item records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal, Optional

MessageKind = Literal[
    "prompt",
    "thought",
    "response",
    "elicitation",
    "error",
    "stop",
    "comment",
    "unknown",
]
MessageDirection = Literal["inbound", "outbound"]
MessageState = Literal["received", "queued", "delivered", "acknowledged", "failed"]
ThreadKind = Literal["conversation", "work_item_discussion", "channel_thread", "unknown"]
ThreadState = Literal["active", "awaiting_input", "complete", "stale", "error", "unknown"]


@dataclass(frozen=True)
class ExternalRef:
    """A stable reference to an object owned by an external workspace provider."""

    provider: str
    id: str
    url: Optional[str] = None


@dataclass(frozen=True)
class WorkItem:
    """A unit of work as CAO understands it, regardless of provider vocabulary."""

    ref: ExternalRef
    identifier: Optional[str] = None
    title: Optional[str] = None
    state: Optional[str] = None


@dataclass(frozen=True)
class ConversationMessage:
    """A message or activity inside an external conversation thread."""

    kind: MessageKind
    body: Optional[str] = None
    ref: Optional[ExternalRef] = None
    direction: MessageDirection = "inbound"
    state: MessageState = "received"
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ConversationThread:
    """A provider-owned conversation thread attached to optional work."""

    ref: ExternalRef
    work_item: Optional[WorkItem] = None
    kind: ThreadKind = "conversation"
    state: ThreadState = "active"
    prompt_context: Optional[str] = None


@dataclass(frozen=True)
class StopAcknowledgement:
    """Result of acknowledging a provider-owned stop or cancel signal."""

    thread_ref: ExternalRef
    supported: bool
    message: Optional[ConversationMessage] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class WorkItemRecord:
    """Durable provider-owned work item stored by CAO."""

    id: int
    provider: str
    external_id: str
    external_url: Optional[str]
    identifier: Optional[str]
    title: Optional[str]
    state: Optional[str]
    raw_snapshot: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ConversationThreadRecord:
    """Durable provider-owned conversation surface stored by CAO."""

    id: int
    provider: str
    external_id: str
    external_url: Optional[str]
    work_item_id: Optional[int]
    kind: str
    state: str
    prompt_context: Optional[str]
    raw_snapshot: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ConversationMessageRecord:
    """Durable provider-owned message or activity stored by CAO."""

    id: int
    thread_id: int
    provider: str
    external_id: Optional[str]
    direction: str
    kind: str
    body: Optional[str]
    state: str
    raw_snapshot: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProcessedProviderEventRecord:
    """Idempotency marker for a provider-owned event delivery."""

    id: int
    provider: str
    external_event_id: str
    event_type: Optional[str]
    processed_at: datetime
    metadata: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class PersistedProviderEventRecords:
    """Records touched while storing a typed workspace provider event."""

    processed_event: Optional[ProcessedProviderEventRecord]
    work_item: Optional[WorkItemRecord]
    thread: Optional[ConversationThreadRecord]
    message: Optional[ConversationMessageRecord]
