"""Linear-owned workspace setup adapter."""

from __future__ import annotations

from cli_agent_orchestrator.agent import AgentRegistry
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.linear.workspace_events import LinearIssueContextEvent
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearProviderConfig,
    LinearWorkspaceProviderConfigError,
    _extract_app_key,
    _extract_app_user_id,
    _extract_app_user_name,
    _linear_presence_from_agent,
    _linear_tool_access_from_agent,
    validate_linear_provider_config,
)
from cli_agent_orchestrator.workspace_setups import (
    WorkspaceProviderCandidateMapping,
    WorkspaceProviderView,
    WorkspaceSetup,
    WorkspaceSetupConfigError,
    WorkspaceTeam,
    WorkspaceTeamAuthorizedMapping,
)


class LinearWorkspaceSetupAdapter:
    """Build team-bound Linear provider views from Linear agent config."""

    provider_name = "linear"

    def build_candidate_mappings(
        self, agent_registry: AgentRegistry
    ) -> tuple[WorkspaceProviderCandidateMapping, ...]:
        mappings: list[WorkspaceProviderCandidateMapping] = []
        for agent in agent_registry.all().values():
            presence = _linear_presence_from_agent(agent)
            if presence is not None:
                mappings.append(
                    WorkspaceProviderCandidateMapping(
                        provider_name=self.provider_name,
                        agent_id=agent.id,
                        mapping_kind="presence",
                        provider_identity="app_key",
                        provider_value=presence.app_key,
                        payload=presence,
                    )
                )
                if presence.app_user_id:
                    mappings.append(
                        WorkspaceProviderCandidateMapping(
                            provider_name=self.provider_name,
                            agent_id=agent.id,
                            mapping_kind="presence_alias",
                            provider_identity="app_user_id",
                            provider_value=presence.app_user_id,
                            payload=presence,
                        )
                    )
                if presence.app_user_name:
                    mappings.append(
                        WorkspaceProviderCandidateMapping(
                            provider_name=self.provider_name,
                            agent_id=agent.id,
                            mapping_kind="presence_alias",
                            provider_identity="app_user_name",
                            provider_value=presence.app_user_name,
                            payload=presence,
                        )
                    )
            for access in _linear_tool_access_from_agent(agent):
                mappings.append(
                    WorkspaceProviderCandidateMapping(
                        provider_name=self.provider_name,
                        agent_id=agent.id,
                        mapping_kind="tool_access",
                        provider_identity="tool_access",
                        provider_value=access.location,
                        payload=access,
                    )
                )
        return tuple(mappings)

    def build_provider_view(
        self,
        *,
        team: WorkspaceTeam,
        setup: WorkspaceSetup,
        authorized_mappings: tuple[WorkspaceTeamAuthorizedMapping, ...],
        agent_registry: AgentRegistry,
    ) -> WorkspaceProviderView:
        presences = {
            mapping.payload.presence_id: mapping.payload
            for mapping in authorized_mappings
            if mapping.mapping_kind in {"presence", "presence_alias"}
        }
        tool_access = {
            mapping.payload.location: mapping.payload
            for mapping in authorized_mappings
            if mapping.mapping_kind == "tool_access"
        }
        config = LinearProviderConfig(
            public_url=None,
            presences=presences,
            tool_access=tool_access,
            agent_policies_enabled=False,
            source=f"workspace_team:{team.id}:setup:{setup.id}",
        )
        try:
            validate_linear_provider_config(config, agent_registry=agent_registry)
        except LinearWorkspaceProviderConfigError as exc:
            raise WorkspaceSetupConfigError(str(exc)) from exc
        return WorkspaceProviderView(
            team_id=team.id,
            setup_id=setup.id,
            provider_name=self.provider_name,
            value=config,
        )

    def resolve_event_agent_id(
        self,
        *,
        provider_view: WorkspaceProviderView,
        event: CaoEvent,
    ) -> tuple[str, object]:
        config = provider_view.value
        if not isinstance(config, LinearProviderConfig):
            raise WorkspaceSetupConfigError("Linear provider view has invalid config")
        if not isinstance(event, LinearIssueContextEvent):
            raise WorkspaceSetupConfigError("Linear setup can only resolve Linear issue events")
        try:
            presence = _resolve_presence_from_config(config, event)
        except LinearWorkspaceProviderConfigError as exc:
            raise WorkspaceSetupConfigError(str(exc)) from exc
        return presence.agent_id, presence

    def describe_event_identity(self, event: CaoEvent) -> str:
        if isinstance(event, LinearIssueContextEvent):
            return (
                f"app_key={event.app_key or 'unknown'}, "
                f"app_user_id={event.app_user_id or 'unknown'}, "
                f"app_user_name={event.app_user_name or 'unknown'}"
            )
        payload = getattr(event, "raw_payload", None)
        if isinstance(payload, dict):
            return (
                f"app_key={_extract_app_key(payload) or 'unknown'}, "
                f"app_user_id={_extract_app_user_id(payload) or 'unknown'}, "
                f"app_user_name={_extract_app_user_name(payload) or 'unknown'}"
            )
        return "unknown"


def _resolve_presence_from_config(config: LinearProviderConfig, event: LinearIssueContextEvent):
    presence = None
    if event.app_key:
        presence = config.presence_by_app_key(event.app_key)
        if presence is None:
            raise LinearWorkspaceProviderConfigError(f"Unknown Linear app key: {event.app_key}")
    if event.app_user_id:
        by_user = config.presence_by_app_user_id(event.app_user_id)
        if by_user is None and presence is None:
            raise LinearWorkspaceProviderConfigError(
                f"Unknown Linear app user id: {event.app_user_id}"
            )
        if by_user is not None and presence is not None and presence != by_user:
            raise LinearWorkspaceProviderConfigError(
                "Linear app key and app user id resolve to different CAO identities"
            )
        if by_user is not None:
            presence = by_user
    if event.app_user_name:
        by_name = config.presence_by_app_user_name(event.app_user_name)
        if by_name is not None and presence is not None and presence != by_name:
            raise LinearWorkspaceProviderConfigError(
                "Linear app key and app user name resolve to different CAO identities"
            )
        if presence is None:
            presence = by_name
    if presence is None:
        raise LinearWorkspaceProviderConfigError(
            "Linear presence could not be resolved from app key or app user id"
        )
    return presence
