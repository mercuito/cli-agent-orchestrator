"""CAO-owned agent identity configuration and lookup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import tomli

from cli_agent_orchestrator.constants import CAO_HOME_DIR

AGENTS_CONFIG_PATH = CAO_HOME_DIR / "agents.toml"


class AgentIdentityConfigError(ValueError):
    """Raised when CAO agent identity configuration is invalid."""


@dataclass(frozen=True)
class AgentIdentity:
    """Durable CAO identity mapped to terminal runtime configuration."""

    id: str
    display_name: str
    agent_profile: str
    cli_provider: str
    workdir: str
    session_name: str


class AgentIdentityRegistry:
    """Lookup table for durable CAO agent identities."""

    def __init__(self, identities: Mapping[str, AgentIdentity]) -> None:
        self._identities = dict(identities)

    def get(self, agent_id: str) -> AgentIdentity:
        try:
            return self._identities[agent_id]
        except KeyError as exc:
            raise AgentIdentityConfigError(f"Unknown CAO agent identity: {agent_id}") from exc

    def has(self, agent_id: str) -> bool:
        return agent_id in self._identities

    def all(self) -> dict[str, AgentIdentity]:
        return dict(self._identities)


def _require_str(table: Mapping[str, object], key: str, *, agent_id: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentIdentityConfigError(f"agents.{agent_id}.{key} must be a non-empty string")
    return value.strip()


def load_agent_identity_registry(
    config_path: Optional[Path] = None,
) -> AgentIdentityRegistry:
    """Load ``agents.toml`` into a CAO identity registry.

    Missing config is valid and returns an empty registry; workspace providers
    that reference identities still fail during their own validation.
    """
    path = AGENTS_CONFIG_PATH if config_path is None else config_path
    if not path.exists():
        return AgentIdentityRegistry({})

    try:
        data = tomli.loads(path.read_text())
    except tomli.TOMLDecodeError as exc:
        raise AgentIdentityConfigError(f"Invalid agents.toml: {exc}") from exc

    agents = data.get("agents")
    if agents is None:
        return AgentIdentityRegistry({})
    if not isinstance(agents, Mapping):
        raise AgentIdentityConfigError("agents.toml must contain an [agents] table")

    identities: dict[str, AgentIdentity] = {}
    for raw_agent_id, raw_config in agents.items():
        agent_id = str(raw_agent_id).strip()
        if not agent_id:
            raise AgentIdentityConfigError("CAO agent identity id must be non-empty")
        if agent_id in identities:
            raise AgentIdentityConfigError(f"Duplicate CAO agent identity: {agent_id}")
        if not isinstance(raw_config, Mapping):
            raise AgentIdentityConfigError(f"agents.{agent_id} must be a table")
        identities[agent_id] = AgentIdentity(
            id=agent_id,
            display_name=_require_str(raw_config, "display_name", agent_id=agent_id),
            agent_profile=_require_str(raw_config, "agent_profile", agent_id=agent_id),
            cli_provider=_require_str(raw_config, "cli_provider", agent_id=agent_id),
            workdir=_require_str(raw_config, "workdir", agent_id=agent_id),
            session_name=_require_str(raw_config, "session_name", agent_id=agent_id),
        )

    return AgentIdentityRegistry(identities)
