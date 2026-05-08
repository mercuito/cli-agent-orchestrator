"""CAO-owned agent identity configuration and lookup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import tomli

from cli_agent_orchestrator.constants import CAO_HOME_DIR

AGENTS_CONFIG_PATH = CAO_HOME_DIR / "agents.toml"
AGENT_IDENTITY_DATA_ROOT = CAO_HOME_DIR / "agents"


class AgentIdentityConfigError(ValueError):
    """Raised when CAO agent identity configuration is invalid."""


class AgentIdentityPathError(ValueError):
    """Raised when an identity/provider id cannot safely own a filesystem path."""


@dataclass(frozen=True)
class AgentIdentity:
    """Durable CAO identity mapped to terminal runtime configuration."""

    id: str
    display_name: str
    agent_profile: str
    cli_provider: str
    workdir: str
    session_name: str


@dataclass(frozen=True)
class AgentIdentityRuntimePaths:
    """CAO-owned runtime path allocation for one identity/provider pair.

    CAO owns the identity data root and allocates each provider's directory.
    Providers own all contents below ``provider_data_dir``.
    """

    identity_data_dir: Path
    provider_data_dir: Path


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


def _safe_path_segment(value: str, *, label: str) -> str:
    segment = value.strip()
    if not segment:
        raise AgentIdentityPathError(f"{label} must be non-empty")
    if segment in {".", ".."} or "/" in segment or "\\" in segment:
        raise AgentIdentityPathError(f"{label} must be a single path segment: {value!r}")
    return segment


def agent_identity_data_dir(
    identity_or_id: AgentIdentity | str,
    *,
    cao_home_dir: Optional[Path] = None,
) -> Path:
    """Return the deterministic CAO-owned data root for an agent identity."""
    root = AGENT_IDENTITY_DATA_ROOT if cao_home_dir is None else cao_home_dir / "agents"
    agent_id = identity_or_id.id if isinstance(identity_or_id, AgentIdentity) else identity_or_id
    return root / _safe_path_segment(agent_id, label="agent identity id")


def provider_identity_data_dir(
    identity_or_id: AgentIdentity | str,
    provider_type: str,
    *,
    cao_home_dir: Optional[Path] = None,
) -> Path:
    """Return the deterministic provider-owned runtime directory for an identity."""
    return (
        agent_identity_data_dir(identity_or_id, cao_home_dir=cao_home_dir)
        / "providers"
        / _safe_path_segment(provider_type, label="provider type")
    )


def ensure_agent_identity_runtime_paths(
    identity: AgentIdentity,
    provider_type: str,
    *,
    cao_home_dir: Optional[Path] = None,
) -> AgentIdentityRuntimePaths:
    """Create and return CAO-owned identity/provider runtime directories."""
    identity_data_dir = agent_identity_data_dir(identity, cao_home_dir=cao_home_dir)
    provider_data_dir = provider_identity_data_dir(
        identity,
        provider_type,
        cao_home_dir=cao_home_dir,
    )
    provider_data_dir.mkdir(parents=True, exist_ok=True)
    return AgentIdentityRuntimePaths(
        identity_data_dir=identity_data_dir,
        provider_data_dir=provider_data_dir,
    )


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
        try:
            _safe_path_segment(agent_id, label="CAO agent identity id")
        except AgentIdentityPathError as exc:
            raise AgentIdentityConfigError(str(exc)) from exc
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
