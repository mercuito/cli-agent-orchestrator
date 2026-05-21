"""Tests for the source-agnostic inbox read API."""

from __future__ import annotations

from cli_agent_orchestrator.inbox import PlainSource, read, send


def test_plain_notification_read_returns_body_metadata_and_replyability(
    runtime_inbox_db_session, monkeypatch
):
    # Given
    monkeypatch.setattr(
        "cli_agent_orchestrator.inbox.readiness.check_and_send_pending_messages",
        lambda _receiver_agent_id: False,
    )
    notification = send(
        "receiver-agent",
        "Can you review this?",
        source=PlainSource("sender-agent"),
    )

    # When
    result = read(notification.id, caller_agent_id="receiver-agent")

    # Then
    assert result.notification.id == notification.id
    assert result.body == "Can you review this?"
    assert result.metadata == {}
    assert result.can_reply is True
