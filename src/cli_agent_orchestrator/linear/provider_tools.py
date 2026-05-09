"""Linear-owned CAO-mediated MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, cast

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
CREATE_ISSUE_TOOL = "cao_linear.create_issue"
UPDATE_ISSUE_TOOL = "cao_linear.update_issue"
READ_POLICY_HOOK = "linear_read_policy"
COMMENT_WRITE_POLICY_HOOK = "linear_comment_write_policy"
ISSUE_MUTATION_POLICY_HOOK = "linear_issue_mutation_policy"
LINEAR_READ_TOOLS = frozenset({GET_ISSUE_TOOL, LIST_COMMENTS_TOOL})
LINEAR_COMMENT_WRITE_TOOLS = frozenset({CREATE_COMMENT_TOOL})
LINEAR_ISSUE_MUTATION_TOOLS = frozenset({CREATE_ISSUE_TOOL, UPDATE_ISSUE_TOOL})
LINEAR_PROVIDER_TOOLS = LINEAR_READ_TOOLS | LINEAR_COMMENT_WRITE_TOOLS | LINEAR_ISSUE_MUTATION_TOOLS
ISSUE_TARGETING_TOOLS = LINEAR_READ_TOOLS | LINEAR_COMMENT_WRITE_TOOLS | {UPDATE_ISSUE_TOOL}
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
REFERENCE_FIELDS = frozenset({"project_id", "state_id", "assignee_id"})
MAX_DESCRIPTION_CHARS = 4000
MAX_COMMENT_BODY_CHARS = 4000
DEFAULT_COMMENT_LIMIT = 50
MAX_COMMENT_LIMIT = 100
_TRUNCATED = "...[truncated]"

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

    @property
    def location(self) -> str:
        return f"tool_access.{self.access_id}"


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
        return (
            ProviderMediatedToolDefinition(
                name=GET_ISSUE_TOOL,
                description="Fetch a compact read-only Linear issue payload for an authorized issue.",
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
        )

    def _hooks(self) -> tuple[ProviderToolHookDefinition, ...]:
        return (
            ProviderToolHookDefinition(
                name=READ_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_before_call,
            ),
            ProviderToolHookDefinition(
                name=COMMENT_WRITE_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_comment_before_call,
            ),
            ProviderToolHookDefinition(
                name=ISSUE_MUTATION_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_issue_mutation_before_call,
            ),
        )

    def _access_requests(self) -> tuple[ProviderToolAccessRequest, ...]:
        requests: list[ProviderToolAccessRequest] = []
        for access in self._config.tool_access.values():
            for tool_name in access.tools:
                if tool_name == CREATE_COMMENT_TOOL:
                    pre_hook = COMMENT_WRITE_POLICY_HOOK
                elif tool_name in LINEAR_ISSUE_MUTATION_TOOLS:
                    pre_hook = ISSUE_MUTATION_POLICY_HOOK
                else:
                    pre_hook = READ_POLICY_HOOK
                requests.append(
                    ProviderToolAccessRequest(
                        tool_name=tool_name,
                        agent_identity_id=access.agent_id,
                        agent_profile=access.agent_profile,
                        pre_hooks=(pre_hook,),
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
            return ProviderToolPreCallResult.deny(
                exc.reason,
                {
                    "provider_name": PROVIDER_NAME,
                    "tool_name": context.tool_name,
                    "detail": str(exc),
                },
            )
        return ProviderToolPreCallResult.allow()

    def _authorize_issue_mutation_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            if context.tool_name == CREATE_ISSUE_TOOL:
                self._validated_create_issue_request(context)
            elif context.tool_name == UPDATE_ISSUE_TOOL:
                self._validated_update_issue_request(context)
            else:
                raise LinearToolError(
                    "malformed_linear_tool_policy",
                    f"unexpected Linear mutation tool {context.tool_name!r}",
                )
        except LinearToolError as exc:
            return ProviderToolPreCallResult.deny(
                exc.reason,
                {
                    "provider_name": PROVIDER_NAME,
                    "tool_name": context.tool_name,
                    "detail": str(exc),
                },
            )
        return ProviderToolPreCallResult.allow()

    def _authorize_comment_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._authorized_issue_request(context)
            _comment_body_from_arguments(context.arguments)
        except LinearToolError as exc:
            return ProviderToolPreCallResult.deny(
                exc.reason,
                {
                    "provider_name": PROVIDER_NAME,
                    "tool_name": context.tool_name,
                    "detail": str(exc),
                },
            )
        return ProviderToolPreCallResult.allow()

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
        "anyOf": [{"required": ["issue"]}, {"required": ["issue_ref"]}],
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
        "anyOf": issue_schema["anyOf"],
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
        "anyOf": issue_schema["anyOf"],
        "additionalProperties": False,
    }


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


def _priority(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LinearToolError("invalid_linear_priority", "priority must be an integer from 0 to 4")
    if value < 0 or value > 4:
        raise LinearToolError("invalid_linear_priority", "priority must be an integer from 0 to 4")
    return cast(int, value)


def _linear_input_field(field: str) -> str:
    return {
        "team_id": "teamId",
        "project_id": "projectId",
        "parent_issue": "parentId",
        "state_id": "stateId",
        "assignee_id": "assigneeId",
        "label_ids": "labelIds",
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


def _validate_linear_reference(field: str, value: str, presence: Any) -> None:
    from cli_agent_orchestrator.linear import app_client

    _preflight_presence_credentials(presence)
    try:
        payload = app_client.linear_graphql(
            """
            query CaoLinearReference($id: String!) {
              node(id: $id) {
                id
              }
            }
            """,
            {"id": value},
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_api_error(exc) from exc
    data = payload.get("data")
    node = data.get("node") if isinstance(data, Mapping) else None
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


def _compact_issue_mutation_payload(
    issue: Mapping[str, Any],
    *,
    status: str,
    changed_fields: tuple[str, ...],
) -> dict[str, Any]:
    return {
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


def _named_object(value: Any, keys: tuple[str, ...]) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    result = {key: str(value[key]) for key in keys if value.get(key) is not None}
    return result or None


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
    "GET_ISSUE_TOOL",
    "LINEAR_COMMENT_WRITE_TOOLS",
    "LINEAR_ISSUE_MUTATION_TOOLS",
    "LINEAR_PROVIDER_TOOLS",
    "LINEAR_READ_TOOLS",
    "LIST_COMMENTS_TOOL",
    "ISSUE_TARGETING_TOOLS",
    "UPDATE_ISSUE_FIELDS",
    "UPDATE_ISSUE_TOOL",
    "LinearToolProvider",
    "LinearToolAccess",
    "LinearToolError",
]
