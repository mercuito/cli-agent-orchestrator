"""Tests for provider-mediated tool access preflight and normalization."""

from __future__ import annotations

from test.support.fake_provider_tools import fake_provider_access_requests_from_config
from typing import Any, Mapping

import pytest

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.workspace_providers import (
    ProviderMediatedToolDefinition,
    ProviderToolAccessConfigError,
    ProviderToolAccessRequest,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
    WorkspaceProviderConfigError,
    load_provider_tool_access_policies,
    normalize_provider_tool_access,
)


def _handler(
    context: ProviderToolInvocationContext, arguments: Mapping[str, Any]
) -> dict[str, bool]:
    return {"handled": True}


def _hook(context: ProviderToolInvocationContext) -> ProviderToolPreCallResult | None:
    if context.phase == ProviderToolHookPhase.PRE_CALL:
        return ProviderToolPreCallResult.allow()
    return None


def _agents() -> AgentIdentityRegistry:
    return AgentIdentityRegistry(
        {
            "identity_a": AgentIdentity(
                id="identity_a",
                display_name="Identity A",
                agent_profile="developer",
                cli_provider="codex",
                workdir="/repo",
                session_name="identity-a",
            ),
            "identity_b": AgentIdentity(
                id="identity_b",
                display_name="Identity B",
                agent_profile="reviewer",
                cli_provider="codex",
                workdir="/repo",
                session_name="identity-b",
            ),
            "identity_c": AgentIdentity(
                id="identity_c",
                display_name="Identity C",
                agent_profile="developer",
                cli_provider="codex",
                workdir="/repo",
                session_name="identity-c",
            ),
        }
    )


def _tools() -> tuple[ProviderMediatedToolDefinition, ...]:
    return (
        ProviderMediatedToolDefinition(
            name="cao_fake.lookup",
            description="Lookup fake provider data",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            handler=_handler,
        ),
        ProviderMediatedToolDefinition(
            name="cao_fake.write",
            description="Write fake provider data",
            input_schema={"type": "object", "properties": {"body": {"type": "string"}}},
            handler=_handler,
        ),
    )


def _hooks() -> tuple[ProviderToolHookDefinition, ...]:
    return (
        ProviderToolHookDefinition(
            name="always_allow",
            phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
            handler=_hook,
        ),
        ProviderToolHookDefinition(
            name="record_after",
            phases=frozenset({ProviderToolHookPhase.POST_CALL}),
            handler=_hook,
        ),
        ProviderToolHookDefinition(
            name="audit_both",
            phases=frozenset({ProviderToolHookPhase.PRE_CALL, ProviderToolHookPhase.POST_CALL}),
            handler=_hook,
        ),
    )


def _normalize(
    requests: tuple[ProviderToolAccessRequest, ...],
    *,
    profile_exists=lambda profile: profile in {"developer", "reviewer"},
):
    return normalize_provider_tool_access(
        provider_name="fake",
        tools=_tools(),
        hooks=_hooks(),
        access_requests=requests,
        agent_registry=_agents(),
        profile_exists=profile_exists,
    )


class FakeProvider:
    """Test provider with intentionally provider-native config vocabulary."""

    name = "fake"

    def __init__(
        self,
        provider_config: Mapping[str, Mapping[str, Any]],
        agent_registry: AgentIdentityRegistry,
        *,
        profile_exists=None,
    ) -> None:
        self._provider_config = provider_config
        self._agent_registry = agent_registry
        self._profile_exists = profile_exists or (
            lambda profile: profile in {"developer", "reviewer"}
        )

    def initialize(self) -> None:
        self._policy = normalize_provider_tool_access(
            provider_name=self.name,
            tools=_tools(),
            hooks=_hooks(),
            access_requests=self._access_requests_from_provider_config(),
            agent_registry=self._agent_registry,
            profile_exists=self._profile_exists,
        )

    def provider_tool_access(self):
        return self._policy

    def _access_requests_from_provider_config(self) -> tuple[ProviderToolAccessRequest, ...]:
        return fake_provider_access_requests_from_config(self._provider_config)


def _fake_provider_config(
    *,
    kind: str = "agent",
    target: str = "identity_a",
    capability: str = "cao_fake.lookup",
    before: tuple[str, ...] = ("always_allow",),
    after: tuple[str, ...] = (),
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "partners": {
            "discovery": {
                "kind": kind,
                "target": target,
                "capability": capability,
                "before": list(before),
                "after": list(after),
            }
        }
    }


def _initialize_fake_provider(
    provider_config: Mapping[str, Mapping[str, Any]],
    *,
    profile_exists=None,
) -> FakeProvider:
    provider = FakeProvider(provider_config, _agents(), profile_exists=profile_exists)
    provider.initialize()
    return provider


def test_fake_provider_config_normalizes_to_identity_scoped_tool_access():
    provider = _initialize_fake_provider(
        {
            "partners": {
                "discovery": {
                    "kind": "agent",
                    "target": "identity_a",
                    "capability": "cao_fake.lookup",
                    "before": ["always_allow"],
                    "after": ["record_after"],
                },
                "developers": {
                    "kind": "role_template",
                    "target": "developer",
                    "capability": "cao_fake.write",
                    "before": ["audit_both"],
                },
            }
        }
    )

    policy = load_provider_tool_access_policies([provider])["fake"]

    identity_a = _agents().get("identity_a")
    identity_b = _agents().get("identity_b")
    identity_c = _agents().get("identity_c")
    assert policy.can_identity_access_tool(identity_a, "cao_fake.lookup")
    assert policy.can_identity_access_tool(identity_a, "cao_fake.write")
    assert not policy.can_identity_access_tool(identity_b, "cao_fake.lookup")
    assert not policy.can_identity_access_tool(identity_b, "cao_fake.write")
    assert policy.can_identity_access_tool(identity_c, "cao_fake.write")
    write_access = [entry for entry in policy.access if entry.tool_name == "cao_fake.write"]
    assert {entry.agent_identity_id for entry in write_access} == {"identity_a", "identity_c"}
    assert {entry.source_location for entry in write_access} == {"partners.developers"}


def test_unknown_tool_fails_preflight_with_config_location():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(_fake_provider_config(capability="cao_fake.missing"))

    message = str(exc_info.value)
    assert "partners.discovery" in message
    assert "unknown provider-mediated tool: cao_fake.missing" in message


def test_unknown_hook_fails_preflight_with_config_location():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(_fake_provider_config(before=("missing_hook",)))

    message = str(exc_info.value)
    assert "partners.discovery.pre_hooks[0]" in message
    assert "unknown hook: missing_hook" in message


def test_unsupported_hook_phase_fails_preflight_with_config_location():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(
            _fake_provider_config(before=("record_after",), after=("always_allow",))
        )

    message = str(exc_info.value)
    assert "partners.discovery.pre_hooks[0]" in message
    assert "hook record_after does not support phase pre_call" in message
    assert "partners.discovery.post_hooks[0]" in message
    assert "hook always_allow does not support phase post_call" in message


def test_identity_reference_must_resolve_before_access_is_exposed():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(_fake_provider_config(target="missing_identity"))

    assert "partners.discovery.agent_identity_id" in str(exc_info.value)
    assert "unknown CAO agent identity: missing_identity" in str(exc_info.value)


def test_profile_reference_must_resolve_before_access_is_exposed():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(
            _fake_provider_config(kind="role_template", target="missing_profile"),
            profile_exists=lambda profile: profile != "missing_profile",
        )

    assert "partners.discovery.agent_profile" in str(exc_info.value)
    assert "unknown CAO agent profile: missing_profile" in str(exc_info.value)


def test_profile_without_configured_identities_fails_preflight():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(
            _fake_provider_config(kind="role_template", target="unused_profile"),
            profile_exists=lambda profile: profile == "unused_profile",
        )

    assert "partners.discovery.agent_profile" in str(exc_info.value)
    assert "no configured CAO agent identities use profile: unused_profile" in str(exc_info.value)


def test_duplicate_effective_identity_tool_access_fails_preflight():
    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        _initialize_fake_provider(
            {
                "partners": {
                    "discovery": {
                        "kind": "agent",
                        "target": "identity_a",
                        "capability": "cao_fake.lookup",
                        "before": ["always_allow"],
                    },
                    "developers": {
                        "kind": "role_template",
                        "target": "developer",
                        "capability": "cao_fake.lookup",
                        "before": ["audit_both"],
                    },
                }
            }
        )

    message = str(exc_info.value)
    assert "partners.developers" in message
    assert (
        "duplicates or conflicts with provider tool access entry at partners.discovery" in message
    )
    assert "identity identity_a and tool cao_fake.lookup" in message


def test_access_entries_may_omit_pre_call_hooks():
    provider = _initialize_fake_provider(_fake_provider_config(before=()))
    access = provider.provider_tool_access().access

    assert len(access) == 1
    assert access[0].pre_hooks == ()
    assert access[0].agent_identity_id == "identity_a"


def test_duplicate_provider_tool_access_policy_names_fail_clearly():
    class StaticProvider:
        name = "fake"

        def __init__(self):
            self._policy = _normalize(
                (
                    ProviderToolAccessRequest(
                        tool_name="cao_fake.lookup",
                        agent_identity_id="identity_a",
                        pre_hooks=("always_allow",),
                        location="partners.discovery",
                    ),
                )
            )

        def initialize(self):
            pass

        def provider_tool_access(self):
            return self._policy

    with pytest.raises(WorkspaceProviderConfigError, match="Duplicate provider tool access policy"):
        load_provider_tool_access_policies([StaticProvider(), StaticProvider()])
