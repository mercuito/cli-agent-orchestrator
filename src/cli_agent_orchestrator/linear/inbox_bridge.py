"""Linear composition for bridging persisted presence events into CAO inboxes."""

from __future__ import annotations

import logging
from typing import Optional

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.presence.inbox_bridge import (
    PresenceInboxNotification,
    create_notification_for_persisted_event,
)
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent
from cli_agent_orchestrator.services import inbox_service

logger = logging.getLogger(__name__)

LINEAR_PRESENCE_INBOX_RECEIVER_ENV = "LINEAR_PRESENCE_INBOX_RECEIVER_ID"


def resolve_receiver_id(receiver_id: Optional[str] = None) -> Optional[str]:
    """Return the explicitly supplied or configured receiver terminal id."""

    if receiver_id:
        return receiver_id
    return app_client.linear_env(LINEAR_PRESENCE_INBOX_RECEIVER_ENV)


def notify_receiver_for_persisted_event(
    persisted_event: Optional[PersistedPresenceEvent],
    *,
    receiver_id: Optional[str] = None,
    attempt_delivery: bool = True,
) -> Optional[PresenceInboxNotification]:
    """Create a provider-neutral inbox notification for a Linear text event.

    Receiver selection stays explicit for this slice. Non-message events and
    activity records without a text body are ignored here so the legacy smoke
    runtime can continue to handle any remaining non-text behavior.
    """

    if persisted_event is None or persisted_event.message is None:
        return None
    if not persisted_event.message.body:
        return None

    resolved_receiver_id = resolve_receiver_id(receiver_id)
    if not resolved_receiver_id:
        return None

    notification = create_notification_for_persisted_event(
        persisted_event,
        receiver_id=resolved_receiver_id,
    )
    if notification.created and attempt_delivery:
        try:
            inbox_service.check_and_send_pending_messages(resolved_receiver_id)
        except Exception as exc:
            logger.warning(
                "Immediate Linear presence inbox delivery failed for %s: %s",
                resolved_receiver_id,
                exc,
            )
    return notification
