"""GraphQL helpers for Linear CAO-mediated exploration tools."""

from __future__ import annotations

from typing import Any, Mapping, cast


class LinearProviderQueryError(RuntimeError):
    """Recoverable Linear query failure with a provider-facing reason."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        super().__init__(f"{reason}: {detail}")


def list_teams(presence: Any, *, limit: int, query: str | None = None) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": limit}
    filter_input: dict[str, Any] = {}
    if query:
        filter_input["or"] = [
            {"name": {"containsIgnoreCase": query}},
            {"key": {"containsIgnoreCase": query}},
        ]
    if filter_input:
        variables["filter"] = filter_input
    payload = _linear_graphql(
        """
        query CaoLinearListTeams($first: Int!, $filter: TeamFilter) {
          teams(first: $first, filter: $filter) {
            nodes {
              id
              key
              name
              description
              createdAt
              updatedAt
              archivedAt
            }
          }
        }
        """,
        variables,
        presence,
    )
    return {"teams": [_compact_team(node) for node in _connection_nodes(payload, "teams")]}


def get_team(presence: Any, *, team_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetTeam($id: String!) {
          team(id: $id) {
            id
            key
            name
            description
            createdAt
            updatedAt
            archivedAt
          }
        }
        """,
        {"id": team_id},
        presence,
    )
    return _required_node(payload, "team", team_id, "linear_team_not_found", _compact_team)


def list_users(
    presence: Any, *, limit: int, query: str | None = None, include_disabled: bool = False
) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": limit, "includeDisabled": include_disabled}
    if query:
        variables["filter"] = {"name": {"containsIgnoreCase": query}}
    payload = _linear_graphql(
        """
        query CaoLinearListUsers($first: Int!, $filter: UserFilter, $includeDisabled: Boolean) {
          users(first: $first, filter: $filter, includeDisabled: $includeDisabled) {
            nodes {
              id
              name
              displayName
              email
              active
              admin
              guest
              createdAt
              updatedAt
            }
          }
        }
        """,
        variables,
        presence,
    )
    return {"users": [_compact_user(node) for node in _connection_nodes(payload, "users")]}


def get_user(presence: Any, *, user_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetUser($id: String!) {
          user(id: $id) {
            id
            name
            displayName
            email
            active
            admin
            guest
            createdAt
            updatedAt
          }
        }
        """,
        {"id": user_id},
        presence,
    )
    return _required_node(payload, "user", user_id, "linear_user_not_found", _compact_user)


def list_issue_statuses(
    presence: Any,
    *,
    limit: int,
    team_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": limit}
    filters: dict[str, Any] = {}
    if team_id:
        filters["team"] = {"id": {"eq": team_id}}
    if query:
        filters["name"] = {"containsIgnoreCase": query}
    if filters:
        variables["filter"] = filters
    payload = _linear_graphql(
        """
        query CaoLinearListIssueStatuses($first: Int!, $filter: WorkflowStateFilter) {
          workflowStates(first: $first, filter: $filter) {
            nodes {
              id
              name
              type
              description
              color
              position
              createdAt
              updatedAt
              team { id key name }
            }
          }
        }
        """,
        variables,
        presence,
    )
    return {
        "issue_statuses": [
            _compact_issue_status(node) for node in _connection_nodes(payload, "workflowStates")
        ]
    }


def get_issue_status(presence: Any, *, status_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetIssueStatus($id: String!) {
          workflowState(id: $id) {
            id
            name
            type
            description
            color
            position
            createdAt
            updatedAt
            team { id key name }
          }
        }
        """,
        {"id": status_id},
        presence,
    )
    return _required_node(
        payload,
        "workflowState",
        status_id,
        "linear_issue_status_not_found",
        _compact_issue_status,
    )


def list_issue_labels(
    presence: Any,
    *,
    limit: int,
    team_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": limit}
    filters: dict[str, Any] = {}
    if team_id:
        filters["team"] = {"id": {"eq": team_id}}
    if query:
        filters["name"] = {"containsIgnoreCase": query}
    if filters:
        variables["filter"] = filters
    payload = _linear_graphql(
        """
        query CaoLinearListIssueLabels($first: Int!, $filter: IssueLabelFilter) {
          issueLabels(first: $first, filter: $filter) {
            nodes {
              id
              name
              description
              color
              isGroup
              createdAt
              updatedAt
              team { id key name }
              parent { id name }
            }
          }
        }
        """,
        variables,
        presence,
    )
    return {
        "issue_labels": [
            _compact_issue_label(node) for node in _connection_nodes(payload, "issueLabels")
        ]
    }


def get_issue_label(presence: Any, *, label_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetIssueLabel($id: String!) {
          issueLabel(id: $id) {
            id
            name
            description
            color
            isGroup
            createdAt
            updatedAt
            team { id key name }
            parent { id name }
          }
        }
        """,
        {"id": label_id},
        presence,
    )
    return _required_node(
        payload, "issueLabel", label_id, "linear_issue_label_not_found", _compact_issue_label
    )


def list_projects(
    presence: Any, *, limit: int, query: str | None = None, team_id: str | None = None
) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": max(limit, 50) if team_id else limit}
    filters: dict[str, Any] = {}
    if query:
        filters["name"] = {"containsIgnoreCase": query}
    if filters:
        variables["filter"] = filters
    payload = _linear_graphql(
        """
        query CaoLinearListProjects($first: Int!, $filter: ProjectFilter) {
          projects(first: $first, filter: $filter) {
            nodes {
              id
              name
              description
              url
              state
              startDate
              targetDate
              createdAt
              updatedAt
              lead { id name }
              teams(first: 10) { nodes { id key name } }
            }
          }
        }
        """,
        variables,
        presence,
    )
    projects = [
        _compact_project(node)
        for node in _connection_nodes(payload, "projects")
        if team_id is None or _project_has_team(node, team_id)
    ]
    return {"projects": projects[:limit]}


def get_project(presence: Any, *, project_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetProject($id: String!) {
          project(id: $id) {
            id
            name
            description
            url
            state
            content
            startDate
            targetDate
            createdAt
            updatedAt
            lead { id name }
            teams(first: 20) { nodes { id key name } }
          }
        }
        """,
        {"id": project_id},
        presence,
    )
    return _required_node(
        payload, "project", project_id, "linear_project_not_found", _compact_project
    )


def _project_has_team(project: Mapping[str, Any], team_id: str) -> bool:
    teams = project.get("teams")
    if not isinstance(teams, Mapping):
        return False
    nodes = teams.get("nodes")
    if not isinstance(nodes, list):
        return False
    needle = str(team_id).lower()
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        if str(node.get("id") or "").lower() == needle:
            return True
        if str(node.get("key") or "").lower() == needle:
            return True
    return False


def list_issues(
    presence: Any,
    *,
    limit: int,
    team_id: str | None = None,
    project_id: str | None = None,
    state_id: str | None = None,
    assignee_id: str | None = None,
) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": limit}
    filters = _issue_filter(
        team_id=team_id,
        project_id=project_id,
        state_id=state_id,
        assignee_id=assignee_id,
    )
    if filters:
        variables["filter"] = filters
    payload = _linear_graphql(
        """
        query CaoLinearListIssues($first: Int!, $filter: IssueFilter) {
          issues(first: $first, filter: $filter) {
            nodes {
              id
              identifier
              title
              description
              url
              priority
              createdAt
              updatedAt
              archivedAt
              state { id name type }
              team { id key name }
              project { id name }
              assignee { id name }
            }
          }
        }
        """,
        variables,
        presence,
    )
    return {"issues": [_compact_issue(node) for node in _connection_nodes(payload, "issues")]}


def search_issues(
    presence: Any,
    *,
    term: str,
    limit: int,
    team_id: str | None = None,
    include_comments: bool = False,
) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearSearchIssues(
          $term: String!
          $first: Int!
          $teamId: String
          $includeComments: Boolean
        ) {
          searchIssues(
            term: $term
            first: $first
            teamId: $teamId
            includeComments: $includeComments
          ) {
            nodes {
              id
              identifier
              title
              description
              url
              priority
              createdAt
              updatedAt
              archivedAt
              state { id name type }
              team { id key name }
              project { id name }
              assignee { id name }
            }
          }
        }
        """,
        {
            "term": term,
            "first": limit,
            "teamId": team_id,
            "includeComments": include_comments,
        },
        presence,
    )
    return {"issues": [_compact_issue(node) for node in _connection_nodes(payload, "searchIssues")]}


def get_comment(presence: Any, *, comment_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetComment($id: String!) {
          comment(id: $id) {
            id
            body
            url
            createdAt
            updatedAt
            issue { id identifier title url }
            parent { id url }
            user { id name }
          }
        }
        """,
        {"id": comment_id},
        presence,
    )
    return _required_node(
        payload, "comment", comment_id, "linear_comment_not_found", _compact_comment
    )


def get_agent_session(presence: Any, *, agent_session_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetAgentSession($id: String!) {
          agentSession(id: $id) {
            id
            url
            status
            summary
            context
            createdAt
            updatedAt
            startedAt
            endedAt
            issue { id identifier title url }
            comment { id url body createdAt updatedAt user { id name } }
            sourceComment { id url body createdAt updatedAt user { id name } }
            appUser { id name }
            creator { id name }
          }
        }
        """,
        {"id": agent_session_id},
        presence,
    )
    return _required_node(
        payload,
        "agentSession",
        agent_session_id,
        "linear_agent_session_not_found",
        _compact_agent_session,
    )


def list_agent_session_activities(
    presence: Any, *, agent_session_id: str, limit: int
) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearListAgentSessionActivities($id: String!, $first: Int!) {
          agentSession(id: $id) {
            id
            activities(first: $first, orderBy: createdAt) {
              nodes {
                id
                signal
                createdAt
                updatedAt
                user { id name }
                sourceComment { id url }
                content {
                  ... on AgentActivityPromptContent { type body }
                  ... on AgentActivityThoughtContent { type body }
                  ... on AgentActivityResponseContent { type body }
                  ... on AgentActivityElicitationContent { type body }
                  ... on AgentActivityErrorContent { type body }
                  ... on AgentActivityActionContent { type action parameter result }
                }
              }
            }
          }
        }
        """,
        {"id": agent_session_id, "first": limit},
        presence,
    )
    session = _required_mapping(
        payload, ("data", "agentSession"), agent_session_id, "linear_agent_session_not_found"
    )
    activities = session.get("activities")
    nodes = activities.get("nodes") if isinstance(activities, Mapping) else None
    if not isinstance(nodes, list):
        nodes = []
    return {
        "agent_session": {"id": _string_or_none(session.get("id"))},
        "activities": [
            _compact_agent_activity(node) for node in nodes if isinstance(node, Mapping)
        ],
    }


def get_agent_session_activity(presence: Any, *, activity_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetAgentSessionActivity($id: String!) {
          agentActivity(id: $id) {
            id
            signal
            createdAt
            updatedAt
            user { id name }
            sourceComment { id url }
            agentSession { id url issue { id identifier title url } }
            content {
              ... on AgentActivityPromptContent { type body }
              ... on AgentActivityThoughtContent { type body }
              ... on AgentActivityResponseContent { type body }
              ... on AgentActivityElicitationContent { type body }
              ... on AgentActivityErrorContent { type body }
              ... on AgentActivityActionContent { type action parameter result }
            }
          }
        }
        """,
        {"id": activity_id},
        presence,
    )
    return _required_node(
        payload,
        "agentActivity",
        activity_id,
        "linear_agent_session_activity_not_found",
        _compact_agent_activity,
    )


def list_documents(
    presence: Any, *, limit: int, project_id: str | None = None, query: str | None = None
) -> dict[str, Any]:
    variables: dict[str, Any] = {"first": limit}
    filters: dict[str, Any] = {}
    if project_id:
        filters["project"] = {"id": {"eq": project_id}}
    if query:
        filters["title"] = {"containsIgnoreCase": query}
    if filters:
        variables["filter"] = filters
    payload = _linear_graphql(
        """
        query CaoLinearListDocuments($first: Int!, $filter: DocumentFilter) {
          documents(first: $first, filter: $filter) {
            nodes {
              id
              slugId
              title
              summary
              content
              url
              createdAt
              updatedAt
              project { id name url }
              issue { id identifier title url }
              team { id key name }
              creator { id name }
              updatedBy { id name }
            }
          }
        }
        """,
        variables,
        presence,
    )
    return {
        "documents": [_compact_document(node) for node in _connection_nodes(payload, "documents")]
    }


def get_document(presence: Any, *, document_id: str) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearGetDocument($id: String!) {
          document(id: $id) {
            id
            slugId
            title
            summary
            content
            url
            createdAt
            updatedAt
            project { id name url }
            issue { id identifier title url }
            team { id key name }
            creator { id name }
            updatedBy { id name }
          }
        }
        """,
        {"id": document_id},
        presence,
    )
    return _required_node(
        payload, "document", document_id, "linear_document_not_found", _compact_document
    )


def search_documents(
    presence: Any,
    *,
    term: str,
    limit: int,
    team_id: str | None = None,
    include_comments: bool = False,
) -> dict[str, Any]:
    payload = _linear_graphql(
        """
        query CaoLinearSearchDocuments(
          $term: String!
          $first: Int!
          $teamId: String
          $includeComments: Boolean
        ) {
          searchDocuments(
            term: $term
            first: $first
            teamId: $teamId
            includeComments: $includeComments
          ) {
            nodes {
              id
              slugId
              title
              summary
              content
              url
              createdAt
              updatedAt
              project { id name url }
              issue { id identifier title url }
              team { id key name }
              creator { id name }
              updatedBy { id name }
            }
          }
        }
        """,
        {
            "term": term,
            "first": limit,
            "teamId": team_id,
            "includeComments": include_comments,
        },
        presence,
    )
    return {
        "documents": [
            _compact_document(node) for node in _connection_nodes(payload, "searchDocuments")
        ]
    }


def _linear_graphql(query: str, variables: Mapping[str, Any], presence: Any) -> Mapping[str, Any]:
    from cli_agent_orchestrator.linear import app_client

    try:
        return app_client.linear_graphql(
            query,
            dict(variables),
            access_token=app_client.access_token_for_presence(presence),
            app_key=presence.app_key,
        )
    except Exception as exc:
        raise _linear_query_error(exc) from exc


def _linear_query_error(exc: Exception) -> LinearProviderQueryError:
    from cli_agent_orchestrator.linear import app_client

    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, LinearProviderQueryError):
        return exc
    if isinstance(exc, app_client.LinearOAuthError):
        if "expired" in lowered or "unauthorized" in lowered or "refresh" in lowered:
            return LinearProviderQueryError("linear_credentials_expired", text)
        return LinearProviderQueryError("linear_credentials_missing", text)
    if "permission" in lowered or "forbidden" in lowered or "unauthorized" in lowered:
        return LinearProviderQueryError("linear_object_inaccessible", text)
    if "not found" in lowered:
        return LinearProviderQueryError("linear_object_not_found", text)
    return LinearProviderQueryError("linear_api_failure", text)


def _connection_nodes(payload: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    data = payload.get("data")
    connection = data.get(field) if isinstance(data, Mapping) else None
    nodes = connection.get("nodes") if isinstance(connection, Mapping) else None
    if not isinstance(nodes, list):
        raise LinearProviderQueryError(
            "linear_api_failure",
            f"Linear {field} query did not return connection nodes",
        )
    return [node for node in nodes if isinstance(node, Mapping)]


def _required_node(
    payload: Mapping[str, Any],
    field: str,
    object_id: str,
    reason: str,
    compact: Any,
) -> dict[str, Any]:
    node = _required_mapping(payload, ("data", field), object_id, reason)
    return cast(dict[str, Any], compact(node))


def _required_mapping(
    payload: Mapping[str, Any],
    path: tuple[str, ...],
    object_id: str,
    reason: str,
) -> Mapping[str, Any]:
    value: Any = payload
    for key in path:
        value = value.get(key) if isinstance(value, Mapping) else None
    if not isinstance(value, Mapping) or not value.get("id"):
        raise LinearProviderQueryError(reason, f"Linear object not found: {object_id}")
    archived_at = value.get("archivedAt")
    if archived_at:
        raise LinearProviderQueryError(
            "linear_object_archived",
            f"Linear object {object_id} is archived at {archived_at}",
        )
    return value


def _issue_filter(
    *,
    team_id: str | None,
    project_id: str | None,
    state_id: str | None,
    assignee_id: str | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if team_id:
        filters["team"] = {"id": {"eq": team_id}}
    if project_id:
        filters["project"] = {"id": {"eq": project_id}}
    if state_id:
        filters["state"] = {"id": {"eq": state_id}}
    if assignee_id:
        filters["assignee"] = {"id": {"eq": assignee_id}}
    return filters


def _compact_team(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "key": _string_or_none(node.get("key")),
        "name": _string_or_none(node.get("name")),
        "description": _string_or_none(node.get("description")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_user(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "name": _string_or_none(node.get("name")),
        "display_name": _string_or_none(node.get("displayName")),
        "email": _string_or_none(node.get("email")),
        "active": _bool_or_none(node.get("active")),
        "admin": _bool_or_none(node.get("admin")),
        "guest": _bool_or_none(node.get("guest")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_issue_status(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "name": _string_or_none(node.get("name")),
        "type": _string_or_none(node.get("type")),
        "description": _string_or_none(node.get("description")),
        "color": _string_or_none(node.get("color")),
        "position": _number_or_none(node.get("position")),
        "team": _named_object(node.get("team"), ("id", "key", "name")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_issue_label(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "name": _string_or_none(node.get("name")),
        "description": _string_or_none(node.get("description")),
        "color": _string_or_none(node.get("color")),
        "is_group": _bool_or_none(node.get("isGroup")),
        "team": _named_object(node.get("team"), ("id", "key", "name")),
        "parent": _named_object(node.get("parent"), ("id", "name")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_project(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "name": _string_or_none(node.get("name")),
        "description": _string_or_none(node.get("description")),
        "content": _bounded_text(node.get("content"), 4000),
        "url": _string_or_none(node.get("url")),
        "state": _string_or_none(node.get("state")),
        "start_date": _string_or_none(node.get("startDate")),
        "target_date": _string_or_none(node.get("targetDate")),
        "lead": _named_object(node.get("lead"), ("id", "name")),
        "teams": _compact_nested_nodes(node.get("teams"), ("id", "key", "name")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_issue(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "identifier": _string_or_none(node.get("identifier")),
        "title": _string_or_none(node.get("title")),
        "description": _bounded_text(node.get("description"), 4000),
        "url": _string_or_none(node.get("url")),
        "priority": _number_or_none(node.get("priority")),
        "status": _named_object(node.get("state"), ("id", "name", "type")),
        "team": _named_object(node.get("team"), ("id", "key", "name")),
        "project": _named_object(node.get("project"), ("id", "name")),
        "assignee": _named_object(node.get("assignee"), ("id", "name")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_comment(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "body": _bounded_text(node.get("body"), 4000),
        "url": _string_or_none(node.get("url")),
        "author": _named_object(node.get("user"), ("id", "name")),
        "issue": _named_object(node.get("issue"), ("id", "identifier", "title", "url")),
        "parent": _named_object(node.get("parent"), ("id", "url")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_agent_session(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "url": _string_or_none(node.get("url")),
        "status": _string_or_none(node.get("status")),
        "summary": _bounded_text(node.get("summary"), 1000),
        "context": node.get("context") if isinstance(node.get("context"), (dict, list)) else None,
        "app_user": _named_object(node.get("appUser"), ("id", "name")),
        "creator": _named_object(node.get("creator"), ("id", "name")),
        "issue": _named_object(node.get("issue"), ("id", "identifier", "title", "url")),
        "comment": _compact_comment_ref(node.get("comment")),
        "source_comment": _compact_comment_ref(node.get("sourceComment")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
        "started_at": _string_or_none(node.get("startedAt")),
        "ended_at": _string_or_none(node.get("endedAt")),
    }


def _compact_agent_activity(node: Mapping[str, Any]) -> dict[str, Any]:
    content = node.get("content")
    content_payload = dict(content) if isinstance(content, Mapping) else {}
    for key in ("body", "result"):
        if key in content_payload:
            content_payload[key] = _bounded_text(content_payload[key], 4000)
    return {
        "id": _string_or_none(node.get("id")),
        "signal": _string_or_none(node.get("signal")),
        "content": content_payload,
        "author": _named_object(node.get("user"), ("id", "name")),
        "source_comment": _named_object(node.get("sourceComment"), ("id", "url")),
        "agent_session": _named_object(node.get("agentSession"), ("id", "url")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_document(node: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _string_or_none(node.get("id")),
        "slug_id": _string_or_none(node.get("slugId")),
        "title": _string_or_none(node.get("title")),
        "summary": _bounded_text(node.get("summary"), 1000),
        "content": _bounded_text(node.get("content"), 4000),
        "url": _string_or_none(node.get("url")),
        "project": _named_object(node.get("project"), ("id", "name", "url")),
        "issue": _named_object(node.get("issue"), ("id", "identifier", "title", "url")),
        "team": _named_object(node.get("team"), ("id", "key", "name")),
        "creator": _named_object(node.get("creator"), ("id", "name")),
        "updated_by": _named_object(node.get("updatedBy"), ("id", "name")),
        "created_at": _string_or_none(node.get("createdAt")),
        "updated_at": _string_or_none(node.get("updatedAt")),
    }


def _compact_comment_ref(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "id": _string_or_none(value.get("id")),
        "url": _string_or_none(value.get("url")),
        "body": _bounded_text(value.get("body"), 1000),
        "author": _named_object(value.get("user"), ("id", "name")),
        "created_at": _string_or_none(value.get("createdAt")),
        "updated_at": _string_or_none(value.get("updatedAt")),
    }


def _compact_nested_nodes(value: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    nodes = value.get("nodes") if isinstance(value, Mapping) else None
    if not isinstance(nodes, list):
        return []
    compacted = [_named_object(node, fields) for node in nodes if isinstance(node, Mapping)]
    return [item for item in compacted if item is not None]


def _named_object(value: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {field: _string_or_none(value.get(field)) for field in fields}


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) <= limit:
        return value
    return value[: limit - len("...[truncated]")] + "...[truncated]"
