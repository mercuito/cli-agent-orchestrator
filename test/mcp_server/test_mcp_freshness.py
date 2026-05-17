"""Tests for agent-visible MCP freshness descriptors."""

from __future__ import annotations

from typing import Any, Mapping

from cli_agent_orchestrator.agent import Agent, AgentRegistry
from cli_agent_orchestrator.mcp_server.freshness import (
    build_agent_mcp_runtime_generation_fingerprint,
    build_agent_mcp_surface_descriptor,
    callable_runtime_fingerprint,
    fingerprint_agent_mcp_surface,
)
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderMediatedToolDefinition,
    ProviderToolAccessRequest,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
    normalize_provider_tool_access,
)


def _builtin_lookup(query: str) -> str:
    """Lookup built-in data."""
    return query


def _builtin_hidden(query: str) -> str:
    """Hidden built-in data."""
    return query


def _local_runtime_dependency() -> str:
    return "runtime dependency"


def _wrapper_with_runtime_dependency() -> str:
    return _local_runtime_dependency()


def _handler(
    context: ProviderToolInvocationContext, arguments: Mapping[str, Any]
) -> dict[str, Any]:
    return {"handled": context.tool_name, "arguments": dict(arguments)}


def _hook(context: ProviderToolInvocationContext) -> ProviderToolPreCallResult | None:
    if context.phase == ProviderToolHookPhase.PRE_CALL:
        return ProviderToolPreCallResult.allow()
    return None


def _agent(agent_id: str = "agent_a") -> Agent:
    return Agent(
        id=agent_id,
        display_name="Agent A",
        cli_provider="codex",
        workdir="/repo",
        session_name="agent-a",
        prompt="",
    )


def _agents() -> AgentRegistry:
    agent_a = _agent("agent_a")
    agent_b = _agent("agent_b")
    return AgentRegistry({agent_a.id: agent_a, agent_b.id: agent_b})


def _provider_tool(
    name: str,
    *,
    description: str = "Lookup fake provider data.",
    schema: Mapping[str, Any] | None = None,
    runtime_generation: Mapping[str, Any] | None = None,
) -> ProviderMediatedToolDefinition:
    return ProviderMediatedToolDefinition(
        name=name,
        description=description,
        input_schema=schema
        or {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=_handler,
        runtime_generation=runtime_generation or {"version": "v1"},
    )


def _policy(
    *,
    visible_tool: ProviderMediatedToolDefinition | None = None,
    hidden_tool: ProviderMediatedToolDefinition | None = None,
    pre_hooks: tuple[str, ...] = ("always_allow",),
    post_hooks: tuple[str, ...] = ("record_after",),
):
    visible_tool = visible_tool or _provider_tool("cao_fake.lookup")
    hidden_tool = hidden_tool or _provider_tool("cao_fake.hidden")
    return normalize_provider_tool_access(
        provider_name="fake",
        tools=(visible_tool, hidden_tool),
        hooks=(
            ProviderToolHookDefinition(
                name="always_allow",
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=_hook,
            ),
            ProviderToolHookDefinition(
                name="deny_before",
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=_hook,
            ),
            ProviderToolHookDefinition(
                name="record_after",
                phases=frozenset({ProviderToolHookPhase.POST_CALL}),
                handler=_hook,
            ),
        ),
        access_requests=(
            ProviderToolAccessRequest(
                tool_name=visible_tool.name,
                agent_id="agent_a",
                pre_hooks=pre_hooks,
                post_hooks=post_hooks,
                location="tool_access.visible",
            ),
            ProviderToolAccessRequest(
                tool_name=hidden_tool.name,
                agent_id="agent_b",
                location="tool_access.hidden",
            ),
        ),
        agent_registry=_agents(),
    )


def _surface_fingerprint(
    *,
    policy=None,
    builtin_allowlist: list[str] | None = None,
) -> str:
    return fingerprint_agent_mcp_surface(
        build_agent_mcp_surface_descriptor(
            agent=_agent(),
            built_in_tools=(("builtin_lookup", _builtin_lookup, {}),),
            built_in_tool_allowlist=builtin_allowlist,
            provider_policies={"fake": policy or _policy()},
            baton_enabled=False,
        )
    )


def _runtime_generation_fingerprint(
    *,
    policy=None,
    builtin_generation: Mapping[str, Any] | None = None,
) -> str:
    return build_agent_mcp_runtime_generation_fingerprint(
        agent=_agent(),
        built_in_tools=(
            ("builtin_lookup", _builtin_lookup, {}),
            ("builtin_hidden", _builtin_hidden, {}),
        ),
        built_in_tool_allowlist=["builtin_lookup"],
        provider_policies={"fake": policy or _policy()},
        baton_enabled=False,
        built_in_runtime_generation=builtin_generation or {"server": "v1"},
    )


def test_surface_descriptor_includes_visible_builtin_and_provider_contracts():
    descriptor = build_agent_mcp_surface_descriptor(
        agent=_agent(),
        built_in_tools=(("builtin_lookup", _builtin_lookup, {}),),
        built_in_tool_allowlist=["builtin_lookup"],
        provider_policies={"fake": _policy()},
        baton_enabled=False,
    )

    assert [tool["name"] for tool in descriptor["tools"]] == [
        "builtin_lookup",
        "cao_fake.lookup",
    ]
    provider_tool = descriptor["tools"][1]
    assert provider_tool["source"] == {"kind": "provider", "name": "fake"}
    assert provider_tool["pre_hooks"] == ["always_allow"]
    assert provider_tool["post_hooks"] == ["record_after"]
    assert "runtime_generation" not in provider_tool


def test_provider_tool_cannot_occupy_reserved_hidden_builtin_name():
    descriptor = build_agent_mcp_surface_descriptor(
        agent=_agent(),
        built_in_tools=(("builtin_hidden", _builtin_hidden, {}),),
        built_in_tool_allowlist=[],
        provider_policies={"fake": _policy(visible_tool=_provider_tool("builtin_hidden"))},
        baton_enabled=False,
    )

    assert descriptor["tools"] == []


def test_surface_fingerprint_changes_for_visible_contract_changes():
    baseline = _surface_fingerprint()

    assert baseline != _surface_fingerprint(
        policy=_policy(
            visible_tool=_provider_tool(
                "cao_fake.lookup",
                description="Lookup fake provider data with a new contract.",
            )
        )
    )
    assert baseline != _surface_fingerprint(
        policy=_policy(
            visible_tool=_provider_tool(
                "cao_fake.lookup",
                schema={
                    "type": "object",
                    "properties": {"query": {"type": "integer"}},
                    "required": ["query"],
                },
            )
        )
    )
    assert baseline != _surface_fingerprint(policy=_policy(pre_hooks=("deny_before",)))


def test_surface_fingerprint_ignores_hidden_tool_contract_changes():
    baseline = _surface_fingerprint()

    changed_hidden = _surface_fingerprint(
        policy=_policy(
            hidden_tool=_provider_tool(
                "cao_fake.hidden",
                description="This hidden tool changed but agent_a cannot see it.",
                schema={
                    "required": ["body"],
                    "properties": {"body": {"type": "string"}},
                    "type": "object",
                },
            )
        )
    )

    assert changed_hidden == baseline


def test_surface_fingerprint_canonicalizes_equivalent_schema_ordering():
    schema_a = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
    }
    schema_b = {
        "required": ["query"],
        "properties": {"limit": {"type": "integer"}, "query": {"type": "string"}},
        "type": "object",
    }

    assert _surface_fingerprint(
        policy=_policy(visible_tool=_provider_tool("cao_fake.lookup", schema=schema_a))
    ) == _surface_fingerprint(
        policy=_policy(visible_tool=_provider_tool("cao_fake.lookup", schema=schema_b))
    )


def test_builtin_allowlist_changes_surface_fingerprint():
    assert _surface_fingerprint(builtin_allowlist=["builtin_lookup"]) != _surface_fingerprint(
        builtin_allowlist=[]
    )


def test_runtime_generation_fingerprint_changes_for_visible_runtime_material_only():
    baseline = _runtime_generation_fingerprint()

    visible_changed = _runtime_generation_fingerprint(
        policy=_policy(
            visible_tool=_provider_tool(
                "cao_fake.lookup",
                runtime_generation={"version": "v2"},
            )
        )
    )
    hidden_changed = _runtime_generation_fingerprint(
        policy=_policy(
            hidden_tool=_provider_tool(
                "cao_fake.hidden",
                runtime_generation={"version": "hidden-v2"},
            )
        )
    )

    assert visible_changed != baseline
    assert hidden_changed == baseline


def test_builtin_runtime_generation_changes_runtime_generation_fingerprint():
    assert _runtime_generation_fingerprint(
        builtin_generation={"server": "v1"}
    ) != _runtime_generation_fingerprint(builtin_generation={"server": "v2"})


def test_builtin_runtime_generation_ignores_hidden_builtin_material():
    baseline = _runtime_generation_fingerprint(
        builtin_generation={
            "tools": {
                "builtin_lookup": {"version": "visible-v1"},
                "builtin_hidden": {"version": "hidden-v1"},
            }
        }
    )
    hidden_changed = _runtime_generation_fingerprint(
        builtin_generation={
            "tools": {
                "builtin_lookup": {"version": "visible-v1"},
                "builtin_hidden": {"version": "hidden-v2"},
            }
        }
    )

    assert hidden_changed == baseline


def test_callable_runtime_fingerprint_includes_local_helper_dependencies():
    material = callable_runtime_fingerprint(_wrapper_with_runtime_dependency)
    entries = {entry["qualname"] for entry in material["entries"]}

    assert "_wrapper_with_runtime_dependency" in entries
    assert "_local_runtime_dependency" in entries
