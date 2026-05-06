"""Tests for routing Linear agent sessions into CAO terminals."""

from __future__ import annotations

from unittest.mock import Mock

from cli_agent_orchestrator.agent_identity import AgentIdentity
from cli_agent_orchestrator.linear import runtime
from cli_agent_orchestrator.linear.workspace_provider import LinearPresence, LinearResolvedPresence
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    PresenceEvent,
)


def _presence_event(
    *,
    action: str = "created",
    thread_id: str = "session-1",
    prompt_context: str | None = None,
    prompt_body: str | None = None,
) -> PresenceEvent:
    return PresenceEvent(
        provider="linear",
        event_type="AgentSessionEvent",
        action=action,
        thread=ConversationThread(
            ref=ExternalRef(provider="linear", id=thread_id),
            prompt_context=prompt_context,
        ),
        message=ConversationMessage(kind="prompt", body=prompt_body) if prompt_body else None,
        raw_payload={"action": action},
    )


def _resolved_presence(
    *,
    app_key: str = "implementation_partner",
    agent_id: str = "implementation_partner",
    session_name: str = "implementation-partner",
    agent_profile: str = "developer",
    cli_provider: str = "codex",
    workdir: str = "/repo",
) -> LinearResolvedPresence:
    return LinearResolvedPresence(
        presence=LinearPresence(
            presence_id=app_key,
            agent_id=agent_id,
            app_key=app_key,
            app_user_name="Implementation Partner",
        ),
        identity=AgentIdentity(
            id=agent_id,
            display_name="Implementation Partner",
            agent_profile=agent_profile,
            cli_provider=cli_provider,
            workdir=workdir,
            session_name=session_name,
        ),
    )


def test_build_terminal_message_uses_prompt_context():
    event = _presence_event(prompt_context='<issue identifier="CAO-13"><title>Demo</title></issue>')

    message = runtime.build_terminal_message(event)

    assert "Action: created" in message
    assert "Conversation thread ID: session-1" in message
    assert '<issue identifier="CAO-13">' in message


def test_build_terminal_message_uses_prompted_body():
    event = _presence_event(action="prompted", prompt_body="Can you scope this?")

    message = runtime.build_terminal_message(event)

    assert "Action: prompted" in message
    assert "User prompt:" in message
    assert "Can you scope this?" in message


def test_ensure_discovery_terminal_reuses_existing_terminal(monkeypatch):
    terminal = {"id": "terminal-1", "tmux_session": "cao-linear-discovery-partner"}
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: _resolved_presence(session_name="linear-discovery-partner"),
    )
    monkeypatch.setattr(runtime.tmux_client, "session_exists", lambda session: True)
    monkeypatch.setattr(runtime, "list_terminals_by_session", lambda session: [terminal])
    create_terminal = Mock()
    monkeypatch.setattr(runtime.terminal_service, "create_terminal", create_terminal)

    assert runtime.ensure_discovery_terminal() == terminal
    create_terminal.assert_not_called()


def test_terminal_config_comes_from_cao_identity_mapping(monkeypatch):
    created = Mock(
        id="terminal-1",
        session_name="cao-implementation-partner",
        name="developer-1234",
        provider=Mock(value="codex"),
        agent_profile="developer",
    )
    monkeypatch.setattr(runtime.tmux_client, "session_exists", lambda session: False)
    monkeypatch.setattr(runtime, "list_terminals_by_session", lambda session: [])
    create_terminal = Mock(return_value=created)
    monkeypatch.setattr(runtime.terminal_service, "create_terminal", create_terminal)

    assert runtime._terminal_for_resolved_presence(_resolved_presence())["id"] == "terminal-1"
    create_terminal.assert_called_once_with(
        provider="codex",
        agent_profile="developer",
        session_name="cao-implementation-partner",
        new_session=True,
        working_directory="/repo",
    )


def test_handle_agent_session_event_updates_linear_and_sends_terminal_input(monkeypatch):
    event = _presence_event(prompt_context="<issue/>")
    calls = []
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: _resolved_presence())
    monkeypatch.setattr(
        runtime,
        "_terminal_for_resolved_presence",
        lambda resolved: {"id": "terminal-1"},
    )
    update_url = Mock(side_effect=lambda *args, **kwargs: calls.append("update_url"))
    create_activity = Mock(side_effect=lambda *args, **kwargs: calls.append("create_activity"))
    send_input = Mock(side_effect=lambda *args: calls.append("send_input"))
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)
    monkeypatch.setattr(runtime.terminal_service, "send_input", send_input)

    assert runtime.handle_presence_event(event) == "terminal-1"
    assert calls == ["send_input", "update_url", "create_activity"]
    update_url.assert_called_once_with(
        "session-1",
        "terminal-1",
        app_key="implementation_partner",
    )
    create_activity.assert_called_once()
    send_input.assert_called_once()


def test_handle_presence_event_uses_verified_linear_app_key(monkeypatch):
    event = _presence_event(prompt_context="<issue/>")
    event.raw_payload["_cao_linear_app_key"] = "implementation_partner"
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: _resolved_presence(app_key=event.raw_payload["_cao_linear_app_key"]),
    )
    monkeypatch.setattr(
        runtime,
        "_terminal_for_resolved_presence",
        lambda resolved: {"id": f"terminal-{resolved.presence.app_key}"},
    )
    monkeypatch.setattr(runtime.app_client, "linear_app_env", lambda app_key, name: None)
    update_url = Mock()
    create_activity = Mock()
    send_input = Mock()
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)
    monkeypatch.setattr(runtime.terminal_service, "send_input", send_input)

    assert runtime.handle_presence_event(event) == "terminal-implementation_partner"

    update_url.assert_called_once_with(
        "session-1",
        "terminal-implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called_once()
    assert create_activity.call_args.kwargs["app_key"] == "implementation_partner"
