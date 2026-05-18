"""Central CAO agent manager and read surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Optional

from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    AgentRegistry,
    load_agent_registry,
    workspace_context_data_dir,
)
from cli_agent_orchestrator.clients import database as db_module

TerminalMetadataResolver = Callable[[str], Mapping[str, object] | None]
TerminalListResolver = Callable[[], list[dict[str, object]]]


@dataclass(frozen=True)
class AgentStatus:
    """Stable CAO agent config plus current runtime status."""

    agent_id: str
    display_name: str
    cli_provider: str
    workdir: str
    session_name: str
    agent: Agent
    active: bool
    active_terminal_id: Optional[str] = None
    active_workspace_context_id: Optional[str] = None
    workspace_team_id: Optional[str] = None
    derived_workspace_setup_id: Optional[str] = None
    workspace_team_diagnostics: tuple[str, ...] = ()
    last_active_at: Optional[datetime] = None

    @classmethod
    def inactive(cls, agent: Agent) -> "AgentStatus":
        return cls(
            agent_id=agent.id,
            display_name=agent.display_name,
            cli_provider=agent.cli_provider,
            workdir=agent.workdir,
            session_name=agent.session_name,
            agent=agent,
            active=False,
            workspace_team_id=agent.workspace.team,
            derived_workspace_setup_id=_derived_workspace_setup_id(agent),
            workspace_team_diagnostics=agent.workspace.diagnostics,
        )


@dataclass(frozen=True)
class OrphanedAgentTerminalReference:
    """Terminal row that points at an agent the manager cannot resolve."""

    terminal_id: str
    agent_id: str
    workspace_context_id: Optional[str]
    last_active_at: Optional[datetime]
    reason: str = "unknown_agent"


class AgentManager:
    """Authoritative CAO surface for agent resolution and status."""

    def __init__(
        self,
        *,
        configured_agents: Optional[AgentRegistry] = None,
        terminal_lister: TerminalListResolver = db_module.list_all_terminals,
        terminal_metadata_resolver: TerminalMetadataResolver = db_module.get_terminal_metadata,
    ) -> None:
        self._configured_agents = configured_agents or load_agent_registry()
        self._terminal_lister = terminal_lister
        self._terminal_metadata_resolver = terminal_metadata_resolver
        self._registered_agents: dict[str, Agent] = {}

    def register_agent(self, agent: Agent) -> Agent:
        """Validate and register a CAO agent through the manager boundary."""
        validated = self._validate_agent(agent).without_runtime_context()
        registered = self._registered_agents.get(validated.id)
        if registered is not None and registered != validated:
            raise AgentConfigError(f"Conflicting CAO agent: {validated.id}")
        self._registered_agents[validated.id] = validated
        return validated

    def resolve_agent(self, agent_id: str) -> Agent:
        """Resolve one CAO agent from registered or configured state."""
        normalized = _required_token(agent_id, "agent_id")
        registered = self._registered_agents.get(normalized)
        if registered is not None:
            return registered
        return self._configured_agents.get(normalized)

    def require_registered_agent(self, agent: Agent) -> Agent:
        """Return the manager-known agent matching ``agent`` or fail closed."""
        resolved = self.resolve_agent(agent.id)
        if resolved.without_runtime_context() != agent.without_runtime_context():
            raise AgentConfigError(f"CAO agent {agent.id!r} does not match the manager-owned agent")
        return resolved

    def agent_for_terminal(self, terminal_id: str) -> Agent:
        """Resolve a terminal's manager-owned CAO agent or fail clearly."""
        metadata = self._terminal_metadata_resolver(_required_token(terminal_id, "terminal_id"))
        if metadata is None:
            raise AgentConfigError(f"Unknown terminal: {terminal_id}")
        agent_id = _terminal_agent_id(metadata)
        try:
            return self.resolve_agent(agent_id)
        except AgentConfigError as exc:
            raise AgentConfigError(
                f"Terminal {terminal_id!r} references unknown CAO agent: {agent_id}"
            ) from exc

    def list_agents(self) -> tuple[Agent, ...]:
        """List configured and registered agents."""
        agents = self._configured_agents.all()
        agents.update(self._registered_agents)
        return tuple(agents[key] for key in sorted(agents))

    def status_for_agent(self, agent_id: str) -> AgentStatus:
        """Return current status for one manager-resolvable agent."""
        agent = self.resolve_agent(agent_id)
        return self._status_for(agent)

    def list_statuses(self, *, active: Optional[bool] = None) -> tuple[AgentStatus, ...]:
        """Return stable status summaries for known agents."""
        statuses = tuple(self._status_for(agent) for agent in self.list_agents())
        if active is None:
            return statuses
        return tuple(status for status in statuses if status.active is active)

    def orphaned_terminal_references(self) -> tuple[OrphanedAgentTerminalReference, ...]:
        """Return terminal agent references that cannot be manager-resolved."""
        orphans: list[OrphanedAgentTerminalReference] = []
        for terminal in self._terminal_lister():
            agent_id = _terminal_agent_id(terminal)
            try:
                self.resolve_agent(agent_id)
            except AgentConfigError:
                orphans.append(
                    OrphanedAgentTerminalReference(
                        terminal_id=str(terminal.get("id")),
                        agent_id=agent_id,
                        workspace_context_id=_optional_str(terminal.get("workspace_context_id")),
                        last_active_at=_optional_datetime(terminal.get("last_active")),
                    )
                )
        return tuple(orphans)

    def _status_for(self, agent: Agent) -> AgentStatus:
        terminals = [
            terminal
            for terminal in self._terminal_lister()
            if _terminal_agent_id(terminal) == agent.id
        ]
        if not terminals:
            return AgentStatus.inactive(agent)
        terminal = max(
            terminals,
            key=lambda item: _optional_datetime(item.get("last_active")) or datetime.min,
        )
        return AgentStatus(
            agent_id=agent.id,
            display_name=agent.display_name,
            cli_provider=agent.cli_provider,
            workdir=agent.workdir,
            session_name=agent.session_name,
            agent=agent,
            active=True,
            active_terminal_id=_optional_str(terminal.get("id")),
            active_workspace_context_id=_optional_str(terminal.get("workspace_context_id")),
            workspace_team_id=agent.workspace.team,
            derived_workspace_setup_id=_derived_workspace_setup_id(agent),
            workspace_team_diagnostics=agent.workspace.diagnostics,
            last_active_at=_optional_datetime(terminal.get("last_active")),
        )

    def _validate_agent(self, agent: Agent) -> Agent:
        _required_token(agent.id, "agent_id")
        workspace_context_data_dir(agent, "validation")
        _required_token(agent.display_name, f"agents.{agent.id}.display_name")
        _required_token(agent.cli_provider, f"agents.{agent.id}.cli_provider")
        _required_token(agent.workdir, f"agents.{agent.id}.workdir")
        _required_token(agent.session_name, f"agents.{agent.id}.session_name")
        return agent


def create_default_agent_manager(
    *,
    agents_root: Optional[Path] = None,
) -> AgentManager:
    """Create a manager wired to configured agents."""
    return AgentManager(configured_agents=load_agent_registry(agents_root))


def default_agent_manager() -> AgentManager:
    """Return a fresh default manager for current config/runtime reads."""
    return create_default_agent_manager()


def _derived_workspace_setup_id(agent: Agent) -> Optional[str]:
    if agent.workspace.team is None:
        return None
    try:
        from cli_agent_orchestrator.workspace_setups import default_workspace_team_service

        return default_workspace_team_service().setup_for_team(agent.workspace.team).id
    except Exception:
        return None


def _terminal_agent_id(metadata: Mapping[str, object]) -> str:
    value = metadata["agent_id"]
    if not isinstance(value, str):
        raise AgentConfigError("terminal agent_id must be a non-empty string")
    return _required_token(value, "terminal agent_id")


def _required_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _optional_str(value: object) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


def _optional_datetime(value: object) -> Optional[datetime]:
    return value if isinstance(value, datetime) else None
