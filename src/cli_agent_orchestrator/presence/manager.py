"""Registry and router for provider-neutral presence providers."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PersistedPresenceEvent,
    PresenceEvent,
    StopAcknowledgement,
)
from cli_agent_orchestrator.presence.persistence import persist_presence_event
from cli_agent_orchestrator.presence.provider import PresenceProvider


class UnknownPresenceProviderError(ValueError):
    """Raised when no presence provider is registered for a provider name."""


class DuplicatePresenceProviderError(ValueError):
    """Raised when registering a duplicate provider without replacement."""


class PresenceProviderMismatchError(ValueError):
    """Raised when a provider normalizes an event for another provider."""


class PresenceProviderManager:
    """In-memory registry that routes presence operations by provider name."""

    def __init__(
        self,
        providers: Optional[Mapping[str, PresenceProvider]] = None,
    ) -> None:
        self._providers: Dict[str, PresenceProvider] = {}
        if providers is not None:
            for name, provider in providers.items():
                self.register_provider(name, provider)

    def register_provider(
        self,
        name: str,
        provider: PresenceProvider,
        *,
        replace: bool = False,
    ) -> PresenceProvider:
        """Register a provider by name.

        Duplicate names fail by default so accidental replacement is explicit.
        Tests and composition roots can pass ``replace=True`` when swapping fakes.
        """

        if not name:
            raise ValueError("presence provider name is required")
        if name in self._providers and not replace:
            raise DuplicatePresenceProviderError(f"Presence provider already registered: {name}")
        self._providers[name] = provider
        return provider

    def clear_providers(self) -> None:
        """Remove all providers from this manager."""

        self._providers.clear()

    def get_provider(self, name: str) -> PresenceProvider:
        """Retrieve a registered provider by name."""

        try:
            return self._providers[name]
        except KeyError as exc:
            raise UnknownPresenceProviderError(f"Unknown presence provider: {name}") from exc

    def list_providers(self) -> List[str]:
        """List registered provider names."""

        return sorted(self._providers)

    def normalize_event(
        self,
        provider_name: str,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        """Normalize a raw event with the named provider."""

        provider = self.get_provider(provider_name)
        return provider.normalize_event(raw_event, delivery_id=delivery_id)

    def ingest_event(
        self,
        provider_name: str,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PersistedPresenceEvent]:
        """Normalize and persist a provider event using generic persistence."""

        event = self.normalize_event(
            provider_name,
            raw_event,
            delivery_id=delivery_id,
        )
        if event is None:
            return None
        self._require_event_provider(event, provider_name)
        return persist_presence_event(event)

    def _require_event_provider(self, event: PresenceEvent, provider_name: str) -> None:
        if event.provider != provider_name:
            raise PresenceProviderMismatchError(
                f"Provider {provider_name} normalized event for provider {event.provider}"
            )
        if event.thread is not None:
            self._require_ref_provider(
                event.thread.ref,
                provider_name,
                "thread",
            )
            if event.thread.work_item is not None:
                self._require_ref_provider(
                    event.thread.work_item.ref,
                    provider_name,
                    "work item",
                )
        if event.message is not None and event.message.ref is not None:
            self._require_ref_provider(
                event.message.ref,
                provider_name,
                "message",
            )

    def _require_ref_provider(
        self,
        ref: ExternalRef,
        provider_name: str,
        label: str,
    ) -> None:
        if ref.provider != provider_name:
            raise PresenceProviderMismatchError(
                f"Provider {provider_name} normalized {label} ref for provider {ref.provider}"
            )

    def fetch_thread(self, thread_ref: ExternalRef) -> ConversationThread:
        """Fetch a thread by routing through ``thread_ref.provider``."""

        return self.get_provider(thread_ref.provider).fetch_thread(thread_ref)

    def fetch_messages(self, thread_ref: ExternalRef) -> List[ConversationMessage]:
        """Fetch thread messages by routing through ``thread_ref.provider``."""

        return self.get_provider(thread_ref.provider).fetch_messages(thread_ref)

    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        """Reply to a thread by routing through ``thread_ref.provider``."""

        return self.get_provider(thread_ref.provider).reply_to_thread(
            thread_ref,
            body,
            kind=kind,
            metadata=metadata,
        )

    def acknowledge_stop(
        self,
        thread_ref: ExternalRef,
        *,
        message_ref: Optional[ExternalRef] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> StopAcknowledgement:
        """Acknowledge stop/cancel by routing through ``thread_ref.provider``."""

        return self.get_provider(thread_ref.provider).acknowledge_stop(
            thread_ref,
            message_ref=message_ref,
            reason=reason,
            metadata=metadata,
        )


presence_provider_manager = PresenceProviderManager()
