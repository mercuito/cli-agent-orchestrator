"""Tests for the agent-to-agent inbox read API."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.inbox import InboxReadError, read, send


def test_notification_read_returns_body_for_receiver_agent(
    runtime_inbox_db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages",
        lambda _receiver_agent_id: False,
    )
    notification = send(
        "receiver-agent",
        "Can you review this?",
        sender_agent_id="sender-agent",
    )

    result = read(notification.id, caller_agent_id="receiver-agent")

    assert result.notification.id == notification.id
    assert result.notification.sender_agent_id == "sender-agent"
    assert result.notification.receiver_agent_id == "receiver-agent"
    assert result.body == "Can you review this?"


def test_notification_read_rejects_non_receiver_agent(
    runtime_inbox_db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages",
        lambda _receiver_agent_id: False,
    )
    notification = send(
        "receiver-agent",
        "Can you review this?",
        sender_agent_id="sender-agent",
    )

    with pytest.raises(InboxReadError, match="not authorized"):
        read(notification.id, caller_agent_id="other-agent")


def test_notification_read_rejects_legacy_agent_alias_receiver(
    runtime_inbox_db_session, monkeypatch
) -> None:
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages",
        lambda _receiver_agent_id: False,
    )
    notification = send(
        "agent:receiver-agent:context:old",
        "Legacy alias should not authorize reads.",
        sender_agent_id="sender-agent",
    )

    with pytest.raises(InboxReadError, match="not authorized"):
        read(notification.id, caller_agent_id="receiver-agent")
