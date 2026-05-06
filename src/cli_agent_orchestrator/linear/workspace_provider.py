"""Linear workspace-provider config, presence mapping, and lifecycle."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

import tomli

from cli_agent_orchestrator.agent_identity import (
    AgentIdentity,
    AgentIdentityConfigError,
    AgentIdentityRegistry,
    load_agent_identity_registry,
)
from cli_agent_orchestrator.constants import CAO_HOME_DIR, DEFAULT_PROVIDER, SESSION_PREFIX
from cli_agent_orchestrator.utils.env import load_env_vars, set_env_var
from cli_agent_orchestrator.workspace_providers.registry import (
    is_workspace_provider_enabled,
    workspace_provider_config_exists,
)

LINEAR_PROVIDER_CONFIG_PATH = CAO_HOME_DIR / "workspace-providers" / "linear.toml"
APP_KEY_PATTERN = re.compile(r"[^A-Za-z0-9]+")
_default_linear_workspace_provider: Optional["LinearWorkspaceProvider"] = None


class LinearWorkspaceProviderConfigError(ValueError):
    """Raised when Linear workspace-provider configuration is invalid."""


@dataclass(frozen=True)
class LinearPresence:
    """A Linear app-user presence mapped to a durable CAO agent identity."""

    presence_id: str
    agent_id: str
    app_key: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    oauth_state: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    app_user_id: Optional[str] = None
    app_user_name: Optional[str] = None
    token_expires_at: Optional[str] = None


@dataclass(frozen=True)
class LinearProviderConfig:
    """Linear workspace-provider config loaded from structured TOML or legacy env."""

    public_url: Optional[str]
    presences: dict[str, LinearPresence]
    source: str = "structured"

    def presence_by_app_key(self, app_key: str) -> Optional[LinearPresence]:
        normalized = normalize_app_key(app_key)
        return next(
            (presence for presence in self.presences.values() if presence.app_key == normalized),
            None,
        )

    def presence_by_app_user_id(self, app_user_id: str) -> Optional[LinearPresence]:
        return next(
            (
                presence
                for presence in self.presences.values()
                if presence.app_user_id == app_user_id
            ),
            None,
        )

    def presence_by_app_user_name(self, app_user_name: str) -> Optional[LinearPresence]:
        return next(
            (
                presence
                for presence in self.presences.values()
                if presence.app_user_name == app_user_name
            ),
            None,
        )

    def presence_by_oauth_state(self, oauth_state: str) -> Optional[LinearPresence]:
        return next(
            (
                presence
                for presence in self.presences.values()
                if presence.oauth_state == oauth_state
            ),
            None,
        )


@dataclass(frozen=True)
class LinearResolvedPresence:
    """Resolved Linear presence plus the CAO runtime identity it maps to."""

    presence: LinearPresence
    identity: AgentIdentity


def linear_env(name: str) -> Optional[str]:
    """Read legacy Linear compatibility config from process env then CAO's env file."""
    return os.environ.get(name) or load_env_vars().get(name)


def normalize_app_key(app_key: str) -> str:
    """Return a stable provider-native app key for Linear presence lookup."""
    normalized = APP_KEY_PATTERN.sub("_", app_key.strip().lower()).strip("_")
    if not normalized:
        raise LinearWorkspaceProviderConfigError(
            "Linear app key must contain at least one letter or digit"
        )
    return normalized


def app_env_prefix(app_key: str) -> str:
    """Return the legacy env prefix for a configured Linear app key."""
    return f"LINEAR_APP_{APP_KEY_PATTERN.sub('_', normalize_app_key(app_key)).upper()}"


def linear_app_env(
    app_key: Optional[str],
    name: str,
    *,
    config_path: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Optional[str]:
    """Read a Linear presence field, preferring structured config over legacy env."""
    config = load_linear_provider_config(
        config_path=config_path,
        allow_legacy_env=False,
        env_reader=env_reader,
    )
    if config is not None:
        if not app_key:
            return None
        presence = config.presence_by_app_key(app_key)
        return _presence_field(presence, name) if presence is not None else None

    if app_key:
        value = env_reader(f"{app_env_prefix(app_key)}_{name}")
        if value:
            return value
    return env_reader(f"LINEAR_{name}")


def configured_app_keys(
    *,
    config_path: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> list[str]:
    """Return Linear app keys, preferring structured config over legacy env."""
    config = load_linear_provider_config(
        config_path=config_path,
        allow_legacy_env=False,
        env_reader=env_reader,
    )
    if config is not None:
        return [presence.app_key for presence in config.presences.values()]

    raw = env_reader("LINEAR_APP_KEYS")
    if not raw:
        return []
    return [normalize_app_key(item) for item in raw.split(",") if item.strip()]


def configured_app_key_for_oauth_state(
    state: Optional[str],
    *,
    config_path: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Optional[str]:
    """Resolve a structured Linear app key from a configured OAuth nonce."""
    if not state:
        return None
    config = load_linear_provider_config(
        config_path=config_path,
        allow_legacy_env=False,
        env_reader=env_reader,
    )
    if config is None:
        return None
    presence = config.presence_by_oauth_state(state)
    return presence.app_key if presence is not None else None


def required_linear_app_env(
    app_key: Optional[str],
    name: str,
    *,
    config_path: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> str:
    """Read a required Linear config value from structured config or legacy env."""
    value = linear_app_env(app_key, name, config_path=config_path, env_reader=env_reader)
    if value:
        return value
    if app_key:
        raise LinearWorkspaceProviderConfigError(f"{app_env_prefix(app_key)}_{name} is required")
    raise LinearWorkspaceProviderConfigError(f"LINEAR_{name} is required")


def _presence_field(presence: LinearPresence, env_name: str) -> Optional[str]:
    field_name = env_name.lower()
    if field_name == "oauth_redirect_uri":
        return presence.oauth_redirect_uri
    if field_name == "oauth_state":
        return presence.oauth_state
    value = getattr(presence, field_name, None)
    return str(value) if value else None


def _require_str(table: Mapping[str, Any], key: str, *, presence_id: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LinearWorkspaceProviderConfigError(
            f"presences.{presence_id}.{key} must be a non-empty string"
        )
    return value.strip()


def _optional_str(table: Mapping[str, Any], key: str) -> Optional[str]:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LinearWorkspaceProviderConfigError(f"{key} must be a string")
    value = value.strip()
    return value or None


def _load_structured_linear_config(path: Path) -> LinearProviderConfig:
    try:
        data = tomli.loads(path.read_text())
    except tomli.TOMLDecodeError as exc:
        raise LinearWorkspaceProviderConfigError(f"Invalid Linear provider config: {exc}") from exc

    presences_table = data.get("presences")
    if not isinstance(presences_table, Mapping):
        raise LinearWorkspaceProviderConfigError("linear.toml must contain a [presences] table")

    presences: dict[str, LinearPresence] = {}
    for raw_presence_id, raw_config in presences_table.items():
        presence_id = str(raw_presence_id).strip()
        if not presence_id:
            raise LinearWorkspaceProviderConfigError("Linear presence id must be non-empty")
        if not isinstance(raw_config, Mapping):
            raise LinearWorkspaceProviderConfigError(f"presences.{presence_id} must be a table")
        presences[presence_id] = LinearPresence(
            presence_id=presence_id,
            agent_id=_require_str(raw_config, "agent_id", presence_id=presence_id),
            app_key=normalize_app_key(_require_str(raw_config, "app_key", presence_id=presence_id)),
            client_id=_optional_str(raw_config, "client_id"),
            client_secret=_optional_str(raw_config, "client_secret"),
            webhook_secret=_optional_str(raw_config, "webhook_secret"),
            oauth_redirect_uri=_optional_str(raw_config, "oauth_redirect_uri"),
            oauth_state=_optional_str(raw_config, "oauth_state"),
            access_token=_optional_str(raw_config, "access_token"),
            refresh_token=_optional_str(raw_config, "refresh_token"),
            app_user_id=_optional_str(raw_config, "app_user_id"),
            app_user_name=_optional_str(raw_config, "app_user_name"),
            token_expires_at=_optional_str(raw_config, "token_expires_at"),
        )

    public_url = _optional_str(data, "public_url")
    return LinearProviderConfig(public_url=public_url, presences=presences, source="structured")


def _legacy_configured_app_keys(env_reader: Callable[[str], Optional[str]]) -> list[str]:
    raw = env_reader("LINEAR_APP_KEYS")
    if raw:
        return [normalize_app_key(item) for item in raw.split(",") if item.strip()]
    if (
        env_reader("LINEAR_CLIENT_ID")
        or env_reader("LINEAR_ACCESS_TOKEN")
        or env_reader("LINEAR_WEBHOOK_SECRET")
    ):
        return ["discovery_partner"]
    return []


def _legacy_presence(
    app_key: str,
    *,
    env_reader: Callable[[str], Optional[str]],
) -> LinearPresence:
    prefix = app_env_prefix(app_key)

    def read(name: str) -> Optional[str]:
        return env_reader(f"{prefix}_{name}") or env_reader(f"LINEAR_{name}")

    agent_id = read("AGENT_ID") or app_key
    if app_key == "discovery_partner":
        agent_id = env_reader("LINEAR_DISCOVERY_AGENT_ID") or agent_id

    return LinearPresence(
        presence_id=app_key,
        agent_id=agent_id,
        app_key=app_key,
        client_id=read("CLIENT_ID"),
        client_secret=read("CLIENT_SECRET"),
        webhook_secret=read("WEBHOOK_SECRET"),
        oauth_redirect_uri=read("OAUTH_REDIRECT_URI"),
        oauth_state=read("OAUTH_STATE"),
        access_token=read("ACCESS_TOKEN"),
        refresh_token=read("REFRESH_TOKEN"),
        app_user_id=read("APP_USER_ID"),
        app_user_name=read("APP_USER_NAME"),
        token_expires_at=read("TOKEN_EXPIRES_AT"),
    )


def _load_legacy_linear_config(
    env_reader: Callable[[str], Optional[str]],
) -> Optional[LinearProviderConfig]:
    keys = _legacy_configured_app_keys(env_reader)
    if not keys:
        return None
    presences = {key: _legacy_presence(key, env_reader=env_reader) for key in keys}
    public_url = env_reader("LINEAR_CAO_PUBLIC_URL")
    return LinearProviderConfig(public_url=public_url, presences=presences, source="legacy_env")


def load_linear_provider_config(
    *,
    config_path: Optional[Path] = None,
    agent_registry: Optional[AgentIdentityRegistry] = None,
    allow_legacy_env: bool = True,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Optional[LinearProviderConfig]:
    """Load Linear workspace-provider config, using legacy env only as fallback."""
    path = LINEAR_PROVIDER_CONFIG_PATH if config_path is None else config_path
    config: Optional[LinearProviderConfig]
    if path.exists():
        config = _load_structured_linear_config(path)
    elif allow_legacy_env:
        config = _load_legacy_linear_config(env_reader)
    else:
        config = None

    if config is not None:
        validate_linear_provider_config(config, agent_registry=agent_registry)
    return config


def validate_linear_provider_config(
    config: LinearProviderConfig,
    *,
    agent_registry: Optional[AgentIdentityRegistry] = None,
) -> None:
    """Validate Linear presence uniqueness and optional CAO identity references."""
    app_keys: set[str] = set()
    app_user_ids: set[str] = set()
    app_user_names: set[str] = set()
    oauth_states: set[str] = set()
    webhook_secrets: set[str] = set()
    agent_ids: set[str] = set()

    for presence in config.presences.values():
        if presence.app_key in app_keys:
            raise LinearWorkspaceProviderConfigError(
                f"Duplicate Linear app_key mapping: {presence.app_key}"
            )
        app_keys.add(presence.app_key)

        if presence.app_user_id:
            if presence.app_user_id in app_user_ids:
                raise LinearWorkspaceProviderConfigError(
                    f"Duplicate Linear app_user_id mapping: {presence.app_user_id}"
                )
            app_user_ids.add(presence.app_user_id)

        if presence.app_user_name:
            if presence.app_user_name in app_user_names:
                raise LinearWorkspaceProviderConfigError(
                    f"Duplicate Linear app_user_name mapping: {presence.app_user_name}"
                )
            app_user_names.add(presence.app_user_name)

        if presence.oauth_state:
            if presence.oauth_state in oauth_states:
                raise LinearWorkspaceProviderConfigError("Duplicate Linear oauth_state mapping")
            oauth_states.add(presence.oauth_state)

        if presence.webhook_secret:
            if presence.webhook_secret in webhook_secrets:
                raise LinearWorkspaceProviderConfigError("Duplicate Linear webhook_secret mapping")
            webhook_secrets.add(presence.webhook_secret)

        if presence.agent_id in agent_ids:
            raise LinearWorkspaceProviderConfigError(
                f"Duplicate Linear CAO agent_id mapping: {presence.agent_id}"
            )
        agent_ids.add(presence.agent_id)

        if agent_registry is not None and config.source != "legacy_env":
            try:
                agent_registry.get(presence.agent_id)
            except AgentIdentityConfigError as exc:
                raise LinearWorkspaceProviderConfigError(
                    f"Linear presence {presence.presence_id} references missing CAO agent "
                    f"identity: {presence.agent_id}"
                ) from exc


def _format_toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def save_linear_provider_config(
    config: LinearProviderConfig,
    *,
    config_path: Optional[Path] = None,
) -> None:
    """Write Linear provider config with owner-only permissions."""
    path = LINEAR_PROVIDER_CONFIG_PATH if config_path is None else config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if config.public_url:
        lines.append(f"public_url = {_format_toml_value(config.public_url)}")
        lines.append("")
    for presence_id in sorted(config.presences):
        presence = config.presences[presence_id]
        lines.append(f"[presences.{presence_id}]")
        for field in (
            "agent_id",
            "app_key",
            "client_id",
            "client_secret",
            "webhook_secret",
            "oauth_redirect_uri",
            "oauth_state",
            "access_token",
            "refresh_token",
            "app_user_id",
            "app_user_name",
            "token_expires_at",
        ):
            value = getattr(presence, field)
            if value:
                lines.append(f"{field} = {_format_toml_value(value)}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n")
    path.chmod(0o600)


def update_linear_presence_tokens(
    app_key: str,
    *,
    access_token: str,
    refresh_token: Optional[str] = None,
    app_user_id: Optional[str] = None,
    app_user_name: Optional[str] = None,
    token_expires_at: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> bool:
    """Persist OAuth token data to structured Linear config when available."""
    path = LINEAR_PROVIDER_CONFIG_PATH if config_path is None else config_path
    config = load_linear_provider_config(config_path=path, allow_legacy_env=False)
    if config is None:
        return False
    presence = config.presence_by_app_key(app_key)
    if presence is None:
        return False
    updated = replace(
        presence,
        access_token=access_token,
        refresh_token=refresh_token or presence.refresh_token,
        app_user_id=app_user_id or presence.app_user_id,
        app_user_name=app_user_name or presence.app_user_name,
        token_expires_at=token_expires_at or presence.token_expires_at,
    )
    config.presences[presence.presence_id] = updated
    save_linear_provider_config(config, config_path=path)
    return True


def persist_linear_oauth_install(
    *,
    app_key: Optional[str],
    access_token: str,
    refresh_token: Optional[str] = None,
    app_user_id: Optional[str] = None,
    app_user_name: Optional[str] = None,
    token_expires_at: Optional[str] = None,
    config_path: Optional[Path] = None,
    env_writer: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Persist Linear OAuth install data at the provider config edge.

    Returns True when structured provider config was updated. A False return
    means the legacy env compatibility path was used.
    """
    if app_key and update_linear_presence_tokens(
        app_key,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        app_user_id=app_user_id,
        app_user_name=app_user_name,
        config_path=config_path,
    ):
        return True

    write_env = env_writer or set_env_var
    prefix = app_env_prefix(app_key) if app_key else "LINEAR"
    write_env(f"{prefix}_ACCESS_TOKEN", access_token)
    if refresh_token:
        write_env(f"{prefix}_REFRESH_TOKEN", refresh_token)
    if token_expires_at:
        write_env(f"{prefix}_TOKEN_EXPIRES_AT", token_expires_at)
    if app_user_id:
        write_env(f"{prefix}_APP_USER_ID", app_user_id)
    if app_user_name:
        write_env(f"{prefix}_APP_USER_NAME", app_user_name)
    return False


def _extract_app_user_id(payload: Mapping[str, Any]) -> Optional[str]:
    keys = ("_cao_linear_app_user_id", "appUserId", "app_user_id", "agentAppUserId")
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)

    data = payload.get("data")
    if isinstance(data, Mapping):
        found = _extract_app_user_id(data)
        if found:
            return found

    for key in ("appUser", "agentUser", "viewer", "actor"):
        value = payload.get(key)
        if isinstance(value, Mapping) and value.get("id"):
            return str(value["id"])
    return None


def _extract_app_user_name(payload: Mapping[str, Any]) -> Optional[str]:
    for key in ("_cao_linear_app_user_name", "appUserName", "app_user_name"):
        value = payload.get(key)
        if value:
            return str(value)
    for key in ("appUser", "agentUser", "viewer", "actor"):
        value = payload.get(key)
        if isinstance(value, Mapping) and value.get("name"):
            return str(value["name"])
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _extract_app_user_name(data)
    return None


def _extract_app_key(payload: Mapping[str, Any]) -> Optional[str]:
    value = payload.get("_cao_linear_app_key") or payload.get("appKey") or payload.get("app_key")
    return normalize_app_key(str(value)) if value else None


def _legacy_identity_for_presence(
    presence: LinearPresence,
    env_reader: Callable[[str], Optional[str]],
) -> AgentIdentity:
    def read(name: str) -> Optional[str]:
        return env_reader(f"{app_env_prefix(presence.app_key)}_{name}") or env_reader(
            f"LINEAR_{name}"
        )

    fallback_slug = (
        "linear-discovery-partner"
        if presence.app_key == "discovery_partner"
        else f"linear-{presence.app_key.replace('_', '-')}"
    )
    session_name = (
        read("SESSION_NAME") or env_reader("LINEAR_DISCOVERY_SESSION_NAME") or fallback_slug
    )
    return AgentIdentity(
        id=presence.agent_id,
        display_name=presence.app_user_name or presence.agent_id.replace("_", " ").title(),
        agent_profile=read("AGENT_PROFILE")
        or env_reader("LINEAR_DISCOVERY_AGENT_PROFILE")
        or "developer",
        cli_provider=read("PROVIDER")
        or env_reader("LINEAR_DISCOVERY_PROVIDER")
        or DEFAULT_PROVIDER,
        workdir=read("WORKDIR") or env_reader("LINEAR_DISCOVERY_WORKDIR") or os.getcwd(),
        session_name=session_name,
    )


class LinearWorkspaceProvider:
    """Linear workspace-provider lifecycle and presence resolver."""

    name = "linear"

    def __init__(
        self,
        *,
        agent_registry: Optional[AgentIdentityRegistry] = None,
        config_path: Optional[Path] = None,
        env_reader: Callable[[str], Optional[str]] = linear_env,
    ) -> None:
        self._agent_registry = agent_registry or load_agent_identity_registry()
        self._config_path = config_path
        self._env_reader = env_reader
        self._config: Optional[LinearProviderConfig] = None

    @property
    def config(self) -> Optional[LinearProviderConfig]:
        return self._config

    def initialize(self) -> None:
        self._config = load_linear_provider_config(
            config_path=self._config_path,
            agent_registry=self._agent_registry,
            allow_legacy_env=True,
            env_reader=self._env_reader,
        )
        if self._config is None:
            raise LinearWorkspaceProviderConfigError(
                "Linear workspace provider is enabled but no Linear config was found"
            )

    def _load_config(self) -> LinearProviderConfig:
        if self._config is None:
            self.initialize()
        if self._config is None:
            raise LinearWorkspaceProviderConfigError("Linear workspace provider is not configured")
        return self._config

    def resolve_presence(
        self,
        *,
        app_key: Optional[str] = None,
        app_user_id: Optional[str] = None,
        app_user_name: Optional[str] = None,
    ) -> LinearPresence:
        config = self._load_config()
        presence: Optional[LinearPresence] = None
        if app_key:
            presence = config.presence_by_app_key(app_key)
            if presence is None:
                raise LinearWorkspaceProviderConfigError(f"Unknown Linear app key: {app_key}")
        if app_user_id:
            by_user = config.presence_by_app_user_id(app_user_id)
            if by_user is None:
                raise LinearWorkspaceProviderConfigError(
                    f"Unknown Linear app user id: {app_user_id}"
                )
            if presence is not None and presence != by_user:
                raise LinearWorkspaceProviderConfigError(
                    "Linear app key and app user id resolve to different CAO identities"
                )
            presence = by_user
        if presence is None and app_user_name:
            presence = config.presence_by_app_user_name(app_user_name)
        if (
            presence is None
            and config.source == "legacy_env"
            and not app_key
            and not app_user_id
            and not app_user_name
            and len(config.presences) == 1
        ):
            presence = next(iter(config.presences.values()))
        if presence is None:
            raise LinearWorkspaceProviderConfigError(
                "Linear presence could not be resolved from app key or app user id"
            )
        return presence

    def resolve_presence_from_payload(self, payload: Mapping[str, Any]) -> LinearPresence:
        return self.resolve_presence(
            app_key=_extract_app_key(payload),
            app_user_id=_extract_app_user_id(payload),
            app_user_name=_extract_app_user_name(payload),
        )

    def resolve_identity_for_presence(self, presence: LinearPresence) -> AgentIdentity:
        config = self._load_config()
        if config.source == "legacy_env":
            return _legacy_identity_for_presence(presence, self._env_reader)
        return self._agent_registry.get(presence.agent_id)

    def resolve_event(self, payload: Mapping[str, Any]) -> LinearResolvedPresence:
        presence = self.resolve_presence_from_payload(payload)
        return LinearResolvedPresence(
            presence=presence,
            identity=self.resolve_identity_for_presence(presence),
        )


def canonical_session_name(session_name: str) -> str:
    """Return a CAO tmux session name with the managed prefix."""
    if session_name.startswith(SESSION_PREFIX):
        return session_name
    return f"{SESSION_PREFIX}{session_name}"


def set_default_linear_workspace_provider(provider: LinearWorkspaceProvider) -> None:
    """Set the startup-validated Linear provider used by routes/runtime."""
    global _default_linear_workspace_provider
    _default_linear_workspace_provider = provider


def get_linear_workspace_provider() -> LinearWorkspaceProvider:
    """Return the startup provider when available, else a lazy compatibility provider."""
    if _default_linear_workspace_provider is not None:
        return _default_linear_workspace_provider
    return LinearWorkspaceProvider()


def webhook_secret_presences(
    *,
    config_path: Optional[Path] = None,
    env_reader: Callable[[str], Optional[str]] = linear_env,
) -> Iterable[LinearPresence]:
    """Yield configured Linear presences that can verify webhooks."""
    config = load_linear_provider_config(
        config_path=config_path,
        allow_legacy_env=True,
        env_reader=env_reader,
    )
    if config is None:
        return []
    return [presence for presence in config.presences.values() if presence.webhook_secret]


def has_legacy_linear_provider_config(
    *, env_reader: Callable[[str], Optional[str]] = linear_env
) -> bool:
    """Return whether legacy Linear env config is present for route compatibility."""
    return _load_legacy_linear_config(env_reader) is not None


def should_enable_linear_routes() -> bool:
    """Return whether Linear routes should be available for this CAO process.

    Structured workspace-provider config is the primary path. Legacy no-config
    route availability is retained only when legacy Linear env config is
    actually present.
    """
    if workspace_provider_config_exists():
        return is_workspace_provider_enabled("linear", default_when_unconfigured=False)
    return has_legacy_linear_provider_config()
