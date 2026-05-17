"""Shared fake workspace provider for provider-mediated MCP contract tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from cli_agent_orchestrator.agent import Agent, AgentRegistry
from cli_agent_orchestrator.workspace_providers import (
    ProviderMediatedToolDefinition,
    ProviderToolAccessPolicy,
    ProviderToolAccessRequest,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
    normalize_provider_tool_access,
)

FAKE_PROVIDER_NAME = "fake"
FAKE_LOOKUP_TOOL = "cao_fake.lookup"
FAKE_RESTRICTED_TOOL = "cao_fake.restricted"


def fake_agents() -> dict[str, Agent]:
    return {
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


def fake_agent_registry() -> AgentRegistry:
    return AgentRegistry(fake_agents())


def fake_agents_toml() -> str:
    lines: list[str] = []
    for agent in fake_agents().values():
        lines.append(f"""
[agent]
id = "{agent.id}"
display_name = "{agent.display_name}"
cli_provider = "{agent.cli_provider}"
workdir = "{agent.workdir}"
session_name = "{agent.session_name}"
prompt = ""
""".strip())
    return "\n\n".join(lines) + "\n"


@dataclass
class FakeProviderRecorder:
    events: list[str] = field(default_factory=list)
    handler_result: dict[str, Any] = field(default_factory=lambda: {"provider": "result"})
    mutate_post_result: bool = False

    def handler(
        self, context: ProviderToolInvocationContext, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.events.append(
            f"handler:{context.agent.id}:{context.tool_name}:{arguments['query']}"
        )
        return self.handler_result

    def allow_hook(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult | None:
        self.events.append(f"{context.phase.value}:{context.hook_name}:{context.tool_name}")
        if context.phase == ProviderToolHookPhase.PRE_CALL:
            return ProviderToolPreCallResult.allow()
        return None

    def deny_hook(self, context: ProviderToolInvocationContext) -> ProviderToolPreCallResult:
        self.events.append(f"{context.phase.value}:{context.hook_name}:{context.tool_name}")
        return ProviderToolPreCallResult.deny(
            "fake policy denied this action",
            {"agent": context.agent.id, "tool": context.tool_name},
        )

    def post_hook(self, context: ProviderToolInvocationContext) -> None:
        self.events.append(
            f"{context.phase.value}:{context.hook_name}:{context.tool_name}:"
            f"{context.handler_result['provider']}"
        )
        if self.mutate_post_result and isinstance(context.handler_result, dict):
            context.handler_result["provider"] = "mutated"


class FakeProvider:
    """Fake provider with intentionally provider-native config vocabulary."""

    name = FAKE_PROVIDER_NAME

    def __init__(
        self,
        provider_config: Mapping[str, Mapping[str, Any]],
        agent_registry: AgentRegistry,
        recorder: FakeProviderRecorder,
    ) -> None:
        self._provider_config = provider_config
        self._agent_registry = agent_registry
        self._recorder = recorder
        self._policy: ProviderToolAccessPolicy | None = None

    def initialize(self) -> None:
        self._policy = normalize_provider_tool_access(
            provider_name=self.name,
            tools=self._tools(),
            hooks=self._hooks(),
            access_requests=self._access_requests_from_provider_config(),
            agent_registry=self._agent_registry,
            profile_exists=lambda profile: profile in {"developer", "reviewer"},
        )

    def provider_tool_access(self) -> ProviderToolAccessPolicy:
        assert self._policy is not None
        return self._policy

    def _tools(self) -> tuple[ProviderMediatedToolDefinition, ...]:
        return (
            ProviderMediatedToolDefinition(
                name=FAKE_LOOKUP_TOOL,
                description="Lookup fake provider data",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=self._recorder.handler,
            ),
            ProviderMediatedToolDefinition(
                name=FAKE_RESTRICTED_TOOL,
                description="Exercise fake provider denial",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=self._recorder.handler,
            ),
        )

    def _hooks(self) -> tuple[ProviderToolHookDefinition, ...]:
        return (
            ProviderToolHookDefinition(
                name="always_allow",
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._recorder.allow_hook,
            ),
            ProviderToolHookDefinition(
                name="deny_before",
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._recorder.deny_hook,
            ),
            ProviderToolHookDefinition(
                name="record_after",
                phases=frozenset({ProviderToolHookPhase.POST_CALL}),
                handler=self._recorder.post_hook,
            ),
        )

    def _access_requests_from_provider_config(self) -> tuple[ProviderToolAccessRequest, ...]:
        return fake_provider_access_requests_from_config(self._provider_config)


def fake_provider_access_requests_from_config(
    provider_config: Mapping[str, Mapping[str, Any]],
) -> tuple[ProviderToolAccessRequest, ...]:
    requests: list[ProviderToolAccessRequest] = []
    for partner_name, partner_config in provider_config["partners"].items():
        target_kind = partner_config["kind"]
        target_value = partner_config["target"]
        requests.append(
            ProviderToolAccessRequest(
                tool_name=partner_config["capability"],
                agent_id=target_value if target_kind == "agent" else None,
                pre_hooks=tuple(partner_config.get("before", ())),
                post_hooks=tuple(partner_config.get("after", ())),
                location=f"partners.{partner_name}",
            )
        )
    return tuple(requests)


def fake_provider_config() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "partners": {
            "discovery": {
                "kind": "agent",
                "target": "agent_a",
                "capability": FAKE_LOOKUP_TOOL,
                "before": ["always_allow"],
                "after": ["record_after"],
            },
            "restricted": {
                "kind": "agent",
                "target": "agent_a",
                "capability": FAKE_RESTRICTED_TOOL,
                "before": ["deny_before"],
            },
        }
    }


def fake_provider_bad_config() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "partners": {
            "bad_discovery": {
                "kind": "agent",
                "target": "agent_a",
                "capability": "cao_fake.missing",
                "before": ["missing_hook"],
            }
        }
    }
