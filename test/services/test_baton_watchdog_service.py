"""Tests for baton watchdog nudges and orphan recovery."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base, BatonEventModel, BatonModel
from cli_agent_orchestrator.inbox import readiness as inbox_service
from cli_agent_orchestrator.inbox import (
    get_notification,
    list_pending_notifications,
)
from cli_agent_orchestrator.models.baton import BatonStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services import baton_service, baton_watchdog_service
from cli_agent_orchestrator.workspaces import (
    DEFAULT_WORKSPACE_ID,
    WorkspaceCollaborationManager,
    WorkspaceTeam,
    WorkspaceTeamRegistry,
    default_workspace_registry,
)

_REAL_AVAILABLE_BATON_HOLDER_TOOLS = baton_service.available_baton_holder_tools


class _TeamStore:
    def __init__(self, teams: tuple[WorkspaceTeam, ...]) -> None:
        self._teams = {team.id: team for team in teams}

    def get(self, team_id: str) -> WorkspaceTeam:
        return self._teams[team_id]

    def list(self) -> tuple[WorkspaceTeam, ...]:
        return tuple(self._teams.values())


@pytest.fixture
def patched_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return TestSession


@pytest.fixture(autouse=True)
def allow_baton_collaboration(monkeypatch):
    monkeypatch.setattr(
        baton_service,
        "require_agent_same_team_collaboration",
        lambda sender_id, receiver_id, **kwargs: None,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.collaboration_policy.default_workspace_collaboration_manager",
        _collaboration_manager,
    )
    monkeypatch.setattr(
        baton_service,
        "available_baton_holder_tools",
        lambda db, terminal_id: (
            "pass_baton",
            "return_baton",
            "complete_baton",
            "block_baton",
        ),
    )


def _agent(agent_id: str, team: str | None = "delivery") -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
    )


def _collaboration_manager() -> WorkspaceCollaborationManager:
    return WorkspaceCollaborationManager(
        workspace_registry=default_workspace_registry(),
        team_registry=WorkspaceTeamRegistry(
            _TeamStore(
                (
                    WorkspaceTeam(
                        id="delivery",
                        display_name="Delivery",
                        workspace=DEFAULT_WORKSPACE_ID,
                    ),
                )
            )
        ),
        agent_registry=AgentRegistry(
            {
                "originator": _agent("originator"),
                "impl": _agent("impl"),
                "detached": _agent("detached", None),
            }
        ),
        provider_adapters={},
    )


def _config(*, grace_seconds=1, rate_limit_seconds=60):
    return baton_watchdog_service.BatonWatchdogConfig(
        interval_seconds=0.01,
        grace_seconds=grace_seconds,
        nudge_rate_limit_seconds=rate_limit_seconds,
    )


def _create_terminal(terminal_id: str):
    _create_terminal_for_agent(terminal_id, terminal_id)


def _create_terminal_for_agent(terminal_id: str, agent_id: str):
    db_module.create_terminal(
        terminal_id=terminal_id,
        tmux_session="cao-test",
        tmux_window=terminal_id,
        provider="codex",
        agent_id=agent_id,
        workspace_context_id=db_module.ensure_default_workspace_context(agent_id).id,
    )


class _ToolService:
    def __init__(self, built_in_tools: tuple[str, ...]) -> None:
        self._built_in_tools = set(built_in_tools)

    def tools_for_agent(self, agent_id: str, *, built_in_tool_names=()):
        return SimpleNamespace(
            built_in_cao_tools=tuple(
                tool for tool in built_in_tool_names if tool in self._built_in_tools
            )
        )


def _provider(status: TerminalStatus):
    provider = MagicMock()
    provider.get_status.return_value = status
    return provider


def _messages(receiver_id: str):
    return list_pending_notifications(receiver_id, limit=50)


def _events(baton_id: str):
    return db_module.list_baton_events(baton_id)


@pytest.mark.parametrize("status", [TerminalStatus.IDLE, TerminalStatus.COMPLETED])
def test_idle_or_completed_holder_receives_nudge_after_grace(patched_db, monkeypatch, status):
    _create_terminal("impl")
    provider = _provider(status)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
        expected_next_action="run the review loop",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.scanned == 1
    assert result.nudged == 1
    baton = db_module.get_baton_record("baton-1")
    assert baton.status == BatonStatus.ACTIVE.value
    assert baton.current_holder_id == "impl"
    assert baton.last_nudged_at is not None
    assert [event.event_type for event in _events("baton-1")] == ["create", "nudge"]
    queued = _messages("impl")
    assert len(queued) == 2
    assert queued[-1].sender_agent_id == baton_watchdog_service.WATCHDOG_ACTOR_ID
    assert "Baton id: baton-1" in queued[-1].body
    assert "Title: T05" in queued[-1].body
    assert "Expected next action: run the review loop" in queued[-1].body
    assert "If you are waiting on another agent to make the next move" in queued[-1].body
    assert "pass the baton to that agent with pass_baton" in queued[-1].body
    assert "Idle detection is advisory" in queued[-1].body
    assert "pass_baton" in queued[-1].body
    assert "return_baton" in queued[-1].body
    assert "complete_baton" in queued[-1].body
    assert "block_baton" in queued[-1].body


def test_idle_holder_without_baton_tools_gets_no_lifecycle_tool_guidance(
    patched_db, monkeypatch
):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    monkeypatch.setattr(
        baton_service,
        "available_baton_holder_tools",
        _REAL_AVAILABLE_BATON_HOLDER_TOOLS,
    )
    monkeypatch.setattr(
        baton_service,
        "default_tool_service",
        lambda: _ToolService(()),
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.nudged == 1
    body = _messages("impl")[-1].body
    assert "no baton lifecycle tools available" in body
    assert "pass_baton" not in body
    assert "return_baton" not in body
    assert "complete_baton" not in body
    assert "block_baton" not in body


def test_processing_holder_is_not_nudged(patched_db, monkeypatch):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.PROCESSING)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.scanned == 1
    assert result.nudged == 0
    assert [event.event_type for event in _events("baton-1")] == ["create"]
    assert len(_messages("impl")) == 1


def test_nudges_are_rate_limited_by_last_nudged_at(patched_db, monkeypatch):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )
    first_scan_at = datetime.now() + timedelta(seconds=5)

    first = baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0, rate_limit_seconds=60),
        now=first_scan_at,
    )
    second = baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0, rate_limit_seconds=60),
        now=first_scan_at + timedelta(seconds=10),
    )

    assert first.nudged == 1
    assert second.nudged == 0
    assert [event.event_type for event in _events("baton-1")] == ["create", "nudge"]
    assert len(_messages("impl")) == 2


def test_teamless_holder_is_orphaned_before_watchdog_inbox_notification(patched_db, monkeypatch):
    _create_terminal("originator")
    _create_terminal("detached")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="detached",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0),
        now=datetime.now() + timedelta(seconds=5),
    )

    baton = db_module.get_baton_record("baton-1")
    assert result.nudged == 0
    assert result.orphaned == 1
    assert baton.status == BatonStatus.ORPHANED.value
    assert [event.event_type for event in _events("baton-1")] == ["create", "orphan"]
    assert len(_messages("detached")) == 1
    assert _messages("detached")[0].sender_agent_id == "originator"
    assert len(_messages("originator")) == 1


def test_watchdog_nudge_notification_delivers_through_semantic_inbox(
    patched_db,
    monkeypatch,
):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )
    baton_watchdog_service.scan_active_batons(
        config=_config(grace_seconds=0),
        now=datetime.now() + timedelta(seconds=5),
    )
    queued = _messages("impl")
    sent = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.terminal_service.send_input",
        lambda terminal_id, message: sent.append((terminal_id, message)),
    )

    assert inbox_service.check_and_send_pending_messages("impl") is True
    assert inbox_service.check_and_send_pending_messages("impl") is True

    delivered = get_notification(queued[-1].id)
    assert delivered is not None
    assert delivered.status.value == "delivered"
    assert "Gentle reminder" in sent[-1][1]


def test_missing_holder_metadata_marks_baton_orphaned_and_notifies_originator(
    patched_db, monkeypatch
):
    _create_terminal("originator")
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: None,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="missing",
        expected_next_action="finish T05",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now(),
    )

    assert result.scanned == 1
    assert result.orphaned == 1
    baton = db_module.get_baton_record("baton-1")
    assert baton.status == BatonStatus.ORPHANED.value
    assert baton.current_holder_id is None
    assert [event.event_type for event in _events("baton-1")] == ["create", "orphan"]
    queued = _messages("originator")
    assert len(queued) == 1
    assert queued[0].sender_agent_id == baton_watchdog_service.WATCHDOG_ACTOR_ID
    assert "Baton id: baton-1" in queued[0].body
    assert "Previous holder: missing" in queued[0].body
    assert "marked orphaned" in queued[0].body


def test_missing_holder_provider_marks_baton_orphaned_and_notifies_originator(
    patched_db, monkeypatch
):
    _create_terminal("originator")
    _create_terminal("impl")

    def provider_missing(terminal_id: str):
        raise ValueError(f"Provider not found for {terminal_id}")

    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        provider_missing,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now(),
    )

    assert result.orphaned == 1
    baton = db_module.get_baton_record("baton-1")
    assert baton.status == BatonStatus.ORPHANED.value
    assert [event.event_type for event in _events("baton-1")] == ["create", "orphan"]


def test_only_active_batons_are_scanned(patched_db, monkeypatch):
    _create_terminal("impl")
    provider = _provider(TerminalStatus.IDLE)
    monkeypatch.setattr(
        baton_watchdog_service.provider_manager,
        "get_provider",
        lambda terminal_id: provider,
    )
    baton_service.create_baton(
        baton_id="baton-1",
        title="T05",
        originator_id="originator",
        holder_id="impl",
    )
    with patched_db() as db:
        row = db.query(BatonModel).filter(BatonModel.id == "baton-1").one()
        row.status = BatonStatus.BLOCKED.value
        db.add(
            BatonEventModel(
                baton_id="baton-1",
                event_type="block",
                actor_id="impl",
                from_holder_id="impl",
                to_holder_id="originator",
                message="blocked",
                created_at=datetime.now(),
            )
        )
        db.commit()

    result = baton_watchdog_service.scan_active_batons(
        config=_config(),
        now=datetime.now() + timedelta(seconds=5),
    )

    assert result.scanned == 0
    assert result.nudged == 0
    assert len(_messages("impl")) == 1
