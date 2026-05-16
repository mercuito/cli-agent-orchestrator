"""Linear-owned CAO-mediated MCP tools."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, Callable, Mapping, cast

from cli_agent_orchestrator.linear import provider_tool_queries as linear_queries
from cli_agent_orchestrator.mcp_server.freshness import callable_runtime_fingerprint
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderMediatedToolDefinition,
    ProviderToolAccessConfigError,
    ProviderToolAccessIssue,
    ProviderToolAccessPolicy,
    ProviderToolAccessRequest,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
    normalize_provider_tool_access,
)

PROVIDER_NAME = "linear"
GET_ISSUE_TOOL = "cao_linear.get_issue"
LIST_COMMENTS_TOOL = "cao_linear.list_comments"
CREATE_COMMENT_TOOL = "cao_linear.create_comment"
OPEN_AGENT_SESSION_ON_ISSUE_TOOL = "cao_linear.open_agent_session_on_issue"
CREATE_ISSUE_TOOL = "cao_linear.create_issue"
UPDATE_ISSUE_TOOL = "cao_linear.update_issue"
CREATE_PROJECT_TOOL = "cao_linear.create_project"
LIST_TEAMS_TOOL = "cao_linear.list_teams"
GET_TEAM_TOOL = "cao_linear.get_team"
LIST_USERS_TOOL = "cao_linear.list_users"
GET_USER_TOOL = "cao_linear.get_user"
LIST_ISSUE_STATUSES_TOOL = "cao_linear.list_issue_statuses"
GET_ISSUE_STATUS_TOOL = "cao_linear.get_issue_status"
LIST_ISSUE_LABELS_TOOL = "cao_linear.list_issue_labels"
GET_ISSUE_LABEL_TOOL = "cao_linear.get_issue_label"
LIST_PROJECTS_TOOL = "cao_linear.list_projects"
GET_PROJECT_TOOL = "cao_linear.get_project"
LIST_ISSUES_TOOL = "cao_linear.list_issues"
SEARCH_ISSUES_TOOL = "cao_linear.search_issues"
GET_COMMENT_TOOL = "cao_linear.get_comment"
GET_AGENT_SESSION_TOOL = "cao_linear.get_agent_session"
LIST_AGENT_SESSION_ACTIVITIES_TOOL = "cao_linear.list_agent_session_activities"
GET_AGENT_SESSION_ACTIVITY_TOOL = "cao_linear.get_agent_session_activity"
LIST_DOCUMENTS_TOOL = "cao_linear.list_documents"
GET_DOCUMENT_TOOL = "cao_linear.get_document"
SEARCH_DOCUMENTS_TOOL = "cao_linear.search_documents"
READ_POLICY_HOOK = "linear_read_policy"
EXPLORATION_READ_POLICY_HOOK = "linear_exploration_read_policy"
COMMENT_WRITE_POLICY_HOOK = "linear_comment_write_policy"
AGENT_SESSION_WRITE_POLICY_HOOK = "linear_agent_session_write_policy"
CREATE_ISSUE_POLICY_HOOK = "linear_create_issue_policy"
UPDATE_ISSUE_POLICY_HOOK = "linear_update_issue_policy"
CREATE_PROJECT_POLICY_HOOK = "linear_create_project_policy"
LINEAR_WORKSPACE_CONTEXT_RESULT_HOOK = "linear_workspace_context_result"
LINEAR_READ_TOOLS = frozenset({GET_ISSUE_TOOL, LIST_COMMENTS_TOOL})
LINEAR_COMMENT_WRITE_TOOLS = frozenset({CREATE_COMMENT_TOOL})
LINEAR_AGENT_SESSION_WRITE_TOOLS = frozenset({OPEN_AGENT_SESSION_ON_ISSUE_TOOL})
LINEAR_ISSUE_MUTATION_TOOLS = frozenset({CREATE_ISSUE_TOOL, UPDATE_ISSUE_TOOL})
LINEAR_CONTEXT_MAPPING_MUTATION_TOOLS = frozenset({CREATE_ISSUE_TOOL})
LINEAR_PROJECT_MUTATION_TOOLS = frozenset({CREATE_PROJECT_TOOL})
LINEAR_EXPLORATION_READ_TOOLS = frozenset(
    {
        LIST_TEAMS_TOOL,
        GET_TEAM_TOOL,
        LIST_USERS_TOOL,
        GET_USER_TOOL,
        LIST_ISSUE_STATUSES_TOOL,
        GET_ISSUE_STATUS_TOOL,
        LIST_ISSUE_LABELS_TOOL,
        GET_ISSUE_LABEL_TOOL,
        LIST_PROJECTS_TOOL,
        GET_PROJECT_TOOL,
        LIST_ISSUES_TOOL,
        SEARCH_ISSUES_TOOL,
        GET_COMMENT_TOOL,
        GET_AGENT_SESSION_TOOL,
        LIST_AGENT_SESSION_ACTIVITIES_TOOL,
        GET_AGENT_SESSION_ACTIVITY_TOOL,
        LIST_DOCUMENTS_TOOL,
        GET_DOCUMENT_TOOL,
        SEARCH_DOCUMENTS_TOOL,
    }
)
LINEAR_PROVIDER_TOOLS = (
    LINEAR_READ_TOOLS
    | LINEAR_EXPLORATION_READ_TOOLS
    | LINEAR_COMMENT_WRITE_TOOLS
    | LINEAR_AGENT_SESSION_WRITE_TOOLS
    | LINEAR_ISSUE_MUTATION_TOOLS
    | LINEAR_PROJECT_MUTATION_TOOLS
)
ISSUE_TARGETING_TOOLS = (
    LINEAR_READ_TOOLS
    | LINEAR_COMMENT_WRITE_TOOLS
    | LINEAR_AGENT_SESSION_WRITE_TOOLS
    | {UPDATE_ISSUE_TOOL}
)
LIST_LIMIT_TOOLS = frozenset(
    {
        LIST_TEAMS_TOOL,
        LIST_USERS_TOOL,
        LIST_ISSUE_STATUSES_TOOL,
        LIST_ISSUE_LABELS_TOOL,
        LIST_PROJECTS_TOOL,
        LIST_ISSUES_TOOL,
        SEARCH_ISSUES_TOOL,
        LIST_AGENT_SESSION_ACTIVITIES_TOOL,
        LIST_DOCUMENTS_TOOL,
        SEARCH_DOCUMENTS_TOOL,
    }
)
CREATE_ISSUE_FIELDS = frozenset(
    {
        "team_id",
        "title",
        "description",
        "project_id",
        "parent_issue",
        "state_id",
        "assignee_id",
        "label_ids",
        "priority",
    }
)
UPDATE_ISSUE_FIELDS = frozenset(
    {
        "title",
        "description",
        "state_id",
        "assignee_id",
        "project_id",
        "parent_issue",
        "label_ids",
        "priority",
    }
)
CREATE_PROJECT_FIELDS = frozenset(
    {
        "team_ids",
        "name",
        "description",
        "content",
        "lead_id",
        "member_ids",
        "start_date",
        "target_date",
        "priority",
    }
)
REFERENCE_FIELDS = frozenset({"project_id", "state_id", "assignee_id"})
PROJECT_REFERENCE_FIELDS = frozenset({"lead_id", "member_ids"})
MAX_DESCRIPTION_CHARS = 4000
MAX_COMMENT_BODY_CHARS = 4000
DEFAULT_COMMENT_LIMIT = 50
MAX_COMMENT_LIMIT = 100
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
_TRUNCATED = "...[truncated]"
DEFAULT_LINEAR_POLICY_REASON = (
    "This agent is configured to not have access to that Linear target or operation."
)
# External contract source: Linear's official GraphQL developer docs document
# issue lookup by shorthand id/UUID, core fields such as id, title, description,
# assignee, createdAt, and archivedAt, and GraphQL mutations returning success
# plus selected objects. Linear's API docs also document create-comment API key
# scope. The public schema explorer is the source for commentCreate fields:
# https://linear.app/developers/graphql
# https://linear.app/docs/api-and-webhooks


class LinearToolError(RuntimeError):
    """Recoverable Linear tool failure with an operator-facing reason."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


@dataclass(frozen=True)
class LinearToolAccess:
    """Provider-native Linear tool policy entry from ``linear.toml``."""

    access_id: str
    agent_id: str | None
    agent_profile: str | None
    tools: tuple[str, ...]
    issues: tuple[str, ...]
    create_team_ids: tuple[str, ...] = ()
    create_project_ids: tuple[str, ...] = ()
    create_parent_issues: tuple[str, ...] = ()
    allow_top_level_create: bool = False
    update_fields: tuple[str, ...] = ()
    reason: str | None = None
    source_location: str | None = None

    @property
    def location(self) -> str:
        if self.source_location is not None:
            return self.source_location
        return f"tool_access.{self.access_id}"


def _with_linear_runtime_generation(
    provider: "LinearToolProvider",
    tools: tuple[ProviderMediatedToolDefinition, ...],
) -> tuple[ProviderMediatedToolDefinition, ...]:
    return tuple(
        replace(tool, runtime_generation=_linear_mcp_runtime_generation_material(provider, tool))
        for tool in tools
    )


LinearRuntimeDependency = tuple[str, Callable[..., Any], bool]


def _linear_runtime_dependency_modules() -> Mapping[str, ModuleType]:
    from cli_agent_orchestrator.linear import app_client
    from cli_agent_orchestrator.linear import workspace_provider as linear_provider

    return {
        "app_client": app_client,
        "linear_queries": linear_queries,
        "linear_provider": linear_provider,
    }


def _linear_mcp_runtime_generation_material(
    provider: "LinearToolProvider",
    tool: ProviderMediatedToolDefinition,
) -> dict[str, Any]:
    dependencies = _linear_runtime_dependency_callables(provider, tool.name)
    dependency_modules = _linear_runtime_dependency_modules()
    return {
        "schema_version": "cao-linear-mcp-tool-runtime-generation.v1",
        "tool_name": tool.name,
        "handler": callable_runtime_fingerprint(
            tool.handler,
            dependency_modules=dependency_modules,
            follow_local_helpers=False,
        ),
        "constants": _linear_runtime_constant_material(tool.name),
        "dependencies": {
            name: callable_runtime_fingerprint(
                dependency,
                dependency_modules=dependency_modules,
                follow_local_helpers=follow_local_helpers,
            )
            for name, dependency, follow_local_helpers in dependencies
        },
    }


def _linear_runtime_dependency_callables(
    provider: "LinearToolProvider",
    tool_name: str,
) -> tuple[LinearRuntimeDependency, ...]:
    query_dependencies: dict[str, Callable[..., Any]] = {
        LIST_TEAMS_TOOL: linear_queries.list_teams,
        GET_TEAM_TOOL: linear_queries.get_team,
        LIST_USERS_TOOL: linear_queries.list_users,
        GET_USER_TOOL: linear_queries.get_user,
        LIST_ISSUE_STATUSES_TOOL: linear_queries.list_issue_statuses,
        GET_ISSUE_STATUS_TOOL: linear_queries.get_issue_status,
        LIST_ISSUE_LABELS_TOOL: linear_queries.list_issue_labels,
        GET_ISSUE_LABEL_TOOL: linear_queries.get_issue_label,
        LIST_PROJECTS_TOOL: linear_queries.list_projects,
        GET_PROJECT_TOOL: linear_queries.get_project,
        LIST_ISSUES_TOOL: linear_queries.list_issues,
        SEARCH_ISSUES_TOOL: linear_queries.search_issues,
        GET_COMMENT_TOOL: linear_queries.get_comment,
        GET_AGENT_SESSION_TOOL: linear_queries.get_agent_session,
        LIST_AGENT_SESSION_ACTIVITIES_TOOL: linear_queries.list_agent_session_activities,
        GET_AGENT_SESSION_ACTIVITY_TOOL: linear_queries.get_agent_session_activity,
        LIST_DOCUMENTS_TOOL: linear_queries.list_documents,
        GET_DOCUMENT_TOOL: linear_queries.get_document,
        SEARCH_DOCUMENTS_TOOL: linear_queries.search_documents,
    }
    from cli_agent_orchestrator.linear import app_client
    from cli_agent_orchestrator.linear import workspace_provider as linear_provider

    issue_read_dependencies: tuple[LinearRuntimeDependency, ...] = (
        ("LinearToolProvider._authorize_before_call", provider._authorize_before_call, False),
        ("LinearToolProvider._authorized_issue_request", provider._authorized_issue_request, True),
        ("LinearToolProvider._presence_for_identity", provider._presence_for_identity, True),
        (
            "LinearToolProvider._require_returned_issue_allowed",
            provider._require_returned_issue_allowed,
            True,
        ),
    )
    local_dependencies: dict[str, tuple[LinearRuntimeDependency, ...]] = {
        GET_ISSUE_TOOL: (
            *issue_read_dependencies,
            ("_fetch_issue", _fetch_issue, True),
            ("_issue_from_payload", _issue_from_payload, True),
            ("_compact_issue_payload", _compact_issue_payload, True),
        ),
        LIST_COMMENTS_TOOL: (
            *issue_read_dependencies,
            ("_comment_limit", _comment_limit, True),
            ("_fetch_issue_comments", _fetch_issue_comments, True),
            ("_issue_from_payload", _issue_from_payload, True),
            ("_comments_from_issue", _comments_from_issue, True),
        ),
        CREATE_COMMENT_TOOL: (
            (
                "LinearToolProvider._authorize_comment_before_call",
                provider._authorize_comment_before_call,
                False,
            ),
            (
                "LinearToolProvider._authorized_issue_request",
                provider._authorized_issue_request,
                True,
            ),
            ("LinearToolProvider._presence_for_identity", provider._presence_for_identity, True),
            (
                "LinearToolProvider._require_returned_issue_allowed",
                provider._require_returned_issue_allowed,
                True,
            ),
            ("_comment_body_from_arguments", _comment_body_from_arguments, True),
            ("_fetch_issue", _fetch_issue, True),
            ("_issue_from_payload", _issue_from_payload, True),
            ("_create_linear_comment", _create_linear_comment, True),
            ("_created_comment_from_payload", _created_comment_from_payload, True),
            ("_compact_created_comment_payload", _compact_created_comment_payload, True),
        ),
        OPEN_AGENT_SESSION_ON_ISSUE_TOOL: (
            (
                "LinearToolProvider._authorize_agent_session_before_call",
                provider._authorize_agent_session_before_call,
                False,
            ),
            (
                "LinearToolProvider._authorized_issue_request",
                provider._authorized_issue_request,
                True,
            ),
            ("LinearToolProvider._presence_for_identity", provider._presence_for_identity, True),
            (
                "LinearToolProvider._require_returned_issue_allowed",
                provider._require_returned_issue_allowed,
                True,
            ),
            (
                "_agent_session_initial_body_from_arguments",
                _agent_session_initial_body_from_arguments,
                True,
            ),
            ("_fetch_issue", _fetch_issue, True),
            ("_issue_from_payload", _issue_from_payload, True),
            ("_open_linear_agent_session_on_issue", _open_linear_agent_session_on_issue, True),
            (
                "app_client.create_agent_session_on_issue",
                app_client.create_agent_session_on_issue,
                True,
            ),
            ("app_client.create_agent_activity", app_client.create_agent_activity, True),
            ("app_client.public_cao_agent_url", app_client.public_cao_agent_url, True),
            (
                "_compact_created_agent_session_payload",
                _compact_created_agent_session_payload,
                True,
            ),
        ),
        CREATE_ISSUE_TOOL: (
            (
                "LinearToolProvider._authorize_create_issue_before_call",
                provider._authorize_create_issue_before_call,
                False,
            ),
            (
                "LinearToolProvider._validated_create_issue_request",
                provider._validated_create_issue_request,
                True,
            ),
            ("LinearToolProvider._presence_for_identity", provider._presence_for_identity, True),
            (
                "LinearToolProvider._require_parent_issue_allowed",
                provider._require_parent_issue_allowed,
                True,
            ),
            ("_fetch_issue", _fetch_issue, True),
            ("_issue_from_payload", _issue_from_payload, True),
            ("_fetch_team", _fetch_team, True),
            ("_team_from_payload", _team_from_payload, True),
            ("_validate_linear_reference", _validate_linear_reference, True),
            ("_create_linear_issue", _create_linear_issue, True),
            ("_mutated_issue_from_payload", _mutated_issue_from_payload, True),
            ("_compact_issue_mutation_payload", _compact_issue_mutation_payload, True),
        ),
        UPDATE_ISSUE_TOOL: (
            (
                "LinearToolProvider._authorize_update_issue_before_call",
                provider._authorize_update_issue_before_call,
                False,
            ),
            (
                "LinearToolProvider._validated_update_issue_request",
                provider._validated_update_issue_request,
                True,
            ),
            ("LinearToolProvider._presence_for_identity", provider._presence_for_identity, True),
            (
                "LinearToolProvider._require_returned_issue_allowed",
                provider._require_returned_issue_allowed,
                True,
            ),
            (
                "LinearToolProvider._require_parent_issue_allowed",
                provider._require_parent_issue_allowed,
                True,
            ),
            ("_fetch_issue", _fetch_issue, True),
            ("_issue_from_payload", _issue_from_payload, True),
            ("_validate_linear_reference", _validate_linear_reference, True),
            ("_update_linear_issue", _update_linear_issue, True),
            ("_mutated_issue_from_payload", _mutated_issue_from_payload, True),
            ("_compact_issue_mutation_payload", _compact_issue_mutation_payload, True),
        ),
        CREATE_PROJECT_TOOL: (
            (
                "LinearToolProvider._authorize_create_project_before_call",
                provider._authorize_create_project_before_call,
                False,
            ),
            (
                "LinearToolProvider._validated_create_project_request",
                provider._validated_create_project_request,
                True,
            ),
            ("LinearToolProvider._presence_for_identity", provider._presence_for_identity, True),
            ("_fetch_team", _fetch_team, True),
            ("_team_from_payload", _team_from_payload, True),
            ("_validate_linear_reference", _validate_linear_reference, True),
            ("_create_linear_project", _create_linear_project, True),
            ("_mutated_project_from_payload", _mutated_project_from_payload, True),
            ("_compact_project_mutation_payload", _compact_project_mutation_payload, True),
        ),
    }
    result: list[LinearRuntimeDependency] = []
    if tool_name in query_dependencies:
        result.append(
            (
                "LinearToolProvider._authorize_exploration_before_call",
                provider._authorize_exploration_before_call,
                False,
            )
        )
        result.append(("_validated_exploration_request", _validated_exploration_request, False))
        validator = _exploration_request_validator(tool_name)
        result.append(
            (
                getattr(validator, "__qualname__", "exploration_validator"),
                cast(Callable[..., Any], validator),
                True,
            )
        )
        result.append(("linear_query", query_dependencies[tool_name], True))
        result.append(("LinearToolProvider._run_linear_query", provider._run_linear_query, True))
    result.extend(local_dependencies.get(tool_name, ()))
    if tool_name in LINEAR_PROVIDER_TOOLS:
        result.append(
            ("app_client.access_token_for_presence", app_client.access_token_for_presence, True)
        )
        result.append(
            ("app_client.access_token_for_app_key", app_client.access_token_for_app_key, True)
        )
        result.append(("app_client.refresh_access_token", app_client.refresh_access_token, True))
        result.append(
            ("app_client.required_linear_app_env", app_client.required_linear_app_env, True)
        )
        result.append(("app_client.linear_env", app_client.linear_env, True))
        result.append(("app_client.linear_graphql", app_client.linear_graphql, True))
        result.append(
            (
                "linear_provider.required_linear_app_env",
                linear_provider.required_linear_app_env,
                True,
            )
        )
        result.append(("linear_provider.linear_app_env", linear_provider.linear_app_env, True))
        result.append(("linear_provider.app_env_prefix", linear_provider.app_env_prefix, True))
        result.append(
            ("linear_provider.normalize_app_key", linear_provider.normalize_app_key, True)
        )
        result.append(
            (
                "linear_provider.persist_linear_oauth_install",
                linear_provider.persist_linear_oauth_install,
                True,
            )
        )
        result.append(
            (
                "linear_provider.update_linear_presence_tokens",
                linear_provider.update_linear_presence_tokens,
                True,
            )
        )
        result.append(
            (
                "linear_provider.LinearProviderConfig.presence_by_app_key",
                linear_provider.LinearProviderConfig.presence_by_app_key,
                True,
            )
        )
    return tuple(result)


def _linear_runtime_constant_material(tool_name: str) -> Mapping[str, Any]:
    values: dict[str, Any] = {}
    if tool_name in LIST_LIMIT_TOOLS:
        values["DEFAULT_LIST_LIMIT"] = DEFAULT_LIST_LIMIT
        values["MAX_LIST_LIMIT"] = MAX_LIST_LIMIT
    if tool_name == LIST_COMMENTS_TOOL:
        values["DEFAULT_COMMENT_LIMIT"] = DEFAULT_COMMENT_LIMIT
        values["MAX_COMMENT_LIMIT"] = MAX_COMMENT_LIMIT
    if tool_name in {
        GET_ISSUE_TOOL,
        LIST_COMMENTS_TOOL,
        CREATE_COMMENT_TOOL,
        CREATE_ISSUE_TOOL,
        UPDATE_ISSUE_TOOL,
        CREATE_PROJECT_TOOL,
    }:
        values["MAX_DESCRIPTION_CHARS"] = MAX_DESCRIPTION_CHARS
        values["_TRUNCATED"] = _TRUNCATED
    if tool_name in {LIST_COMMENTS_TOOL, CREATE_COMMENT_TOOL}:
        values["MAX_COMMENT_BODY_CHARS"] = MAX_COMMENT_BODY_CHARS
    if tool_name == OPEN_AGENT_SESSION_ON_ISSUE_TOOL:
        values["MAX_COMMENT_BODY_CHARS"] = MAX_COMMENT_BODY_CHARS
    if tool_name == CREATE_ISSUE_TOOL:
        values["CREATE_ISSUE_FIELDS"] = sorted(CREATE_ISSUE_FIELDS)
        values["REFERENCE_FIELDS"] = sorted(REFERENCE_FIELDS)
    if tool_name == UPDATE_ISSUE_TOOL:
        values["UPDATE_ISSUE_FIELDS"] = sorted(UPDATE_ISSUE_FIELDS)
        values["REFERENCE_FIELDS"] = sorted(REFERENCE_FIELDS)
    if tool_name == CREATE_PROJECT_TOOL:
        values["CREATE_PROJECT_FIELDS"] = sorted(CREATE_PROJECT_FIELDS)
        values["PROJECT_REFERENCE_FIELDS"] = sorted(PROJECT_REFERENCE_FIELDS)
    if tool_name in LINEAR_PROVIDER_TOOLS:
        values["DEFAULT_LINEAR_POLICY_REASON"] = DEFAULT_LINEAR_POLICY_REASON
        from cli_agent_orchestrator.linear import app_client
        from cli_agent_orchestrator.linear import workspace_provider as linear_provider

        values["LINEAR_GRAPHQL_URL"] = app_client.LINEAR_GRAPHQL_URL
        values["LINEAR_TOKEN_URL"] = app_client.LINEAR_TOKEN_URL
        values["TOKEN_REFRESH_SKEW_SECONDS"] = app_client.TOKEN_REFRESH_SKEW.total_seconds()
        values["APP_KEY_PATTERN"] = linear_provider.APP_KEY_PATTERN.pattern
    return {
        "schema_version": "cao-linear-mcp-tool-runtime-constants.v1",
        "values": values,
    }


class LinearToolProvider:
    """Build and execute Linear's CAO-mediated tool policy."""

    def __init__(
        self,
        *,
        config: Any,
        agent_registry: Any,
        profile_exists: Any,
    ) -> None:
        self._config = config
        self._agent_registry = agent_registry
        self._profile_exists = profile_exists
        self._access_by_location: dict[str, LinearToolAccess] = {
            access.location: access for access in config.tool_access.values()
        }

    def provider_tool_access(self) -> ProviderToolAccessPolicy:
        policy = normalize_provider_tool_access(
            provider_name=PROVIDER_NAME,
            tools=self._tools(),
            hooks=self._hooks(),
            access_requests=self._access_requests(),
            agent_registry=self._agent_registry,
            profile_exists=self._profile_exists,
        )
        issues: list[ProviderToolAccessIssue] = []
        for access in policy.access:
            if self._find_presence_for_identity(access.agent_identity_id) is None:
                issues.append(
                    ProviderToolAccessIssue(
                        access.source_location,
                        "grants Linear tool access to identity "
                        f"{access.agent_identity_id!r}, but that identity has no "
                        "Linear presence",
                    )
                )
        if issues:
            raise ProviderToolAccessConfigError(PROVIDER_NAME, issues)
        return policy

    def _tools(self) -> tuple[ProviderMediatedToolDefinition, ...]:
        return _with_linear_runtime_generation(
            self,
            (
                ProviderMediatedToolDefinition(
                    name=GET_ISSUE_TOOL,
                    description=(
                        "Fetch a compact read-only Linear issue payload for an authorized issue."
                    ),
                    input_schema=_issue_input_schema(),
                    handler=self._get_issue,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_COMMENTS_TOOL,
                    description=("Fetch ordered bounded Linear comments for an authorized issue."),
                    input_schema={
                        **_issue_input_schema(),
                        "properties": {
                            **_issue_input_schema()["properties"],
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": MAX_COMMENT_LIMIT,
                                "description": "Maximum comments to return.",
                            },
                        },
                    },
                    handler=self._list_comments,
                ),
                ProviderMediatedToolDefinition(
                    name=CREATE_COMMENT_TOOL,
                    description="Create a Linear issue comment on an authorized issue.",
                    input_schema=_create_comment_input_schema(),
                    handler=self._create_comment,
                ),
                ProviderMediatedToolDefinition(
                    name=OPEN_AGENT_SESSION_ON_ISSUE_TOOL,
                    description=(
                        "Open a Linear AgentSession on an authorized issue and post an "
                        "initial elicitation activity."
                    ),
                    input_schema=_open_agent_session_on_issue_input_schema(),
                    handler=self._open_agent_session_on_issue,
                ),
                ProviderMediatedToolDefinition(
                    name=CREATE_ISSUE_TOOL,
                    description="Create a Linear issue or sub-issue inside configured boundaries.",
                    input_schema=_create_issue_input_schema(),
                    handler=self._create_issue,
                ),
                ProviderMediatedToolDefinition(
                    name=UPDATE_ISSUE_TOOL,
                    description="Update explicitly allowed fields on an authorized Linear issue.",
                    input_schema=_update_issue_input_schema(),
                    handler=self._update_issue,
                ),
                ProviderMediatedToolDefinition(
                    name=CREATE_PROJECT_TOOL,
                    description="Create a Linear project inside configured team boundaries.",
                    input_schema=_create_project_input_schema(),
                    handler=self._create_project,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_TEAMS_TOOL,
                    description="List compact Linear teams visible to this Linear app presence.",
                    input_schema=_list_query_schema(),
                    handler=self._list_teams,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_TEAM_TOOL,
                    description="Fetch one compact Linear team by id or key.",
                    input_schema=_id_input_schema("team_id", "Linear team UUID or key."),
                    handler=self._get_team,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_USERS_TOOL,
                    description="List compact Linear users visible to this Linear app presence.",
                    input_schema=_list_users_input_schema(),
                    handler=self._list_users,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_USER_TOOL,
                    description="Fetch one compact Linear user by id.",
                    input_schema=_id_input_schema("user_id", "Linear user UUID."),
                    handler=self._get_user,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_ISSUE_STATUSES_TOOL,
                    description="List compact Linear issue statuses, optionally filtered by team.",
                    input_schema=_list_team_scoped_schema(),
                    handler=self._list_issue_statuses,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_ISSUE_STATUS_TOOL,
                    description="Fetch one compact Linear issue status by workflow state id.",
                    input_schema=_id_input_schema("status_id", "Linear workflow state UUID."),
                    handler=self._get_issue_status,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_ISSUE_LABELS_TOOL,
                    description="List compact Linear issue labels, optionally filtered by team.",
                    input_schema=_list_team_scoped_schema(),
                    handler=self._list_issue_labels,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_ISSUE_LABEL_TOOL,
                    description="Fetch one compact Linear issue label by id.",
                    input_schema=_id_input_schema("label_id", "Linear issue label UUID."),
                    handler=self._get_issue_label,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_PROJECTS_TOOL,
                    description="List compact Linear projects visible to this Linear app presence.",
                    input_schema=_list_projects_input_schema(),
                    handler=self._list_projects,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_PROJECT_TOOL,
                    description="Fetch one compact Linear project by id or slug.",
                    input_schema=_id_input_schema("project_id", "Linear project UUID or slug."),
                    handler=self._get_project,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_ISSUES_TOOL,
                    description="List compact Linear issues with ordinary optional filters.",
                    input_schema=_list_issues_input_schema(),
                    handler=self._list_issues,
                ),
                ProviderMediatedToolDefinition(
                    name=SEARCH_ISSUES_TOOL,
                    description="Search Linear issues by term and return compact issue results.",
                    input_schema=_search_input_schema(),
                    handler=self._search_issues,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_COMMENT_TOOL,
                    description="Fetch one compact Linear comment by id.",
                    input_schema=_id_input_schema("comment_id", "Linear comment UUID."),
                    handler=self._get_comment,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_AGENT_SESSION_TOOL,
                    description="Fetch one compact Linear agent session by id.",
                    input_schema=_id_input_schema("agent_session_id", "Linear AgentSession UUID."),
                    handler=self._get_agent_session,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_AGENT_SESSION_ACTIVITIES_TOOL,
                    description="List bounded activities for a Linear agent session.",
                    input_schema=_list_agent_session_activities_schema(),
                    handler=self._list_agent_session_activities,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_AGENT_SESSION_ACTIVITY_TOOL,
                    description="Fetch one Linear agent session activity by id.",
                    input_schema=_id_input_schema("activity_id", "Linear AgentActivity UUID."),
                    handler=self._get_agent_session_activity,
                ),
                ProviderMediatedToolDefinition(
                    name=LIST_DOCUMENTS_TOOL,
                    description="List compact Linear documents, optionally filtered by project.",
                    input_schema=_list_documents_input_schema(),
                    handler=self._list_documents,
                ),
                ProviderMediatedToolDefinition(
                    name=GET_DOCUMENT_TOOL,
                    description="Fetch one compact Linear document by id.",
                    input_schema=_id_input_schema("document_id", "Linear document UUID."),
                    handler=self._get_document,
                ),
                ProviderMediatedToolDefinition(
                    name=SEARCH_DOCUMENTS_TOOL,
                    description="Search Linear documents by term and return compact document results.",
                    input_schema=_search_input_schema(),
                    handler=self._search_documents,
                ),
            ),
        )

    def _hooks(self) -> tuple[ProviderToolHookDefinition, ...]:
        return (
            ProviderToolHookDefinition(
                name=READ_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_before_call,
            ),
            ProviderToolHookDefinition(
                name=EXPLORATION_READ_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_exploration_before_call,
            ),
            ProviderToolHookDefinition(
                name=COMMENT_WRITE_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_comment_before_call,
            ),
            ProviderToolHookDefinition(
                name=AGENT_SESSION_WRITE_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_agent_session_before_call,
            ),
            ProviderToolHookDefinition(
                name=CREATE_ISSUE_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_create_issue_before_call,
            ),
            ProviderToolHookDefinition(
                name=UPDATE_ISSUE_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_update_issue_before_call,
            ),
            ProviderToolHookDefinition(
                name=CREATE_PROJECT_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_create_project_before_call,
            ),
            ProviderToolHookDefinition(
                name=LINEAR_WORKSPACE_CONTEXT_RESULT_HOOK,
                phases=frozenset({ProviderToolHookPhase.POST_CALL}),
                handler=self._resolve_tool_result_workspace_context,
            ),
        )

    def _access_requests(self) -> tuple[ProviderToolAccessRequest, ...]:
        requests: list[ProviderToolAccessRequest] = []
        for access in self._config.tool_access.values():
            for tool_name in access.tools:
                if tool_name == CREATE_COMMENT_TOOL:
                    pre_hook = COMMENT_WRITE_POLICY_HOOK
                elif tool_name == OPEN_AGENT_SESSION_ON_ISSUE_TOOL:
                    pre_hook = AGENT_SESSION_WRITE_POLICY_HOOK
                elif tool_name == CREATE_ISSUE_TOOL:
                    pre_hook = CREATE_ISSUE_POLICY_HOOK
                elif tool_name == UPDATE_ISSUE_TOOL:
                    pre_hook = UPDATE_ISSUE_POLICY_HOOK
                elif tool_name == CREATE_PROJECT_TOOL:
                    pre_hook = CREATE_PROJECT_POLICY_HOOK
                elif tool_name in LINEAR_EXPLORATION_READ_TOOLS:
                    pre_hook = EXPLORATION_READ_POLICY_HOOK
                else:
                    pre_hook = READ_POLICY_HOOK
                post_hooks: tuple[str, ...] = ()
                if tool_name in LINEAR_CONTEXT_MAPPING_MUTATION_TOOLS:
                    post_hooks = (LINEAR_WORKSPACE_CONTEXT_RESULT_HOOK,)
                requests.append(
                    ProviderToolAccessRequest(
                        tool_name=tool_name,
                        agent_identity_id=access.agent_id,
                        agent_profile=access.agent_profile,
                        pre_hooks=(pre_hook,),
                        post_hooks=post_hooks,
                        location=access.location,
                    )
                )
        return tuple(requests)

    def _authorize_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._authorized_issue_request(context)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _authorize_exploration_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._presence_for_identity(context.agent_identity.id)
            _validated_exploration_request(context.tool_name, context.arguments)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _authorize_create_issue_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._validated_create_issue_request(context)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _authorize_update_issue_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._validated_update_issue_request(context)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _authorize_create_project_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._validated_create_project_request(context)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _resolve_tool_result_workspace_context(
        self, context: ProviderToolInvocationContext
    ) -> None:
        from cli_agent_orchestrator.linear.workspace_context_tool_results import (
            resolve_linear_tool_result_workspace_context,
        )

        resolve_linear_tool_result_workspace_context(context)

    def _authorize_comment_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._authorized_issue_request(context)
            _comment_body_from_arguments(context.arguments)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _authorize_agent_session_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._authorized_issue_request(context)
            _agent_session_initial_body_from_arguments(context.arguments)
        except LinearToolError as exc:
            return self._deny_with_policy_context(context, exc)
        return ProviderToolPreCallResult.allow()

    def _deny_with_policy_context(
        self,
        context: ProviderToolInvocationContext,
        exc: LinearToolError,
    ) -> ProviderToolPreCallResult:
        access = self._access_by_location.get(context.access.source_location)
        policy_reason = access.reason if access and access.reason else DEFAULT_LINEAR_POLICY_REASON
        return ProviderToolPreCallResult.deny(
            exc.reason,
            {
                "provider_name": PROVIDER_NAME,
                "tool_name": context.tool_name,
                "detail": str(exc),
                "display_detail": exc.detail,
                "policy_reason": policy_reason,
            },
        )

    def _get_issue(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        issue_key = self._authorized_issue_request(context)
        presence = self._presence_for_identity(context.agent_identity.id)
        issue = _fetch_issue(issue_key, presence)
        self._require_returned_issue_allowed(issue, context.access.source_location)
        return _compact_issue_payload(issue)

    def _list_comments(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        issue_key = self._authorized_issue_request(context)
        presence = self._presence_for_identity(context.agent_identity.id)
        limit = _comment_limit(arguments.get("limit"))
        issue = _fetch_issue_comments(issue_key, presence, limit=limit)
        self._require_returned_issue_allowed(issue, context.access.source_location)
        comments = _comments_from_issue(issue)
        return {
            "issue": {
                "id": _string_or_none(issue.get("id")),
                "identifier": _string_or_none(issue.get("identifier")),
            },
            "comments": comments[:limit],
        }

    def _create_comment(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        issue_key = self._authorized_issue_request(context)
        body = _comment_body_from_arguments(arguments)
        presence = self._presence_for_identity(context.agent_identity.id)
        issue = _fetch_issue(issue_key, presence)
        self._require_returned_issue_allowed(issue, context.access.source_location)
        comment = _create_linear_comment(issue, body, presence)
        return _compact_created_comment_payload(comment, issue)

    def _open_agent_session_on_issue(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        issue_key = self._authorized_issue_request(context)
        initial_body = _agent_session_initial_body_from_arguments(arguments)
        presence = self._presence_for_identity(context.agent_identity.id)
        issue = _fetch_issue(issue_key, presence)
        self._require_returned_issue_allowed(issue, context.access.source_location)
        agent_session = _open_linear_agent_session_on_issue(
            issue,
            initial_body,
            presence,
            agent_id=context.agent_identity.id,
        )
        return _compact_created_agent_session_payload(agent_session, issue)

    def _create_issue(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = self._validated_create_issue_request(context)
        presence = self._presence_for_identity(context.agent_identity.id)
        mutation_input: dict[str, Any] = {}
        parent_issue = None
        for field, value in request.items():
            if field == "parent_issue":
                parent_issue = _fetch_issue(value, presence)
                self._require_parent_issue_allowed(
                    value,
                    parent_issue,
                    context.access.source_location,
                )
                mutation_input["parentId"] = _required_string(
                    parent_issue.get("id"),
                    field="parent_issue",
                    reason="linear_parent_issue_not_found",
                )
            elif field == "team_id":
                team = _fetch_team(value, presence)
                mutation_input["teamId"] = _required_string(
                    team.get("id"),
                    field="team_id",
                    reason="invalid_linear_team_id",
                )
            elif field in REFERENCE_FIELDS:
                _validate_linear_reference(field, value, presence)
                mutation_input[_linear_input_field(field)] = value
            elif field == "label_ids":
                for label_id in value:
                    _validate_linear_reference(field, label_id, presence)
                mutation_input["labelIds"] = list(value)
            else:
                mutation_input[_linear_input_field(field)] = value
        issue = _create_linear_issue(mutation_input, presence)
        return _compact_issue_mutation_payload(
            issue,
            status="created",
            changed_fields=tuple(sorted(request)),
        )

    def _update_issue(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        target_issue_key, request = self._validated_update_issue_request(context)
        presence = self._presence_for_identity(context.agent_identity.id)
        target_issue = _fetch_issue(target_issue_key, presence)
        self._require_returned_issue_allowed(target_issue, context.access.source_location)
        target_issue_id = _required_string(
            target_issue.get("id"),
            field="issue",
            reason="linear_issue_not_found",
        )
        mutation_input: dict[str, Any] = {}
        for field, value in request.items():
            if field == "parent_issue":
                parent_issue = _fetch_issue(value, presence)
                self._require_parent_issue_allowed(
                    value,
                    parent_issue,
                    context.access.source_location,
                )
                mutation_input["parentId"] = _required_string(
                    parent_issue.get("id"),
                    field="parent_issue",
                    reason="linear_parent_issue_not_found",
                )
            elif field in REFERENCE_FIELDS:
                _validate_linear_reference(field, value, presence)
                mutation_input[_linear_input_field(field)] = value
            elif field == "label_ids":
                for label_id in value:
                    _validate_linear_reference(field, label_id, presence)
                mutation_input["labelIds"] = list(value)
            else:
                mutation_input[_linear_input_field(field)] = value
        issue = _update_linear_issue(target_issue_id, mutation_input, presence)
        return _compact_issue_mutation_payload(
            issue,
            status="updated",
            changed_fields=tuple(sorted(request)),
        )

    def _create_project(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = self._validated_create_project_request(context)
        presence = self._presence_for_identity(context.agent_identity.id)
        mutation_input: dict[str, Any] = {}
        for field, value in request.items():
            if field == "team_ids":
                team_ids: list[str] = []
                for team_ref in value:
                    team = _fetch_team(team_ref, presence)
                    team_ids.append(
                        _required_string(
                            team.get("id"),
                            field="team_ids",
                            reason="invalid_linear_team_id",
                        )
                    )
                mutation_input["teamIds"] = team_ids
            elif field in PROJECT_REFERENCE_FIELDS:
                values = value if isinstance(value, tuple) else (value,)
                for reference in values:
                    _validate_linear_reference(field, reference, presence)
                mutation_input[_linear_input_field(field)] = (
                    list(value) if field == "member_ids" else value
                )
            else:
                mutation_input[_linear_input_field(field)] = value
        project = _create_linear_project(mutation_input, presence)
        return _compact_project_mutation_payload(
            project,
            status="created",
            changed_fields=tuple(sorted(request)),
        )

    def _list_teams(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.list_teams,
            limit=request["limit"],
            query=request.get("query"),
        )

    def _get_team(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(context, linear_queries.get_team, team_id=request["team_id"])

    def _list_users(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.list_users,
            limit=request["limit"],
            query=request.get("query"),
            include_disabled=request["include_disabled"],
        )

    def _get_user(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(context, linear_queries.get_user, user_id=request["user_id"])

    def _list_issue_statuses(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.list_issue_statuses,
            limit=request["limit"],
            team_id=request.get("team_id"),
            query=request.get("query"),
        )

    def _get_issue_status(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context, linear_queries.get_issue_status, status_id=request["status_id"]
        )

    def _list_issue_labels(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.list_issue_labels,
            limit=request["limit"],
            team_id=request.get("team_id"),
            query=request.get("query"),
        )

    def _get_issue_label(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context, linear_queries.get_issue_label, label_id=request["label_id"]
        )

    def _list_projects(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.list_projects,
            limit=request["limit"],
            query=request.get("query"),
            team_id=request.get("team_id"),
        )

    def _get_project(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context, linear_queries.get_project, project_id=request["project_id"]
        )

    def _list_issues(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(context, linear_queries.list_issues, **request)

    def _search_issues(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(context, linear_queries.search_issues, **request)

    def _get_comment(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context, linear_queries.get_comment, comment_id=request["comment_id"]
        )

    def _get_agent_session(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.get_agent_session,
            agent_session_id=request["agent_session_id"],
        )

    def _list_agent_session_activities(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.list_agent_session_activities,
            agent_session_id=request["agent_session_id"],
            limit=request["limit"],
        )

    def _get_agent_session_activity(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context,
            linear_queries.get_agent_session_activity,
            activity_id=request["activity_id"],
        )

    def _list_documents(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(context, linear_queries.list_documents, **request)

    def _get_document(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(
            context, linear_queries.get_document, document_id=request["document_id"]
        )

    def _search_documents(
        self,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        request = _validated_exploration_request(context.tool_name, arguments)
        return self._run_linear_query(context, linear_queries.search_documents, **request)

    def _run_linear_query(
        self,
        context: ProviderToolInvocationContext,
        query_func: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        presence = self._presence_for_identity(context.agent_identity.id)
        try:
            return cast(dict[str, Any], query_func(presence, **kwargs))
        except linear_queries.LinearProviderQueryError as exc:
            raise LinearToolError(exc.reason, str(exc)) from exc

    def _validated_create_issue_request(
        self,
        context: ProviderToolInvocationContext,
    ) -> dict[str, Any]:
        access = self._linear_access_for_context(context)
        arguments = context.arguments
        unknown = set(arguments) - CREATE_ISSUE_FIELDS
        if unknown:
            raise LinearToolError(
                "invalid_linear_create_issue_field",
                f"unsupported create_issue fields: {', '.join(sorted(unknown))}",
            )
        team_id = _required_string(
            arguments.get("team_id"),
            field="team_id",
            reason="invalid_linear_team_id",
        )
        if _canonical_issue_key(team_id) not in {
            _canonical_issue_key(item) for item in access.create_team_ids
        }:
            raise LinearToolError(
                "unauthorized_linear_team",
                f"team_id {team_id!r} is not authorized by {access.location}",
            )
        request: dict[str, Any] = {
            "team_id": team_id,
            "title": _required_title(arguments.get("title")),
        }
        _copy_optional_string(arguments, request, "description")
        _copy_optional_reference(arguments, request, "state_id")
        _copy_optional_reference(arguments, request, "assignee_id")
        if "priority" in arguments:
            request["priority"] = _priority(arguments["priority"])
        if "label_ids" in arguments:
            request["label_ids"] = _label_ids(arguments["label_ids"])
        if "project_id" in arguments:
            project_id = _required_string(
                arguments.get("project_id"),
                field="project_id",
                reason="invalid_linear_project_id",
            )
            if _canonical_issue_key(project_id) not in {
                _canonical_issue_key(item) for item in access.create_project_ids
            }:
                raise LinearToolError(
                    "unauthorized_linear_project",
                    f"project_id {project_id!r} is not authorized by {access.location}",
                )
            request["project_id"] = project_id
        if "parent_issue" in arguments:
            parent_issue = _required_string(
                arguments.get("parent_issue"),
                field="parent_issue",
                reason="invalid_linear_parent_issue",
            )
            if _canonical_issue_key(parent_issue) not in {
                _canonical_issue_key(item) for item in access.create_parent_issues
            }:
                raise LinearToolError(
                    "unauthorized_linear_parent_issue",
                    f"parent_issue {parent_issue!r} is not authorized by {access.location}",
                )
            request["parent_issue"] = parent_issue
        elif not access.allow_top_level_create:
            raise LinearToolError(
                "unauthorized_linear_top_level_create",
                f"{access.location} does not allow top-level issue creation",
            )
        return request

    def _validated_update_issue_request(
        self,
        context: ProviderToolInvocationContext,
    ) -> tuple[str, dict[str, Any]]:
        access = self._linear_access_for_context(context)
        issue_key = self._authorized_issue_request(context)
        arguments = context.arguments
        mutation_fields = set(arguments) - {"issue", "issue_ref"}
        unknown = mutation_fields - UPDATE_ISSUE_FIELDS
        if unknown:
            raise LinearToolError(
                "invalid_linear_update_issue_field",
                f"unsupported update_issue fields: {', '.join(sorted(unknown))}",
            )
        if not mutation_fields:
            raise LinearToolError(
                "invalid_linear_update_issue_field",
                "update_issue requires at least one mutation field",
            )
        allowed_fields = set(access.update_fields)
        denied = mutation_fields - allowed_fields
        if denied:
            raise LinearToolError(
                "unauthorized_linear_update_field",
                f"update fields are not authorized by {access.location}: "
                f"{', '.join(sorted(denied))}",
            )
        request: dict[str, Any] = {}
        if "title" in arguments:
            request["title"] = _required_title(arguments.get("title"))
        _copy_optional_string(arguments, request, "description")
        _copy_optional_reference(arguments, request, "state_id")
        _copy_optional_reference(arguments, request, "assignee_id")
        if "project_id" in arguments:
            project_id = _required_string(
                arguments.get("project_id"),
                field="project_id",
                reason="invalid_linear_project_id",
            )
            if _canonical_issue_key(project_id) not in {
                _canonical_issue_key(item) for item in access.create_project_ids
            }:
                raise LinearToolError(
                    "unauthorized_linear_project",
                    f"project_id {project_id!r} is not authorized by {access.location}",
                )
            request["project_id"] = project_id
        if "parent_issue" in arguments:
            parent_issue = _required_string(
                arguments.get("parent_issue"),
                field="parent_issue",
                reason="invalid_linear_parent_issue",
            )
            if _canonical_issue_key(parent_issue) not in {
                _canonical_issue_key(item) for item in access.create_parent_issues
            }:
                raise LinearToolError(
                    "unauthorized_linear_parent_issue",
                    f"parent_issue {parent_issue!r} is not authorized by {access.location}",
                )
            request["parent_issue"] = parent_issue
        if "label_ids" in arguments:
            request["label_ids"] = _label_ids(arguments["label_ids"])
        if "priority" in arguments:
            request["priority"] = _priority(arguments["priority"])
        return issue_key, request

    def _validated_create_project_request(
        self,
        context: ProviderToolInvocationContext,
    ) -> dict[str, Any]:
        access = self._linear_access_for_context(context)
        arguments = context.arguments
        unknown = set(arguments) - CREATE_PROJECT_FIELDS
        if unknown:
            raise LinearToolError(
                "invalid_linear_create_project_field",
                f"unsupported create_project fields: {', '.join(sorted(unknown))}",
            )
        team_ids = _team_ids(arguments.get("team_ids"))
        allowed_teams = {_canonical_issue_key(item) for item in access.create_team_ids}
        unauthorized = [
            team_id for team_id in team_ids if _canonical_issue_key(team_id) not in allowed_teams
        ]
        if unauthorized:
            raise LinearToolError(
                "unauthorized_linear_team",
                "team_ids are not authorized by "
                f"{access.location}: {', '.join(sorted(unauthorized))}",
            )
        request: dict[str, Any] = {
            "team_ids": team_ids,
            "name": _required_string(
                arguments.get("name"),
                field="name",
                reason="invalid_linear_project_name",
            ),
        }
        _copy_optional_string(arguments, request, "description")
        _copy_optional_string(arguments, request, "content")
        _copy_optional_reference(arguments, request, "lead_id")
        _copy_optional_date(arguments, request, "start_date")
        _copy_optional_date(arguments, request, "target_date")
        if "member_ids" in arguments:
            request["member_ids"] = _member_ids(arguments["member_ids"])
        if "priority" in arguments:
            request["priority"] = _priority(arguments["priority"])
        return request

    def _linear_access_for_context(
        self,
        context: ProviderToolInvocationContext,
    ) -> LinearToolAccess:
        access = self._access_by_location.get(context.access.source_location)
        if access is None:
            raise LinearToolError(
                "malformed_linear_tool_policy",
                f"missing Linear tool policy for {context.access.source_location}",
            )
        return access

    def _authorized_issue_request(self, context: ProviderToolInvocationContext) -> str:
        access = self._linear_access_for_context(context)
        issue_key = _issue_key_from_arguments(context.arguments)
        if _allows_any_issue(access.issues):
            return issue_key
        if _canonical_issue_key(issue_key) not in {
            _canonical_issue_key(item) for item in access.issues
        }:
            raise LinearToolError(
                "unauthorized_linear_issue",
                f"{issue_key!r} is not authorized by {access.location}",
            )
        return issue_key

    def _require_returned_issue_allowed(
        self,
        issue: Mapping[str, Any],
        source_location: str,
    ) -> None:
        access = self._access_by_location[source_location]
        if _allows_any_issue(access.issues):
            return
        allowed = {_canonical_issue_key(item) for item in access.issues}
        returned = {
            _canonical_issue_key(value)
            for value in (issue.get("id"), issue.get("identifier"))
            if value
        }
        if not returned.intersection(allowed):
            raise LinearToolError(
                "linear_issue_outside_policy",
                "Linear returned an issue that does not match the authorized target",
            )

    def _require_parent_issue_allowed(
        self,
        parent_key: str,
        issue: Mapping[str, Any],
        source_location: str,
    ) -> None:
        access = self._access_by_location[source_location]
        if _allows_any_issue(access.create_parent_issues):
            return
        allowed = {_canonical_issue_key(item) for item in access.create_parent_issues}
        returned = {
            _canonical_issue_key(value)
            for value in (parent_key, issue.get("id"), issue.get("identifier"))
            if value
        }
        if not returned.intersection(allowed):
            raise LinearToolError(
                "linear_parent_issue_outside_policy",
                "Linear returned a parent issue that does not match the authorized parent target",
            )

    def _presence_for_identity(self, agent_identity_id: str) -> Any:
        presence = self._find_presence_for_identity(agent_identity_id)
        if presence is None:
            raise LinearToolError(
                "missing_linear_presence",
                f"CAO identity {agent_identity_id!r} has Linear tool access but no presence",
            )
        return presence

    def _find_presence_for_identity(self, agent_identity_id: str) -> Any:
        return next(
            (
                candidate
                for candidate in self._config.presences.values()
                if candidate.agent_id == agent_identity_id
            ),
            None,
        )


def _issue_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "issue": {
                "type": "string",
                "description": "Linear issue UUID or shorthand identifier such as CAO-28.",
            },
            "issue_ref": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "id": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["provider", "id"],
                "additionalProperties": True,
            },
        },
        "additionalProperties": False,
    }


def _id_input_schema(field: str, description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            field: {
                "type": "string",
                "description": description,
            }
        },
        "required": [field],
        "additionalProperties": False,
    }


def _list_query_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "limit": _limit_schema(),
            "query": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _list_team_scoped_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "limit": _limit_schema(),
            "query": {"type": "string"},
            "team_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _list_users_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "limit": _limit_schema(),
            "query": {"type": "string"},
            "include_disabled": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def _list_projects_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "limit": _limit_schema(),
            "query": {"type": "string"},
            "team_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _list_issues_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "limit": _limit_schema(),
            "team_id": {"type": "string"},
            "project_id": {"type": "string"},
            "state_id": {"type": "string"},
            "assignee_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _search_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "term": {"type": "string"},
            "limit": _limit_schema(),
            "team_id": {"type": "string"},
            "include_comments": {"type": "boolean"},
        },
        "required": ["term"],
        "additionalProperties": False,
    }


def _list_agent_session_activities_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "agent_session_id": {"type": "string"},
            "limit": _limit_schema(),
        },
        "required": ["agent_session_id"],
        "additionalProperties": False,
    }


def _list_documents_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "limit": _limit_schema(),
            "query": {"type": "string"},
            "project_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _limit_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_LIST_LIMIT,
        "description": "Maximum objects to return.",
    }


def _create_comment_input_schema() -> dict[str, Any]:
    issue_schema = _issue_input_schema()
    return {
        "type": "object",
        "properties": {
            **issue_schema["properties"],
            "body": {
                "type": "string",
                "description": "Markdown comment body to create on the Linear issue.",
            },
        },
        "required": ["body"],
        "additionalProperties": False,
    }


def _open_agent_session_on_issue_input_schema() -> dict[str, Any]:
    issue_schema = _issue_input_schema()
    return {
        "type": "object",
        "properties": {
            **issue_schema["properties"],
            "initial_body": {
                "type": "string",
                "description": "Initial elicitation text to post into the new AgentSession.",
            },
        },
        "required": ["initial_body"],
        "additionalProperties": False,
    }


def _create_issue_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "team_id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "project_id": {"type": "string"},
            "parent_issue": {"type": "string"},
            "state_id": {"type": "string"},
            "assignee_id": {"type": "string"},
            "label_ids": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "integer", "minimum": 0, "maximum": 4},
        },
        "required": ["team_id", "title"],
        "additionalProperties": False,
    }


def _update_issue_input_schema() -> dict[str, Any]:
    issue_schema = _issue_input_schema()
    return {
        "type": "object",
        "properties": {
            **issue_schema["properties"],
            "title": {"type": "string"},
            "description": {"type": "string"},
            "state_id": {"type": "string"},
            "assignee_id": {"type": "string"},
            "project_id": {"type": "string"},
            "parent_issue": {"type": "string"},
            "label_ids": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "integer", "minimum": 0, "maximum": 4},
        },
        "additionalProperties": False,
    }


def _create_project_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "team_ids": {"type": "array", "items": {"type": "string"}},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "content": {"type": "string"},
            "lead_id": {"type": "string"},
            "member_ids": {"type": "array", "items": {"type": "string"}},
            "start_date": {
                "type": "string",
                "description": "Optional Linear TimelessDate in YYYY-MM-DD format.",
            },
            "target_date": {
                "type": "string",
                "description": "Optional Linear TimelessDate in YYYY-MM-DD format.",
            },
            "priority": {"type": "integer", "minimum": 0, "maximum": 4},
        },
        "required": ["team_ids", "name"],
        "additionalProperties": False,
    }


def _validated_exploration_request(
    tool_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    validator = _exploration_request_validator(tool_name)
    if validator is not None:
        return validator(arguments, tool_name)
    raise LinearToolError(
        "malformed_linear_tool_policy",
        f"unexpected Linear exploration tool {tool_name!r}",
    )


def _exploration_request_validator(
    tool_name: str,
) -> Callable[[Mapping[str, Any], str], dict[str, Any]] | None:
    return _EXPLORATION_REQUEST_VALIDATORS.get(tool_name)


def _list_query_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    _require_only_arguments(arguments, {"limit", "query"}, tool_name)
    return {
        "limit": _list_limit(arguments.get("limit")),
        **_optional_argument(arguments, "query"),
    }


def _list_users_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    _require_only_arguments(arguments, {"limit", "query", "include_disabled"}, tool_name)
    return {
        "limit": _list_limit(arguments.get("limit")),
        "include_disabled": _optional_bool(arguments.get("include_disabled")),
        **_optional_argument(arguments, "query"),
    }


def _list_team_scoped_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    _require_only_arguments(arguments, {"limit", "query", "team_id"}, tool_name)
    return {
        "limit": _list_limit(arguments.get("limit")),
        **_optional_argument(arguments, "query"),
        **_optional_argument(arguments, "team_id"),
    }


def _list_issues_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    _require_only_arguments(
        arguments,
        {"limit", "team_id", "project_id", "state_id", "assignee_id"},
        tool_name,
    )
    return {
        "limit": _list_limit(arguments.get("limit")),
        **_optional_argument(arguments, "team_id"),
        **_optional_argument(arguments, "project_id"),
        **_optional_argument(arguments, "state_id"),
        **_optional_argument(arguments, "assignee_id"),
    }


def _list_agent_session_activities_request(
    arguments: Mapping[str, Any], tool_name: str
) -> dict[str, Any]:
    _require_only_arguments(arguments, {"agent_session_id", "limit"}, tool_name)
    return {
        "agent_session_id": _required_argument(arguments, "agent_session_id", tool_name=tool_name),
        "limit": _list_limit(arguments.get("limit")),
    }


def _list_documents_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    _require_only_arguments(arguments, {"limit", "query", "project_id"}, tool_name)
    return {
        "limit": _list_limit(arguments.get("limit")),
        **_optional_argument(arguments, "query"),
        **_optional_argument(arguments, "project_id"),
    }


def _get_team_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"team_id": _single_required_argument(arguments, "team_id", tool_name)}


def _get_user_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"user_id": _single_required_argument(arguments, "user_id", tool_name)}


def _get_issue_status_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"status_id": _single_required_argument(arguments, "status_id", tool_name)}


def _get_issue_label_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"label_id": _single_required_argument(arguments, "label_id", tool_name)}


def _get_project_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"project_id": _single_required_argument(arguments, "project_id", tool_name)}


def _get_comment_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"comment_id": _single_required_argument(arguments, "comment_id", tool_name)}


def _get_agent_session_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"agent_session_id": _single_required_argument(arguments, "agent_session_id", tool_name)}


def _get_agent_session_activity_request(
    arguments: Mapping[str, Any], tool_name: str
) -> dict[str, Any]:
    return {"activity_id": _single_required_argument(arguments, "activity_id", tool_name)}


def _get_document_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    return {"document_id": _single_required_argument(arguments, "document_id", tool_name)}


def _search_request(arguments: Mapping[str, Any], tool_name: str) -> dict[str, Any]:
    _require_only_arguments(arguments, {"term", "limit", "team_id", "include_comments"}, tool_name)
    return {
        "term": _required_argument(arguments, "term", tool_name=tool_name),
        "limit": _list_limit(arguments.get("limit")),
        "include_comments": _optional_bool(arguments.get("include_comments")),
        **_optional_argument(arguments, "team_id"),
    }


_EXPLORATION_REQUEST_VALIDATORS: Mapping[
    str, Callable[[Mapping[str, Any], str], dict[str, Any]]
] = {
    LIST_TEAMS_TOOL: _list_query_request,
    GET_TEAM_TOOL: _get_team_request,
    LIST_USERS_TOOL: _list_users_request,
    GET_USER_TOOL: _get_user_request,
    LIST_ISSUE_STATUSES_TOOL: _list_team_scoped_request,
    GET_ISSUE_STATUS_TOOL: _get_issue_status_request,
    LIST_ISSUE_LABELS_TOOL: _list_team_scoped_request,
    GET_ISSUE_LABEL_TOOL: _get_issue_label_request,
    LIST_PROJECTS_TOOL: _list_team_scoped_request,
    GET_PROJECT_TOOL: _get_project_request,
    LIST_ISSUES_TOOL: _list_issues_request,
    SEARCH_ISSUES_TOOL: _search_request,
    GET_COMMENT_TOOL: _get_comment_request,
    GET_AGENT_SESSION_TOOL: _get_agent_session_request,
    LIST_AGENT_SESSION_ACTIVITIES_TOOL: _list_agent_session_activities_request,
    GET_AGENT_SESSION_ACTIVITY_TOOL: _get_agent_session_activity_request,
    LIST_DOCUMENTS_TOOL: _list_documents_request,
    GET_DOCUMENT_TOOL: _get_document_request,
    SEARCH_DOCUMENTS_TOOL: _search_request,
}


def _single_required_argument(
    arguments: Mapping[str, Any],
    field: str,
    tool_name: str,
) -> str:
    _require_only_arguments(arguments, {field}, tool_name)
    return _required_argument(arguments, field, tool_name=tool_name)


def _required_argument(
    arguments: Mapping[str, Any],
    field: str,
    *,
    tool_name: str,
) -> str:
    value = arguments.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LinearToolError(
            "invalid_linear_tool_argument",
            f"{tool_name} requires non-empty string argument {field}",
        )
    return value.strip()


def _optional_argument(arguments: Mapping[str, Any], field: str) -> dict[str, str]:
    if field not in arguments or arguments.get(field) is None:
        return {}
    value = arguments.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LinearToolError(
            "invalid_linear_tool_argument",
            f"{field} must be a non-empty string when provided",
        )
    return {field: value.strip()}


def _optional_bool(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise LinearToolError(
            "invalid_linear_tool_argument",
            "boolean arguments must be true or false",
        )
    return value


def _require_only_arguments(
    arguments: Mapping[str, Any],
    allowed: set[str],
    tool_name: str,
) -> None:
    unknown = set(arguments) - allowed
    if unknown:
        raise LinearToolError(
            "invalid_linear_tool_argument",
            f"{tool_name} does not accept arguments: {', '.join(sorted(unknown))}",
        )


def _list_limit(value: Any) -> int:
    if value is None:
        return DEFAULT_LIST_LIMIT
    if isinstance(value, bool) or not isinstance(value, int):
        raise LinearToolError(
            "invalid_linear_list_limit",
            "limit must be an integer",
        )
    if value < 1 or value > MAX_LIST_LIMIT:
        raise LinearToolError(
            "invalid_linear_list_limit",
            f"limit must be between 1 and {MAX_LIST_LIMIT}",
        )
    return cast(int, value)


def _issue_key_from_arguments(arguments: Mapping[str, Any]) -> str:
    issue = arguments.get("issue")
    issue_ref = arguments.get("issue_ref")
    if isinstance(issue, str) and issue.strip():
        return issue.strip()
    if isinstance(issue_ref, Mapping):
        provider = _string_or_none(issue_ref.get("provider"))
        if provider != PROVIDER_NAME:
            raise LinearToolError(
                "wrong_provider_ref",
                f"expected a Linear issue ref, got provider {provider!r}",
            )
        ref_id = _string_or_none(issue_ref.get("id"))
        if ref_id:
            return ref_id
    raise LinearToolError(
        "invalid_linear_issue_argument",
        "provide issue or issue_ref with a non-empty Linear issue id",
    )


def _comment_body_from_arguments(arguments: Mapping[str, Any]) -> str:
    body = arguments.get("body")
    if not isinstance(body, str):
        raise LinearToolError(
            "invalid_linear_comment_body",
            "comment body must be a non-empty string",
        )
    stripped = body.strip()
    if not stripped:
        raise LinearToolError(
            "invalid_linear_comment_body",
            "comment body must not be blank",
        )
    return body


def _agent_session_initial_body_from_arguments(arguments: Mapping[str, Any]) -> str:
    body = arguments.get("initial_body")
    if not isinstance(body, str):
        raise LinearToolError(
            "invalid_linear_agent_session_body",
            "initial_body must be a non-empty string",
        )
    stripped = body.strip()
    if not stripped:
        raise LinearToolError(
            "invalid_linear_agent_session_body",
            "initial_body must not be blank",
        )
    if len(body) > MAX_COMMENT_BODY_CHARS:
        raise LinearToolError(
            "invalid_linear_agent_session_body",
            f"initial_body must be at most {MAX_COMMENT_BODY_CHARS} characters",
        )
    return body


def _required_string(value: Any, *, field: str, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LinearToolError(reason, f"{field} must be a non-empty string")
    return value.strip()


def _required_title(value: Any) -> str:
    return _required_string(value, field="title", reason="invalid_linear_issue_title")


def _copy_optional_string(
    arguments: Mapping[str, Any],
    request: dict[str, Any],
    field: str,
) -> None:
    if field not in arguments:
        return
    value = arguments[field]
    if not isinstance(value, str):
        raise LinearToolError(
            f"invalid_linear_{field}",
            f"{field} must be a string",
        )
    request[field] = value


def _copy_optional_reference(
    arguments: Mapping[str, Any],
    request: dict[str, Any],
    field: str,
) -> None:
    if field in arguments:
        request[field] = _required_string(
            arguments.get(field),
            field=field,
            reason=f"invalid_linear_{field}",
        )


def _copy_optional_date(
    arguments: Mapping[str, Any],
    request: dict[str, Any],
    field: str,
) -> None:
    if field not in arguments:
        return
    value = _required_string(arguments.get(field), field=field, reason=f"invalid_linear_{field}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise LinearToolError(
            f"invalid_linear_{field}",
            f"{field} must use YYYY-MM-DD format",
        ) from exc
    request[field] = value


def _label_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LinearToolError("invalid_linear_label_ids", "label_ids must be a list of strings")
    labels = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(labels) != len(value) or not labels:
        raise LinearToolError(
            "invalid_linear_label_ids",
            "label_ids must be a list of non-empty strings",
        )
    return labels


def _team_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LinearToolError("invalid_linear_team_ids", "team_ids must be a list of strings")
    team_ids = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(team_ids) != len(value) or not team_ids:
        raise LinearToolError(
            "invalid_linear_team_ids",
            "team_ids must be a non-empty list of non-empty strings",
        )
    return team_ids


def _member_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LinearToolError("invalid_linear_member_ids", "member_ids must be a list of strings")
    member_ids = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(member_ids) != len(value) or not member_ids:
        raise LinearToolError(
            "invalid_linear_member_ids",
            "member_ids must be a non-empty list of non-empty strings",
        )
    return member_ids


def _priority(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LinearToolError("invalid_linear_priority", "priority must be an integer from 0 to 4")
    if value < 0 or value > 4:
        raise LinearToolError("invalid_linear_priority", "priority must be an integer from 0 to 4")
    return cast(int, value)


def _linear_input_field(field: str) -> str:
    return {
        "team_id": "teamId",
        "team_ids": "teamIds",
        "project_id": "projectId",
        "parent_issue": "parentId",
        "state_id": "stateId",
        "assignee_id": "assigneeId",
        "label_ids": "labelIds",
        "lead_id": "leadId",
        "member_ids": "memberIds",
        "start_date": "startDate",
        "target_date": "targetDate",
    }.get(field, field)


def _fetch_issue(issue_key: str, presence: Any) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            query CaoLinearIssue($id: String!) {
              issue(id: $id) {
                id
                identifier
                title
                description
                url
                createdAt
                updatedAt
                archivedAt
                state { name type }
                team { key name }
                project { name }
                assignee { name }
              }
            }
            """,
            {"id": issue_key},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _issue_from_payload(payload, issue_key)


def _fetch_issue_comments(issue_key: str, presence: Any, *, limit: int) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            query CaoLinearIssueComments($id: String!, $first: Int!) {
              issue(id: $id) {
                id
                identifier
                archivedAt
                comments(first: $first) {
                  nodes {
                    id
                    body
                    createdAt
                    updatedAt
                    user { id name }
                  }
                }
              }
            }
            """,
            {"id": issue_key, "first": limit},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _issue_from_payload(payload, issue_key)


def _create_linear_comment(
    issue: Mapping[str, Any],
    body: str,
    presence: Any,
) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    issue_id = _string_or_none(issue.get("id"))
    if not issue_id:
        raise LinearToolError(
            "linear_issue_not_found",
            "Linear issue id missing before comment creation",
        )
    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            mutation CaoLinearCreateComment($input: CommentCreateInput!) {
              commentCreate(input: $input) {
                success
                comment {
                  id
                  url
                  body
                  createdAt
                  updatedAt
                  issue {
                    id
                    identifier
                    url
                  }
                }
              }
            }
            """,
            {"input": {"issueId": issue_id, "body": body}},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _created_comment_from_payload(payload, issue_id)


def _open_linear_agent_session_on_issue(
    issue: Mapping[str, Any],
    initial_body: str,
    presence: Any,
    *,
    agent_id: str,
) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    issue_id = _string_or_none(issue.get("id"))
    if not issue_id:
        raise LinearToolError(
            "linear_issue_not_found",
            "Linear issue id missing before AgentSession creation",
        )
    _preflight_presence_credentials(presence)
    external_url = app_client.public_cao_agent_url(agent_id)
    external_urls = [{"label": "Open CAO", "url": external_url}] if external_url else None
    try:
        agent_session = app_client.create_agent_session_on_issue(
            issue_id,
            external_urls=external_urls,
            app_key=presence.app_key,
        )
        session_id = _required_string(
            agent_session.get("id"),
            field="agent_session_id",
            reason="linear_agent_session_not_created",
        )
        app_client.create_agent_activity(
            session_id,
            {"type": "elicitation", "body": initial_body},
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return agent_session


def _validate_linear_reference(field: str, value: str, presence: Any) -> None:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    query_field = {
        "project_id": "project",
        "state_id": "workflowState",
        "assignee_id": "user",
        "lead_id": "user",
        "member_ids": "user",
        "label_ids": "issueLabel",
    }.get(field)
    if query_field is None:
        raise LinearToolError(
            "invalid_linear_reference",
            f"unsupported Linear reference field: {field}",
        )
    try:
        payload = app_client.linear_graphql(
            f"""
            query CaoLinearReference($id: String!) {{
              {query_field}(id: $id) {{
                id
              }}
            }}
            """,
            {"id": value},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    data = payload.get("data")
    node = data.get(query_field) if isinstance(data, Mapping) else None
    if not isinstance(node, Mapping) or not node.get("id"):
        raise LinearToolError(
            "invalid_linear_reference",
            f"{field} references an unknown Linear object: {value}",
        )


def _fetch_team(team_ref: str, presence: Any) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            query CaoLinearTeams {
              teams {
                nodes {
                  id
                  key
                  name
                }
              }
            }
            """,
            {},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _team_from_payload(payload, team_ref)


def _create_linear_issue(
    mutation_input: Mapping[str, Any],
    presence: Any,
) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            mutation CaoLinearCreateIssue($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue {
                  id
                  identifier
                  title
                  url
                  state { name type }
                  team { key name }
                  project { name }
                  parent { id identifier }
                }
              }
            }
            """,
            {"input": dict(mutation_input)},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _mutated_issue_from_payload(payload, "issueCreate")


def _update_linear_issue(
    issue_id: str,
    mutation_input: Mapping[str, Any],
    presence: Any,
) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            mutation CaoLinearUpdateIssue($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) {
                success
                issue {
                  id
                  identifier
                  title
                  url
                  state { name type }
                  team { key name }
                  project { name }
                  parent { id identifier }
                }
              }
            }
            """,
            {"id": issue_id, "input": dict(mutation_input)},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _mutated_issue_from_payload(payload, "issueUpdate")


def _create_linear_project(
    mutation_input: Mapping[str, Any],
    presence: Any,
) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            mutation CaoLinearCreateProject($input: ProjectCreateInput!) {
              projectCreate(input: $input) {
                success
                project {
                  id
                  name
                  description
                  url
                  state
                  startDate
                  targetDate
                  lead { id name }
                  teams(first: 20) { nodes { id key name } }
                  createdAt
                  updatedAt
                }
              }
            }
            """,
            {"input": dict(mutation_input)},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    return _mutated_project_from_payload(payload, "projectCreate")


def _issue_from_payload(payload: Mapping[str, Any], issue_key: str) -> Mapping[str, Any]:
    data = payload.get("data")
    issue = data.get("issue") if isinstance(data, Mapping) else None
    if not isinstance(issue, Mapping) or not issue.get("id"):
        raise LinearToolError("linear_issue_not_found", f"Linear issue not found: {issue_key}")
    archived_at = issue.get("archivedAt")
    if archived_at:
        raise LinearToolError(
            "linear_issue_archived",
            f"Linear issue {issue_key} is archived at {archived_at}",
        )
    return issue


def _team_from_payload(payload: Mapping[str, Any], team_ref: str) -> Mapping[str, Any]:
    data = payload.get("data")
    teams = data.get("teams") if isinstance(data, Mapping) else None
    nodes = teams.get("nodes") if isinstance(teams, Mapping) else None
    if not isinstance(nodes, list):
        raise LinearToolError(
            "invalid_linear_team_id",
            "Linear teams lookup did not return a node list",
        )
    target = _canonical_issue_key(team_ref)
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        candidates = {
            _canonical_issue_key(value) for value in (node.get("id"), node.get("key")) if value
        }
        if target in candidates:
            return node
    raise LinearToolError(
        "invalid_linear_team_id",
        f"team_id references an unknown Linear team id or key: {team_ref}",
    )


def _created_comment_from_payload(
    payload: Mapping[str, Any],
    issue_id: str,
) -> Mapping[str, Any]:
    data = payload.get("data")
    result = data.get("commentCreate") if isinstance(data, Mapping) else None
    if not isinstance(result, Mapping):
        raise LinearToolError(
            "linear_comment_create_failed",
            "Linear commentCreate did not return a result object",
        )
    if result.get("success") is not True:
        raise LinearToolError(
            "linear_comment_create_failed",
            f"Linear commentCreate did not report success for issue {issue_id}",
        )
    comment = result.get("comment")
    if not isinstance(comment, Mapping) or not comment.get("id"):
        raise LinearToolError(
            "linear_comment_create_failed",
            f"Linear commentCreate did not return a comment id for issue {issue_id}",
        )
    return comment


def _mutated_issue_from_payload(
    payload: Mapping[str, Any], mutation_name: str
) -> Mapping[str, Any]:
    data = payload.get("data")
    result = data.get(mutation_name) if isinstance(data, Mapping) else None
    if not isinstance(result, Mapping):
        raise LinearToolError(
            f"linear_{mutation_name}_failed",
            f"Linear {mutation_name} did not return a result object",
        )
    if result.get("success") is not True:
        raise LinearToolError(
            f"linear_{mutation_name}_failed",
            f"Linear {mutation_name} did not report success",
        )
    issue = result.get("issue")
    if not isinstance(issue, Mapping) or not issue.get("id"):
        raise LinearToolError(
            f"linear_{mutation_name}_failed",
            f"Linear {mutation_name} did not return an issue id",
        )
    return issue


def _mutated_project_from_payload(
    payload: Mapping[str, Any], mutation_name: str
) -> Mapping[str, Any]:
    data = payload.get("data")
    result = data.get(mutation_name) if isinstance(data, Mapping) else None
    if not isinstance(result, Mapping):
        raise LinearToolError(
            f"linear_{mutation_name}_failed",
            f"Linear {mutation_name} did not return a result object",
        )
    if result.get("success") is not True:
        raise LinearToolError(
            f"linear_{mutation_name}_failed",
            f"Linear {mutation_name} did not report success",
        )
    project = result.get("project")
    if not isinstance(project, Mapping) or not project.get("id"):
        raise LinearToolError(
            f"linear_{mutation_name}_failed",
            f"Linear {mutation_name} did not return a project id",
        )
    return project


def _preflight_presence_credentials(presence: Any) -> None:
    access_token = getattr(presence, "access_token", None)
    refresh_token = getattr(presence, "refresh_token", None)
    if not access_token and not refresh_token:
        raise LinearToolError(
            "linear_credentials_missing",
            f"Linear presence {presence.presence_id} has no access_token or refresh_token",
        )
    expires_at = _parse_expires_at(getattr(presence, "token_expires_at", None))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc) and not refresh_token:
        raise LinearToolError(
            "linear_credentials_expired",
            f"Linear presence {presence.presence_id} access token expired at "
            f"{expires_at.isoformat()}",
        )


def _linear_api_error(exc: Exception) -> LinearToolError:
    from cli_agent_orchestrator.linear import app_client

    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, LinearToolError):
        return exc
    if isinstance(exc, app_client.LinearOAuthError):
        if "expired" in lowered or "unauthorized" in lowered or "refresh" in lowered:
            return LinearToolError("linear_credentials_expired", text)
        return LinearToolError("linear_credentials_missing", text)
    if "permission" in lowered or "forbidden" in lowered or "unauthorized" in lowered:
        return LinearToolError("linear_issue_inaccessible", text)
    if "not found" in lowered:
        return LinearToolError("linear_issue_not_found", text)
    return LinearToolError("linear_api_failure", text)


def _compact_issue_payload(issue: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(issue.get("id")),
        "identifier": _string_or_none(issue.get("identifier")),
        "title": _string_or_none(issue.get("title")),
        "status": _named_object(issue.get("state"), ("name", "type")),
        "team": _named_object(issue.get("team"), ("key", "name")),
        "project": _named_object(issue.get("project"), ("name",)),
        "assignee": _named_object(issue.get("assignee"), ("name",)),
        "description": _bounded_text(issue.get("description"), MAX_DESCRIPTION_CHARS),
        "url": _string_or_none(issue.get("url")),
        "created_at": _string_or_none(issue.get("createdAt")),
        "updated_at": _string_or_none(issue.get("updatedAt")),
    }


def _comments_from_issue(issue: Mapping[str, Any]) -> list[dict[str, Any]]:
    comments = issue.get("comments")
    nodes = comments.get("nodes") if isinstance(comments, Mapping) else None
    if not isinstance(nodes, list):
        return []
    result = [
        {
            "id": _string_or_none(node.get("id")),
            "body": _bounded_text(node.get("body"), MAX_COMMENT_BODY_CHARS),
            "author": _named_object(node.get("user"), ("id", "name")),
            "created_at": _string_or_none(node.get("createdAt")),
            "updated_at": _string_or_none(node.get("updatedAt")),
        }
        for node in nodes
        if isinstance(node, Mapping)
    ]
    return sorted(result, key=lambda item: item.get("created_at") or "")


def _comment_limit(value: Any) -> int:
    if value is None:
        return DEFAULT_COMMENT_LIMIT
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise LinearToolError("invalid_linear_comment_limit", "limit must be an integer") from exc
    if limit < 1 or limit > MAX_COMMENT_LIMIT:
        raise LinearToolError(
            "invalid_linear_comment_limit",
            f"limit must be between 1 and {MAX_COMMENT_LIMIT}",
        )
    return limit


def _compact_created_comment_payload(
    comment: Mapping[str, Any],
    fallback_issue: Mapping[str, Any],
) -> dict[str, Any]:
    issue = comment.get("issue") if isinstance(comment.get("issue"), Mapping) else fallback_issue
    issue_url = _string_or_none(issue.get("url")) if isinstance(issue, Mapping) else None
    comment_url = _string_or_none(comment.get("url"))
    return {
        "status": "created",
        "id": _string_or_none(comment.get("id")),
        "url": comment_url or issue_url,
        "issue": {
            "id": _string_or_none(issue.get("id")) if isinstance(issue, Mapping) else None,
            "identifier": (
                _string_or_none(issue.get("identifier")) if isinstance(issue, Mapping) else None
            ),
            "url": issue_url,
        },
        "created_at": _string_or_none(comment.get("createdAt")),
        "updated_at": _string_or_none(comment.get("updatedAt")),
    }


def _compact_created_agent_session_payload(
    agent_session: Mapping[str, Any],
    fallback_issue: Mapping[str, Any],
) -> dict[str, Any]:
    issue = (
        agent_session.get("issue")
        if isinstance(agent_session.get("issue"), Mapping)
        else fallback_issue
    )
    return {
        "status": "created",
        "id": _string_or_none(agent_session.get("id")),
        "url": _string_or_none(agent_session.get("url")),
        "issue": {
            "id": _string_or_none(issue.get("id")) if isinstance(issue, Mapping) else None,
            "identifier": (
                _string_or_none(issue.get("identifier")) if isinstance(issue, Mapping) else None
            ),
            "title": _string_or_none(issue.get("title")) if isinstance(issue, Mapping) else None,
            "url": _string_or_none(issue.get("url")) if isinstance(issue, Mapping) else None,
        },
        "initial_activity": {"type": "elicitation", "status": "created"},
    }


def _compact_issue_mutation_payload(
    issue: Mapping[str, Any],
    *,
    status: str,
    changed_fields: tuple[str, ...],
) -> dict[str, Any]:
    payload = {
        "status": status,
        "id": _string_or_none(issue.get("id")),
        "identifier": _string_or_none(issue.get("identifier")),
        "title": _string_or_none(issue.get("title")),
        "url": _string_or_none(issue.get("url")),
        "team": _named_object(issue.get("team"), ("key", "name")),
        "project": _named_object(issue.get("project"), ("name",)),
        "state": _named_object(issue.get("state"), ("name", "type")),
        "changed_fields": list(changed_fields),
    }
    parent = _named_object(issue.get("parent"), ("id", "identifier"))
    if parent is not None:
        payload["parent"] = parent
    return payload


def _compact_project_mutation_payload(
    project: Mapping[str, Any],
    *,
    status: str,
    changed_fields: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "status": status,
        "id": _string_or_none(project.get("id")),
        "name": _string_or_none(project.get("name")),
        "url": _string_or_none(project.get("url")),
        "state": _string_or_none(project.get("state")),
        "lead": _named_object(project.get("lead"), ("id", "name")),
        "teams": _compact_nested_named_nodes(project.get("teams"), ("id", "key", "name")),
        "created_at": _string_or_none(project.get("createdAt")),
        "updated_at": _string_or_none(project.get("updatedAt")),
        "changed_fields": list(changed_fields),
    }


def _named_object(value: Any, keys: tuple[str, ...]) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    result = {key: str(value[key]) for key in keys if value.get(key) is not None}
    return result or None


def _compact_nested_named_nodes(value: Any, keys: tuple[str, ...]) -> list[dict[str, str]]:
    nodes = value.get("nodes") if isinstance(value, Mapping) else None
    if not isinstance(nodes, list):
        return []
    result: list[dict[str, str]] = []
    for node in nodes:
        named = _named_object(node, keys)
        if named:
            result.append(named)
    return result


def _string_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _bounded_text(value: Any, limit: int) -> str | None:
    text = _string_or_none(value)
    if text is None or len(text) <= limit:
        return text
    return text[: max(0, limit - len(_TRUNCATED))] + _TRUNCATED


def _canonical_issue_key(value: Any) -> str:
    return str(value).strip().lower()


def _allows_any_issue(values: tuple[str, ...]) -> bool:
    return any(value.strip() == "*" for value in values)


def _parse_expires_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = [
    "CREATE_COMMENT_TOOL",
    "CREATE_ISSUE_FIELDS",
    "CREATE_ISSUE_TOOL",
    "CREATE_PROJECT_FIELDS",
    "CREATE_PROJECT_TOOL",
    "GET_ISSUE_TOOL",
    "LINEAR_AGENT_SESSION_WRITE_TOOLS",
    "LINEAR_COMMENT_WRITE_TOOLS",
    "LINEAR_ISSUE_MUTATION_TOOLS",
    "LINEAR_CONTEXT_MAPPING_MUTATION_TOOLS",
    "LINEAR_PROJECT_MUTATION_TOOLS",
    "LINEAR_PROVIDER_TOOLS",
    "LINEAR_READ_TOOLS",
    "LIST_COMMENTS_TOOL",
    "OPEN_AGENT_SESSION_ON_ISSUE_TOOL",
    "ISSUE_TARGETING_TOOLS",
    "UPDATE_ISSUE_FIELDS",
    "UPDATE_ISSUE_TOOL",
    "LinearToolProvider",
    "LinearToolAccess",
    "LinearToolError",
]
