"""Workspace-tool-provider typed event publication and subscription contracts."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Mapping, Optional


@dataclass(frozen=True, kw_only=True)
class WorkspaceToolProviderEvent(ABC):
    """Base class for typed events published by workspace tool providers."""

    provider_name: ClassVar[str]
    event_name: ClassVar[str]
    description: ClassVar[str] = ""

    delivery_id: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class WorkspaceToolProviderEventHandlerResult:
    """Result returned by one event subscriber."""

    subscription_id: str
    result: Any


@dataclass(frozen=True)
class WorkspaceToolProviderEventPublication:
    """Published event plus ordered subscriber results."""

    event: WorkspaceToolProviderEvent
    handler_results: tuple[WorkspaceToolProviderEventHandlerResult, ...]

    def first_result_of_type(self, result_type: type) -> Any | None:
        """Return the first subscriber result matching ``result_type``."""

        for handler_result in self.handler_results:
            if isinstance(handler_result.result, result_type):
                return handler_result.result
        return None


WorkspaceToolProviderEventHandler = Callable[[WorkspaceToolProviderEvent], Any]


class WorkspaceToolProviderEventConfigError(ValueError):
    """Raised when provider event configuration is invalid."""


class UnknownWorkspaceToolProviderEventError(WorkspaceToolProviderEventConfigError):
    """Raised when publishing or subscribing to an undeclared provider event."""


class WorkspaceToolProviderEventDispatcher:
    """Synchronous dispatcher for provider-declared typed events."""

    def __init__(
        self,
        event_types: Optional[tuple[type[WorkspaceToolProviderEvent], ...]] = None,
    ) -> None:
        self._event_types: dict[
            type[WorkspaceToolProviderEvent], type[WorkspaceToolProviderEvent]
        ] = {}
        self._subscribers: dict[
            type[WorkspaceToolProviderEvent], dict[str, WorkspaceToolProviderEventHandler]
        ] = {}
        if event_types:
            self.register_events(event_types)

    def register_events(self, event_types: tuple[type[WorkspaceToolProviderEvent], ...]) -> None:
        """Register provider-declared event classes."""

        for event_type in event_types:
            normalized = _validate_event_type(event_type)
            self._event_types[normalized] = normalized

    def published_events(self, provider_name: str) -> tuple[type[WorkspaceToolProviderEvent], ...]:
        """Return registered event classes for one provider."""

        normalized = _normalize_token(provider_name, "provider_name")
        return tuple(
            event_type
            for event_type in sorted(
                self._event_types,
                key=lambda item: (_event_type_provider_name(item), _event_type_event_name(item)),
            )
            if _event_type_provider_name(event_type) == normalized
        )

    def subscribe(
        self,
        *,
        event_type: type[WorkspaceToolProviderEvent],
        handler: WorkspaceToolProviderEventHandler,
        subscription_id: str,
    ) -> None:
        """Subscribe to a provider-declared event class."""

        normalized_event_type = _validate_event_type(event_type)
        if normalized_event_type not in self._event_types:
            raise UnknownWorkspaceToolProviderEventError(
                "Unknown workspace-tool-provider event: "
                f"{_event_type_provider_name(normalized_event_type)}."
                f"{_event_type_event_name(normalized_event_type)}"
            )
        subscriber_id = _normalize_token(subscription_id, "subscription_id")
        self._subscribers.setdefault(normalized_event_type, {})[subscriber_id] = handler

    def publish(self, event: WorkspaceToolProviderEvent) -> WorkspaceToolProviderEventPublication:
        """Publish a provider-declared event instance and synchronously run subscribers."""

        event_type = _validate_event_instance(event)
        if event_type not in self._event_types:
            raise UnknownWorkspaceToolProviderEventError(
                "Unknown workspace-tool-provider event: "
                f"{_event_type_provider_name(event_type)}.{_event_type_event_name(event_type)}"
            )
        results: list[WorkspaceToolProviderEventHandlerResult] = []
        for subscription_id, handler in self._subscribers.get(event_type, {}).items():
            results.append(
                WorkspaceToolProviderEventHandlerResult(
                    subscription_id=subscription_id,
                    result=handler(event),
                )
            )
        return WorkspaceToolProviderEventPublication(event=event, handler_results=tuple(results))


_DEFAULT_WORKSPACE_TOOL_PROVIDER_EVENT_DISPATCHER = WorkspaceToolProviderEventDispatcher()


def default_workspace_tool_provider_event_dispatcher() -> WorkspaceToolProviderEventDispatcher:
    """Return CAO's process-local workspace-tool-provider event dispatcher."""

    return _DEFAULT_WORKSPACE_TOOL_PROVIDER_EVENT_DISPATCHER


def _normalize_token(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise WorkspaceToolProviderEventConfigError(f"{label} must be non-empty")
    return normalized


def _event_type_provider_name(event_type: type[WorkspaceToolProviderEvent]) -> str:
    value = getattr(event_type, "provider_name", None)
    if not isinstance(value, str):
        raise WorkspaceToolProviderEventConfigError(
            f"{event_type.__name__} must declare string ClassVar provider_name"
        )
    return _normalize_token(value, "provider_name")


def _event_type_event_name(event_type: type[WorkspaceToolProviderEvent]) -> str:
    value = getattr(event_type, "event_name", None)
    if not isinstance(value, str):
        raise WorkspaceToolProviderEventConfigError(
            f"{event_type.__name__} must declare string ClassVar event_name"
        )
    return _normalize_token(value, "event_name")


def _validate_event_type(
    event_type: type[WorkspaceToolProviderEvent],
) -> type[WorkspaceToolProviderEvent]:
    if not isinstance(event_type, type) or not issubclass(event_type, WorkspaceToolProviderEvent):
        raise WorkspaceToolProviderEventConfigError(
            "workspace tool provider events must extend WorkspaceToolProviderEvent"
        )
    _event_type_provider_name(event_type)
    _event_type_event_name(event_type)
    return event_type


def _validate_event_instance(event: WorkspaceToolProviderEvent) -> type[WorkspaceToolProviderEvent]:
    if not isinstance(event, WorkspaceToolProviderEvent):
        raise WorkspaceToolProviderEventConfigError(
            "published workspace tool provider events must extend WorkspaceToolProviderEvent"
        )
    event_type = _validate_event_type(type(event))
    if event.delivery_id is not None and not isinstance(event.delivery_id, str):
        raise WorkspaceToolProviderEventConfigError(
            f"{event_type.__name__}.delivery_id must be a string or None"
        )
    if event.metadata is not None and not isinstance(event.metadata, Mapping):
        raise WorkspaceToolProviderEventConfigError(
            f"{event_type.__name__}.metadata must be a mapping or None"
        )
    return event_type
