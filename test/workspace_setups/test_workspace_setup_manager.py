from __future__ import annotations

from dataclasses import dataclass

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry, AgentWorkspaceConfig
from cli_agent_orchestrator.workspace_contexts import WorkspaceContextResolution
from cli_agent_orchestrator.workspace_setups import (
    WorkspaceProviderCandidateMapping,
    WorkspaceProviderView,
    WorkspaceSetup,
    WorkspaceSetupAuthorizedMapping,
    WorkspaceSetupConfigError,
    WorkspaceSetupManager,
    WorkspaceSetupRegistry,
)


def _agent(agent_id: str, setup: str | None = None) -> Agent:
    return Agent(
        id=agent_id,
        display_name=agent_id,
        cli_provider="codex",
        workdir="/repo",
        session_name=agent_id,
        prompt="",
        workspace=AgentWorkspaceConfig(setup=setup),
    )


@dataclass(frozen=True)
class Event:
    agent_key: str


class RecordingProviderAdapter:
    provider_name = "test"

    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        return (
            WorkspaceProviderCandidateMapping(
                provider_name="test",
                agent_id="agent_a",
                mapping_kind="presence",
                provider_identity="app_user_id",
                provider_value="provider-a",
                payload={"agent": "agent_a"},
            ),
            WorkspaceProviderCandidateMapping(
                provider_name="test",
                agent_id="agent_b",
                mapping_kind="presence",
                provider_identity="app_user_id",
                provider_value="provider-b",
                payload={"agent": "agent_b"},
            ),
        )

    def build_provider_view(
        self,
        *,
        setup: WorkspaceSetup,
        authorized_mappings: tuple[WorkspaceSetupAuthorizedMapping, ...],
        agent_registry: AgentRegistry,
    ) -> WorkspaceProviderView:
        return WorkspaceProviderView(
            setup_id=setup.id,
            provider_name="test",
            value={mapping.provider_value: mapping.agent_id for mapping in authorized_mappings},
        )

    def resolve_event_agent_id(
        self, *, provider_view: WorkspaceProviderView, event
    ) -> tuple[str, object]:
        try:
            return provider_view.value[event.agent_key], event.agent_key
        except KeyError as exc:
            raise WorkspaceSetupConfigError("provider identity is not setup-authorized") from exc

    def describe_event_identity(self, event) -> str:
        return event.agent_key


def _resolver(_event):
    return WorkspaceContextResolution(
        workspace_context_id="wctx",
        resolver_id="linear_planning",
        boundary_provider_id="test",
        boundary_object_type="issue",
        boundary_object_id="CAO-1",
    )


def test_setup_authorizes_only_provider_candidates_for_setup_members():
    registry = AgentRegistry(
        {
            "agent_a": _agent("agent_a", "cao_delivery"),
            "agent_b": _agent("agent_b"),
        }
    )
    manager = WorkspaceSetupManager(
        setup_registry=WorkspaceSetupRegistry(
            (
                WorkspaceSetup(
                    id="cao_delivery",
                    display_name="CAO Delivery",
                    providers=("test",),
                    resolver=_resolver,
                ),
            )
        ),
        agent_registry=registry,
        provider_adapters={"test": RecordingProviderAdapter()},
    )

    view = manager.provider_view("cao_delivery", "test")

    assert view.value == {"provider-a": "agent_a"}
    assert [
        diagnostic.message
        for diagnostic in manager.diagnostics()
        if diagnostic.code == "pruned_provider_identity"
    ] == [
        "Workspace setup cao_delivery pruned test app_user_id provider-b for "
        "out-of-setup agent agent_b"
    ]


def test_manager_reports_unknown_setup_and_unavailable_provider():
    manager = WorkspaceSetupManager(
        setup_registry=WorkspaceSetupRegistry(
            (
                WorkspaceSetup(
                    id="cao_delivery",
                    display_name="CAO Delivery",
                    providers=("missing",),
                    resolver=_resolver,
                ),
            )
        ),
        agent_registry=AgentRegistry({"agent_a": _agent("agent_a", "unknown_setup")}),
        provider_adapters={},
        available_providers=(),
    )

    diagnostics = manager.diagnostics()

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "unknown_setup",
        "unavailable_provider",
    ]


def test_setup_rejects_multiple_resolvers():
    with pytest.raises(WorkspaceSetupConfigError, match="exactly one resolver"):
        WorkspaceSetup(
            id="cao_delivery",
            display_name="CAO Delivery",
            providers=("test",),
            resolver=(_resolver, _resolver),  # type: ignore[arg-type]
        )


def test_setup_rejects_non_callable_resolver():
    with pytest.raises(WorkspaceSetupConfigError, match="resolver must be callable"):
        WorkspaceSetup(
            id="cao_delivery",
            display_name="CAO Delivery",
            providers=("test",),
            resolver="linear_planning",  # type: ignore[arg-type]
        )


def test_authorized_mappings_reject_provider_outside_setup():
    manager = WorkspaceSetupManager(
        setup_registry=WorkspaceSetupRegistry(
            (
                WorkspaceSetup(
                    id="cao_delivery",
                    display_name="CAO Delivery",
                    providers=("test",),
                    resolver=_resolver,
                ),
            )
        ),
        agent_registry=AgentRegistry({"agent_a": _agent("agent_a", "cao_delivery")}),
        provider_adapters={
            "test": RecordingProviderAdapter(),
            "other": RecordingProviderAdapter(),
        },
    )

    with pytest.raises(WorkspaceSetupConfigError, match="does not include provider other"):
        manager.authorized_mappings("cao_delivery", "other")


def test_agents_without_setup_do_not_resolve_provider_events():
    manager = WorkspaceSetupManager(
        setup_registry=WorkspaceSetupRegistry(
            (
                WorkspaceSetup(
                    id="cao_delivery",
                    display_name="CAO Delivery",
                    providers=("test",),
                    resolver=_resolver,
                ),
            )
        ),
        agent_registry=AgentRegistry({"agent_a": _agent("agent_a")}),
        provider_adapters={"test": RecordingProviderAdapter()},
    )

    assert manager.resolve_event_context(_agent("agent_a"), Event("provider-a")) is None


def test_collaboration_requires_same_non_empty_setup():
    manager = WorkspaceSetupManager(
        setup_registry=WorkspaceSetupRegistry(
            (
                WorkspaceSetup(
                    id="cao_delivery",
                    display_name="CAO Delivery",
                    providers=("test",),
                    resolver=_resolver,
                ),
            )
        ),
        agent_registry=AgentRegistry({}),
        provider_adapters={"test": RecordingProviderAdapter()},
    )
    sender = _agent("agent_a", "cao_delivery")

    manager.require_same_setup_collaboration(sender=sender, receiver=_agent("agent_b", "cao_delivery"))

    with pytest.raises(WorkspaceSetupConfigError, match="sender agent_a setup cao_delivery"):
        manager.require_same_setup_collaboration(
            sender=sender,
            receiver=_agent("agent_b", "other_setup"),
        )
    with pytest.raises(WorkspaceSetupConfigError, match="receiver agent_b setup none"):
        manager.require_same_setup_collaboration(sender=sender, receiver=_agent("agent_b"))
