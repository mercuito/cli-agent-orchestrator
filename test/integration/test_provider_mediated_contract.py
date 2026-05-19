"""End-to-end proof for CAO-mediated provider MCP tools."""

from __future__ import annotations

from test.support.fake_provider_tools import (
    FAKE_LOOKUP_TOOL,
    FAKE_PROVIDER_NAME,
    FAKE_RESTRICTED_TOOL,
    FakeProvider,
    FakeProviderRecorder,
    fake_agents,
    fake_provider_bad_config,
    fake_provider_config,
)
from unittest.mock import Mock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from cli_agent_orchestrator.agent import load_agent_registry, write_agent
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.mcp_server import server
from cli_agent_orchestrator.mcp_server.provider_tools import register_provider_mediated_mcp_tools
from cli_agent_orchestrator.workspace_providers import (
    ProviderToolAccessConfigError,
    ProviderToolAccessIssue,
    WorkspaceProviderRegistry,
    load_enabled_provider_tool_access_policies,
)
from cli_agent_orchestrator.workspace_providers.invocation import (
    ProviderMediatedToolAccessDenied,
    ProviderMediatedToolInvocationService,
)


def _write_workspace_provider_files(tmp_path):
    enabled_config = tmp_path / "workspace-providers.toml"
    enabled_config.write_text('enabled = ["fake"]\n')
    agents_root = tmp_path / "agents"
    for agent in fake_agents().values():
        write_agent(agent, agents_root=agents_root)
    return enabled_config, agents_root


def _fake_provider_registry(
    recorder: FakeProviderRecorder,
    provider_config,
) -> WorkspaceProviderRegistry:
    registry = WorkspaceProviderRegistry()
    registry.register(
        FAKE_PROVIDER_NAME,
        lambda agents: FakeProvider(provider_config, agents, recorder),
    )
    return registry


def _persist_contract_terminals() -> None:
    db_module.create_terminal(
        "terminal-a",
        "cao-session",
        "window-a",
        "codex",
        "agent_a",
        workspace_context_id=db_module.ensure_default_workspace_context("agent_a").id,
    )
    db_module.create_terminal(
        "terminal-b",
        "cao-session",
        "window-b",
        "codex",
        "agent_b",
        workspace_context_id=db_module.ensure_default_workspace_context("agent_b").id,
    )
    db_module.create_terminal(
        "raw-terminal",
        "cao-session",
        "window-raw",
        "codex",
        "unknown_agent",
        "wctx_raw",
    )


async def _registered_tool_names(mcp: FastMCP) -> set[str]:
    return {tool.name for tool in await mcp.list_tools()}


@pytest.mark.asyncio
async def test_fake_provider_contract_runs_through_mcp_registration_and_invocation(
    tmp_path,
    runtime_inbox_db_session,
):
    enabled_config, agents_config = _write_workspace_provider_files(tmp_path)
    recorder = FakeProviderRecorder(mutate_post_result=True)
    agent_registry = load_agent_registry(agents_config)
    policies = load_enabled_provider_tool_access_policies(
        enabled_config_path=enabled_config,
        agents_config_path=agents_config,
        registry=_fake_provider_registry(recorder, fake_provider_config()),
    )
    _persist_contract_terminals()

    mcp_a = FastMCP("provider-contract-a", mask_error_details=False)
    registered_a = register_provider_mediated_mcp_tools(
        terminal_id="terminal-a",
        mcp_instance=mcp_a,
        policies=policies,
        agent_registry=agent_registry,
        reserved_tool_names={name for name, _, _ in server._PENDING_TOOLS},
    )

    assert registered_a == [FAKE_LOOKUP_TOOL, FAKE_RESTRICTED_TOOL]
    assert await _registered_tool_names(mcp_a) == {FAKE_LOOKUP_TOOL, FAKE_RESTRICTED_TOOL}

    result = await mcp_a.call_tool(FAKE_LOOKUP_TOOL, {"query": "alpha"})

    assert result.content[0].text == '{"provider":"result"}'
    assert recorder.handler_result == {"provider": "result"}
    assert recorder.events == [
        f"pre_call:always_allow:{FAKE_LOOKUP_TOOL}",
        f"handler:agent_a:{FAKE_LOOKUP_TOOL}:alpha",
        f"post_call:record_after:{FAKE_LOOKUP_TOOL}:result",
    ]

    with pytest.raises(ToolError, match="Provider-mediated tool call denied by pre-call hook"):
        await mcp_a.call_tool(FAKE_RESTRICTED_TOOL, {"query": "beta"})

    assert recorder.events == [
        f"pre_call:always_allow:{FAKE_LOOKUP_TOOL}",
        f"handler:agent_a:{FAKE_LOOKUP_TOOL}:alpha",
        f"post_call:record_after:{FAKE_LOOKUP_TOOL}:result",
        f"pre_call:deny_before:{FAKE_RESTRICTED_TOOL}",
    ]

    for terminal_id in ("terminal-b", "raw-terminal"):
        mcp = FastMCP(f"provider-contract-{terminal_id}", mask_error_details=False)
        registered = register_provider_mediated_mcp_tools(
            terminal_id=terminal_id,
            mcp_instance=mcp,
            policies=policies,
            agent_registry=agent_registry,
            reserved_tool_names={name for name, _, _ in server._PENDING_TOOLS},
        )

        assert registered == []
        assert await _registered_tool_names(mcp) == set()

    service = ProviderMediatedToolInvocationService(
        policies=policies,
        agent_registry=agent_registry,
    )
    with pytest.raises(ProviderMediatedToolAccessDenied) as agent_b_denial:
        service.invoke(
            terminal_id="terminal-b",
            provider_name=FAKE_PROVIDER_NAME,
            tool_name=FAKE_LOOKUP_TOOL,
            arguments={"query": "gamma"},
        )
    assert agent_b_denial.value.reason == "missing_tool_access"

    with pytest.raises(ProviderMediatedToolAccessDenied) as raw_terminal_denial:
        service.invoke(
            terminal_id="raw-terminal",
            provider_name=FAKE_PROVIDER_NAME,
            tool_name=FAKE_LOOKUP_TOOL,
            arguments={"query": "delta"},
        )
    assert raw_terminal_denial.value.reason == "unmapped_agent"


@pytest.mark.asyncio
async def test_provider_preflight_failure_stops_mcp_startup_before_serving_tools(
    tmp_path,
    runtime_inbox_db_session,
    monkeypatch,
):
    enabled_config, agents_config = _write_workspace_provider_files(tmp_path)
    recorder = FakeProviderRecorder()
    _persist_contract_terminals()

    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        load_enabled_provider_tool_access_policies(
            enabled_config_path=enabled_config,
            agents_config_path=agents_config,
            registry=_fake_provider_registry(recorder, fake_provider_bad_config()),
        )

    assert "partners.bad_discovery" in str(exc_info.value)
    assert "unknown provider-mediated tool: cao_fake.missing" in str(exc_info.value)
    assert "partners.bad_discovery.pre_hooks[0]" in str(exc_info.value)
    assert "unknown hook: missing_hook" in str(exc_info.value)

    mcp = FastMCP("provider-contract-builtins", mask_error_details=False)
    monkeypatch.setenv("CAO_TERMINAL_ID", "terminal-a")
    monkeypatch.setattr(server, "mcp", mcp)
    run = Mock()
    monkeypatch.setattr(mcp, "run", run)
    monkeypatch.setattr(
        server,
        "register_provider_mediated_mcp_tools_for_terminal",
        lambda **kwargs: (_ for _ in ()).throw(
            ProviderToolAccessConfigError(
                FAKE_PROVIDER_NAME,
                [ProviderToolAccessIssue("partners.bad_discovery", "bad provider config")],
            )
        ),
    )

    with pytest.raises(ProviderToolAccessConfigError, match="bad provider config"):
        server.main()

    assert await _registered_tool_names(mcp) == set()
    run.assert_not_called()
