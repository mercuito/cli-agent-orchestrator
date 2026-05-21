"""Tests for the source-agnostic inbox read API."""

from __future__ import annotations

import pytest

from cli_agent_orchestrator.clients.database import create_inbox_notification_event
from cli_agent_orchestrator.inbox import NotReplyable, PlainSource, read, reply, send


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


def test_unregistered_source_kind_reply_raises_not_replyable(runtime_inbox_db_session):
    # Given
    notification = create_inbox_notification_event(
        "agent:receiver-agent",
        "Baton event payload.",
        source_kind="baton",
        source_id="baton-1",
    )

    # When / Then
    with pytest.raises(NotReplyable, match="source_kind 'baton' is not replyable"):
        reply(notification.id, "Reply body", caller_agent_id="receiver-agent")
