"""Backend read service for agent CAO event timelines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import CaoEventRecord
from cli_agent_orchestrator.services.agent_manager import (
    AgentManager,
    AgentStatus,
)


class UnknownTimelineEventError(ValueError):
    """Raised when a requested CAO event does not exist in the durable event log."""


@dataclass(frozen=True)
class TimelineEventRead:
    """Envelope-level CAO event facts for dashboard agent timeline reads."""

    event_id: str
    event_name: str
    event_type_key: str
    source_type: str
    source_id: str
    occurred_at: datetime
    correlation_id: str | None
    causation_id: str | None
    event_data: dict[str, Any]
    participant_role: str | None = None


@dataclass(frozen=True)
class AgentTimelineRead:
    """One manager-resolved agent plus its participant-index timeline."""

    agent: AgentStatus
    events: tuple[TimelineEventRead, ...]


@dataclass(frozen=True)
class CausationRelatedEventsRead:
    """Direct cause/effect reads for one canonical CAO event."""

    direct_cause: TimelineEventRead | None
    direct_effects: tuple[TimelineEventRead, ...]


@dataclass(frozen=True)
class RelatedEventsRead:
    """Envelope-based related threads for one canonical CAO event."""

    event: TimelineEventRead
    correlation_events: tuple[TimelineEventRead, ...]
    causation_events: CausationRelatedEventsRead


class AgentTimelineService:
    """Compose manager-owned agents with durable CAO event-log reads."""

    def __init__(self, agent_manager: AgentManager) -> None:
        self._agent_manager = agent_manager

    def timeline_for_agent(self, agent_id: str) -> AgentTimelineRead:
        """Return one agent's participant-index timeline."""

        agent_status = self._agent_manager.status_for_agent(agent_id)
        participant_records = db_module.list_cao_event_participants_by_agent(
            agent_status.agent_id
        )
        return AgentTimelineRead(
            agent=agent_status,
            events=tuple(
                _timeline_event_from_record(
                    participant_record.record,
                    participant_role=participant_record.participant_role,
                )
                for participant_record in participant_records
            ),
        )

    def related_events_for_agent_event(self, agent_id: str, event_id: str) -> RelatedEventsRead:
        """Return envelope-related CAO event threads for a manager-resolved agent."""

        agent_status = self._agent_manager.status_for_agent(agent_id)
        participant_roles = _participant_roles_by_event_id(agent_status.agent_id)
        record = db_module.get_cao_event(event_id)
        if record is None:
            raise UnknownTimelineEventError(f"Unknown CAO event: {event_id}")

        direct_cause = None
        if record.causation_id is not None:
            direct_cause = db_module.get_cao_event(record.causation_id)
        correlation_records = (
            db_module.list_cao_events_by_correlation_id(record.correlation_id)
            if record.correlation_id is not None
            else ()
        )
        direct_effect_records = db_module.list_cao_events_by_causation_id(record.event_id)

        return RelatedEventsRead(
            event=_timeline_event_from_record(
                record,
                participant_role=participant_roles.get(record.event_id),
            ),
            correlation_events=tuple(
                _timeline_event_from_record(
                    related_record,
                    participant_role=participant_roles.get(related_record.event_id),
                )
                for related_record in correlation_records
            ),
            causation_events=CausationRelatedEventsRead(
                direct_cause=(
                    _timeline_event_from_record(
                        direct_cause,
                        participant_role=participant_roles.get(direct_cause.event_id),
                    )
                    if direct_cause is not None
                    else None
                ),
                direct_effects=tuple(
                    _timeline_event_from_record(
                        related_record,
                        participant_role=participant_roles.get(related_record.event_id),
                    )
                    for related_record in direct_effect_records
                ),
            ),
        )


def _timeline_event_from_record(
    record: CaoEventRecord,
    *,
    participant_role: str | None = None,
) -> TimelineEventRead:
    return TimelineEventRead(
        event_id=record.event_id,
        event_name=record.event_name,
        event_type_key=record.event_type_key,
        source_type=record.source_type,
        source_id=record.source_id,
        occurred_at=record.occurred_at,
        correlation_id=record.correlation_id,
        causation_id=record.causation_id,
        event_data=record.event_data,
        participant_role=participant_role,
    )


def _participant_roles_by_event_id(agent_id: str) -> dict[str, str]:
    return {
        participant_record.record.event_id: participant_record.participant_role
        for participant_record in db_module.list_cao_event_participants_by_agent(agent_id)
    }
