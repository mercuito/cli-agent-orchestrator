"""Tests for MCP registration of provider-mediated tools."""

from __future__ import annotations

from typing import Any, Mapping

import pytest
from fastmcp import FastMCP

from cli_agent_orchestrator.agent import Agent, AgentRegistry
from cli_agent_orchestrator.mcp_server.provider_tools import (
    register_provider_mediated_mcp_tools,
    register_provider_mediated_mcp_tools_for_terminal,
)
from cli_agent_orchestrator.workspace_tool_providers import (
    ProviderMediatedToolDefinition,
    ProviderToolAccessRequest,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
    WorkspaceToolProviderConfigError,
    normalize_provider_tool_access,
)


def _agents() -> AgentRegistry:
    return AgentRegistry(
        {
            "agent_a": Agent(
                id="agent_a",
                display_name="Agent A",
                cli_provider="codex",
                workdir="/repo",
                session_name="agent-a",
                prompt="",
            ),
            "agent_b": Agent(
                id="agent_b",
                display_name="Agent B",
                cli_provider="codex",
                workdir="/repo",
                session_name="agent-b",
                prompt="",
            ),
        }
    )


class _FakeAgentManager:
    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def list_agents(self):
        return tuple(self.registry.all().values())

    def resolve_agent(self, agent_id: str):
        return self.registry.get(agent_id)


class FakeProviderTool:
    def __init__(self) -> None:
        self.events: list[str] = []

    def handler(
        self, context: ProviderToolInvocationContext, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.events.append(f"handler:{context.agent.id}:{arguments['query']}")
        return {"agent": context.agent.id, "query": arguments["query"]}

    def hook(self, context: ProviderToolInvocationContext) -> ProviderToolPreCallResult:
        self.events.append(f"{context.phase.value}:{context.hook_name}")
        return ProviderToolPreCallResult.allow()


def _policy(fake_tool: FakeProviderTool):
    return normalize_provider_tool_access(
        provider_name="fake",
        tools=(
            ProviderMediatedToolDefinition(
                name="cao_fake.lookup",
                description="Lookup fake provider data",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=fake_tool.handler,
            ),
        ),
        hooks=(
            ProviderToolHookDefinition(
                name="always_allow",
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=fake_tool.hook,
            ),
        ),
        access_requests=(
            ProviderToolAccessRequest(
                tool_name="cao_fake.lookup",
                agent_id="agent_a",
                pre_hooks=("always_allow",),
                location="partners.discovery",
            ),
        ),
        agent_registry=_agents(),
    )


def _terminal_metadata(terminal_id: str) -> Mapping[str, Any] | None:
    return {
        "terminal-a": {"id": "terminal-a", "agent_id": "agent_a"},
        "terminal-b": {"id": "terminal-b", "agent_id": "agent_b"},
        "raw-terminal": {"id": "raw-terminal", "agent_id": None},
    }.get(terminal_id)


@pytest.mark.asyncio
async def test_registers_named_provider_tool_for_agent_managed_terminal():
    fake_tool = FakeProviderTool()
    mcp = FastMCP("test-provider-tools", mask_error_details=False)

    registered = register_provider_mediated_mcp_tools(
        terminal_id="terminal-a",
        mcp_instance=mcp,
        policies={"fake": _policy(fake_tool)},
        agent_registry=_agents(),
        terminal_metadata_resolver=_terminal_metadata,
    )

    assert registered == ["cao_fake.lookup"]
    listed = {tool.name: tool for tool in await mcp.list_tools()}
    assert listed["cao_fake.lookup"].parameters == {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    result = await mcp.call_tool("cao_fake.lookup", {"query": "alpha"})

    assert result.content[0].text == '{"agent":"agent_a","query":"alpha"}'
    assert fake_tool.events == ["pre_call:always_allow", "handler:agent_a:alpha"]


@pytest.mark.parametrize("terminal_id", ("terminal-b", "raw-terminal", "missing-terminal"))
def test_provider_tools_fail_closed_at_registration_for_unavailable_access(terminal_id: str):
    fake_tool = FakeProviderTool()
    mcp = FastMCP("test-provider-tools")

    registered = register_provider_mediated_mcp_tools(
        terminal_id=terminal_id,
        mcp_instance=mcp,
        policies={"fake": _policy(fake_tool)},
        agent_registry=_agents(),
        terminal_metadata_resolver=_terminal_metadata,
    )

    assert registered == []
    assert fake_tool.events == []


@pytest.mark.asyncio
async def test_provider_registration_does_not_change_builtin_registration_semantics():
    fake_tool = FakeProviderTool()
    mcp = FastMCP("test-provider-tools", mask_error_details=False)

    @mcp.tool("send_message")
    def send_message(message: str) -> str:
        return message

    registered = register_provider_mediated_mcp_tools(
        terminal_id="raw-terminal",
        mcp_instance=mcp,
        policies={"fake": _policy(fake_tool)},
        agent_registry=_agents(),
        terminal_metadata_resolver=_terminal_metadata,
    )

    assert registered == []
    result = await mcp.call_tool("send_message", {"message": "still here"})
    assert result.content[0].text == "still here"


def test_provider_tools_do_not_override_builtin_tool_names():
    fake_tool = FakeProviderTool()
    mcp = FastMCP("test-provider-tools")

    registered = register_provider_mediated_mcp_tools(
        terminal_id="terminal-a",
        mcp_instance=mcp,
        policies={"fake": _policy(fake_tool)},
        agent_registry=_agents(),
        reserved_tool_names={"cao_fake.lookup"},
        terminal_metadata_resolver=_terminal_metadata,
    )

    assert registered == []


def test_provider_policy_loading_failure_hides_provider_tools(monkeypatch):
    mcp = FastMCP("test-provider-tools")
    monkeypatch.setattr(
        "cli_agent_orchestrator.mcp_server.provider_tools.default_agent_manager",
        lambda: _FakeAgentManager(_agents()),
    )
    service = _FailingProviderPolicyService(RuntimeError("provider config unavailable"))

    registered = register_provider_mediated_mcp_tools_for_terminal(
        terminal_id="terminal-a",
        mcp_instance=mcp,
        tool_service=service,
    )

    assert registered == []


def test_provider_config_failure_is_surfaced(monkeypatch):
    mcp = FastMCP("test-provider-tools")
    monkeypatch.setattr(
        "cli_agent_orchestrator.mcp_server.provider_tools.default_agent_manager",
        lambda: _FakeAgentManager(_agents()),
    )
    service = _FailingProviderPolicyService(WorkspaceToolProviderConfigError("bad provider config"))

    with pytest.raises(WorkspaceToolProviderConfigError, match="bad provider config"):
        register_provider_mediated_mcp_tools_for_terminal(
            terminal_id="terminal-a",
            mcp_instance=mcp,
            tool_service=service,
        )


class _FailingProviderPolicyService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def provider_policies(self):
        raise self.exc
