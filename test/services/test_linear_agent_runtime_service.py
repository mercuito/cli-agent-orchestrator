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
    handle = Mock()
    handle.ensure_started.return_value.as_terminal_metadata.return_value = terminal
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: _resolved_presence(session_name="linear-discovery-partner"),
    )
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)

    assert runtime.ensure_discovery_terminal() == terminal
    handle.ensure_started.assert_called_once()


def test_terminal_config_comes_from_cao_identity_mapping(monkeypatch):
    handle = Mock()
    handle.ensure_started.return_value.as_terminal_metadata.return_value = {"id": "terminal-1"}
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)

    assert runtime._terminal_for_resolved_presence(_resolved_presence())["id"] == "terminal-1"
    handle.ensure_started.assert_called_once()


def test_handle_agent_session_event_updates_linear_and_sends_terminal_input(monkeypatch):
    event = _presence_event(prompt_context="<issue/>")
    calls = []
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-1",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(runtime, "_resolve_linear_event", lambda event: _resolved_presence())
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    update_url = Mock(side_effect=lambda *args, **kwargs: calls.append("update_url"))
    create_activity = Mock(side_effect=lambda *args, **kwargs: calls.append("create_activity"))
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    assert runtime.handle_presence_event(event) == "terminal-1"
    assert calls == ["update_url", "create_activity"]
    handle.notify.assert_called_once()
    assert handle.notify.call_args.kwargs["source_kind"] == runtime.LINEAR_RUNTIME_SOURCE_KIND
    update_url.assert_called_once_with(
        "session-1",
        "terminal-1",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called_once()


def test_handle_presence_event_uses_verified_linear_app_key(monkeypatch):
    event = _presence_event(prompt_context="<issue/>")
    event.raw_payload["_cao_linear_app_key"] = "implementation_partner"
    handle = Mock()
    handle.notify.return_value = Mock(
        terminal_id="terminal-implementation_partner",
        status=Mock(value="idle"),
        notification=Mock(created=True),
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_linear_event",
        lambda event: _resolved_presence(app_key=event.raw_payload["_cao_linear_app_key"]),
    )
    monkeypatch.setattr(runtime, "_runtime_handle_for_resolved_presence", lambda resolved: handle)
    monkeypatch.setattr(runtime.app_client, "linear_app_env", lambda app_key, name: None)
    update_url = Mock()
    create_activity = Mock()
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)

    assert runtime.handle_presence_event(event) == "terminal-implementation_partner"

    update_url.assert_called_once_with(
        "session-1",
        "terminal-implementation_partner",
        agent_id="implementation_partner",
        app_key="implementation_partner",
    )
    create_activity.assert_called_once()
    assert create_activity.call_args.kwargs["app_key"] == "implementation_partner"
    assert handle.notify.call_args.kwargs["sender_id"] == "linear:implementation_partner"
