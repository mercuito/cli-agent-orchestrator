"""Authorization helpers for inbox notification read/reply tools."""

from __future__ import annotations

from typing import Any, Callable, Mapping, TypeVar

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.services.tool_service import ToolService
from cli_agent_orchestrator.workspace_setups import default_workspace_collaboration_manager

ErrorT = TypeVar("ErrorT", bound=Exception)


def require_inbox_notification_receiver(
    delivery: InboxDelivery,
    *,
    caller_terminal_id: str | None,
    error: Callable[[str], ErrorT],
) -> None:
    """Require the caller terminal to own the notification receiver target."""

    if not caller_terminal_id:
        raise error("caller terminal id is required to read or reply to this inbox notification")

    receiver_id = delivery.notification.receiver_id
    if receiver_id == caller_terminal_id:
        return

    metadata = db_module.get_terminal_metadata(caller_terminal_id)
    if metadata is None:
        raise error(f"caller terminal {caller_terminal_id!r} was not found")

    agent_id = metadata.get("agent_id")
    if not agent_id:
        raise error(f"caller terminal {caller_terminal_id!r} is not attached to an agent")

    agent_receiver_prefix = f"agent:{agent_id}"
    if receiver_id == agent_receiver_prefix or receiver_id.startswith(f"{agent_receiver_prefix}:"):
        return

    raise error("caller terminal is not authorized for this inbox notification")


def require_provider_inbox_authorization(
    delivery: InboxDelivery,
    *,
    caller_terminal_id: str | None,
    provider: str,
    operation: str,
    thread_metadata: Mapping[str, Any] | None = None,
    thread_raw_snapshot: Mapping[str, Any] | None = None,
    message_metadata: Mapping[str, Any] | None = None,
    message_raw_snapshot: Mapping[str, Any] | None = None,
    error: Callable[[str], ErrorT],
) -> None:
    """Require current receiver ownership and team-bound provider authorization."""

    decision = provider_inbox_authorization_decision(
        delivery,
        caller_terminal_id=caller_terminal_id,
        provider=provider,
        operation=operation,
        thread_metadata=thread_metadata,
        thread_raw_snapshot=thread_raw_snapshot,
        message_metadata=message_metadata,
        message_raw_snapshot=message_raw_snapshot,
        error=error,
    )
    if not decision.allowed:
        raise error(
            "Provider inbox notification is not authorized by ToolService: "
            f"{decision.reason}"
        )


def provider_inbox_authorization_decision(
    delivery: InboxDelivery,
    *,
    caller_terminal_id: str | None,
    provider: str,
    operation: str,
    thread_metadata: Mapping[str, Any] | None = None,
    thread_raw_snapshot: Mapping[str, Any] | None = None,
    message_metadata: Mapping[str, Any] | None = None,
    message_raw_snapshot: Mapping[str, Any] | None = None,
    error: Callable[[str], ErrorT],
):
    """Return the current ToolService provider inbox decision for this receiver."""

    require_inbox_notification_receiver(
        delivery,
        caller_terminal_id=caller_terminal_id,
        error=error,
    )
    provider_identity = provider_identity_from_metadata(
        provider,
        thread_metadata,
        thread_raw_snapshot,
        message_metadata,
        message_raw_snapshot,
    )
    if provider == "linear" and not provider_identity:
        raise error("Linear provider inbox notification is missing a current app key")
    return default_tool_service().provider_conversation_decision_for_inbox(
        delivery,
        caller_terminal_id=caller_terminal_id,
        provider=provider,
        operation=operation,
        provider_identity=provider_identity,
    )


def provider_conversation_tool_service() -> ToolService:
    """Return ToolService wired through the provider-conversation manager hook."""

    return ToolService(
        collaboration_manager_factory=lambda registry: _provider_conversation_manager(registry)
    )


def default_tool_service() -> ToolService:
    return provider_conversation_tool_service()


def provider_identity_from_metadata(
    provider: str, *values: Mapping[str, Any] | None
) -> str | None:
    """Return the provider identity used for ToolService conversation decisions."""
    if provider.strip().lower() == "linear":
        return _linear_app_key(*values)
    return None


def _provider_conversation_manager(registry: Any):
    try:
        return default_workspace_collaboration_manager(agent_registry=registry)
    except TypeError:
        return default_workspace_collaboration_manager()


def _linear_app_key(*values: Mapping[str, Any] | None) -> str | None:
    from cli_agent_orchestrator.linear.workspace_provider import normalize_app_key

    for value in values:
        found = _linear_app_key_from_nested(value)
        if found:
            return normalize_app_key(found)
    return None


def _linear_app_key_from_nested(value: Any) -> str | None:
    if isinstance(value, Mapping):
        direct = (
            value.get("_cao_linear_app_key")
            or value.get("linear_app_key")
            or value.get("app_key")
            or value.get("appKey")
        )
        if direct:
            return str(direct)
        data = value.get("data")
        if isinstance(data, Mapping):
            found = _linear_app_key_from_nested(data)
            if found:
                return found
        for item in value.values():
            found = _linear_app_key_from_nested(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _linear_app_key_from_nested(item)
            if found:
                return found
    return None
