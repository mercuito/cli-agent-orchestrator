"""Provider-neutral models for external agent presence systems."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

MessageKind = Literal[
    "prompt",
    "thought",
    "response",
    "elicitation",
    "error",
    "stop",
    "unknown",
]


@dataclass(frozen=True)
class ExternalRef:
    """A stable reference to an object owned by an external presence provider."""

    provider: str
    id: str
    url: Optional[str] = None


@dataclass(frozen=True)
class WorkItem:
    """A unit of work as CAO understands it, regardless of provider vocabulary."""

    ref: ExternalRef
    identifier: Optional[str] = None
    title: Optional[str] = None


@dataclass(frozen=True)
class ConversationMessage:
    """A message or activity inside an external conversation thread."""

    kind: MessageKind
    body: Optional[str] = None
    ref: Optional[ExternalRef] = None


@dataclass(frozen=True)
class ConversationThread:
    """A provider-owned conversation thread attached to optional work."""

    ref: ExternalRef
    work_item: Optional[WorkItem] = None
    prompt_context: Optional[str] = None


@dataclass(frozen=True)
class PresenceEvent:
    """A normalized event emitted by an external presence provider."""

    provider: str
    event_type: str
    action: Optional[str]
    thread: Optional[ConversationThread] = None
    message: Optional[ConversationMessage] = None
    delivery_id: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None

