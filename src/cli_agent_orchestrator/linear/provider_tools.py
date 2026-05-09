"""Linear-owned CAO-mediated read-only MCP tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

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
READ_POLICY_HOOK = "linear_read_policy"
LINEAR_READ_TOOLS = frozenset({GET_ISSUE_TOOL, LIST_COMMENTS_TOOL})
MAX_DESCRIPTION_CHARS = 4000
MAX_COMMENT_BODY_CHARS = 4000
DEFAULT_COMMENT_LIMIT = 50
MAX_COMMENT_LIMIT = 100
_TRUNCATED = "...[truncated]"

# External contract source: Linear's official GraphQL developer docs document
# issue lookup by shorthand id/UUID and core fields such as id, title,
# description, assignee, createdAt, and archivedAt. They also document GraphQL
# error-array handling and the public schema explorer:
# https://linear.app/developers/graphql
# https://linear.app/docs/api-and-webhooks


class LinearReadToolError(RuntimeError):
    """Recoverable Linear read-tool failure with an operator-facing reason."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        super().__init__(f"{reason}: {detail}")


@dataclass(frozen=True)
class LinearToolAccess:
    """Provider-native Linear read policy entry from ``linear.toml``."""

    access_id: str
    agent_id: str | None
    agent_profile: str | None
    tools: tuple[str, ...]
    issues: tuple[str, ...]

    @property
    def location(self) -> str:
        return f"tool_access.{self.access_id}"


class LinearReadToolProvider:
    """Build and execute Linear's CAO-mediated read-only tool policy."""

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
        self._access_by_location = {
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
        )

    def _hooks(self) -> tuple[ProviderToolHookDefinition, ...]:
        return (
            ProviderToolHookDefinition(
                name=READ_POLICY_HOOK,
                phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
                handler=self._authorize_before_call,
            ),
        )

    def _access_requests(self) -> tuple[ProviderToolAccessRequest, ...]:
        requests: list[ProviderToolAccessRequest] = []
        for access in self._config.tool_access.values():
            for tool_name in access.tools:
                requests.append(
                    ProviderToolAccessRequest(
                        tool_name=tool_name,
                        agent_identity_id=access.agent_id,
                        agent_profile=access.agent_profile,
                        pre_hooks=(READ_POLICY_HOOK,),
                        location=access.location,
                    )
                )
        return tuple(requests)

    def _authorize_before_call(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult:
        try:
            self._authorized_issue_request(context)
        except LinearReadToolError as exc:
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

    def _authorized_issue_request(self, context: ProviderToolInvocationContext) -> str:
        access = self._access_by_location.get(context.access.source_location)
        if access is None:
            raise LinearReadToolError(
                "malformed_linear_read_policy",
                f"missing Linear read policy for {context.access.source_location}",
            )
        issue_key = _issue_key_from_arguments(context.arguments)
        if _canonical_issue_key(issue_key) not in {
            _canonical_issue_key(item) for item in access.issues
        }:
            raise LinearReadToolError(
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
            raise LinearReadToolError(
                "linear_issue_outside_policy",
                "Linear returned an issue that does not match the authorized target",
            )

    def _presence_for_identity(self, agent_identity_id: str) -> Any:
        presence = self._find_presence_for_identity(agent_identity_id)
        if presence is None:
            raise LinearReadToolError(
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


def _issue_key_from_arguments(arguments: Mapping[str, Any]) -> str:
    issue = arguments.get("issue")
    issue_ref = arguments.get("issue_ref")
    if isinstance(issue, str) and issue.strip():
        return issue.strip()
    if isinstance(issue_ref, Mapping):
        provider = _string_or_none(issue_ref.get("provider"))
        if provider != PROVIDER_NAME:
            raise LinearReadToolError(
                "wrong_provider_ref",
                f"expected a Linear issue ref, got provider {provider!r}",
            )
        ref_id = _string_or_none(issue_ref.get("id"))
        if ref_id:
            return ref_id
    raise LinearReadToolError(
        "invalid_linear_issue_argument",
        "provide issue or issue_ref with a non-empty Linear issue id",
    )


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


def _issue_from_payload(payload: Mapping[str, Any], issue_key: str) -> Mapping[str, Any]:
    data = payload.get("data")
    issue = data.get("issue") if isinstance(data, Mapping) else None
    if not isinstance(issue, Mapping) or not issue.get("id"):
        raise LinearReadToolError("linear_issue_not_found", f"Linear issue not found: {issue_key}")
    archived_at = issue.get("archivedAt")
    if archived_at:
        raise LinearReadToolError(
            "linear_issue_archived",
            f"Linear issue {issue_key} is archived at {archived_at}",
        )
    return issue


def _preflight_presence_credentials(presence: Any) -> None:
    access_token = getattr(presence, "access_token", None)
    refresh_token = getattr(presence, "refresh_token", None)
    if not access_token and not refresh_token:
        raise LinearReadToolError(
            "linear_credentials_missing",
            f"Linear presence {presence.presence_id} has no access_token or refresh_token",
        )
    expires_at = _parse_expires_at(getattr(presence, "token_expires_at", None))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc) and not refresh_token:
        raise LinearReadToolError(
            "linear_credentials_expired",
            f"Linear presence {presence.presence_id} access token expired at "
            f"{expires_at.isoformat()}",
        )


def _linear_api_error(exc: Exception) -> LinearReadToolError:
    from cli_agent_orchestrator.linear import app_client

    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, LinearReadToolError):
        return exc
    if isinstance(exc, app_client.LinearOAuthError):
        if "expired" in lowered or "unauthorized" in lowered or "refresh" in lowered:
            return LinearReadToolError("linear_credentials_expired", text)
        return LinearReadToolError("linear_credentials_missing", text)
    if "permission" in lowered or "forbidden" in lowered or "unauthorized" in lowered:
        return LinearReadToolError("linear_issue_inaccessible", text)
    if "not found" in lowered:
        return LinearReadToolError("linear_issue_not_found", text)
    return LinearReadToolError("linear_api_failure", text)


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
        raise LinearReadToolError(
            "invalid_linear_comment_limit", "limit must be an integer"
        ) from exc
    if limit < 1 or limit > MAX_COMMENT_LIMIT:
        raise LinearReadToolError(
            "invalid_linear_comment_limit",
            f"limit must be between 1 and {MAX_COMMENT_LIMIT}",
        )
    return limit


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
    "GET_ISSUE_TOOL",
    "LINEAR_READ_TOOLS",
    "LIST_COMMENTS_TOOL",
    "LinearReadToolProvider",
    "LinearToolAccess",
]
