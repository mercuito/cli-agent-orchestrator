from __future__ import annotations

from datetime import datetime

from cli_agent_orchestrator.inbox.models import Notification, ReadResult
from cli_agent_orchestrator.mcp_server.server import (
    _inbox_read_result_to_dict,
    built_in_cao_tool_names,
)
from cli_agent_orchestrator.models.inbox import MessageStatus


def test_read_inbox_result_returns_body_only() -> None:
    result = ReadResult(
        notification=Notification(
            id=42,
            sender_agent_id="implementation_partner",
            receiver_agent_id="reviewer",
            body="Please review this.",
            status=MessageStatus.PENDING,
            created_at=datetime(2026, 5, 20, 12, 0, 0),
        ),
        body="Please review this.",
    )

    assert _inbox_read_result_to_dict(result) == {
        "success": True,
        "body": "Please review this.",
    }


def test_reply_to_inbox_message_is_not_a_builtin_tool() -> None:
    assert "read_inbox_message" in built_in_cao_tool_names(include_disabled=True)
    assert "reply_to_inbox_message" not in built_in_cao_tool_names(include_disabled=True)
