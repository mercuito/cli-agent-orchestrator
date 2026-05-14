"""Backend read service for agent identity CAO event timelines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import CaoEventRecord
from cli_agent_orchestrator.services.agent_identity_manager import (
    AgentIdentityManager,
    AgentIdentityStatus,
)


class UnknownTimelineEventError(ValueError):
    """Raised when a requested CAO event does not exist in the durable event log."""


@dataclass(frozen=True)
class TimelineEventRead:
    """Envelope-level CAO event facts for dashboard identity timeline reads."""

    event_id: str
    event_name: str
    event_type_key: str
    source_type: str
    source_id: str
    occurred_at: datetime
    correlation_id: str | None
    causation_id: str | None
    participant_role: str | None = None


@dataclass(frozen=True)
class IdentityTimelineRead:
    """One manager-resolved identity plus its participant-index timeline."""

    identity: AgentIdentityStatus
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


class AgentIdentityTimelineService:
    """Compose manager-owned identities with durable CAO event-log reads."""

    def __init__(self, identity_manager: AgentIdentityManager) -> None:
        self._identity_manager = identity_manager

    def timeline_for_identity(self, agent_id: str) -> IdentityTimelineRead:
        """Return one identity's participant-index timeline."""

        identity_status = self._identity_manager.status_for_identity(agent_id)
        participant_records = db_module.list_cao_event_participants_by_agent_identity(
            identity_status.agent_identity_id
        )
        return IdentityTimelineRead(
            identity=identity_status,
            events=tuple(
                _timeline_event_from_record(
                    participant_record.record,
                    participant_role=participant_record.participant_role,
                )
                for participant_record in participant_records
            ),
        )

    def related_events_for_identity_event(self, agent_id: str, event_id: str) -> RelatedEventsRead:
        """Return envelope-related CAO event threads for a manager-resolved identity."""

        self._identity_manager.status_for_identity(agent_id)
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
            event=_timeline_event_from_record(record),
            correlation_events=tuple(
                _timeline_event_from_record(related_record)
                for related_record in correlation_records
            ),
            causation_events=CausationRelatedEventsRead(
                direct_cause=(
                    _timeline_event_from_record(direct_cause)
                    if direct_cause is not None
                    else None
                ),
                direct_effects=tuple(
                    _timeline_event_from_record(related_record)
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
        participant_role=participant_role,
    )
