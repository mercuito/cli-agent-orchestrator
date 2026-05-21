"""Runtime-owned CAO event declarations and publishers."""

from __future__ import annotations

import hashlib
from dataclasses import field
from datetime import datetime, timezone
from typing import ClassVar, Literal
from uuid import uuid4

from pydantic.dataclasses import dataclass

from cli_agent_orchestrator.events import (
    AgentParticipant,
    AgentReady,
    CaoCausationId,
    CaoCorrelationId,
    CaoEvent,
    CaoEventDispatcher,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventPublication,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
    default_cao_event_dispatcher,
)

RUNTIME_CAO_SOURCE_TYPE = CaoEventSourceType("cao_runtime")
RUNTIME_AGENT_PARTICIPANT_ROLE_NOTIFICATION_RECEIVER = "notification_receiver"
RUNTIME_AGENT_PARTICIPANT_ROLE_DELIVERY_TARGET = "delivery_target"
RUNTIME_AGENT_PARTICIPANT_ROLE_LIFECYCLE_AGENT = "lifecycle_agent"
RUNTIME_AGENT_PARTICIPANT_ROLE_CONTEXT_SWITCH_AGENT = "context_switch_agent"
RUNTIME_AGENT_PARTICIPANT_ROLE_READY_AGENT = "ready_agent"


def _now() -> CaoEventOccurredAt:
    return CaoEventOccurredAt(datetime.now(timezone.utc))


def _runtime_source_ref(source_id: str) -> CaoEventSourceRef:
    return CaoEventSourceRef(
        source_type=RUNTIME_CAO_SOURCE_TYPE,
        source_id=CaoEventSourceId(source_id),
    )


def _runtime_event_id(event_name: str, *parts: object) -> CaoEventId:
    normalized_parts = [str(part) for part in parts if part is not None and str(part)]
    if normalized_parts:
        source = ":".join(normalized_parts)
    else:
        source = str(uuid4())
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]
    return CaoEventId(f"cao_runtime:{event_name}:{digest}")


def _causation_for(causing_event: CaoEvent | None) -> CaoCausationId | None:
    if causing_event is None:
        return None
    return CaoCausationId(str(causing_event.event_id))


def _correlation_for(causing_event: CaoEvent | None) -> CaoCorrelationId | None:
    if causing_event is None:
        return None
    return causing_event.correlation_id


def _agent_participants(agent_id: str, role: str) -> tuple[AgentParticipant, ...]:
    return (AgentParticipant(agent_id=agent_id, role=role),)


@dataclass(frozen=True, kw_only=True)
class _AgentRuntimeEventMetadata:
    event_id: CaoEventId
    source: CaoEventSourceRef
    occurred_at: CaoEventOccurredAt = field(default_factory=_now)
    correlation_id: CaoCorrelationId | None = None
    causation_id: CaoCausationId | None = None
    agent_participants: tuple[AgentParticipant, ...]


@dataclass(frozen=True, kw_only=True)
class AgentRuntimeNotificationAcceptedEvent(_AgentRuntimeEventMetadata):
    """Runtime accepted a newly durable notification for an agent."""

    event_name: ClassVar[str] = "agent_runtime_notification_accepted"
    kind: Literal["cao_runtime.agent_runtime_notification_accepted"] = (
        "cao_runtime.agent_runtime_notification_accepted"
    )

    agent_id: str
    workspace_context_id: str
    inbox_notification_id: int
    receiver_agent_id: str
    sender_agent_id: str


@dataclass(frozen=True, kw_only=True)
class AgentRuntimeNotificationDeliveryEvent(_AgentRuntimeEventMetadata):
    """Runtime delivery for an accepted notification was delivered, deferred, or failed."""

    event_name: ClassVar[str] = "agent_runtime_notification_delivery"
    kind: Literal["cao_runtime.agent_runtime_notification_delivery"] = (
        "cao_runtime.agent_runtime_notification_delivery"
    )

    agent_id: str
    workspace_context_id: str
    inbox_notification_id: int
    receiver_agent_id: str
    terminal_id: str | None
    runtime_status: str
    outcome: str
    attempted: bool
    delivered: bool
    error: str | None
    message_body: str | None = None


@dataclass(frozen=True, kw_only=True)
class AgentRuntimeLifecycleEvent(_AgentRuntimeEventMetadata):
    """Runtime lifecycle reconciliation started, reused, refreshed, deferred, or failed."""

    event_name: ClassVar[str] = "agent_runtime_lifecycle"
    kind: Literal["cao_runtime.agent_runtime_lifecycle"] = "cao_runtime.agent_runtime_lifecycle"

    agent_id: str
    workspace_context_id: str
    action: str
    runtime_status: str
    terminal_id: str | None
    ready: bool
    fresh: bool
    error: str | None


@dataclass(frozen=True, kw_only=True)
class AgentRuntimeWorkspaceContextSwitchEvent(_AgentRuntimeEventMetadata):
    """Runtime switched workspace context, deferred the switch, or failed it."""

    event_name: ClassVar[str] = "agent_runtime_workspace_context_switch"
    kind: Literal["cao_runtime.agent_runtime_workspace_context_switch"] = (
        "cao_runtime.agent_runtime_workspace_context_switch"
    )

    agent_id: str
    from_workspace_context_id: str
    to_workspace_context_id: str
    terminal_id: str
    runtime_status: str
    outcome: str
    error: str | None


@dataclass(frozen=True, kw_only=True)
class RuntimeWorkspaceEvent:
    """Workspace-wide runtime activity that is not scoped to one agent."""

    event_name: ClassVar[str] = "runtime_workspace"
    kind: Literal["cao_runtime.runtime_workspace"] = "cao_runtime.runtime_workspace"

    event_id: CaoEventId
    source: CaoEventSourceRef
    occurred_at: CaoEventOccurredAt = field(default_factory=_now)
    correlation_id: CaoCorrelationId | None = None
    causation_id: CaoCausationId | None = None
    workspace_context_id: str
    action: str
    runtime_status: str
    error: str | None = None


RUNTIME_CAO_EVENTS = (
    AgentReady,
    AgentRuntimeNotificationAcceptedEvent,
    AgentRuntimeNotificationDeliveryEvent,
    AgentRuntimeLifecycleEvent,
    AgentRuntimeWorkspaceContextSwitchEvent,
    RuntimeWorkspaceEvent,
)


def register_runtime_cao_events(
    dispatcher: CaoEventDispatcher | None = None,
) -> CaoEventDispatcher:
    """Register runtime-owned CAO events on ``dispatcher``."""

    event_dispatcher = dispatcher or default_cao_event_dispatcher()
    event_dispatcher.register_events(RUNTIME_CAO_EVENTS)
    return event_dispatcher


def publish_runtime_event(
    event: CaoEvent,
    *,
    dispatcher: CaoEventDispatcher | None = None,
) -> CaoEventPublication[CaoEvent]:
    """Publish one runtime-owned CAO event through the framework dispatcher."""

    event_dispatcher = register_runtime_cao_events(dispatcher)
    return event_dispatcher.publish(event)


def notification_accepted_event(
    *,
    agent_id: str,
    workspace_context_id: str,
    inbox_notification_id: int,
    receiver_agent_id: str,
    sender_agent_id: str,
    causing_event: CaoEvent | None = None,
) -> AgentRuntimeNotificationAcceptedEvent:
    """Build a runtime notification acceptance event."""

    return AgentRuntimeNotificationAcceptedEvent(
        event_id=_runtime_event_id(
            AgentRuntimeNotificationAcceptedEvent.event_name,
            agent_id,
            workspace_context_id,
            inbox_notification_id,
        ),
        source=_runtime_source_ref(f"notification:{inbox_notification_id}"),
        correlation_id=_correlation_for(causing_event),
        causation_id=_causation_for(causing_event),
        agent_id=agent_id,
        workspace_context_id=workspace_context_id,
        inbox_notification_id=inbox_notification_id,
        receiver_agent_id=receiver_agent_id,
        sender_agent_id=sender_agent_id,
        agent_participants=_agent_participants(
            agent_id,
            RUNTIME_AGENT_PARTICIPANT_ROLE_NOTIFICATION_RECEIVER,
        ),
    )


def agent_ready_event(
    *,
    agent_id: str,
    terminal_id: str,
    causing_event: CaoEvent | None = None,
) -> AgentReady:
    """Build an event announcing that an agent runtime can receive delivery."""

    return AgentReady(
        event_id=_runtime_event_id(
            AgentReady.event_name,
            agent_id,
            terminal_id,
        ),
        source=_runtime_source_ref(terminal_id),
        occurred_at=_now(),
        correlation_id=_correlation_for(causing_event),
        causation_id=_causation_for(causing_event),
        agent_id=agent_id,
        agent_participants=_agent_participants(
            agent_id,
            RUNTIME_AGENT_PARTICIPANT_ROLE_READY_AGENT,
        ),
    )


def notification_delivery_event(
    *,
    agent_id: str,
    workspace_context_id: str,
    inbox_notification_id: int,
    receiver_agent_id: str,
    terminal_id: str | None,
    runtime_status: str,
    outcome: str,
    attempted: bool,
    delivered: bool,
    error: str | None,
    message_body: str | None = None,
    causing_event: CaoEvent | None = None,
) -> AgentRuntimeNotificationDeliveryEvent:
    """Build a runtime notification delivery outcome event."""

    return AgentRuntimeNotificationDeliveryEvent(
        event_id=_runtime_event_id(
            AgentRuntimeNotificationDeliveryEvent.event_name,
            agent_id,
            workspace_context_id,
            inbox_notification_id,
            outcome,
        ),
        source=_runtime_source_ref(f"notification:{inbox_notification_id}"),
        correlation_id=_correlation_for(causing_event),
        causation_id=_causation_for(causing_event),
        agent_id=agent_id,
        workspace_context_id=workspace_context_id,
        inbox_notification_id=inbox_notification_id,
        receiver_agent_id=receiver_agent_id,
        terminal_id=terminal_id,
        runtime_status=runtime_status,
        outcome=outcome,
        attempted=attempted,
        delivered=delivered,
        error=error,
        message_body=message_body,
        agent_participants=_agent_participants(
            agent_id,
            RUNTIME_AGENT_PARTICIPANT_ROLE_DELIVERY_TARGET,
        ),
    )


def lifecycle_event(
    *,
    agent_id: str,
    workspace_context_id: str,
    action: str,
    runtime_status: str,
    terminal_id: str | None,
    ready: bool,
    fresh: bool,
    error: str | None,
    causing_event: CaoEvent | None = None,
) -> AgentRuntimeLifecycleEvent:
    """Build a runtime lifecycle event."""

    return AgentRuntimeLifecycleEvent(
        event_id=_runtime_event_id(
            AgentRuntimeLifecycleEvent.event_name,
            agent_id,
            workspace_context_id,
            terminal_id,
            action,
            runtime_status,
            ready,
            fresh,
            error,
        ),
        source=_runtime_source_ref(terminal_id or f"agent:{agent_id}"),
        correlation_id=_correlation_for(causing_event),
        causation_id=_causation_for(causing_event),
        agent_id=agent_id,
        workspace_context_id=workspace_context_id,
        action=action,
        runtime_status=runtime_status,
        terminal_id=terminal_id,
        ready=ready,
        fresh=fresh,
        error=error,
        agent_participants=_agent_participants(
            agent_id,
            RUNTIME_AGENT_PARTICIPANT_ROLE_LIFECYCLE_AGENT,
        ),
    )


def workspace_runtime_event(
    *,
    workspace_context_id: str,
    action: str,
    runtime_status: str,
    error: str | None = None,
    correlation_id: CaoCorrelationId | None = None,
    causing_event: CaoEvent | None = None,
) -> RuntimeWorkspaceEvent:
    """Build a workspace-wide runtime event with no agent participants."""

    return RuntimeWorkspaceEvent(
        event_id=_runtime_event_id(
            RuntimeWorkspaceEvent.event_name,
            workspace_context_id,
            action,
            runtime_status,
            error,
        ),
        source=_runtime_source_ref(f"workspace:{workspace_context_id}"),
        correlation_id=_correlation_for(causing_event) or correlation_id,
        causation_id=_causation_for(causing_event),
        workspace_context_id=workspace_context_id,
        action=action,
        runtime_status=runtime_status,
        error=error,
    )


def workspace_context_switch_event(
    *,
    agent_id: str,
    from_workspace_context_id: str,
    to_workspace_context_id: str,
    terminal_id: str,
    runtime_status: str,
    outcome: str,
    error: str | None,
    causing_event: CaoEvent | None = None,
) -> AgentRuntimeWorkspaceContextSwitchEvent:
    """Build a runtime workspace-context switch event."""

    return AgentRuntimeWorkspaceContextSwitchEvent(
        event_id=_runtime_event_id(
            AgentRuntimeWorkspaceContextSwitchEvent.event_name,
            agent_id,
            from_workspace_context_id,
            to_workspace_context_id,
            terminal_id,
            outcome,
            runtime_status,
            error,
        ),
        source=_runtime_source_ref(terminal_id),
        correlation_id=_correlation_for(causing_event),
        causation_id=_causation_for(causing_event),
        agent_id=agent_id,
        from_workspace_context_id=from_workspace_context_id,
        to_workspace_context_id=to_workspace_context_id,
        terminal_id=terminal_id,
        runtime_status=runtime_status,
        outcome=outcome,
        error=error,
        agent_participants=_agent_participants(
            agent_id,
            RUNTIME_AGENT_PARTICIPANT_ROLE_CONTEXT_SWITCH_AGENT,
        ),
    )
