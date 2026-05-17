"""Framework-wide typed CAO event primitives and dispatcher."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, NewType, Protocol, TypeVar, get_type_hints, runtime_checkable

__all__ = [
    "AgentParticipant",
    "CaoAllEventHandler",
    "CaoCausationId",
    "CaoCorrelationId",
    "CaoEvent",
    "CaoEventDispatcher",
    "CaoEventHandler",
    "CaoEventHandlerResult",
    "CaoEventId",
    "CaoEventOccurredAt",
    "CaoEventPublication",
    "CaoEventSourceId",
    "CaoEventSourceRef",
    "CaoEventSourceType",
    "InvalidCaoEventError",
    "UnknownCaoEventError",
    "WithAgentParticipants",
    "agent_participants_for",
    "default_cao_event_dispatcher",
    "event_involves_agent",
]

CaoEventId = NewType("CaoEventId", str)
CaoEventSourceType = NewType("CaoEventSourceType", str)
CaoEventSourceId = NewType("CaoEventSourceId", str)
CaoCorrelationId = NewType("CaoCorrelationId", str)
CaoCausationId = NewType("CaoCausationId", str)
CaoEventOccurredAt = NewType("CaoEventOccurredAt", datetime)


class InvalidCaoEventError(ValueError):
    """Raised when a CAO event declaration or instance is invalid."""


class UnknownCaoEventError(InvalidCaoEventError):
    """Raised when publishing or subscribing to an undeclared CAO event."""


@dataclass(frozen=True, kw_only=True)
class CaoEventSourceRef:
    """Typed reference to the CAO-owned source that produced an event."""

    source_type: CaoEventSourceType
    source_id: CaoEventSourceId

    def __post_init__(self) -> None:
        _normalize_token(self.source_type, "source_type")
        _normalize_token(self.source_id, "source_id")


@dataclass(frozen=True, kw_only=True)
class AgentParticipant:
    """One CAO agent involved in an event.

    Participant roles are owned by each event family and intentionally remain
    optional plain strings rather than a framework-wide enum.
    """

    agent_id: str
    role: str | None = None

    def __post_init__(self) -> None:
        _normalize_token(self.agent_id, "agent_id")
        if self.role is not None:
            _normalize_token(self.role, "agent participant role")


@runtime_checkable
class CaoEvent(Protocol):
    """Structural protocol for framework-wide CAO events."""

    @property
    def event_name(self) -> str:
        """Family-owned event type name."""

    @property
    def event_id(self) -> CaoEventId:
        """Unique identifier for this concrete event occurrence."""

    @property
    def source(self) -> CaoEventSourceRef:
        """Typed reference to the system source that emitted this event."""

    @property
    def occurred_at(self) -> CaoEventOccurredAt:
        """Timezone-aware timestamp when the event occurred."""

    @property
    def correlation_id(self) -> CaoCorrelationId | None:
        """Optional ID that groups related event chains."""

    @property
    def causation_id(self) -> CaoCausationId | None:
        """Optional ID of the event that directly caused this event."""


@runtime_checkable
class WithAgentParticipants(Protocol):
    """Facet for events that expose involved CAO agents."""

    @property
    def agent_participants(self) -> tuple[AgentParticipant, ...]:
        """Agent identities involved in this event."""


CaoEventT = TypeVar("CaoEventT", bound=CaoEvent)
CaoEventHandler = Callable[[CaoEventT], Any]
CaoAllEventHandler = Callable[[CaoEvent], Any]

_EVENT_TYPE_REQUIRED_FIELDS = {
    "event_id": CaoEventId,
    "source": CaoEventSourceRef,
    "occurred_at": CaoEventOccurredAt,
    "correlation_id": CaoCorrelationId | None,
    "causation_id": CaoCausationId | None,
}


@dataclass(frozen=True)
class CaoEventHandlerResult:
    """Result returned by one CAO event subscriber."""

    subscription_id: str
    result: Any


@dataclass(frozen=True)
class CaoEventPublication(Generic[CaoEventT]):
    """Published event plus ordered subscriber results."""

    event: CaoEventT
    handler_results: tuple[CaoEventHandlerResult, ...]

    def first_result_of_type(self, result_type: type) -> Any | None:
        """Return the first subscriber result matching ``result_type``."""

        for handler_result in self.handler_results:
            if isinstance(handler_result.result, result_type):
                return handler_result.result
        return None


@dataclass(frozen=True)
class _CaoEventSubscription:
    subscription_id: str
    event_type: type[CaoEvent] | None
    handler: Callable[[Any], Any]


class CaoEventDispatcher:
    """Synchronous dispatcher for registered framework-wide typed events."""

    def __init__(
        self,
        event_types: tuple[type[CaoEvent], ...] | None = None,
        *,
        persist_events: bool = False,
    ) -> None:
        self._event_types: dict[type[CaoEvent], type[CaoEvent]] = {}
        self._subscriptions: list[_CaoEventSubscription] = []
        self._subscription_ids: set[str] = set()
        self._persist_events = persist_events
        if event_types:
            self.register_events(event_types)

    def register_events(self, event_types: tuple[type[CaoEvent], ...]) -> None:
        """Register CAO event classes that may be published."""

        normalized_events = tuple(_validate_event_type(event_type) for event_type in event_types)
        from cli_agent_orchestrator.events.serialization import register_cao_event_serializers

        register_cao_event_serializers(normalized_events)
        for event_type in normalized_events:
            self._event_types[event_type] = event_type

    @classmethod
    def persistent(
        cls,
        event_types: tuple[type[CaoEvent], ...] | None = None,
    ) -> "CaoEventDispatcher":
        """Create a dispatcher that persists published events before subscribers run."""

        return cls(event_types, persist_events=True)

    def published_events(self) -> tuple[type[CaoEvent], ...]:
        """Return registered event classes ordered by event name."""

        return tuple(sorted(self._event_types, key=_event_type_event_name))

    def subscribe_all(
        self,
        *,
        handler: CaoAllEventHandler,
        subscription_id: str,
    ) -> None:
        """Subscribe to every registered CAO event."""

        self._add_subscription(
            event_type=None,
            handler=handler,
            subscription_id=subscription_id,
        )

    def subscribe(
        self,
        *,
        event_type: type[CaoEventT],
        handler: CaoEventHandler[CaoEventT],
        subscription_id: str,
    ) -> None:
        """Subscribe to one registered concrete CAO event type."""

        normalized_event_type = _validate_event_type(event_type)
        if normalized_event_type not in self._event_types:
            raise UnknownCaoEventError(
                f"Unknown CAO event: {_event_type_event_name(normalized_event_type)}"
            )
        self._add_subscription(
            event_type=normalized_event_type,
            handler=handler,
            subscription_id=subscription_id,
        )

    def publish(self, event: CaoEventT) -> CaoEventPublication[CaoEventT]:
        """Publish one registered event instance and run matching subscribers."""

        event_type = _validate_event_instance(event)
        if event_type not in self._event_types:
            raise UnknownCaoEventError(f"Unknown CAO event: {_event_type_event_name(event_type)}")

        if self._persist_events:
            from cli_agent_orchestrator.clients.cao_event_store import persist_cao_event

            persist_cao_event(event)

        results: list[CaoEventHandlerResult] = []
        for subscription in self._subscriptions:
            if subscription.event_type is not None and subscription.event_type is not event_type:
                continue
            results.append(
                CaoEventHandlerResult(
                    subscription_id=subscription.subscription_id,
                    result=subscription.handler(event),
                )
            )
        return CaoEventPublication(event=event, handler_results=tuple(results))

    def _add_subscription(
        self,
        *,
        event_type: type[CaoEvent] | None,
        handler: Callable[[Any], Any],
        subscription_id: str,
    ) -> None:
        subscriber_id = _normalize_token(subscription_id, "subscription_id")
        if subscriber_id in self._subscription_ids:
            raise InvalidCaoEventError(f"Duplicate CAO event subscription_id: {subscriber_id}")
        self._subscription_ids.add(subscriber_id)
        self._subscriptions.append(
            _CaoEventSubscription(
                subscription_id=subscriber_id,
                event_type=event_type,
                handler=handler,
            )
        )


_DEFAULT_CAO_EVENT_DISPATCHER = CaoEventDispatcher.persistent()


def default_cao_event_dispatcher() -> CaoEventDispatcher:
    """Return CAO's process-local framework-wide event dispatcher."""

    return _DEFAULT_CAO_EVENT_DISPATCHER


def agent_participants_for(event: CaoEvent | WithAgentParticipants) -> tuple[AgentParticipant, ...]:
    """Return agent participants for events that expose the participant facet."""

    if not isinstance(event, WithAgentParticipants):
        return ()
    participants = event.agent_participants
    if not isinstance(participants, tuple):
        raise InvalidCaoEventError("agent_participants must be a tuple")
    for participant in participants:
        if not isinstance(participant, AgentParticipant):
            raise InvalidCaoEventError("agent_participants must contain AgentParticipant values")
    return participants


def event_involves_agent(
    event: CaoEvent | WithAgentParticipants,
    agent_id: str,
) -> bool:
    """Return whether ``agent_id`` is one of the event's participants."""

    normalized_agent_id = _normalize_token(agent_id, "agent_id")
    return any(
        participant.agent_id == normalized_agent_id
        for participant in agent_participants_for(event)
    )


def _normalize_token(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidCaoEventError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise InvalidCaoEventError(f"{label} must be non-empty")
    return normalized


def _event_type_event_name(event_type: type[CaoEvent]) -> str:
    value = getattr(event_type, "event_name", None)
    if not isinstance(value, str):
        raise InvalidCaoEventError(f"{event_type.__name__} must declare string event_name")
    return _normalize_token(value, "event_name")


def _validate_event_type(event_type: type[CaoEvent]) -> type[CaoEvent]:
    if not isinstance(event_type, type):
        raise InvalidCaoEventError("CAO event types must be classes")
    _event_type_event_name(event_type)
    if issubclass(event_type, Mapping):
        raise InvalidCaoEventError("CAO events must be typed objects, not mappings")
    type_hints = get_type_hints(event_type)
    for field_name, expected_type in _EVENT_TYPE_REQUIRED_FIELDS.items():
        field_type = type_hints.get(field_name)
        if field_type != expected_type:
            raise InvalidCaoEventError(
                f"{event_type.__name__}.{field_name} must be annotated as {expected_type}"
            )
    return event_type


def _validate_event_instance(event: CaoEvent) -> type[CaoEvent]:
    if isinstance(event, Mapping) or not isinstance(event, CaoEvent):
        raise InvalidCaoEventError("published CAO events must satisfy CaoEvent")

    event_type = _validate_event_type(type(event))
    _normalize_token(event.event_id, "event_id")
    if not isinstance(event.source, CaoEventSourceRef):
        raise InvalidCaoEventError(f"{event_type.__name__}.source must be CaoEventSourceRef")
    if not isinstance(event.occurred_at, datetime):
        raise InvalidCaoEventError(f"{event_type.__name__}.occurred_at must be a datetime")
    if event.occurred_at.tzinfo is None or event.occurred_at.utcoffset() is None:
        raise InvalidCaoEventError(f"{event_type.__name__}.occurred_at must be timezone-aware")
    if event.correlation_id is not None:
        _normalize_token(event.correlation_id, "correlation_id")
    if event.causation_id is not None:
        _normalize_token(event.causation_id, "causation_id")
    agent_participants_for(event)
    return event_type
