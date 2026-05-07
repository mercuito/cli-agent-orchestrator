"""Flow schedule persistence."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, String

from cli_agent_orchestrator.clients.database_core import Base
from cli_agent_orchestrator.constants import DEFAULT_PROVIDER
from cli_agent_orchestrator.models.flow import Flow


class FlowModel(Base):
    """SQLAlchemy model for flow metadata."""

    __tablename__ = "flows"

    name = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    schedule = Column(String, nullable=False)
    agent_profile = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    script = Column(String, nullable=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)


def _session_local():
    from cli_agent_orchestrator.clients import database as db_module

    return db_module.SessionLocal


def flow_from_model(row: FlowModel) -> Flow:
    """Convert a SQLAlchemy flow row to its typed domain model."""
    return Flow(
        name=row.name,
        file_path=row.file_path,
        schedule=row.schedule,
        agent_profile=row.agent_profile,
        provider=row.provider,
        script=row.script,
        last_run=row.last_run,
        next_run=row.next_run,
        enabled=row.enabled,
    )


def create_flow(
    name: str,
    file_path: str,
    schedule: str,
    agent_profile: str,
    provider: str,
    script: str,
    next_run: datetime,
) -> Flow:
    """Create flow record."""
    with _session_local()() as db:
        flow = FlowModel(
            name=name,
            file_path=file_path,
            schedule=schedule,
            agent_profile=agent_profile,
            provider=provider,
            script=script,
            next_run=next_run,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        return flow_from_model(flow)


def get_flow(name: str) -> Optional[Flow]:
    """Get flow by name."""
    with _session_local()() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if not flow:
            return None
        return flow_from_model(flow)


def list_flows() -> List[Flow]:
    """List all flows."""
    with _session_local()() as db:
        flows = db.query(FlowModel).order_by(FlowModel.next_run).all()
        return [flow_from_model(flow) for flow in flows]


def update_flow_run_times(name: str, last_run: datetime, next_run: datetime) -> bool:
    """Update flow run times after execution."""
    with _session_local()() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if flow:
            flow.last_run = last_run
            flow.next_run = next_run
            db.commit()
            return True
        return False


def update_flow_enabled(name: str, enabled: bool, next_run: Optional[datetime] = None) -> bool:
    """Update flow enabled status and optionally next_run."""
    with _session_local()() as db:
        flow = db.query(FlowModel).filter(FlowModel.name == name).first()
        if flow:
            flow.enabled = enabled
            if next_run is not None:
                flow.next_run = next_run
            db.commit()
            return True
        return False


def delete_flow(name: str) -> bool:
    """Delete flow."""
    with _session_local()() as db:
        deleted = db.query(FlowModel).filter(FlowModel.name == name).delete()
        db.commit()
        return deleted > 0


def get_flows_to_run() -> List[Flow]:
    """Get enabled flows where next_run <= now."""
    with _session_local()() as db:
        now = datetime.now()
        flows = (
            db.query(FlowModel).filter(FlowModel.enabled == True, FlowModel.next_run <= now).all()
        )
        return [flow_from_model(flow) for flow in flows]
