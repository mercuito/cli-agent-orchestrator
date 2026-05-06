"""Built-in presence-provider registration owned by the presence boundary."""

from __future__ import annotations

from cli_agent_orchestrator.presence.manager import (
    UnknownPresenceProviderError,
    presence_provider_manager,
)


def ensure_builtin_presence_provider(provider_name: str) -> None:
    """Register a built-in presence provider when CAO ships an adapter for it."""

    try:
        presence_provider_manager.get_provider(provider_name)
        return
    except UnknownPresenceProviderError:
        pass

    if provider_name == "linear":
        presence_provider_manager.register_provider("linear", _create_linear_presence_provider())
        return

    raise UnknownPresenceProviderError(f"Unknown presence provider: {provider_name}")


def _create_linear_presence_provider():
    from cli_agent_orchestrator.linear.presence_provider import LinearPresenceProvider

    return LinearPresenceProvider()
