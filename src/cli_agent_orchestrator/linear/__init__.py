"""Linear integration surface for CAO."""

from __future__ import annotations

from typing import Any

from cli_agent_orchestrator.inbox.models import Notification
from cli_agent_orchestrator.inbox.source_registry import register_reply_handler

PROVIDER_CONVERSATION_INBOX_SOURCE_KIND = "provider_conversation"


def _reply_to_provider_conversation(
    notification: Notification,
    body: str,
    caller_agent_id: str,
) -> Any:
    from cli_agent_orchestrator.linear.reply_handler import reply_to_provider_conversation

    return reply_to_provider_conversation(notification, body, caller_agent_id)


register_reply_handler(
    PROVIDER_CONVERSATION_INBOX_SOURCE_KIND,
    _reply_to_provider_conversation,
)
