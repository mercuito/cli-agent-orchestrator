"""Linear workspace-provider config, presence mapping, and lifecycle."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
from cli_agent_orchestrator.linear.provider_tools import (
    CREATE_ISSUE_TOOL,
    ISSUE_TARGETING_TOOLS,
    LINEAR_PROVIDER_TOOLS,
    UPDATE_ISSUE_FIELDS,
    UPDATE_ISSUE_TOOL,
    LinearToolAccess,
    LinearToolProvider,
)
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.env import load_env_vars, set_env_var
from cli_agent_orchestrator.workspace_providers.registry import (
    is_workspace_provider_enabled,
    workspace_provider_config_exists,
)
from cli_agent_orchestrator.workspace_providers.tool_access import ProviderToolAccessPolicy

LINEAR_PROVIDER_CONFIG_PATH = CAO_HOME_DIR / "workspace-providers" / "linear.toml"
APP_KEY_PATTERN = re.compile(r"[^A-Za-z0-9]+")
TOOL_ACCESS_ISSUES_KEY = "issues"
TOOL_ACCESS_CREATE_TEAM_IDS_KEY = "create_team_ids"
TOOL_ACCESS_CREATE_PROJECT_IDS_KEY = "create_project_ids"
TOOL_ACCESS_CREATE_PARENT_ISSUES_KEY = "create_parent_issues"
TOOL_ACCESS_ALLOW_TOP_LEVEL_CREATE_KEY = "allow_top_level_create"
TOOL_ACCESS_UPDATE_FIELDS_KEY = "update_fields"
TOOL_ACCESS_REASON_KEY = "reason"
AGENT_POLICIES_SECTION = "agent_policies"
AGENT_POLICIES_ENABLED_KEY = "enabled"
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


LinearCredentialChecker = Callable[[LinearPresence], Mapping[str, Any]]


@dataclass(frozen=True)
class LinearProviderConfig:
    """Linear workspace-provider config loaded from structured TOML or legacy env."""

    public_url: Optional[str]
    presences: dict[str, LinearPresence]
    tool_access: dict[str, LinearToolAccess]
    agent_policies_enabled: bool = False
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


def _optional_str_list(
    table: Mapping[str, Any],
    key: str,
    *,
    location: str,
    required: bool = False,
) -> tuple[str, ...]:
    value = table.get(key)
    if value is None:
        if required:
            raise LinearWorkspaceProviderConfigError(
                f"{location}.{key} must be a non-empty string list"
            )
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LinearWorkspaceProviderConfigError(
            f"{location}.{key} must be a non-empty string list"
        )
    normalized = tuple(item.strip() for item in value if item.strip())
    if required and not normalized:
        raise LinearWorkspaceProviderConfigError(
            f"{location}.{key} must be a non-empty string list"
        )
    return normalized


def _optional_bool(table: Mapping[str, Any], key: str, *, location: str) -> bool:
    value = table.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise LinearWorkspaceProviderConfigError(f"{location}.{key} must be a boolean")
    return value


def _load_linear_agent_policies_enabled(data: Mapping[str, Any]) -> bool:
    raw_table = data.get(AGENT_POLICIES_SECTION, {})
    if raw_table is None:
        return False
    if not isinstance(raw_table, Mapping):
        raise LinearWorkspaceProviderConfigError(f"{AGENT_POLICIES_SECTION} must be a table")
    return _optional_bool(
        raw_table,
        AGENT_POLICIES_ENABLED_KEY,
        location=AGENT_POLICIES_SECTION,
    )


def _load_linear_tool_access(data: Mapping[str, Any]) -> dict[str, LinearToolAccess]:
    raw_table = data.get("tool_access", {})
    if raw_table is None:
        return {}
    if not isinstance(raw_table, Mapping):
        raise LinearWorkspaceProviderConfigError("tool_access must be a table")

    tool_access: dict[str, LinearToolAccess] = {}
    for raw_access_id, raw_config in raw_table.items():
        access_id = str(raw_access_id).strip()
        location = f"tool_access.{access_id or '<empty>'}"
        if not access_id:
            raise LinearWorkspaceProviderConfigError("Linear tool_access id must be non-empty")
        if not isinstance(raw_config, Mapping):
            raise LinearWorkspaceProviderConfigError(f"{location} must be a table")

        agent_id = _optional_str(raw_config, "agent_id")
        agent_profile = _optional_str(raw_config, "agent_profile")
        if bool(agent_id) == bool(agent_profile):
            raise LinearWorkspaceProviderConfigError(
                f"{location} must configure exactly one of agent_id or agent_profile"
            )
        tools = _optional_str_list(raw_config, "tools", location=location, required=True)
        for index, tool in enumerate(tools):
            if tool not in LINEAR_PROVIDER_TOOLS:
                raise LinearWorkspaceProviderConfigError(
                    f"{location}.tools[{index}] unknown Linear tool: {tool}"
                )
        issues = _optional_str_list(
            raw_config,
            TOOL_ACCESS_ISSUES_KEY,
            location=location,
            required=any(tool in ISSUE_TARGETING_TOOLS for tool in tools),
        )
        create_team_ids = _optional_str_list(
            raw_config,
            TOOL_ACCESS_CREATE_TEAM_IDS_KEY,
            location=location,
            required=CREATE_ISSUE_TOOL in tools,
        )
        create_project_ids = _optional_str_list(
            raw_config,
            TOOL_ACCESS_CREATE_PROJECT_IDS_KEY,
            location=location,
        )
        create_parent_issues = _optional_str_list(
            raw_config,
            TOOL_ACCESS_CREATE_PARENT_ISSUES_KEY,
            location=location,
        )
        allow_top_level_create = _optional_bool(
            raw_config,
            TOOL_ACCESS_ALLOW_TOP_LEVEL_CREATE_KEY,
            location=location,
        )
        if CREATE_ISSUE_TOOL in tools and not allow_top_level_create and not create_parent_issues:
            raise LinearWorkspaceProviderConfigError(
                f"{location} must allow top-level issue creation or configure "
                "create_parent_issues for cao_linear.create_issue"
            )
        update_fields = _optional_str_list(
            raw_config,
            TOOL_ACCESS_UPDATE_FIELDS_KEY,
            location=location,
            required=UPDATE_ISSUE_TOOL in tools,
        )
        for index, field in enumerate(update_fields):
            if field not in UPDATE_ISSUE_FIELDS:
                raise LinearWorkspaceProviderConfigError(
                    f"{location}.update_fields[{index}] unknown Linear update field: {field}"
                )
        reason = _optional_str(raw_config, TOOL_ACCESS_REASON_KEY)
        tool_access[access_id] = LinearToolAccess(
            access_id=access_id,
            agent_id=agent_id,
            agent_profile=agent_profile,
            tools=tools,
            issues=issues,
            create_team_ids=create_team_ids,
            create_project_ids=create_project_ids,
            create_parent_issues=create_parent_issues,
            allow_top_level_create=allow_top_level_create,
            update_fields=update_fields,
            reason=reason,
        )
    return tool_access


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
    return LinearProviderConfig(
        public_url=public_url,
        presences=presences,
        tool_access=_load_linear_tool_access(data),
        agent_policies_enabled=_load_linear_agent_policies_enabled(data),
        source="structured",
    )


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
    return LinearProviderConfig(
        public_url=public_url,
        presences=presences,
        tool_access={},
        agent_policies_enabled=False,
        source="legacy_env",
    )


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

    for access in config.tool_access.values():
        if access.agent_id and access.agent_id not in agent_ids:
            raise LinearWorkspaceProviderConfigError(
                f"{access.location}.agent_id references missing Linear presence: {access.agent_id}"
            )


def parse_linear_token_expires_at(presence: LinearPresence) -> Optional[datetime]:
    if not presence.token_expires_at:
        return None
    raw = presence.token_expires_at.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LinearWorkspaceProviderConfigError(
            f"Linear presence {presence.presence_id} token_expires_at is not a valid ISO datetime"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_check_linear_presence_credentials(presence: LinearPresence) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    try:
        access_token = app_client.access_token_for_presence(presence)
        viewer = app_client.fetch_viewer(access_token)
    except app_client.LinearOAuthError as exc:
        raise LinearWorkspaceProviderConfigError(
            f"Linear presence {presence.presence_id} could not obtain a valid access token; "
            "reauthorize the Linear app if token refresh is unavailable"
        ) from exc
    return viewer


def preflight_linear_provider_credentials(
    config: LinearProviderConfig,
    *,
    credential_checker: LinearCredentialChecker = _default_check_linear_presence_credentials,
) -> None:
    """Verify configured Linear app credentials before the provider accepts traffic."""
    for presence in config.presences.values():
        if not presence.access_token and not presence.refresh_token:
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} is missing access_token and "
                "refresh_token; reauthorize the Linear app before starting the provider"
            )
        expires_at = parse_linear_token_expires_at(presence)
        if (
            expires_at is not None
            and expires_at <= datetime.now(timezone.utc)
            and not presence.refresh_token
        ):
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} access token expired at "
                f"{expires_at.isoformat()} and no refresh_token is configured; reauthorize the "
                "Linear app before starting the provider"
            )
        viewer = credential_checker(presence)
        viewer_id = viewer.get("id")
        if not viewer_id:
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} credential check did not return a "
                "viewer id"
            )
        if presence.app_user_id and presence.app_user_id != str(viewer_id):
            raise LinearWorkspaceProviderConfigError(
                f"Linear presence {presence.presence_id} app_user_id does not match the "
                "authenticated Linear app user"
            )


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
    lines.append(
        "# WIP agent-presence policy guardrails. Keep disabled while workflow shape is "
        "being explored."
    )
    lines.append(f"[{AGENT_POLICIES_SECTION}]")
    lines.append(
        f"{AGENT_POLICIES_ENABLED_KEY} = "
        f"{_format_toml_value(config.agent_policies_enabled)}"
    )
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
    for access_id in sorted(config.tool_access):
        access = config.tool_access[access_id]
        lines.append(f"[tool_access.{access_id}]")
        if access.agent_id:
            lines.append(f"agent_id = {_format_toml_value(access.agent_id)}")
        if access.agent_profile:
            lines.append(f"agent_profile = {_format_toml_value(access.agent_profile)}")
        lines.append(f"tools = {_format_toml_value(list(access.tools))}")
        if access.issues:
            lines.append(f"{TOOL_ACCESS_ISSUES_KEY} = {_format_toml_value(list(access.issues))}")
        if access.create_team_ids:
            lines.append(
                f"{TOOL_ACCESS_CREATE_TEAM_IDS_KEY} = "
                f"{_format_toml_value(list(access.create_team_ids))}"
            )
        if access.create_project_ids:
            lines.append(
                f"{TOOL_ACCESS_CREATE_PROJECT_IDS_KEY} = "
                f"{_format_toml_value(list(access.create_project_ids))}"
            )
        if access.create_parent_issues:
            lines.append(
                f"{TOOL_ACCESS_CREATE_PARENT_ISSUES_KEY} = "
                f"{_format_toml_value(list(access.create_parent_issues))}"
            )
        if access.allow_top_level_create:
            lines.append(
                f"{TOOL_ACCESS_ALLOW_TOP_LEVEL_CREATE_KEY} = "
                f"{_format_toml_value(access.allow_top_level_create)}"
            )
        if access.update_fields:
            lines.append(
                f"{TOOL_ACCESS_UPDATE_FIELDS_KEY} = "
                f"{_format_toml_value(list(access.update_fields))}"
            )
        if access.reason:
            lines.append(f"{TOOL_ACCESS_REASON_KEY} = {_format_toml_value(access.reason)}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n")
    path.chmod(0o600)


def _toml_section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    header = f"[{section}]"
    start: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if stripped == header:
                start = index
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            return start, index
    if start is None:
        return None
    return start, len(lines)


def _patch_toml_section_values(
    text: str,
    *,
    section: str,
    values: Mapping[str, Any],
) -> str:
    lines = text.splitlines()
    bounds = _toml_section_bounds(lines, section)
    if bounds is None:
        return text
    start, end = bounds
    pending = dict(values)
    key_pattern = re.compile(r"^(\s*)([A-Za-z0-9_]+)\s*=.*$")
    for index in range(start + 1, end):
        match = key_pattern.match(lines[index])
        if match is None:
            continue
        indent, key = match.groups()
        if key in pending:
            lines[index] = f"{indent}{key} = {_format_toml_value(pending.pop(key))}"
    insert_at = end
    for key, value in pending.items():
        lines.insert(insert_at, f"{key} = {_format_toml_value(value)}")
        insert_at += 1
    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


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
    updates: dict[str, str] = {"access_token": access_token}
    if refresh_token:
        updates["refresh_token"] = refresh_token
    if app_user_id:
        updates["app_user_id"] = app_user_id
    if app_user_name:
        updates["app_user_name"] = app_user_name
    if token_expires_at:
        updates["token_expires_at"] = token_expires_at
    patched = _patch_toml_section_values(
        path.read_text(),
        section=f"presences.{presence.presence_id}",
        values=updates,
    )
    path.write_text(patched)
    path.chmod(0o600)
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


def _agent_profile_exists(profile: str) -> bool:
    try:
        load_agent_profile(profile)
    except Exception:
        return False
    return True


class LinearWorkspaceProvider:
    """Linear workspace-provider lifecycle and presence resolver."""

    name = "linear"

    def __init__(
        self,
        *,
        agent_registry: Optional[AgentIdentityRegistry] = None,
        config_path: Optional[Path] = None,
        env_reader: Callable[[str], Optional[str]] = linear_env,
        preflight_credentials: bool = True,
        credential_checker: Optional[LinearCredentialChecker] = None,
    ) -> None:
        self._agent_registry = agent_registry or load_agent_identity_registry()
        self._config_path = config_path
        self._env_reader = env_reader
        self._preflight_credentials = preflight_credentials
        self._credential_checker = credential_checker or _default_check_linear_presence_credentials
        self._config: Optional[LinearProviderConfig] = None

    @property
    def config(self) -> Optional[LinearProviderConfig]:
        return self._config

    def has_provider_tool_access_config(self) -> bool:
        """Return whether Linear config declares CAO-mediated tool access."""
        try:
            config = load_linear_provider_config(
                config_path=self._config_path,
                agent_registry=self._agent_registry,
                allow_legacy_env=False,
                env_reader=self._env_reader,
            )
        except LinearWorkspaceProviderConfigError:
            return True
        return bool(config and config.tool_access)

    def agent_policies_enabled(self) -> bool:
        """Return whether Linear's WIP agent-presence policy guardrails are enabled."""
        return self._load_config().agent_policies_enabled

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
        if self._preflight_credentials:
            preflight_linear_provider_credentials(
                self._config,
                credential_checker=self._credential_checker,
            )

    def provider_tool_access(self) -> ProviderToolAccessPolicy:
        """Return Linear CAO-mediated MCP tool access."""
        config = self._load_config()
        return LinearToolProvider(
            config=config,
            agent_registry=self._agent_registry,
            profile_exists=_agent_profile_exists,
        ).provider_tool_access()

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
            if by_user is None and presence is None:
                raise LinearWorkspaceProviderConfigError(
                    f"Unknown Linear app user id: {app_user_id}"
                )
            if by_user is not None and presence is not None and presence != by_user:
                raise LinearWorkspaceProviderConfigError(
                    "Linear app key and app user id resolve to different CAO identities"
                )
            if by_user is not None:
                presence = by_user
        if app_user_name:
            by_name = config.presence_by_app_user_name(app_user_name)
            if by_name is not None and presence is not None and presence != by_name:
                raise LinearWorkspaceProviderConfigError(
                    "Linear app key and app user name resolve to different CAO identities"
                )
            if presence is None:
                presence = by_name
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

    def resolve_identity_for_agent_id(self, agent_id: str) -> AgentIdentity:
        """Resolve a CAO agent identity through this provider's presence mapping."""
        config = self._load_config()
        presence = next(
            (
                candidate
                for candidate in config.presences.values()
                if candidate.agent_id == agent_id
            ),
            None,
        )
        if presence is None:
            raise LinearWorkspaceProviderConfigError(
                f"Linear provider has no presence for CAO agent identity: {agent_id}"
            )
        return self.resolve_identity_for_presence(presence)

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


def should_enable_linear_agent_policies() -> bool:
    """Return whether Linear's WIP agent-presence policy guardrails should run."""
    try:
        return get_linear_workspace_provider().agent_policies_enabled()
    except LinearWorkspaceProviderConfigError:
        return False


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
