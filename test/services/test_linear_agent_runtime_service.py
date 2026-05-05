"""Tests for routing Linear agent sessions into CAO terminals."""

from __future__ import annotations

from unittest.mock import Mock

from cli_agent_orchestrator.linear import runtime
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


def test_build_terminal_message_uses_prompt_context():
    event = _presence_event(
        prompt_context='<issue identifier="CAO-13"><title>Demo</title></issue>'
    )

    message = runtime.build_terminal_message(event)

    assert "Action: created" in message
    assert "Conversation thread ID: session-1" in message
    assert "<issue identifier=\"CAO-13\">" in message


def test_build_terminal_message_uses_prompted_body():
    event = _presence_event(action="prompted", prompt_body="Can you scope this?")

    message = runtime.build_terminal_message(event)

    assert "Action: prompted" in message
    assert "User prompt:" in message
    assert "Can you scope this?" in message


def test_ensure_discovery_terminal_reuses_existing_terminal(monkeypatch):
    terminal = {"id": "terminal-1", "tmux_session": "cao-linear-discovery-partner"}
    monkeypatch.setattr(runtime.tmux_client, "session_exists", lambda session: True)
    monkeypatch.setattr(runtime, "list_terminals_by_session", lambda session: [terminal])
    create_terminal = Mock()
    monkeypatch.setattr(runtime.terminal_service, "create_terminal", create_terminal)

    assert runtime.ensure_discovery_terminal() == terminal
    create_terminal.assert_not_called()


def test_ensure_discovery_terminal_creates_terminal(monkeypatch):
    created = Mock(
        id="terminal-1",
        session_name="cao-linear-discovery-partner",
        name="developer-1234",
        provider=Mock(value="codex"),
        agent_profile="developer",
    )
    monkeypatch.setattr(runtime.tmux_client, "session_exists", lambda session: False)
    monkeypatch.setattr(runtime, "list_terminals_by_session", lambda session: [])
    monkeypatch.setattr(runtime, "_provider", lambda: "codex")
    monkeypatch.setattr(runtime, "_agent_profile", lambda: "developer")
    monkeypatch.setattr(runtime, "_working_directory", lambda: "/repo")
    create_terminal = Mock(return_value=created)
    monkeypatch.setattr(runtime.terminal_service, "create_terminal", create_terminal)

    assert runtime.ensure_discovery_terminal()["id"] == "terminal-1"
    create_terminal.assert_called_once_with(
        provider="codex",
        agent_profile="developer",
        session_name="cao-linear-discovery-partner",
        new_session=True,
        working_directory="/repo",
    )


def test_handle_agent_session_event_updates_linear_and_sends_terminal_input(monkeypatch):
    event = _presence_event(prompt_context="<issue/>")
    calls = []
    monkeypatch.setattr(runtime, "ensure_discovery_terminal", lambda: {"id": "terminal-1"})
    update_url = Mock(side_effect=lambda *args: calls.append("update_url"))
    create_activity = Mock(side_effect=lambda *args: calls.append("create_activity"))
    send_input = Mock(side_effect=lambda *args: calls.append("send_input"))
    monkeypatch.setattr(runtime.app_client, "update_agent_session_external_url", update_url)
    monkeypatch.setattr(runtime.app_client, "create_agent_activity", create_activity)
    monkeypatch.setattr(runtime.terminal_service, "send_input", send_input)

    assert runtime.handle_presence_event(event) == "terminal-1"
    assert calls == ["send_input", "update_url", "create_activity"]
    update_url.assert_called_once_with("session-1", "terminal-1")
    create_activity.assert_called_once()
    send_input.assert_called_once()
