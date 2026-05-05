"""Provider contract for external presence integrations."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Protocol

from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    StopAcknowledgement,
)


class PresenceProvider(Protocol):
    """Boundary implemented by systems that expose work conversations to CAO."""

    name: str

    def normalize_event(
        self,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        """Translate a raw provider event into a provider-neutral CAO event."""

    def fetch_thread(self, thread_ref: ExternalRef) -> ConversationThread:
        """Fetch or hydrate an external conversation thread."""

    def fetch_messages(self, thread_ref: ExternalRef) -> List[ConversationMessage]:
        """Fetch provider-neutral messages for an external conversation thread."""

    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        """Send a provider-neutral reply to an external conversation thread."""

    def acknowledge_stop(
        self,
        thread_ref: ExternalRef,
        *,
        message_ref: Optional[ExternalRef] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> StopAcknowledgement:
        """Acknowledge a stop or cancel signal when the provider supports it."""
