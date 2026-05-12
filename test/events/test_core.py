"""Tests for the CAO framework-wide typed event core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar, cast

import pytest

from cli_agent_orchestrator.events import (
    AgentParticipant,
    CaoCausationId,
    CaoCorrelationId,
    CaoEvent,
    CaoEventDispatcher,
    CaoEventId,
    CaoEventOccurredAt,
    CaoEventSourceId,
    CaoEventSourceRef,
    CaoEventSourceType,
    InvalidCaoEventError,
    UnknownCaoEventError,
    WithAgentParticipants,
    agent_participants_for,
    event_involves_agent,
)

OCCURRED_AT = CaoEventOccurredAt(datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc))
SOURCE_REF = CaoEventSourceRef(
    source_type=CaoEventSourceType("test"),
    source_id=CaoEventSourceId("event-fixture"),
)


@dataclass(frozen=True)
class TimelineNoteEvent:
    event_name: ClassVar[str] = "test.timeline_note"

    event_id: CaoEventId
    source: CaoEventSourceRef
    occurred_at: CaoEventOccurredAt
    correlation_id: CaoCorrelationId | None
    causation_id: CaoCausationId | None
    message: str


@dataclass(frozen=True)
class AgentPromptedEvent:
    event_name: ClassVar[str] = "test.agent_prompted"

    event_id: CaoEventId
    source: CaoEventSourceRef
    occurred_at: CaoEventOccurredAt
    correlation_id: CaoCorrelationId | None
    causation_id: CaoCausationId | None
    prompt: str
    agent_participants: tuple[AgentParticipant, ...]


@dataclass(frozen=True)
class MissingEventMetadata:
    event_name: ClassVar[str] = "test.missing_metadata"

    message: str


def _timeline_event(message: str = "hello") -> TimelineNoteEvent:
    return TimelineNoteEvent(
        event_id=CaoEventId("event-1"),
        source=SOURCE_REF,
        occurred_at=OCCURRED_AT,
        correlation_id=CaoCorrelationId("correlation-1"),
        causation_id=CaoCausationId("causation-1"),
        message=message,
    )


def _agent_event(
    participants: tuple[AgentParticipant, ...],
    *,
    event_id: str = "agent-event-1",
) -> AgentPromptedEvent:
    return AgentPromptedEvent(
        event_id=CaoEventId(event_id),
        source=SOURCE_REF,
        occurred_at=OCCURRED_AT,
        correlation_id=None,
        causation_id=None,
        prompt="Can you inspect this?",
        agent_participants=participants,
    )


def test_dispatcher_registers_and_publishes_concrete_typed_events() -> None:
    dispatcher = CaoEventDispatcher()

    with pytest.raises(UnknownCaoEventError):
        dispatcher.subscribe(
            event_type=TimelineNoteEvent,
            handler=lambda event: event.message,
            subscription_id="timeline-subscriber",
        )

    dispatcher.register_events((TimelineNoteEvent,))

    seen_messages: list[str] = []

    def handle_timeline_event(event: TimelineNoteEvent) -> str:
        seen_messages.append(event.message)
        return event.message.upper()

    dispatcher.subscribe(
        event_type=TimelineNoteEvent,
        handler=handle_timeline_event,
        subscription_id="timeline-subscriber",
    )

    publication = dispatcher.publish(_timeline_event("typed payload"))

    assert seen_messages == ["typed payload"]
    assert publication.event.message == "typed payload"
    assert publication.handler_results[0].subscription_id == "timeline-subscriber"
    assert publication.handler_results[0].result == "TYPED PAYLOAD"
    assert publication.first_result_of_type(str) == "TYPED PAYLOAD"


def test_dispatcher_supports_all_event_and_concrete_type_subscribers_in_order() -> None:
    dispatcher = CaoEventDispatcher((TimelineNoteEvent, AgentPromptedEvent))
    seen: list[str] = []

    def handle_any_event(event: CaoEvent) -> str:
        seen.append(f"all:{event.event_id}")
        return event.event_name

    def handle_agent_event(event: AgentPromptedEvent) -> str:
        seen.append(f"agent:{event.prompt}")
        return event.agent_participants[0].agent_identity_id

    dispatcher.subscribe_all(handler=handle_any_event, subscription_id="timeline")
    dispatcher.subscribe(
        event_type=AgentPromptedEvent,
        handler=handle_agent_event,
        subscription_id="agent",
    )

    publication = dispatcher.publish(
        _agent_event(
            (
                AgentParticipant(
                    agent_identity_id="implementation_partner",
                    role="prompt_recipient",
                ),
            )
        )
    )

    assert seen == ["all:agent-event-1", "agent:Can you inspect this?"]
    assert [result.subscription_id for result in publication.handler_results] == [
        "timeline",
        "agent",
    ]
    assert [result.result for result in publication.handler_results] == [
        "test.agent_prompted",
        "implementation_partner",
    ]


def test_participant_helpers_cover_zero_one_and_many_agent_participants() -> None:
    no_participants = _timeline_event()
    one_participant = _agent_event(
        (
            AgentParticipant(
                agent_identity_id="implementation_partner",
            ),
        ),
        event_id="agent-event-2",
    )
    many_participants = _agent_event(
        (
            AgentParticipant(
                agent_identity_id="implementation_partner",
                role="prompt_recipient",
            ),
            AgentParticipant(
                agent_identity_id="reviewer",
                role="mentioned_agent",
            ),
        ),
        event_id="agent-event-3",
    )

    assert agent_participants_for(no_participants) == ()
    assert agent_participants_for(one_participant) == one_participant.agent_participants
    assert one_participant.agent_participants[0].role is None
    assert agent_participants_for(many_participants) == many_participants.agent_participants
    assert event_involves_agent(many_participants, "reviewer")
    assert not event_involves_agent(many_participants, "discovery_partner")


def test_generic_timeline_code_can_reason_through_event_protocols() -> None:
    generic_event: CaoEvent = _agent_event(
        (
            AgentParticipant(
                agent_identity_id="implementation_partner",
                role="prompt_recipient",
            ),
        )
    )
    participant_event: WithAgentParticipants = _agent_event(
        (
            AgentParticipant(
                agent_identity_id="reviewer",
                role="mentioned_agent",
            ),
        ),
        event_id="agent-event-4",
    )

    assert generic_event.source == SOURCE_REF
    assert generic_event.occurred_at == OCCURRED_AT
    assert agent_participants_for(participant_event)[0].role == "mentioned_agent"


def test_dispatcher_rejects_unregistered_or_malformed_event_instances() -> None:
    dispatcher = CaoEventDispatcher((TimelineNoteEvent,))

    with pytest.raises(UnknownCaoEventError, match="Unknown CAO event"):
        dispatcher.publish(
            _agent_event(
                (
                    AgentParticipant(
                        agent_identity_id="implementation_partner",
                        role="prompt_recipient",
                    ),
                )
            )
        )

    with pytest.raises(InvalidCaoEventError, match="MissingEventMetadata.event_id"):
        dispatcher.register_events((cast(type[CaoEvent], MissingEventMetadata),))

    with pytest.raises(InvalidCaoEventError, match="published CAO events must satisfy CaoEvent"):
        dispatcher.publish(cast(CaoEvent, MissingEventMetadata(message="missing metadata")))


def test_event_metadata_and_participant_values_must_be_non_empty() -> None:
    with pytest.raises(InvalidCaoEventError, match="event_id must be non-empty"):
        CaoEventDispatcher((TimelineNoteEvent,)).publish(
            TimelineNoteEvent(
                event_id=CaoEventId(" "),
                source=SOURCE_REF,
                occurred_at=OCCURRED_AT,
                correlation_id=None,
                causation_id=None,
                message="blank event id",
            )
        )

    with pytest.raises(InvalidCaoEventError, match="agent participant role must be non-empty"):
        AgentParticipant(agent_identity_id="implementation_partner", role=" ")

    with pytest.raises(InvalidCaoEventError, match="occurred_at must be timezone-aware"):
        CaoEventDispatcher((TimelineNoteEvent,)).publish(
            TimelineNoteEvent(
                event_id=CaoEventId("event-2"),
                source=SOURCE_REF,
                occurred_at=CaoEventOccurredAt(datetime(2026, 5, 12, 12, 0)),
                correlation_id=None,
                causation_id=None,
                message="naive timestamp",
            )
        )
