"""Shared fixtures for the CAO test suite."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.agent import Agent, AgentRegistry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services.agent_manager import AgentManager


@pytest.fixture
def runtime_inbox_db_session(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Patch SessionLocal to an in-memory SQLite database with FK checks enabled."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn: Any, _conn_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", test_session)

    with test_session() as session:
        assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    return test_session


@pytest.fixture
def implementation_partner_agent_factory():
    def _agent(**overrides: str | None) -> Agent:
        values = {
            "id": "implementation_partner",
            "display_name": "Implementation Partner",
            "cli_provider": "codex",
            "workdir": "/repo",
            "session_name": "implementation-partner",
            "prompt": "",
        }
        values.update(overrides)
        return Agent(**values)

    return _agent


@pytest.fixture
def agent_manager_factory():
    """Sanctioned manager-backed factory for framework-consumed test agents."""

    def _manager(
        *agents: Agent,
        terminals: list[dict[str, object]] | None = None,
        providers: tuple[object, ...] = (),
    ) -> AgentManager:
        manager = AgentManager(
            configured_agents=AgentRegistry({}),
            terminal_lister=lambda: list(terminals or []),
            terminal_metadata_resolver=lambda terminal_id: {
                terminal["id"]: terminal for terminal in terminals or []
            }.get(terminal_id),
        )
        for agent in agents:
            manager.register_agent(agent)
        return manager

    return _manager


class FakeTerminalProvider:
    def __init__(self, status: TerminalStatus | Exception) -> None:
        self.status = status

    def get_status(self) -> TerminalStatus:
        if isinstance(self.status, Exception):
            raise self.status
        return self.status


@pytest.fixture
def terminal_provider_patcher(monkeypatch: pytest.MonkeyPatch):
    def _patch(provider_manager: Any, status: TerminalStatus | Exception | None):
        provider = None if status is None else FakeTerminalProvider(status)
        monkeypatch.setattr(provider_manager, "get_provider", lambda terminal_id: provider)
        return provider

    return _patch


@pytest.fixture
def terminal_send_patcher(monkeypatch: pytest.MonkeyPatch):
    def _patch(terminal_service: Any) -> Mock:
        send_input = Mock()
        monkeypatch.setattr(terminal_service, "send_input", send_input)
        return send_input

    return _patch
