"""Tests for baton_service state transitions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.inbox import readiness as inbox_service
from cli_agent_orchestrator.inbox import (
    get_notification,
    list_pending_notifications,
)
from cli_agent_orchestrator.models.baton import BatonStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.services import baton_service
from cli_agent_orchestrator.services.collaboration_policy import (
    require_agent_same_team_collaboration,
    require_agent_workspace_team,
)
from cli_agent_orchestrator.workspaces import (
    DEFAULT_WORKSPACE_ID,
    WorkspaceCollaborationManager,
    WorkspaceConfigError,
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
        baton_service,
        "require_agent_workspace_team",
        lambda agent_id, **kwargs: None,
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


def _agent(agent_id: str, team: str) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(team=team),
    )


def _create_terminal(terminal_id: str, agent_id: str) -> None:
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
                    WorkspaceTeam(
                        id="research",
                        display_name="Research",
                        workspace=DEFAULT_WORKSPACE_ID,
                    ),
                )
            )
        ),
        agent_registry=AgentRegistry(
            {
                "originator": _agent("originator", "delivery"),
                "impl": _agent("impl", "delivery"),
                "reviewer": _agent("reviewer", "delivery"),
                "outsider": _agent("outsider", "research"),
            }
        ),
        provider_adapters={},
    )


def _event_types(baton_id):
    return [event.event_type for event in db_module.list_baton_events(baton_id)]


def _messages(receiver_id):
    return list_pending_notifications(receiver_id, limit=50)


def test_baton_inbox_notification_requires_same_workspace_team_before_queue(
    patched_db,
    monkeypatch,
):
    monkeypatch.setattr(
        baton_service,
        "require_agent_same_team_collaboration",
        require_agent_same_team_collaboration,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.collaboration_policy.default_workspace_collaboration_manager",
        _collaboration_manager,
    )
    _create_terminal("originator", "originator")
    _create_terminal("impl", "impl")
    _create_terminal("outsider", "outsider")
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    with pytest.raises(WorkspaceConfigError, match="cannot collaborate"):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="impl",
            receiver_id="outsider",
            message="please pick this up",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert baton.return_stack == []
    assert _event_types("baton-1") == ["create"]
    assert _messages("outsider") == []


def test_baton_reassign_requires_same_workspace_team_before_state_change(
    patched_db,
    monkeypatch,
):
    monkeypatch.setattr(
        baton_service,
        "require_agent_same_team_collaboration",
        require_agent_same_team_collaboration,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.collaboration_policy.default_workspace_collaboration_manager",
        _collaboration_manager,
    )
    monkeypatch.setattr(
        baton_service,
        "require_agent_workspace_team",
        require_agent_workspace_team,
    )
    _create_terminal("originator", "originator")
    _create_terminal("impl", "impl")
    _create_terminal("outsider", "outsider")
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    with pytest.raises(WorkspaceConfigError, match="cannot collaborate"):
        baton_service.reassign_baton(
            baton_id="baton-1",
            actor_id="impl",
            receiver_id="outsider",
            message="operator should not see this state change",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert baton.return_stack == []
    assert _event_types("baton-1") == ["create"]
    assert _messages("outsider") == []


def test_operator_reassign_rejects_out_of_team_durable_holder(
    patched_db,
    monkeypatch,
):
    monkeypatch.setattr(
        baton_service,
        "require_agent_same_team_collaboration",
        require_agent_same_team_collaboration,
    )
    monkeypatch.setattr(
        baton_service,
        "require_agent_workspace_team",
        require_agent_workspace_team,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.collaboration_policy.default_workspace_collaboration_manager",
        _collaboration_manager,
    )
    _create_terminal("originator", "originator")
    _create_terminal("impl", "impl")
    _create_terminal("outsider", "outsider")
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    with pytest.raises(WorkspaceConfigError, match="cannot collaborate"):
        baton_service.reassign_baton(
            baton_id="baton-1",
            actor_id="originator",
            receiver_id="outsider",
            operator_recovery=True,
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert _event_types("baton-1") == ["create"]


def test_operator_reassign_rejects_out_of_team_return_stack_participant(
    patched_db,
    monkeypatch,
):
    monkeypatch.setattr(
        baton_service,
        "require_agent_same_team_collaboration",
        require_agent_same_team_collaboration,
    )
    monkeypatch.setattr(
        baton_service,
        "require_agent_workspace_team",
        require_agent_workspace_team,
    )
    monkeypatch.setattr(
        "cli_agent_orchestrator.services.collaboration_policy.default_workspace_collaboration_manager",
        _collaboration_manager,
    )
    _create_terminal("originator", "originator")
    _create_terminal("impl", "impl")
    _create_terminal("reviewer", "reviewer")
    _create_terminal("outsider", "outsider")
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    with patched_db() as session:
        row = session.query(db_module.BatonModel).filter(db_module.BatonModel.id == "baton-1").one()
        row.return_stack_json = '["outsider"]'
        session.commit()

    with pytest.raises(WorkspaceConfigError, match="cannot collaborate"):
        baton_service.reassign_baton(
            baton_id="baton-1",
            actor_id="originator",
            receiver_id="reviewer",
            operator_recovery=True,
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert baton.return_stack == ["outsider"]
    assert _event_types("baton-1") == ["create"]


def test_create_baton_persists_active_holder_and_event(patched_db):
    baton = baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
        message="start",
        expected_next_action="implement",
    )

    assert baton.id == "baton-1"
    assert baton.status == BatonStatus.ACTIVE.value
    assert baton.current_holder_id == "impl"
    assert baton.return_stack == []
    assert baton.expected_next_action == "implement"
    assert _event_types("baton-1") == ["create"]
    queued = _messages("impl")
    assert len(queued) == 1
    assert queued[0].sender_agent_id == "originator"
    assert "Baton id: baton-1" in queued[0].body
    assert "Title: T01" in queued[0].body
    assert "Current expectation: implement" in queued[0].body
    assert "complete_baton" in queued[0].body


def test_create_baton_guidance_uses_tool_service_baton_access(patched_db, monkeypatch):
    _create_terminal("impl", "impl")
    monkeypatch.setattr(
        baton_service,
        "available_baton_holder_tools",
        _REAL_AVAILABLE_BATON_HOLDER_TOOLS,
    )
    monkeypatch.setattr(
        baton_service,
        "default_tool_service",
        lambda: _ToolService(("complete_baton",)),
    )

    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    body = _messages("impl")[0].body
    assert "complete_baton" in body
    assert "pass_baton" not in body
    assert "return_baton" not in body
    assert "block_baton" not in body


def test_pass_baton_pushes_previous_holder_and_sets_receiver(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    baton = baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
        message="please review",
        expected_next_action="review",
    )

    assert baton.current_holder_id == "reviewer"
    assert baton.return_stack == ["impl"]
    assert baton.expected_next_action == "review"
    assert _event_types("baton-1") == ["create", "pass"]
    queued = _messages("reviewer")
    assert len(queued) == 1
    assert queued[0].sender_agent_id == "impl"
    assert "please review" in queued[0].body
    assert "Current expectation: review" in queued[0].body
    assert "pass_baton" in queued[0].body
    assert "Do not use send_message to transfer baton ownership" in queued[0].body


def test_pass_baton_notification_delivers_through_semantic_inbox(patched_db, monkeypatch):
    _create_terminal("reviewer", "reviewer")
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
        message="please review",
    )
    queued = _messages("reviewer")
    idle_provider = type("IdleProvider", (), {"get_status": lambda self: TerminalStatus.IDLE})()
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.provider_manager.get_provider",
        lambda terminal_id: idle_provider,
    )
    sent = []
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.terminal_service.send_input",
        lambda terminal_id, message: sent.append((terminal_id, message)),
    )

    assert inbox_service.check_and_send_pending_messages("reviewer") is True

    delivered = get_notification(queued[0].id)
    assert delivered is not None
    assert delivered.status.value == "delivered"
    assert sent[0][0] == "reviewer"
    assert "please review" in sent[0][1]


def test_pass_baton_rejects_self_pass(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    with pytest.raises(baton_service.BatonInvalidTransition, match="to yourself"):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="impl",
            receiver_id="impl",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert baton.return_stack == []
    assert _event_types("baton-1") == ["create"]
    assert len(_messages("impl")) == 1


def test_pass_baton_rejects_receiver_waiting_in_return_stack(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
    )

    with pytest.raises(
        baton_service.BatonInvalidTransition,
        match="impl is waiting for this baton to come back from you",
    ):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="reviewer",
            receiver_id="impl",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "reviewer"
    assert baton.return_stack == ["impl"]
    assert _event_types("baton-1") == ["create", "pass"]
    assert len(_messages("impl")) == 1


def test_pass_baton_rejects_originator_when_return_stack_not_empty(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
    )

    with pytest.raises(
        baton_service.BatonInvalidTransition,
        match="another holder is still waiting in the return path",
    ):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="reviewer",
            receiver_id="originator",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "reviewer"
    assert baton.return_stack == ["impl"]
    assert _event_types("baton-1") == ["create", "pass"]


def test_return_baton_pops_previous_holder(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
    )

    baton = baton_service.return_baton(
        baton_id="baton-1",
        actor_id="reviewer",
        message="changes requested",
        expected_next_action="revise",
    )

    assert baton.current_holder_id == "impl"
    assert baton.return_stack == []
    assert baton.expected_next_action == "revise"
    assert _event_types("baton-1") == ["create", "pass", "return"]
    queued = _messages("impl")
    assert len(queued) == 2
    assert "changes requested" in queued[-1].body
    assert "return_baton" in queued[-1].body


def test_return_baton_with_empty_stack_returns_to_originator(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    baton = baton_service.return_baton(
        baton_id="baton-1",
        actor_id="impl",
        message="back to you",
    )

    assert baton.current_holder_id == "originator"
    assert baton.return_stack == []


def test_complete_baton_resolves_and_clears_current_holder(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    baton = baton_service.complete_baton(
        baton_id="baton-1",
        actor_id="impl",
        message="done",
    )

    assert baton.status == BatonStatus.COMPLETED.value
    assert baton.current_holder_id is None
    assert baton.completed_at is not None
    assert _event_types("baton-1") == ["create", "complete"]
    queued = _messages("originator")
    assert len(queued) == 1
    assert queued[0].sender_agent_id == "impl"
    assert "A baton has been completed" in queued[0].body
    assert "get_baton" in queued[0].body


def test_block_baton_marks_blocked_and_keeps_holder_visible(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    baton = baton_service.block_baton(
        baton_id="baton-1",
        actor_id="impl",
        reason="contract mismatch",
    )

    assert baton.status == BatonStatus.BLOCKED.value
    assert baton.current_holder_id == "impl"
    assert _event_types("baton-1") == ["create", "block"]
    queued = _messages("originator")
    assert len(queued) == 1
    assert "contract mismatch" in queued[0].body
    assert "A baton is blocked" in queued[0].body


def test_non_holder_agent_transition_fails(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    with pytest.raises(baton_service.BatonAuthorizationError):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="reviewer",
            receiver_id="other",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert _event_types("baton-1") == ["create"]


def test_completed_baton_rejects_later_agent_transition(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.complete_baton(baton_id="baton-1", actor_id="impl")

    with pytest.raises(baton_service.BatonInvalidTransition):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="impl",
            receiver_id="reviewer",
        )


def test_cancel_requires_holder_unless_operator_recovery(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    with pytest.raises(baton_service.BatonAuthorizationError):
        baton_service.cancel_baton(
            baton_id="baton-1",
            actor_id="originator",
            message="stop",
        )

    baton = baton_service.cancel_baton(
        baton_id="baton-1",
        actor_id="originator",
        message="operator stop",
        operator_recovery=True,
    )

    assert baton.status == BatonStatus.CANCELED.value
    assert baton.current_holder_id is None
    assert _event_types("baton-1") == ["create", "cancel"]


def test_reassign_requires_holder_unless_operator_recovery_and_preserves_stack(patched_db):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )
    baton_service.pass_baton(
        baton_id="baton-1",
        actor_id="impl",
        receiver_id="reviewer",
    )

    with pytest.raises(baton_service.BatonAuthorizationError):
        baton_service.reassign_baton(
            baton_id="baton-1",
            actor_id="originator",
            receiver_id="replacement",
        )

    baton = baton_service.reassign_baton(
        baton_id="baton-1",
        actor_id="originator",
        receiver_id="replacement",
        expected_next_action="take over review",
        operator_recovery=True,
    )

    assert baton.status == BatonStatus.ACTIVE.value
    assert baton.current_holder_id == "replacement"
    assert baton.return_stack == ["impl"]
    assert baton.expected_next_action == "take over review"
    assert _event_types("baton-1") == ["create", "pass", "reassign"]


def test_create_baton_rolls_back_if_initial_message_enqueue_fails(patched_db, monkeypatch):
    def fail_enqueue(*args, **kwargs):
        raise RuntimeError("inbox unavailable")

    monkeypatch.setattr(baton_service, "send_inbox_message", fail_enqueue)

    with pytest.raises(RuntimeError, match="inbox unavailable"):
        baton_service.create_baton(
            baton_id="baton-1",
            title="T01",
            originator_id="originator",
            holder_id="impl",
            message="start",
        )

    assert db_module.get_baton_record("baton-1") is None
    assert _event_types("baton-1") == []


def test_pass_baton_rolls_back_state_if_transfer_message_enqueue_fails(patched_db, monkeypatch):
    baton_service.create_baton(
        baton_id="baton-1",
        title="T01",
        originator_id="originator",
        holder_id="impl",
    )

    def fail_enqueue(*args, **kwargs):
        raise RuntimeError("inbox unavailable")

    monkeypatch.setattr(baton_service, "send_inbox_message", fail_enqueue)

    with pytest.raises(RuntimeError, match="inbox unavailable"):
        baton_service.pass_baton(
            baton_id="baton-1",
            actor_id="impl",
            receiver_id="reviewer",
            message="please review",
        )

    baton = db_module.get_baton_record("baton-1")
    assert baton.current_holder_id == "impl"
    assert baton.return_stack == []
    assert _event_types("baton-1") == ["create"]
    assert _messages("reviewer") == []
