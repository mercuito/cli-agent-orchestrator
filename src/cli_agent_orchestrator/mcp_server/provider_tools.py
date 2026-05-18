"""FastMCP registration for CAO-mediated provider tools."""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from fastmcp.tools.base import Tool, ToolResult
from pydantic import PrivateAttr

from cli_agent_orchestrator.agent import AgentRegistry
from cli_agent_orchestrator.services.agent_manager import (
    AgentManager,
    default_agent_manager,
)
from cli_agent_orchestrator.workspace_providers.invocation import (
    ProviderMediatedToolAccessDenied,
    ProviderMediatedToolInvocationService,
    TerminalMetadataResolver,
)
from cli_agent_orchestrator.workspace_providers.registry import (
    WorkspaceProviderConfigError,
    load_enabled_provider_tool_access_policies,
)
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderToolAccessConfigError,
    ProviderToolAccessPolicy,
)

logger = logging.getLogger(__name__)


class ProviderMediatedMCPTool(Tool):
    """Named FastMCP tool backed by CAO's provider-mediated invocation lifecycle."""

    _terminal_id: str = PrivateAttr()
    _provider_name: str = PrivateAttr()
    _tool_name: str = PrivateAttr()
    _invocation_service: ProviderMediatedToolInvocationService = PrivateAttr()

    def __init__(
        self,
        *,
        terminal_id: str,
        provider_name: str,
        tool_name: str,
        invocation_service: ProviderMediatedToolInvocationService,
        **tool_data: Any,
    ) -> None:
        super().__init__(**tool_data)
        self._terminal_id = terminal_id
        self._provider_name = provider_name
        self._tool_name = tool_name
        self._invocation_service = invocation_service

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        result = self._invocation_service.invoke(
            terminal_id=self._terminal_id,
            provider_name=self._provider_name,
            tool_name=self._tool_name,
            arguments=arguments,
        )
        return ToolResult(content=result)


def register_provider_mediated_mcp_tools_for_terminal(
    *,
    terminal_id: str,
    mcp_instance: Any,
    reserved_tool_names: Iterable[str] = (),
) -> list[str]:
    """Load provider access and register agent-visible provider tools.

    This is the production MCP startup boundary. Invalid provider config is
    surfaced clearly; unavailable provider/access loading hides mediated tools
    while leaving built-in CAO MCP registration untouched.
    """
    try:
        agent_manager = default_agent_manager()
        agent_registry = AgentRegistry({agent.id: agent for agent in agent_manager.list_agents()})
        policies = load_enabled_provider_tool_access_policies(agent_registry=agent_registry)
    except (ProviderToolAccessConfigError, WorkspaceProviderConfigError):
        logger.exception("Provider-mediated MCP tool configuration is invalid")
        raise
    except Exception:
        logger.exception(
            "Provider-mediated MCP tool registration failed while loading provider access; "
            "continuing with built-in CAO MCP tools only"
        )
        return []

    return register_provider_mediated_mcp_tools(
        terminal_id=terminal_id,
        mcp_instance=mcp_instance,
        policies=policies,
        agent_registry=agent_registry,
        agent_manager=agent_manager,
        reserved_tool_names=reserved_tool_names,
    )


def register_provider_mediated_mcp_tools(
    *,
    terminal_id: str,
    mcp_instance: Any,
    policies: Mapping[str, ProviderToolAccessPolicy],
    agent_registry: AgentRegistry,
    agent_manager: AgentManager | None = None,
    reserved_tool_names: Iterable[str] = (),
    terminal_metadata_resolver: TerminalMetadataResolver | None = None,
) -> list[str]:
    """Register provider-mediated tools visible to one MCP terminal."""
    service = ProviderMediatedToolInvocationService(
        policies=policies,
        agent_registry=agent_registry,
        agent_manager=agent_manager,
        terminal_metadata_resolver=terminal_metadata_resolver,
    )
    try:
        visible_tools = service.accessible_tools_for_terminal(terminal_id)
    except ProviderMediatedToolAccessDenied as exc:
        logger.info(
            "No provider-mediated MCP tools registered for terminal %r: %s",
            terminal_id,
            exc.reason,
        )
        return []
    except Exception:
        logger.exception(
            "Provider-mediated MCP tool registration failed while resolving terminal %r; "
            "continuing with built-in CAO MCP tools only",
            terminal_id,
        )
        return []

    reserved = set(reserved_tool_names)
    registered: list[str] = []
    seen_provider_tool_names: set[str] = set()
    for provider_name, tool in visible_tools:
        if tool.name in reserved:
            logger.error(
                "Provider-mediated MCP tool %r from provider %r conflicts with a built-in "
                "CAO MCP tool; skipping provider tool",
                tool.name,
                provider_name,
            )
            continue
        if tool.name in seen_provider_tool_names:
            logger.error(
                "Provider-mediated MCP tool name %r is exposed by multiple provider policies; "
                "skipping duplicate",
                tool.name,
            )
            continue
        mcp_instance.add_tool(
            ProviderMediatedMCPTool(
                name=tool.name,
                description=tool.description,
                parameters=dict(tool.input_schema),
                terminal_id=terminal_id,
                provider_name=provider_name,
                tool_name=tool.name,
                invocation_service=service,
            )
        )
        seen_provider_tool_names.add(tool.name)
        registered.append(tool.name)
    return registered


__all__ = [
    "register_provider_mediated_mcp_tools",
    "register_provider_mediated_mcp_tools_for_terminal",
]
