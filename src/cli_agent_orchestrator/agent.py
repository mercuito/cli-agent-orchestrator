"""Durable CAO agent configuration, storage, and validation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional

try:  # pragma: no cover - Python 3.10 fallback
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from cli_agent_orchestrator.constants import CAO_HOME_DIR
from cli_agent_orchestrator.models.provider import ProviderType

CAO_AGENTS_DIR_ENV = "CAO_AGENTS_DIR"
DEFAULT_AGENTS_ROOT = CAO_HOME_DIR / "agents"
AGENTS_ROOT = Path(os.environ.get(CAO_AGENTS_DIR_ENV, str(DEFAULT_AGENTS_ROOT))).expanduser()
AGENT_CONFIG_FILENAME = "agent.toml"
AGENT_PROMPT_FILENAME = "prompt.md"
AGENT_CONFIG_MODE = 0o600
AGENT_PROMPT_MODE = 0o644

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class FrozenConfigDict(dict[str, Any]):
    """Dict-compatible immutable view for nested agent config maps."""

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("agent config mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


class FrozenConfigList(list[Any]):
    """List-compatible immutable view for nested agent config sequences."""

    def _immutable(self, *args: object, **kwargs: object) -> None:
        raise TypeError("agent config sequences are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable


class AgentConfigError(ValueError):
    """Raised when durable CAO agent configuration is invalid."""


class AgentPathError(ValueError):
    """Raised when an agent/runtime id cannot safely own a filesystem path."""


class AgentValidationError(ValueError):
    """Raised when one or more agent directories fail validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("\n".join(errors))


def configure_agents_root(agents_root: str | Path) -> Path:
    """Configure the process-wide durable CAO agent root."""
    global AGENTS_ROOT
    AGENTS_ROOT = Path(agents_root).expanduser()
    return AGENTS_ROOT


@dataclass(frozen=True)
class AgentWorkspaceContextConfig:
    """Workspace-context behavior configured for one durable agent."""

    enabled: bool = False
    resolver_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise AgentConfigError("workspace_context.enabled must be a boolean")
        if self.resolver_id is not None:
            _required_str(self.resolver_id, "workspace_context.resolver_id")
        if self.enabled and self.resolver_id is None:
            raise AgentConfigError(
                "workspace_context.resolver_id is required when workspace_context is enabled"
            )


@dataclass(frozen=True)
class LinearToolAccessConfig:
    """One Linear tool access policy owned by an agent."""

    access_id: str
    tools: tuple[str, ...]
    issues: tuple[str, ...]
    create_team_ids: tuple[str, ...] = ()
    create_project_ids: tuple[str, ...] = ()
    create_parent_issues: tuple[str, ...] = ()
    allow_top_level_create: bool = False
    update_fields: tuple[str, ...] = ()
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        _safe_path_segment(self.access_id, label="linear.tool_access id")
        _require_non_empty_str_tuple(self.tools, "linear.tool_access.tools")
        _require_str_tuple(self.issues, "linear.tool_access.issues")
        _require_str_tuple(self.create_team_ids, "linear.tool_access.create_team_ids")
        _require_str_tuple(self.create_project_ids, "linear.tool_access.create_project_ids")
        _require_str_tuple(self.create_parent_issues, "linear.tool_access.create_parent_issues")
        _require_str_tuple(self.update_fields, "linear.tool_access.update_fields")
        if not isinstance(self.allow_top_level_create, bool):
            raise AgentConfigError("linear.tool_access.allow_top_level_create must be a boolean")
        if self.reason is not None:
            _required_str(self.reason, "linear.tool_access.reason")


@dataclass(frozen=True)
class LinearConfig:
    """Linear OAuth presence and tool policies owned by an agent."""

    app_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[str] = None
    app_user_id: Optional[str] = None
    app_user_name: Optional[str] = None
    oauth_state: Optional[str] = None
    tool_access: tuple[LinearToolAccessConfig, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "app_key",
            "client_id",
            "client_secret",
            "webhook_secret",
            "oauth_redirect_uri",
            "access_token",
            "refresh_token",
            "token_expires_at",
            "app_user_id",
            "app_user_name",
            "oauth_state",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _required_str(value, f"linear.{field_name}")
        if not isinstance(self.tool_access, tuple) or not all(
            isinstance(access, LinearToolAccessConfig) for access in self.tool_access
        ):
            raise AgentConfigError("linear.tool_access must contain LinearToolAccessConfig values")


@dataclass(frozen=True)
class Agent:
    """Durable CAO agent config and prompt."""

    id: str
    display_name: str
    cli_provider: str
    workdir: str
    session_name: str
    prompt: str
    description: Optional[str] = None
    model: Optional[str] = None
    reasoning_effort: Optional[str] = None
    mcp_servers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    tool_aliases: Mapping[str, str] = field(default_factory=dict)
    tools_settings: Mapping[str, Any] = field(default_factory=dict)
    cao_tools: Optional[tuple[str, ...]] = None
    skills: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    hooks: Mapping[str, Any] = field(default_factory=dict)
    use_legacy_mcp_json: Optional[bool] = None
    runtime_capabilities: Optional[tuple[str, ...]] = None
    codex_config: Mapping[str, Any] = field(default_factory=dict)
    workspace_context: AgentWorkspaceContextConfig = AgentWorkspaceContextConfig()
    linear: Optional[LinearConfig] = None
    current_workspace_context_id: Optional[str] = None

    def __post_init__(self) -> None:
        _safe_path_segment(self.id, label="agent id")
        _required_str(self.display_name, f"agents.{self.id}.display_name")
        _required_str(self.cli_provider, f"agents.{self.id}.cli_provider")
        try:
            ProviderType(self.cli_provider)
        except ValueError as exc:
            raise AgentConfigError(
                f"agents.{self.id}.cli_provider is not a supported provider: "
                f"{self.cli_provider}"
            ) from exc
        _required_str(self.workdir, f"agents.{self.id}.workdir")
        _required_str(self.session_name, f"agents.{self.id}.session_name")
        if not isinstance(self.prompt, str):
            raise AgentConfigError(f"agents.{self.id}.prompt must be a string")
        if self.description is not None:
            _required_str(self.description, f"agents.{self.id}.description")
        if self.model is not None:
            _required_str(self.model, f"agents.{self.id}.model")
        if self.reasoning_effort is not None:
            _required_str(self.reasoning_effort, f"agents.{self.id}.reasoning_effort")
        object.__setattr__(
            self,
            "mcp_servers",
            _freeze_mapping(self.mcp_servers, f"agents.{self.id}.mcp_servers"),
        )
        _require_str_tuple(self.tools, f"agents.{self.id}.tools")
        _require_str_mapping(self.tool_aliases, f"agents.{self.id}.tool_aliases")
        object.__setattr__(
            self,
            "tool_aliases",
            _freeze_mapping(self.tool_aliases, f"agents.{self.id}.tool_aliases"),
        )
        object.__setattr__(
            self,
            "tools_settings",
            _freeze_mapping(self.tools_settings, f"agents.{self.id}.tools_settings"),
        )
        if self.cao_tools is not None:
            _require_str_tuple(self.cao_tools, f"agents.{self.id}.cao_tools")
        _require_str_tuple(self.skills, f"agents.{self.id}.skills")
        _require_str_tuple(self.tags, f"agents.{self.id}.tags")
        _require_str_tuple(self.resources, f"agents.{self.id}.resources")
        object.__setattr__(
            self,
            "hooks",
            _freeze_mapping(self.hooks, f"agents.{self.id}.hooks"),
        )
        if self.use_legacy_mcp_json is not None and not isinstance(self.use_legacy_mcp_json, bool):
            raise AgentConfigError(f"agents.{self.id}.use_legacy_mcp_json must be a boolean")
        if self.runtime_capabilities is not None:
            _require_str_tuple(self.runtime_capabilities, f"agents.{self.id}.runtime_capabilities")
        object.__setattr__(
            self,
            "codex_config",
            _freeze_mapping(self.codex_config, f"agents.{self.id}.codex_config"),
        )
        if not isinstance(self.workspace_context, AgentWorkspaceContextConfig):
            raise AgentConfigError(
                f"agents.{self.id}.workspace_context must be AgentWorkspaceContextConfig"
            )
        if self.linear is not None and not isinstance(self.linear, LinearConfig):
            raise AgentConfigError(f"agents.{self.id}.linear must be LinearConfig")
        if self.current_workspace_context_id is not None:
            _safe_path_segment(
                self.current_workspace_context_id,
                label="current workspace context id",
            )

    def for_workspace_context(self, workspace_context_id: str) -> "Agent":
        """Return this agent bound to the active runtime workspace context."""
        _safe_path_segment(workspace_context_id, label="workspace context id")
        return replace(self, current_workspace_context_id=workspace_context_id)

    def without_runtime_context(self) -> "Agent":
        """Return durable config without active runtime context."""
        return replace(self, current_workspace_context_id=None)


@dataclass(frozen=True)
class AgentWorkspaceContextRuntimePaths:
    """CAO-owned runtime path allocation for one agent/context/provider tuple."""

    agent_data_dir: Path
    context_data_dir: Path
    provider_data_dir: Path


class AgentRegistry:
    """Lookup table for durable CAO agents."""

    def __init__(self, agents: Mapping[str, Agent]) -> None:
        self._agents = dict(agents)

    def get(self, agent_id: str) -> Agent:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise AgentConfigError(f"Unknown CAO agent: {agent_id}") from exc

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def all(self) -> dict[str, Agent]:
        return dict(self._agents)


def agent_data_dir(agent: Agent, *, cao_home_dir: Optional[Path] = None) -> Path:
    """Return the deterministic CAO-owned data root for an agent."""
    root = AGENTS_ROOT if cao_home_dir is None else cao_home_dir / "agents"
    return root / _safe_path_segment(agent.id, label="agent id")


def workspace_context_data_dir(
    agent: Agent,
    workspace_context_id: str,
    *,
    cao_home_dir: Optional[Path] = None,
) -> Path:
    """Return the deterministic CAO-owned root for one agent workspace context."""
    return (
        agent_data_dir(agent, cao_home_dir=cao_home_dir)
        / "contexts"
        / _safe_path_segment(workspace_context_id, label="workspace context id")
    )


def workspace_context_provider_data_dir(
    agent: Agent,
    workspace_context_id: str,
    provider_type: str,
    *,
    cao_home_dir: Optional[Path] = None,
) -> Path:
    """Return the provider runtime directory inside a workspace context."""
    return (
        workspace_context_data_dir(
            agent,
            workspace_context_id,
            cao_home_dir=cao_home_dir,
        )
        / "runtime"
        / _safe_path_segment(provider_type, label="provider type")
    )


def ensure_agent_workspace_context_runtime_paths(
    agent: Agent,
    workspace_context_id: str,
    provider_type: str,
    *,
    cao_home_dir: Optional[Path] = None,
) -> AgentWorkspaceContextRuntimePaths:
    """Create and return CAO-owned context/provider runtime directories."""
    root = agent_data_dir(agent, cao_home_dir=cao_home_dir)
    context_root = workspace_context_data_dir(
        agent,
        workspace_context_id,
        cao_home_dir=cao_home_dir,
    )
    provider_root = workspace_context_provider_data_dir(
        agent,
        workspace_context_id,
        provider_type,
        cao_home_dir=cao_home_dir,
    )
    provider_root.mkdir(parents=True, exist_ok=True)
    return AgentWorkspaceContextRuntimePaths(
        agent_data_dir=root,
        context_data_dir=context_root,
        provider_data_dir=provider_root,
    )


def load_agent(agent_id: str, *, agents_root: Optional[Path] = None) -> Agent:
    """Load one agent directory from ``agents/<id>/``."""
    root = AGENTS_ROOT if agents_root is None else agents_root
    safe_id = _safe_path_segment(agent_id, label="agent id")
    agent_dir = root / safe_id
    config_path = agent_dir / AGENT_CONFIG_FILENAME
    prompt_path = agent_dir / AGENT_PROMPT_FILENAME
    if not agent_dir.is_dir():
        raise AgentConfigError(f"Agent {safe_id!r} directory not found: {agent_dir}")
    if not config_path.is_file():
        raise AgentConfigError(f"Agent {safe_id!r} missing config file: {config_path}")
    if not prompt_path.is_file():
        raise AgentConfigError(f"Agent {safe_id!r} missing prompt file: {prompt_path}")
    try:
        raw_config = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise AgentConfigError(f"Agent {safe_id!r} invalid TOML at {config_path}: {exc}") from exc
    if not isinstance(raw_config, Mapping):
        raise AgentConfigError(f"Agent {safe_id!r} config must be a TOML table: {config_path}")
    try:
        return _agent_from_config(safe_id, raw_config, prompt_path.read_text(), config_path)
    except (AgentConfigError, AgentPathError) as exc:
        message = str(exc)
        if f"Agent {safe_id!r}" in message and str(config_path) in message:
            raise
        raise AgentConfigError(
            f"Agent {safe_id!r} invalid config at {config_path}: {message}"
        ) from exc


def load_all_agents(*, agents_root: Optional[Path] = None) -> AgentRegistry:
    """Load every agent directory under the configured agents root."""
    root = AGENTS_ROOT if agents_root is None else agents_root
    if not root.exists():
        return AgentRegistry({})
    agents: dict[str, Agent] = {}
    for agent_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        agent = load_agent(agent_dir.name, agents_root=root)
        if agent.id in agents:
            raise AgentConfigError(f"Duplicate CAO agent: {agent.id}")
        agents[agent.id] = agent
    return AgentRegistry(agents)


def load_agent_registry(agents_root: Optional[Path] = None) -> AgentRegistry:
    """Load every durable agent into a registry."""
    return load_all_agents(agents_root=agents_root)


def write_agent(agent: Agent, *, agents_root: Optional[Path] = None) -> None:
    """Atomically write ``agent.toml`` and ``prompt.md`` with required permissions."""
    root = AGENTS_ROOT if agents_root is None else agents_root
    agent_dir = root / _safe_path_segment(agent.id, label="agent id")
    agent_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        agent_dir / AGENT_CONFIG_FILENAME,
        _agent_to_toml(agent),
        mode=AGENT_CONFIG_MODE,
    )
    _atomic_write_text(
        agent_dir / AGENT_PROMPT_FILENAME,
        agent.prompt,
        mode=AGENT_PROMPT_MODE,
    )


def patch_agent_section(
    agent_id: str,
    section: str,
    values: Mapping[str, object],
    *,
    agents_root: Optional[Path] = None,
) -> None:
    """Patch scalar keys inside one TOML section while preserving unrelated text."""
    root = AGENTS_ROOT if agents_root is None else agents_root
    safe_id = _safe_path_segment(agent_id, label="agent id")
    config_path = root / safe_id / AGENT_CONFIG_FILENAME
    if not config_path.is_file():
        raise AgentConfigError(f"Agent {safe_id!r} missing config file: {config_path}")
    if not values:
        return
    text = config_path.read_text()
    patched = _patch_toml_section_values(text, section, values)
    _atomic_write_text(config_path, patched, mode=AGENT_CONFIG_MODE)


def patch_agent_config(
    agent: Agent,
    *,
    changed_fields: set[str],
    agents_root: Optional[Path] = None,
) -> None:
    """Patch one durable agent while preserving unrelated config text."""
    root = AGENTS_ROOT if agents_root is None else agents_root
    safe_id = _safe_path_segment(agent.id, label="agent id")
    agent_dir = root / safe_id
    config_path = agent_dir / AGENT_CONFIG_FILENAME
    prompt_path = agent_dir / AGENT_PROMPT_FILENAME
    if not config_path.is_file():
        raise AgentConfigError(f"Agent {safe_id!r} missing config file: {config_path}")

    text = config_path.read_text()
    root_fields = {
        "display_name": agent.display_name,
        "cli_provider": agent.cli_provider,
        "workdir": agent.workdir,
        "session_name": agent.session_name,
        "description": agent.description,
        "model": agent.model,
        "reasoning_effort": agent.reasoning_effort,
        "tools": list(agent.tools),
        "cao_tools": list(agent.cao_tools) if agent.cao_tools is not None else None,
        "skills": list(agent.skills),
        "tags": list(agent.tags),
        "resources": list(agent.resources),
        "use_legacy_mcp_json": agent.use_legacy_mcp_json,
        "runtime_capabilities": (
            list(agent.runtime_capabilities) if agent.runtime_capabilities is not None else None
        ),
    }
    root_patch = {key: value for key, value in root_fields.items() if key in changed_fields}
    if root_patch:
        text = _patch_toml_root_values(text, root_patch)

    table_replacements: list[tuple[str, Mapping[str, Any] | None]] = []
    if "mcp_servers" in changed_fields:
        table_replacements.append(("mcp_servers", dict(agent.mcp_servers)))
    if "tool_aliases" in changed_fields:
        table_replacements.append(("tool_aliases", dict(agent.tool_aliases)))
    if "tools_settings" in changed_fields:
        table_replacements.append(("tools_settings", dict(agent.tools_settings)))
    if "hooks" in changed_fields:
        table_replacements.append(("hooks", dict(agent.hooks)))
    if "codex_config" in changed_fields:
        table_replacements.append(("codex_config", dict(agent.codex_config)))
    if "workspace_context" in changed_fields:
        workspace = {
            "enabled": agent.workspace_context.enabled,
            **(
                {"resolver_id": agent.workspace_context.resolver_id}
                if agent.workspace_context.resolver_id is not None
                else {}
            ),
        }
        table_replacements.append(
            (
                "workspace_context",
                workspace if agent.workspace_context != AgentWorkspaceContextConfig() else None,
            )
        )
    if "linear" in changed_fields:
        table_replacements.append(
            (
                "linear",
                _linear_to_toml_mapping(agent.linear) if agent.linear is not None else None,
            )
        )

    for table_name, values in table_replacements:
        text = _replace_toml_table_tree(text, table_name, values)

    _atomic_write_text(config_path, text, mode=AGENT_CONFIG_MODE)
    if "prompt" in changed_fields:
        _atomic_write_text(prompt_path, agent.prompt, mode=AGENT_PROMPT_MODE)


def create_stub_agent(
    agent_id: str,
    *,
    display_name: Optional[str] = None,
    workdir: str,
    cli_provider: str,
    agents_root: Optional[Path] = None,
) -> Agent:
    """Create a minimal valid agent directory and return the Agent value."""
    safe_id = _safe_path_segment(agent_id, label="agent id")
    agent = Agent(
        id=safe_id,
        display_name=display_name or safe_id.replace("_", " ").replace("-", " ").title(),
        cli_provider=cli_provider,
        workdir=workdir,
        session_name=safe_id.replace("_", "-"),
        prompt="# Agent\n",
    )
    write_agent(agent, agents_root=agents_root)
    return agent


def validate_agents_root(*, agents_root: Optional[Path] = None) -> None:
    """Validate all configured agent directories or raise aggregated errors."""
    root = AGENTS_ROOT if agents_root is None else agents_root
    errors: list[str] = []
    if not root.is_dir():
        raise AgentValidationError([f"agents root not found: {root}"])
    for agent_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        errors.extend(validate_agent_dir(agent_dir))
    _validate_linear_uniqueness(root, errors)
    if errors:
        raise AgentValidationError(errors)


def validate_agent_dir(agent_dir: Path) -> list[str]:
    """Return validation errors for one agent directory."""
    errors: list[str] = []
    agent_id = agent_dir.name
    config_path = agent_dir / AGENT_CONFIG_FILENAME
    prompt_path = agent_dir / AGENT_PROMPT_FILENAME
    try:
        agent = load_agent(agent_id, agents_root=agent_dir.parent)
        if agent.id != agent_id:
            errors.append(f"{agent_id}: {config_path}: id must match directory name")
    except AgentConfigError as exc:
        errors.append(str(exc))
        return errors
    if not agent.prompt.strip():
        errors.append(f"{agent.id}: {prompt_path}: prompt.md must be non-empty")
    errors.extend(_mode_errors(agent.id, config_path, AGENT_CONFIG_MODE))
    errors.extend(_mode_errors(agent.id, prompt_path, AGENT_PROMPT_MODE))
    errors.extend(_linear_tool_access_errors(agent, config_path))
    return errors


def _agent_from_config(
    agent_id: str,
    data: Mapping[str, object],
    prompt: str,
    config_path: Path,
) -> Agent:
    raw_id = data.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise AgentConfigError(f"Agent {agent_id!r} missing required field 'id': {config_path}")
    if raw_id.strip() != agent_id:
        raise AgentConfigError(f"Agent {agent_id!r} id must match directory name: {config_path}")
    return Agent(
        id=agent_id,
        display_name=_require_config_str(data, "display_name", agent_id, config_path),
        cli_provider=_require_config_str(data, "cli_provider", agent_id, config_path),
        workdir=_require_config_str(data, "workdir", agent_id, config_path),
        session_name=_require_config_str(data, "session_name", agent_id, config_path),
        prompt=prompt,
        description=_optional_config_str(data, "description", agent_id, config_path),
        model=_optional_config_str(data, "model", agent_id, config_path),
        reasoning_effort=_optional_config_str(data, "reasoning_effort", agent_id, config_path),
        mcp_servers=_mapping_of_mappings(data.get("mcp_servers"), "mcp_servers", config_path),
        tools=_tuple_of_strs(data.get("tools"), "tools", config_path),
        tool_aliases=_mapping_of_strs(data.get("tool_aliases"), "tool_aliases", config_path),
        tools_settings=_mapping(data.get("tools_settings"), "tools_settings", config_path),
        cao_tools=_optional_tuple_of_strs(data.get("cao_tools"), "cao_tools", config_path),
        skills=_tuple_of_strs(data.get("skills"), "skills", config_path),
        tags=_tuple_of_strs(data.get("tags"), "tags", config_path),
        resources=_tuple_of_strs(data.get("resources"), "resources", config_path),
        hooks=_mapping(data.get("hooks"), "hooks", config_path),
        use_legacy_mcp_json=_optional_bool(
            data.get("use_legacy_mcp_json"),
            "use_legacy_mcp_json",
            config_path,
        ),
        runtime_capabilities=_optional_tuple_of_strs(
            data.get("runtime_capabilities"),
            "runtime_capabilities",
            config_path,
        ),
        codex_config=_mapping(data.get("codex_config"), "codex_config", config_path),
        workspace_context=_workspace_context_config(data, agent_id=agent_id, path=config_path),
        linear=_linear_config(data.get("linear"), path=config_path),
    )


def _workspace_context_config(
    data: Mapping[str, object],
    *,
    agent_id: str,
    path: Path,
) -> AgentWorkspaceContextConfig:
    raw = data.get("workspace_context")
    if raw is None:
        return AgentWorkspaceContextConfig()
    if not isinstance(raw, Mapping):
        raise AgentConfigError(f"{path}: agents.{agent_id}.workspace_context must be a table")
    enabled = raw.get("enabled", False)
    resolver_id = raw.get("resolver_id")
    if resolver_id is not None and not isinstance(resolver_id, str):
        raise AgentConfigError(
            f"{path}: agents.{agent_id}.workspace_context.resolver_id must be a string"
        )
    return AgentWorkspaceContextConfig(
        enabled=enabled,  # type: ignore[arg-type]
        resolver_id=resolver_id.strip() if isinstance(resolver_id, str) else None,
    )


def _linear_config(raw: object, *, path: Path) -> Optional[LinearConfig]:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise AgentConfigError(f"{path}: linear must be a table")
    tool_access_raw = raw.get("tool_access")
    access_entries: list[LinearToolAccessConfig] = []
    if tool_access_raw is not None:
        if not isinstance(tool_access_raw, Mapping):
            raise AgentConfigError(f"{path}: linear.tool_access must be a table")
        for access_id, access in tool_access_raw.items():
            if not isinstance(access, Mapping):
                raise AgentConfigError(f"{path}: linear.tool_access.{access_id} must be a table")
            allow_top_level_create = access.get("allow_top_level_create", False)
            if not isinstance(allow_top_level_create, bool):
                raise AgentConfigError(
                    f"{path}: linear.tool_access.{access_id}.allow_top_level_create "
                    "must be a boolean"
                )
            tools = _require_mapping_value(
                access,
                "tools",
                f"linear.tool_access.{access_id}.tools",
                path,
            )
            access_entries.append(
                LinearToolAccessConfig(
                    access_id=str(access_id),
                    tools=_tuple_of_strs(tools, "linear.tool_access.tools", path),
                    issues=_tuple_of_strs(
                        access.get("issues", ()),
                        "linear.tool_access.issues",
                        path,
                    ),
                    create_team_ids=_tuple_of_strs(
                        access.get("create_team_ids", ()),
                        "linear.tool_access.create_team_ids",
                        path,
                    ),
                    create_project_ids=_tuple_of_strs(
                        access.get("create_project_ids", ()),
                        "linear.tool_access.create_project_ids",
                        path,
                    ),
                    create_parent_issues=_tuple_of_strs(
                        access.get("create_parent_issues", ()),
                        "linear.tool_access.create_parent_issues",
                        path,
                    ),
                    allow_top_level_create=allow_top_level_create,
                    update_fields=_tuple_of_strs(
                        access.get("update_fields", ()),
                        "linear.tool_access.update_fields",
                        path,
                    ),
                    reason=_optional_mapping_str(access, "reason", path),
                )
            )
    return LinearConfig(
        app_key=_optional_mapping_str(raw, "app_key", path),
        client_id=_optional_mapping_str(raw, "client_id", path),
        client_secret=_optional_mapping_str(raw, "client_secret", path),
        webhook_secret=_optional_mapping_str(raw, "webhook_secret", path),
        oauth_redirect_uri=_optional_mapping_str(raw, "oauth_redirect_uri", path),
        access_token=_optional_mapping_str(raw, "access_token", path),
        refresh_token=_optional_mapping_str(raw, "refresh_token", path),
        token_expires_at=_optional_mapping_str(raw, "token_expires_at", path),
        app_user_id=_optional_mapping_str(raw, "app_user_id", path),
        app_user_name=_optional_mapping_str(raw, "app_user_name", path),
        oauth_state=_optional_mapping_str(raw, "oauth_state", path),
        tool_access=tuple(sorted(access_entries, key=lambda item: item.access_id)),
    )


def _linear_tool_access_errors(agent: Agent, config_path: Path) -> list[str]:
    errors: list[str] = []
    if agent.linear is None:
        return errors
    from cli_agent_orchestrator.linear.provider_tools import (
        LINEAR_PROVIDER_TOOLS,
        UPDATE_ISSUE_FIELDS,
    )

    for access in agent.linear.tool_access:
        for tool in access.tools:
            if tool not in LINEAR_PROVIDER_TOOLS:
                errors.append(
                    f"{agent.id}: {config_path}: unknown Linear tool in "
                    f"linear.tool_access.{access.access_id}: {tool}"
                )
        for field_name in access.update_fields:
            if field_name not in UPDATE_ISSUE_FIELDS:
                errors.append(
                    f"{agent.id}: {config_path}: unknown Linear update field in "
                    f"linear.tool_access.{access.access_id}: {field_name}"
                )
    return errors


def _validate_linear_uniqueness(root: Path, errors: list[str]) -> None:
    seen: dict[tuple[str, str], str] = {}
    agents: Iterable[Agent]
    try:
        agents = load_all_agents(agents_root=root).all().values()
    except AgentConfigError:
        agents = (
            load_agent(agent_dir.name, agents_root=root)
            for agent_dir in sorted(path for path in root.iterdir() if path.is_dir())
            if not validate_agent_dir(agent_dir)
        )
    for agent in agents:
        if agent.linear is None:
            continue
        for field_name in ("app_user_id", "app_user_name", "oauth_state"):
            value = getattr(agent.linear, field_name)
            if value is None:
                continue
            key = (field_name, value)
            if key in seen:
                errors.append(f"{agent.id}: linear.{field_name} duplicates {seen[key]}: {value}")
            else:
                seen[key] = agent.id


def _mode_errors(agent_id: str, path: Path, expected_mode: int) -> list[str]:
    actual = path.stat().st_mode & 0o777
    if actual == expected_mode:
        return []
    return [
        f"{agent_id}: {path}: mode must be {expected_mode:04o}, found {actual:04o}",
    ]


def _agent_to_toml(agent: Agent) -> str:
    data: dict[str, Any] = {
        "id": agent.id,
        "display_name": agent.display_name,
        "cli_provider": agent.cli_provider,
        "workdir": agent.workdir,
        "session_name": agent.session_name,
    }
    if agent.model is not None:
        data["model"] = agent.model
    if agent.description is not None:
        data["description"] = agent.description
    if agent.reasoning_effort is not None:
        data["reasoning_effort"] = agent.reasoning_effort
    if agent.tools:
        data["tools"] = list(agent.tools)
    if agent.tool_aliases:
        data["tool_aliases"] = dict(agent.tool_aliases)
    if agent.tools_settings:
        data["tools_settings"] = dict(agent.tools_settings)
    if agent.cao_tools is not None:
        data["cao_tools"] = list(agent.cao_tools)
    if agent.skills:
        data["skills"] = list(agent.skills)
    if agent.tags:
        data["tags"] = list(agent.tags)
    if agent.resources:
        data["resources"] = list(agent.resources)
    if agent.hooks:
        data["hooks"] = dict(agent.hooks)
    if agent.use_legacy_mcp_json is not None:
        data["use_legacy_mcp_json"] = agent.use_legacy_mcp_json
    if agent.runtime_capabilities is not None:
        data["runtime_capabilities"] = list(agent.runtime_capabilities)
    if agent.workspace_context != AgentWorkspaceContextConfig():
        data["workspace_context"] = {
            "enabled": agent.workspace_context.enabled,
            "resolver_id": agent.workspace_context.resolver_id,
        }
    if agent.mcp_servers:
        data["mcp_servers"] = dict(agent.mcp_servers)
    if agent.codex_config:
        data["codex_config"] = dict(agent.codex_config)
    if agent.linear is not None:
        linear: dict[str, Any] = {
            key: value
            for key, value in {
                "app_key": agent.linear.app_key,
                "client_id": agent.linear.client_id,
                "client_secret": agent.linear.client_secret,
                "webhook_secret": agent.linear.webhook_secret,
                "oauth_redirect_uri": agent.linear.oauth_redirect_uri,
                "access_token": agent.linear.access_token,
                "refresh_token": agent.linear.refresh_token,
                "token_expires_at": agent.linear.token_expires_at,
                "app_user_id": agent.linear.app_user_id,
                "app_user_name": agent.linear.app_user_name,
                "oauth_state": agent.linear.oauth_state,
            }.items()
            if value is not None
        }
        if agent.linear.tool_access:
            linear["tool_access"] = {
                access.access_id: {
                    "tools": list(access.tools),
                    "issues": list(access.issues),
                    "create_team_ids": list(access.create_team_ids),
                    "create_project_ids": list(access.create_project_ids),
                    "create_parent_issues": list(access.create_parent_issues),
                    "allow_top_level_create": access.allow_top_level_create,
                    "update_fields": list(access.update_fields),
                    **({"reason": access.reason} if access.reason is not None else {}),
                }
                for access in agent.linear.tool_access
            }
        data["linear"] = linear
    return _dump_toml(data)


def _patch_toml_section_values(text: str, section: str, values: Mapping[str, object]) -> str:
    lines = text.splitlines()
    header = f"[{section}]"
    section_start: int | None = None
    section_end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == header:
            section_start = index
            continue
        if section_start is not None and index > section_start and stripped.startswith("["):
            section_end = index
            break
    rendered_values = {key: _format_toml_value(value) for key, value in values.items()}
    if section_start is None:
        extra = ["", header, *(f"{key} = {value}" for key, value in rendered_values.items())]
        return "\n".join([*lines, *extra]).strip() + "\n"
    existing_keys: set[str] = set()
    patched_lines = list(lines)
    for index in range(section_start + 1, section_end):
        line = patched_lines[index]
        stripped = line.strip()
        for key, rendered in rendered_values.items():
            if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
                prefix = line[: len(line) - len(line.lstrip())]
                comment = ""
                if " #" in line:
                    comment = " " + line.split(" #", 1)[1]
                    comment = " #" + comment.lstrip("# ")
                patched_lines[index] = f"{prefix}{key} = {rendered}{comment}".rstrip()
                existing_keys.add(key)
    missing = [key for key in rendered_values if key not in existing_keys]
    if missing:
        insert_at = section_end
        additions = [f"{key} = {rendered_values[key]}" for key in missing]
        patched_lines[insert_at:insert_at] = additions
    return "\n".join(patched_lines).rstrip() + "\n"


def _patch_toml_root_values(text: str, values: Mapping[str, object | None]) -> str:
    lines = text.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if line.strip().startswith("[")),
        len(lines),
    )
    rendered_values = {
        key: _format_toml_value(value) for key, value in values.items() if value is not None
    }
    remove_keys = {key for key, value in values.items() if value is None}
    existing_keys: set[str] = set()
    patched_lines = list(lines)
    deleted_indexes: set[int] = set()
    for index in range(first_section):
        stripped = patched_lines[index].strip()
        for key in values:
            if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
                if key in remove_keys:
                    deleted_indexes.add(index)
                    existing_keys.add(key)
                    continue
                prefix = patched_lines[index][
                    : len(patched_lines[index]) - len(patched_lines[index].lstrip())
                ]
                patched_lines[index] = f"{prefix}{key} = {rendered_values[key]}".rstrip()
                existing_keys.add(key)
    patched_lines = [
        line for index, line in enumerate(patched_lines) if index not in deleted_indexes
    ]
    first_section = next(
        (index for index, line in enumerate(patched_lines) if line.strip().startswith("[")),
        len(patched_lines),
    )
    additions = [
        f"{key} = {rendered_values[key]}" for key in rendered_values if key not in existing_keys
    ]
    if additions:
        patched_lines[first_section:first_section] = additions
    return "\n".join(patched_lines).rstrip() + "\n"


def _replace_toml_table_tree(
    text: str,
    table_name: str,
    values: Mapping[str, Any] | None,
) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            header = stripped.strip("[]")
            skipping = header == table_name or header.startswith(f"{table_name}.")
        if not skipping:
            kept.append(line)
    rendered = _dump_toml({table_name: values}).strip() if values else ""
    result = "\n".join(kept).rstrip()
    if rendered:
        result = f"{result}\n\n{rendered}" if result else rendered
    return result.rstrip() + "\n"


def _linear_to_toml_mapping(linear: LinearConfig) -> Mapping[str, Any]:
    data: dict[str, Any] = {
        key: value
        for key, value in {
            "app_key": linear.app_key,
            "client_id": linear.client_id,
            "client_secret": linear.client_secret,
            "webhook_secret": linear.webhook_secret,
            "oauth_redirect_uri": linear.oauth_redirect_uri,
            "access_token": linear.access_token,
            "refresh_token": linear.refresh_token,
            "token_expires_at": linear.token_expires_at,
            "app_user_id": linear.app_user_id,
            "app_user_name": linear.app_user_name,
            "oauth_state": linear.oauth_state,
        }.items()
        if value is not None
    }
    if linear.tool_access:
        data["tool_access"] = {
            access.access_id: {
                "tools": list(access.tools),
                "issues": list(access.issues),
                "create_team_ids": list(access.create_team_ids),
                "create_project_ids": list(access.create_project_ids),
                "create_parent_issues": list(access.create_parent_issues),
                "allow_top_level_create": access.allow_top_level_create,
                "update_fields": list(access.update_fields),
                **({"reason": access.reason} if access.reason is not None else {}),
            }
            for access in linear.tool_access
        }
    return data


def _dump_toml(data: Mapping[str, Any]) -> str:
    lines: list[str] = []

    def emit(prefix: list[str], table: Mapping[str, Any]) -> None:
        scalar_items: list[tuple[str, Any]] = []
        table_items: list[tuple[str, Mapping[str, Any]]] = []
        for key in sorted(table):
            value = table[key]
            if isinstance(value, Mapping):
                table_items.append((str(key), value))
            else:
                scalar_items.append((str(key), value))
        if prefix:
            lines.append("[" + ".".join(_format_toml_key(part) for part in prefix) + "]")
        for key, value in scalar_items:
            lines.append(f"{_format_toml_key(key)} = {_format_toml_value(value)}")
        if scalar_items and table_items:
            lines.append("")
        for index, (key, value) in enumerate(table_items):
            emit([*prefix, key], value)
            if index != len(table_items) - 1:
                lines.append("")

    emit([], data)
    return "\n".join(lines).rstrip() + "\n"


def _format_toml_key(key: str) -> str:
    if key.replace("_", "").replace("-", "").isalnum() and key[0].isalpha():
        return key
    return json.dumps(key)


def _format_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    if value is None:
        raise TypeError("TOML values cannot be None")
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def _atomic_write_text(path: Path, text: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(text)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        os.chmod(path, mode)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _require_config_str(
    table: Mapping[str, object],
    key: str,
    agent_id: str,
    path: Path,
) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentConfigError(f"Agent {agent_id!r} missing required field {key!r}: {path}")
    return value.strip()


def _optional_config_str(
    table: Mapping[str, object],
    key: str,
    agent_id: str,
    path: Path,
) -> Optional[str]:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AgentConfigError(f"Agent {agent_id!r} field {key!r} must be a string: {path}")
    return value.strip()


def _optional_mapping_str(table: Mapping[str, object], key: str, path: Path) -> Optional[str]:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AgentConfigError(f"{path}: {key} must be a non-empty string")
    return value.strip()


def _require_mapping_value(
    table: Mapping[str, object],
    key: str,
    label: str,
    path: Path,
) -> object:
    if key not in table:
        raise AgentConfigError(f"{path}: {label} is required")
    return table[key]


def _mapping(value: object, label: str, path: Path) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AgentConfigError(f"{path}: {label} must be a table")
    return dict(value)


def _mapping_of_strs(value: object, label: str, path: Path) -> Mapping[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise AgentConfigError(f"{path}: {label} must be a table of strings")
    return {key: item for key, item in value.items() if key.strip() and item.strip()}


def _mapping_of_mappings(
    value: object,
    label: str,
    path: Path,
) -> Mapping[str, Mapping[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AgentConfigError(f"{path}: {label} must be a table")
    result: dict[str, Mapping[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(item, Mapping):
            raise AgentConfigError(f"{path}: {label}.{key} must be a table")
        result[str(key)] = dict(item)
    return result


def _tuple_of_strs(value: object, label: str, path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise AgentConfigError(f"{path}: {label} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


def _optional_tuple_of_strs(value: object, label: str, path: Path) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    return _tuple_of_strs(value, label, path)


def _optional_bool(value: object, label: str, path: Path) -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise AgentConfigError(f"{path}: {label} must be a boolean")
    return value


def _required_str(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _require_str_tuple(values: tuple[str, ...], label: str) -> None:
    if not isinstance(values, tuple) or not all(isinstance(item, str) and item for item in values):
        raise AgentConfigError(f"{label} must be a tuple of non-empty strings")


def _require_non_empty_str_tuple(values: tuple[str, ...], label: str) -> None:
    _require_str_tuple(values, label)
    if not values:
        raise AgentConfigError(f"{label} must be a non-empty tuple of strings")


def _require_str_mapping(values: Mapping[str, str], label: str) -> None:
    if not isinstance(values, Mapping) or not all(
        isinstance(key, str) and key and isinstance(value, str) and value
        for key, value in values.items()
    ):
        raise AgentConfigError(f"{label} must be a mapping of non-empty strings")


def _freeze_mapping(values: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise AgentConfigError(f"{label} must be a mapping")
    return FrozenConfigDict(
        {str(key): _freeze_config_value(value, f"{label}.{key}") for key, value in values.items()}
    )


def _freeze_config_value(value: Any, label: str) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value, label)
    if isinstance(value, list):
        return FrozenConfigList(_freeze_config_value(item, label) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_config_value(item, label) for item in value)
    return value


def _safe_path_segment(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentPathError(f"{label} must be non-empty")
    segment = value.strip()
    if segment in {".", ".."} or "/" in segment or "\\" in segment:
        raise AgentPathError(f"{label} must be a single path segment: {value!r}")
    if not _SAFE_SEGMENT.match(segment):
        raise AgentPathError(f"{label} contains unsupported characters: {value!r}")
    return segment
