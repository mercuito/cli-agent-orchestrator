"""Durable typed CAO event log persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from cli_agent_orchestrator.clients.database_core import Base
from cli_agent_orchestrator.events import CaoEvent, agent_participants_for
from cli_agent_orchestrator.events.serialization import deserialize_cao_event, serialize_cao_event

_NO_PARTICIPANT_ROLE = ""
CAO_EVENTS_TABLE = "cao_events"
CAO_EVENT_AGENT_PARTICIPANTS_TABLE = "cao_event_agent_participants"
CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX = (
    "ix_cao_event_agent_participants_agent_occurred"
)
CAO_EVENT_ID_COLUMN = "event_id"
CAO_EVENT_OCCURRED_AT_COLUMN = "occurred_at"
CAO_EVENT_AGENT_IDENTITY_ID_COLUMN = "agent_identity_id"
CAO_EVENT_PARTICIPANT_ROLE_COLUMN = "participant_role"


class CaoEventModel(Base):
    """Universal persisted CAO event envelope plus canonical typed payload."""

    __tablename__ = CAO_EVENTS_TABLE
    __table_args__ = (
        Index("ix_cao_events_event_name_occurred_at", "event_name", "occurred_at"),
        Index("ix_cao_events_source_occurred_at", "source_type", "source_id", "occurred_at"),
        Index("ix_cao_events_correlation_occurred_at", "correlation_id", "occurred_at"),
        Index("ix_cao_events_causation_occurred_at", "causation_id", "occurred_at"),
    )

    event_id = Column(CAO_EVENT_ID_COLUMN, String, primary_key=True)
    event_name = Column(String, nullable=False, index=True)
    event_type_key = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False, index=True)
    source_id = Column(String, nullable=False, index=True)
    occurred_at = Column(
        CAO_EVENT_OCCURRED_AT_COLUMN,
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    correlation_id = Column(String, nullable=True, index=True)
    causation_id = Column(String, nullable=True, index=True)
    event_data_json = Column(Text, nullable=False)


class CaoEventAgentParticipantModel(Base):
    """First-class agent participant index for CAO events."""

    __tablename__ = CAO_EVENT_AGENT_PARTICIPANTS_TABLE
    __table_args__ = (
        UniqueConstraint(
            CAO_EVENT_ID_COLUMN,
            CAO_EVENT_AGENT_IDENTITY_ID_COLUMN,
            CAO_EVENT_PARTICIPANT_ROLE_COLUMN,
            name="uq_cao_event_agent_participant",
        ),
        Index(
            CAO_EVENT_AGENT_PARTICIPANTS_AGENT_OCCURRED_INDEX,
            CAO_EVENT_AGENT_IDENTITY_ID_COLUMN,
            CAO_EVENT_OCCURRED_AT_COLUMN,
            CAO_EVENT_ID_COLUMN,
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(
        CAO_EVENT_ID_COLUMN,
        String,
        ForeignKey(f"{CAO_EVENTS_TABLE}.{CAO_EVENT_ID_COLUMN}", ondelete="CASCADE"),
        nullable=False,
    )
    agent_identity_id = Column(
        CAO_EVENT_AGENT_IDENTITY_ID_COLUMN,
        String,
        nullable=False,
        index=True,
    )
    participant_role = Column(CAO_EVENT_PARTICIPANT_ROLE_COLUMN, String, nullable=False)
    occurred_at = Column(CAO_EVENT_OCCURRED_AT_COLUMN, DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class CaoEventRecord:
    """Reconstructed event plus the persisted envelope metadata."""

    event_id: str
    event_name: str
    event_type_key: str
    source_type: str
    source_id: str
    occurred_at: datetime
    correlation_id: str | None
    causation_id: str | None
    event: CaoEvent


def persist_cao_event(event: CaoEvent) -> CaoEventRecord:
    """Persist one typed CAO event and participant index idempotently by event id."""

    event_type_key, event_data_json = serialize_cao_event(event)
    values = {
        CAO_EVENT_ID_COLUMN: str(event.event_id),
        "event_name": event.event_name,
        "event_type_key": event_type_key,
        "source_type": str(event.source.source_type),
        "source_id": str(event.source.source_id),
        CAO_EVENT_OCCURRED_AT_COLUMN: event.occurred_at,
        "correlation_id": str(event.correlation_id) if event.correlation_id is not None else None,
        "causation_id": str(event.causation_id) if event.causation_id is not None else None,
        "event_data_json": event_data_json,
    }
    with _session_local()() as session:
        canonical_insert = session.execute(
            sqlite_insert(CaoEventModel)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[CAO_EVENT_ID_COLUMN])
        )
        if canonical_insert.rowcount:
            for participant in agent_participants_for(event):
                session.execute(
                    sqlite_insert(CaoEventAgentParticipantModel)
                    .values(
                        **{
                            CAO_EVENT_ID_COLUMN: str(event.event_id),
                            CAO_EVENT_AGENT_IDENTITY_ID_COLUMN: participant.agent_identity_id,
                            CAO_EVENT_PARTICIPANT_ROLE_COLUMN: (
                                participant.role or _NO_PARTICIPANT_ROLE
                            ),
                            CAO_EVENT_OCCURRED_AT_COLUMN: event.occurred_at,
                        }
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            CAO_EVENT_ID_COLUMN,
                            CAO_EVENT_AGENT_IDENTITY_ID_COLUMN,
                            CAO_EVENT_PARTICIPANT_ROLE_COLUMN,
                        ]
                    )
                )
        row = session.get(CaoEventModel, str(event.event_id))
        if row is None:
            raise ValueError(f"CAO event was not persisted: {event.event_id}")
        record = _record_from_model(row)
        session.commit()
    return record


def get_cao_event(event_id: str) -> CaoEventRecord | None:
    """Return one persisted CAO event by id."""

    with _session_local()() as session:
        row = session.get(CaoEventModel, event_id)
        return _record_from_model(row) if row is not None else None


def list_cao_events_by_agent_identity(agent_identity_id: str) -> tuple[CaoEventRecord, ...]:
    """List events involving one agent identity, ordered by occurrence time."""

    with _session_local()() as session:
        rows = (
            session.query(CaoEventModel)
            .join(
                CaoEventAgentParticipantModel,
                CaoEventAgentParticipantModel.event_id == CaoEventModel.event_id,
            )
            .filter(CaoEventAgentParticipantModel.agent_identity_id == agent_identity_id)
            .distinct()
            .order_by(
                CaoEventAgentParticipantModel.occurred_at.asc(),
                CaoEventAgentParticipantModel.event_id.asc(),
            )
            .all()
        )
        return tuple(_record_from_model(row) for row in rows)


def list_cao_events_by_event_name(event_name: str) -> tuple[CaoEventRecord, ...]:
    """List events by framework event name, ordered by occurrence time."""

    return _list_records(CaoEventModel.event_name == event_name)


def list_cao_events_by_source(
    *,
    source_type: str,
    source_id: str,
) -> tuple[CaoEventRecord, ...]:
    """List events from one CAO source reference, ordered by occurrence time."""

    return _list_records(
        CaoEventModel.source_type == source_type,
        CaoEventModel.source_id == source_id,
    )


def list_cao_events_by_correlation_id(correlation_id: str) -> tuple[CaoEventRecord, ...]:
    """List events sharing one correlation id, ordered by occurrence time."""

    return _list_records(CaoEventModel.correlation_id == correlation_id)


def list_cao_events_by_causation_id(causation_id: str) -> tuple[CaoEventRecord, ...]:
    """List direct child events of one causing event id, ordered by occurrence time."""

    return _list_records(CaoEventModel.causation_id == causation_id)


def _list_records(*criteria: object) -> tuple[CaoEventRecord, ...]:
    with _session_local()() as session:
        query = session.query(CaoEventModel)
        for criterion in criteria:
            query = query.filter(criterion)
        rows = query.order_by(CaoEventModel.occurred_at.asc(), CaoEventModel.event_id.asc()).all()
        return tuple(_record_from_model(row) for row in rows)


def _record_from_model(row: CaoEventModel) -> CaoEventRecord:
    event_type_key = cast(str, row.event_type_key)
    event_data_json = cast(str, row.event_data_json)
    event = deserialize_cao_event(event_type_key, event_data_json)
    return CaoEventRecord(
        event_id=cast(str, row.event_id),
        event_name=cast(str, row.event_name),
        event_type_key=event_type_key,
        source_type=cast(str, row.source_type),
        source_id=cast(str, row.source_id),
        occurred_at=cast(datetime, row.occurred_at),
        correlation_id=cast(str | None, row.correlation_id),
        causation_id=cast(str | None, row.causation_id),
        event=event,
    )


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal
