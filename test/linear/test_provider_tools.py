"""Tests for CAO-mediated Linear provider tools."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Mapping

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.provider_tools import (
    CREATE_COMMENT_TOOL,
    CREATE_ISSUE_TOOL,
    GET_AGENT_SESSION_ACTIVITY_TOOL,
    GET_AGENT_SESSION_TOOL,
    GET_COMMENT_TOOL,
    GET_DOCUMENT_TOOL,
    GET_ISSUE_LABEL_TOOL,
    GET_ISSUE_STATUS_TOOL,
    GET_ISSUE_TOOL,
    GET_PROJECT_TOOL,
    GET_TEAM_TOOL,
    GET_USER_TOOL,
    LINEAR_EXPLORATION_READ_TOOLS,
    LINEAR_PROVIDER_TOOLS,
    LIST_AGENT_SESSION_ACTIVITIES_TOOL,
    LIST_COMMENTS_TOOL,
    LIST_DOCUMENTS_TOOL,
    LIST_ISSUE_LABELS_TOOL,
    LIST_ISSUE_STATUSES_TOOL,
    LIST_ISSUES_TOOL,
    LIST_PROJECTS_TOOL,
    LIST_TEAMS_TOOL,
    LIST_USERS_TOOL,
    SEARCH_DOCUMENTS_TOOL,
    SEARCH_ISSUES_TOOL,
    UPDATE_ISSUE_FIELDS,
    UPDATE_ISSUE_TOOL,
)
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
    LinearWorkspaceProviderConfigError,
)
from cli_agent_orchestrator.mcp_server.provider_tools import (
    register_provider_mediated_mcp_tools,
)
from cli_agent_orchestrator.workspace_providers.invocation import (
    ProviderMediatedToolAccessDenied,
    ProviderMediatedToolHandlerError,
    ProviderMediatedToolInvocationService,
)
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderToolAccessConfigError,
)

# The mocked Linear issue/comment payloads mirror the GraphQL object shape used
# by Linear's official developer docs and schema explorer. See the contract note
# beside the production queries in ``linear.provider_tools``.


def test_provider_tools_imports_without_workspace_provider_import_order():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import cli_agent_orchestrator.linear.provider_tools",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _agents() -> AgentIdentityRegistry:
    return AgentIdentityRegistry(
        {
            "implementation_partner": AgentIdentity(
                id="implementation_partner",
                display_name="Implementation Partner",
                agent_profile="developer",
                cli_provider="codex",
                workdir="/repo",
                session_name="implementation-partner",
            ),
            "discovery_partner": AgentIdentity(
                id="discovery_partner",
                display_name="Discovery Partner",
                agent_profile="reviewer",
                cli_provider="codex",
                workdir="/other",
                session_name="discovery-partner",
            ),
        }
    )


def _linear_config(tmp_path, body: str):
    path = tmp_path / "workspace-providers" / "linear.toml"
    path.parent.mkdir(parents=True)
    path.write_text(body)
    return path


def _provider(tmp_path, tool_access_body: str) -> LinearWorkspaceProvider:
    config = _linear_config(
        tmp_path,
        f"""
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
access_token = "access-token"

[presences.discovery_partner]
agent_id = "discovery_partner"
app_key = "discovery_partner"
access_token = "discovery-token"

{tool_access_body}
""",
    )
    provider = LinearWorkspaceProvider(
        agent_registry=_agents(),
        config_path=config,
        preflight_credentials=False,
    )
    provider.initialize()
    return provider


def _terminal_metadata(terminal_id: str) -> Mapping[str, Any] | None:
    return {
        "terminal-impl": {
            "id": "terminal-impl",
            "agent_identity_id": "implementation_partner",
        },
        "terminal-discovery": {
            "id": "terminal-discovery",
            "agent_identity_id": "discovery_partner",
        },
        "raw-terminal": {"id": "raw-terminal", "agent_identity_id": None},
    }.get(terminal_id)


def _mcp_for_provider(provider: LinearWorkspaceProvider, terminal_id: str):
    policy = provider.provider_tool_access()
    mcp = FastMCP(f"linear-tools-{terminal_id}", mask_error_details=False)
    registered = register_provider_mediated_mcp_tools(
        terminal_id=terminal_id,
        mcp_instance=mcp,
        policies={"linear": policy},
        agent_registry=_agents(),
        terminal_metadata_resolver=_terminal_metadata,
    )
    return mcp, registered


def _linear_reference_payload(object_id: str | None) -> dict[str, Any]:
    node = {"id": object_id} if object_id else None
    return {
        "data": {
            "project": node,
            "workflowState": node,
            "user": node,
            "issueLabel": node,
        }
    }


def test_linear_provider_tool_schemas_are_codex_compatible(tmp_path):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_all]
agent_id = "implementation_partner"
tools = {json.dumps(sorted(LINEAR_PROVIDER_TOOLS))}
issues = ["CAO-28"]
create_team_ids = ["team-cao"]
create_project_ids = ["project-smoke"]
create_parent_issues = ["CAO-28"]
allow_top_level_create = true
update_fields = {json.dumps(sorted(UPDATE_ISSUE_FIELDS))}
""",
    )
    policy = provider.provider_tool_access()

    forbidden_top_level_keywords = {"anyOf", "oneOf", "allOf", "enum", "not"}
    assert set(policy.tools) == LINEAR_PROVIDER_TOOLS
    for tool in policy.tools.values():
        assert tool.input_schema.get("type") == "object"
        assert not forbidden_top_level_keywords.intersection(tool.input_schema)


def test_linear_provider_tools_include_runtime_generation_material(tmp_path):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_all]
agent_id = "implementation_partner"
tools = {json.dumps(sorted(LINEAR_PROVIDER_TOOLS))}
issues = ["CAO-28"]
create_team_ids = ["team-cao"]
create_project_ids = ["project-smoke"]
create_parent_issues = ["CAO-28"]
allow_top_level_create = true
update_fields = {json.dumps(sorted(UPDATE_ISSUE_FIELDS))}
""",
    )

    policy = provider.provider_tool_access()

    for tool in policy.tools.values():
        material = tool.runtime_generation
        assert material["schema_version"] == "cao-linear-mcp-tool-runtime-generation.v1"
        assert material["tool_name"] == tool.name
        assert material["handler"]["schema_version"] == "cao-callable-runtime-fingerprint.v1"
        assert material["handler"]["entries"]
        assert all(len(entry["sha256"]) == 64 for entry in material["handler"]["entries"])

    list_teams_material = policy.tools[LIST_TEAMS_TOOL].runtime_generation
    assert list_teams_material["constants"]["values"] == {
        "APP_KEY_PATTERN": "[^A-Za-z0-9]+",
        "DEFAULT_LINEAR_POLICY_REASON": (
            "This agent is configured to not have access to that Linear target or operation."
        ),
        "DEFAULT_LIST_LIMIT": 50,
        "LINEAR_GRAPHQL_URL": "https://api.linear.app/graphql",
        "LINEAR_TOKEN_URL": "https://api.linear.app/oauth/token",
        "MAX_LIST_LIMIT": 100,
        "TOKEN_REFRESH_SKEW_SECONDS": 300.0,
    }
    list_teams_handler_entries = {
        (entry["module"], entry["qualname"]) for entry in list_teams_material["handler"]["entries"]
    }
    assert (
        "cli_agent_orchestrator.linear.provider_tools",
        "LinearToolProvider._list_teams",
    ) in list_teams_handler_entries
    list_teams_query_entries = {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["linear_query"]["entries"]
    }
    assert (
        "cli_agent_orchestrator.linear.provider_tool_queries",
        "list_teams",
    ) in list_teams_query_entries
    assert (
        "cli_agent_orchestrator.linear.app_client",
        "linear_graphql",
    ) in list_teams_query_entries
    assert "app_client.access_token_for_app_key" in list_teams_material["dependencies"]
    list_teams_refresh_entries = {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["app_client.refresh_access_token"][
            "entries"
        ]
    }
    assert (
        "cli_agent_orchestrator.linear.app_client",
        "refresh_access_token",
    ) in list_teams_refresh_entries
    assert (
        "cli_agent_orchestrator.linear.workspace_provider",
        "persist_linear_oauth_install",
    ) in list_teams_refresh_entries
    assert (
        "cli_agent_orchestrator.linear.app_client",
        "required_linear_app_env",
    ) in {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["app_client.required_linear_app_env"][
            "entries"
        ]
    }
    assert (
        "cli_agent_orchestrator.linear.workspace_provider",
        "required_linear_app_env",
    ) in {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["app_client.required_linear_app_env"][
            "entries"
        ]
    }
    assert (
        "cli_agent_orchestrator.linear.app_client",
        "linear_env",
    ) in {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["app_client.linear_env"]["entries"]
    }
    assert {
        "linear_provider.required_linear_app_env",
        "linear_provider.linear_app_env",
        "linear_provider.app_env_prefix",
        "linear_provider.normalize_app_key",
        "linear_provider.persist_linear_oauth_install",
        "linear_provider.update_linear_presence_tokens",
        "linear_provider.LinearProviderConfig.presence_by_app_key",
    }.issubset(list_teams_material["dependencies"])
    assert (
        "cli_agent_orchestrator.linear.workspace_provider",
        "linear_app_env",
    ) in {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["linear_provider.linear_app_env"][
            "entries"
        ]
    }
    assert (
        "cli_agent_orchestrator.linear.workspace_provider",
        "update_linear_presence_tokens",
    ) in {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"][
            "linear_provider.update_linear_presence_tokens"
        ]["entries"]
    }
    assert (
        "cli_agent_orchestrator.linear.provider_tools",
        "_list_query_request",
    ) in {
        (entry["module"], entry["qualname"])
        for entry in list_teams_material["dependencies"]["_list_query_request"]["entries"]
    }
    assert "_validated_exploration_request" in list_teams_material["dependencies"]

    get_issue_material = policy.tools[GET_ISSUE_TOOL].runtime_generation
    get_issue_dependencies = set(get_issue_material["dependencies"])
    assert {
        "LinearToolProvider._authorized_issue_request",
        "LinearToolProvider._presence_for_identity",
        "LinearToolProvider._require_returned_issue_allowed",
        "_fetch_issue",
        "_issue_from_payload",
        "_compact_issue_payload",
    }.issubset(get_issue_dependencies)

    update_issue_dependencies = set(
        policy.tools[UPDATE_ISSUE_TOOL].runtime_generation["dependencies"]
    )
    assert policy.tools[UPDATE_ISSUE_TOOL].runtime_generation["constants"]["values"][
        "UPDATE_ISSUE_FIELDS"
    ] == sorted(UPDATE_ISSUE_FIELDS)
    assert {
        "LinearToolProvider._validated_update_issue_request",
        "LinearToolProvider._require_parent_issue_allowed",
    }.issubset(update_issue_dependencies)
    assert "_fetch_team" not in update_issue_dependencies


def _issue_payload(
    *,
    id: str = "issue-28",
    identifier: str = "CAO-28",
    archived_at: str | None = None,
    description: str = "Expose read-only Linear context.",
) -> dict[str, Any]:
    return {
        "id": id,
        "identifier": identifier,
        "title": "Add read-only CAO-mediated Linear MCP tools",
        "description": description,
        "url": "https://linear.app/yards-framework/issue/CAO-28/example",
        "createdAt": "2026-05-06T09:03:14.941Z",
        "updatedAt": "2026-05-09T02:41:53.100Z",
        "archivedAt": archived_at,
        "state": {"name": "In Progress", "type": "started"},
        "team": {"key": "CAO", "name": "CAO"},
        "project": {"name": "Linear-backed CAO agent bridge"},
        "assignee": {"name": "Implementation Partner"},
    }


def _comments_payload() -> dict[str, Any]:
    return {
        **_issue_payload(),
        "comments": {
            "nodes": [
                {
                    "id": "comment-2",
                    "body": "Second useful note.",
                    "createdAt": "2026-05-08T10:00:00.000Z",
                    "updatedAt": "2026-05-08T10:01:00.000Z",
                    "user": {"id": "user-2", "name": "AJ"},
                },
                {
                    "id": "comment-1",
                    "body": "First useful note.",
                    "createdAt": "2026-05-07T10:00:00.000Z",
                    "updatedAt": "2026-05-07T10:01:00.000Z",
                    "user": {"id": "user-1", "name": "RJ Wilson"},
                },
            ]
        },
    }


def _created_comment_payload() -> dict[str, Any]:
    return {
        "id": "comment-created",
        "url": "https://linear.app/yards-framework/issue/CAO-50/example#comment-created",
        "body": "Implementation complete.",
        "createdAt": "2026-05-09T04:10:00.000Z",
        "updatedAt": "2026-05-09T04:10:00.000Z",
        "issue": {
            "id": "issue-50",
            "identifier": "CAO-50",
            "url": "https://linear.app/yards-framework/issue/CAO-50/example",
        },
    }


def _teams_payload() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "team-cao", "key": "CAO", "name": "CAO"},
            {"id": "team-yards", "key": "YARDS", "name": "Yards"},
        ]
    }


def _users_payload() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "user-1",
                "name": "RJ Wilson",
                "displayName": "RJ Wilson",
                "email": "rj@example.test",
                "active": True,
                "admin": False,
                "guest": False,
                "createdAt": "2026-05-01T00:00:00.000Z",
                "updatedAt": "2026-05-02T00:00:00.000Z",
            }
        ]
    }


def _issue_status_payload() -> dict[str, Any]:
    return {
        "id": "status-started",
        "name": "In Progress",
        "type": "started",
        "description": "Work has started.",
        "color": "#f2c94c",
        "position": 2,
        "createdAt": "2026-05-01T00:00:00.000Z",
        "updatedAt": "2026-05-02T00:00:00.000Z",
        "team": {"id": "team-cao", "key": "CAO", "name": "CAO"},
    }


def _issue_label_payload() -> dict[str, Any]:
    return {
        "id": "label-provider",
        "name": "provider",
        "description": "Provider work",
        "color": "#36c",
        "isGroup": False,
        "createdAt": "2026-05-01T00:00:00.000Z",
        "updatedAt": "2026-05-02T00:00:00.000Z",
        "team": {"id": "team-cao", "key": "CAO", "name": "CAO"},
        "parent": {"id": "label-area", "name": "area"},
    }


def _project_payload() -> dict[str, Any]:
    return {
        "id": "project-bridge",
        "name": "Linear-backed CAO agent bridge",
        "description": "Bridge project.",
        "content": "Project notes.",
        "url": "https://linear.app/yards-framework/project/bridge",
        "state": "started",
        "startDate": "2026-05-01",
        "targetDate": "2026-05-30",
        "createdAt": "2026-05-01T00:00:00.000Z",
        "updatedAt": "2026-05-02T00:00:00.000Z",
        "lead": {"id": "user-1", "name": "RJ Wilson"},
        "teams": {"nodes": [{"id": "team-cao", "key": "CAO", "name": "CAO"}]},
    }


def _agent_session_payload() -> dict[str, Any]:
    return {
        "id": "agent-session-1",
        "url": "https://linear.app/yards-framework/issue/CAO-54#agent-session-1",
        "status": "working",
        "summary": "Testing session",
        "context": {"issue": "CAO-54"},
        "createdAt": "2026-05-07T10:00:00.000Z",
        "updatedAt": "2026-05-07T10:01:00.000Z",
        "startedAt": "2026-05-07T10:00:00.000Z",
        "endedAt": None,
        "issue": {"id": "issue-54", "identifier": "CAO-54", "title": "Tools", "url": "url"},
        "comment": {
            "id": "comment-1",
            "url": "comment-url",
            "body": "Mentioned you.",
            "createdAt": "2026-05-07T10:00:00.000Z",
            "updatedAt": "2026-05-07T10:00:00.000Z",
            "user": {"id": "user-1", "name": "RJ Wilson"},
        },
        "sourceComment": {
            "id": "comment-1",
            "url": "comment-url",
            "body": "Mentioned you.",
            "createdAt": "2026-05-07T10:00:00.000Z",
            "updatedAt": "2026-05-07T10:00:00.000Z",
            "user": {"id": "user-1", "name": "RJ Wilson"},
        },
        "appUser": {"id": "app-user-1", "name": "Discovery Partner"},
        "creator": {"id": "user-1", "name": "RJ Wilson"},
    }


def _agent_activity_payload() -> dict[str, Any]:
    return {
        "id": "activity-1",
        "signal": "prompt",
        "createdAt": "2026-05-07T10:00:00.000Z",
        "updatedAt": "2026-05-07T10:00:00.000Z",
        "user": {"id": "user-1", "name": "RJ Wilson"},
        "sourceComment": {"id": "comment-1", "url": "comment-url"},
        "agentSession": {"id": "agent-session-1", "url": "session-url"},
        "content": {"type": "prompt", "body": "testing"},
    }


def _document_payload() -> dict[str, Any]:
    return {
        "id": "document-1",
        "slugId": "doc-1",
        "title": "Planning document",
        "summary": "Plan summary",
        "content": "Plan body",
        "url": "https://linear.app/yards-framework/document/doc-1",
        "createdAt": "2026-05-07T10:00:00.000Z",
        "updatedAt": "2026-05-07T10:00:00.000Z",
        "project": {"id": "project-bridge", "name": "Bridge", "url": "project-url"},
        "issue": {"id": "issue-54", "identifier": "CAO-54", "title": "Tools", "url": "url"},
        "team": {"id": "team-cao", "key": "CAO", "name": "CAO"},
        "creator": {"id": "user-1", "name": "RJ Wilson"},
        "updatedBy": {"id": "user-1", "name": "RJ Wilson"},
    }


def _mutated_issue_payload(
    *,
    id: str = "issue-51",
    identifier: str = "CAO-51",
    title: str = "Add governed Linear issue mutation write tools",
) -> dict[str, Any]:
    return {
        "id": id,
        "identifier": identifier,
        "title": title,
        "url": f"https://linear.app/yards-framework/issue/{identifier.lower()}/example",
        "state": {"name": "Todo", "type": "unstarted"},
        "team": {"key": "CAO", "name": "CAO"},
        "project": {"name": "Linear-backed CAO agent bridge"},
    }


def _service(provider: LinearWorkspaceProvider) -> ProviderMediatedToolInvocationService:
    return ProviderMediatedToolInvocationService(
        policies={"linear": provider.provider_tool_access()},
        agent_registry=_agents(),
        terminal_metadata_resolver=_terminal_metadata,
    )


@pytest.mark.asyncio
async def test_linear_create_issue_tool_registers_and_creates_authorized_subissue(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_create]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["CAO"]
create_project_ids = ["project-bridge"]
create_parent_issues = ["CAO-25", "parent-25"]
""",
    )
    calls: list[dict[str, Any]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        calls.append({"query": query, "variables": variables, "app_key": app_key})
        assert app_key == "implementation_partner"
        if "CaoLinearTeams" in query:
            assert variables == {}
            return {"data": {"teams": _teams_payload()}}
        if "issueCreate" in query:
            assert variables == {
                "input": {
                    "teamId": "team-cao",
                    "title": "Governed mutation task",
                    "projectId": "project-bridge",
                    "parentId": "parent-25",
                    "priority": 2,
                }
            }
            return {"data": {"issueCreate": {"success": True, "issue": _mutated_issue_payload()}}}
        if "CaoLinearReference" in query:
            return _linear_reference_payload(variables["id"])
        assert variables == {"id": "CAO-25"}
        return {"data": {"issue": _issue_payload(id="parent-25", identifier="CAO-25")}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    # Given the Linear provider grants issue creation only under an authorized parent.
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    # When the identity-managed terminal creates a governed sub-issue.
    result = await mcp.call_tool(
        CREATE_ISSUE_TOOL,
        {
            "team_id": "CAO",
            "title": "Governed mutation task",
            "project_id": "project-bridge",
            "parent_issue": "CAO-25",
            "priority": 2,
        },
    )

    # Then the provider resolves/validates references before issuing a compact success result.
    payload = json.loads(result.content[0].text)
    assert registered == [CREATE_ISSUE_TOOL]
    assert payload == {
        "status": "created",
        "id": "issue-51",
        "identifier": "CAO-51",
        "title": "Add governed Linear issue mutation write tools",
        "url": "https://linear.app/yards-framework/issue/cao-51/example",
        "team": {"key": "CAO", "name": "CAO"},
        "project": {"name": "Linear-backed CAO agent bridge"},
        "state": {"name": "Todo", "type": "unstarted"},
        "changed_fields": ["parent_issue", "priority", "project_id", "team_id", "title"],
    }
    assert ["issueCreate" in call["query"] for call in calls] == [False, False, False, True]


@pytest.mark.asyncio
async def test_linear_update_issue_tool_registers_and_updates_authorized_fields(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_update]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51", "issue-51"]
create_parent_issues = ["CAO-25", "parent-25"]
update_fields = ["title", "state_id", "parent_issue", "label_ids"]
""",
    )
    calls: list[dict[str, Any]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        calls.append({"query": query, "variables": variables})
        if "issueUpdate" in query:
            assert variables == {
                "id": "issue-51",
                "input": {
                    "title": "Updated governed mutation task",
                    "stateId": "state-started",
                    "parentId": "parent-25",
                    "labelIds": ["label-work"],
                },
            }
            return {
                "data": {
                    "issueUpdate": {
                        "success": True,
                        "issue": _mutated_issue_payload(
                            title="Updated governed mutation task",
                        ),
                    }
                }
            }
        if "CaoLinearReference" in query:
            return _linear_reference_payload(variables["id"])
        if variables == {"id": "CAO-25"}:
            return {"data": {"issue": _issue_payload(id="parent-25", identifier="CAO-25")}}
        assert variables == {"id": "CAO-51"}
        return {"data": {"issue": _mutated_issue_payload()}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    result = await mcp.call_tool(
        UPDATE_ISSUE_TOOL,
        {
            "issue": "CAO-51",
            "title": "Updated governed mutation task",
            "state_id": "state-started",
            "parent_issue": "CAO-25",
            "label_ids": ["label-work"],
        },
    )

    payload = json.loads(result.content[0].text)
    assert registered == [UPDATE_ISSUE_TOOL]
    assert payload["status"] == "updated"
    assert payload["id"] == "issue-51"
    assert payload["changed_fields"] == ["label_ids", "parent_issue", "state_id", "title"]
    assert ["issueUpdate" in call["query"] for call in calls] == [
        False,
        False,
        False,
        False,
        True,
    ]


@pytest.mark.parametrize(
    ("tool_access_body", "arguments", "expected"),
    (
        (
            f"""
[tool_access.implementation_partner_issue_create]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
""",
            {"team_id": "team-other", "title": "Denied"},
            "unauthorized_linear_team",
        ),
        (
            f"""
[tool_access.implementation_partner_issue_create]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["team-cao"]
create_parent_issues = ["CAO-25"]
""",
            {"team_id": "team-cao", "title": "Denied", "parent_issue": "CAO-52"},
            "unauthorized_linear_parent_issue",
        ),
        (
            f"""
[tool_access.implementation_partner_issue_create]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["team-cao"]
create_project_ids = ["project-bridge"]
allow_top_level_create = true
""",
            {"team_id": "team-cao", "title": "Denied", "project_id": "project-other"},
            "unauthorized_linear_project",
        ),
        (
            f"""
[tool_access.implementation_partner_issue_update]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
create_project_ids = ["project-bridge"]
update_fields = ["project_id"]
""",
            {"issue": "CAO-51", "project_id": "project-other"},
            "unauthorized_linear_project",
        ),
        (
            f"""
[tool_access.implementation_partner_issue_update]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
create_parent_issues = ["CAO-25"]
update_fields = ["parent_issue"]
""",
            {"issue": "CAO-51", "parent_issue": "CAO-52"},
            "unauthorized_linear_parent_issue",
        ),
        (
            f"""
[tool_access.implementation_partner_issue_update]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
update_fields = ["title"]
""",
            {"issue": "CAO-52", "title": "Denied"},
            "unauthorized_linear_issue",
        ),
        (
            f"""
[tool_access.implementation_partner_issue_update]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
update_fields = ["title"]
""",
            {"issue": "CAO-51", "description": "Denied"},
            "unauthorized_linear_update_field",
        ),
    ),
)
def test_linear_issue_mutation_tools_reject_unauthorized_targets_before_graphql(
    tmp_path,
    monkeypatch,
    tool_access_body,
    arguments,
    expected,
):
    provider = _provider(tmp_path, tool_access_body)
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )
    tool_name = CREATE_ISSUE_TOOL if "team_id" in arguments else UPDATE_ISSUE_TOOL

    with pytest.raises(ProviderMediatedToolAccessDenied, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=tool_name,
            arguments=arguments,
        )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    (
        ({"team_id": "team-cao", "title": "   "}, "invalid_linear_issue_title"),
        (
            {"team_id": "team-cao", "title": "Bad labels", "label_ids": [""]},
            "invalid_linear_label_ids",
        ),
        (
            {"team_id": "team-cao", "title": "Bad priority", "priority": 9},
            "invalid_linear_priority",
        ),
        (
            {"team_id": "team-cao", "title": "Bad priority", "priority": "2"},
            "invalid_linear_priority",
        ),
        (
            {"team_id": "team-cao", "title": "Unknown", "raw_passthrough": True},
            "invalid_linear_create_issue_field",
        ),
    ),
)
def test_linear_create_issue_tool_rejects_invalid_fields_before_graphql(
    tmp_path,
    monkeypatch,
    arguments,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_create]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    with pytest.raises(ProviderMediatedToolAccessDenied, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_ISSUE_TOOL,
            arguments=arguments,
        )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    (
        ({"issue": "CAO-51", "title": "   "}, "invalid_linear_issue_title"),
        ({"issue": "CAO-51", "label_ids": [""]}, "invalid_linear_label_ids"),
        ({"issue": "CAO-51", "priority": 2.2}, "invalid_linear_priority"),
        ({"issue": "CAO-51", "raw_passthrough": True}, "invalid_linear_update_issue_field"),
    ),
)
def test_linear_update_issue_tool_rejects_invalid_fields_before_graphql(
    tmp_path,
    monkeypatch,
    arguments,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_update]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
update_fields = ["title", "label_ids", "priority"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    with pytest.raises(ProviderMediatedToolAccessDenied, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=UPDATE_ISSUE_TOOL,
            arguments=arguments,
        )


def test_linear_issue_mutation_tools_reject_invalid_references_before_mutation(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_create]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
""",
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        assert "issueCreate" not in query
        if "CaoLinearTeams" in query:
            return {"data": {"teams": _teams_payload()}}
        assert "CaoLinearReference" in query
        return _linear_reference_payload(None)

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    with pytest.raises(ProviderMediatedToolHandlerError, match="invalid_linear_reference"):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_ISSUE_TOOL,
            arguments={
                "team_id": "team-cao",
                "title": "Invalid ref",
                "state_id": "missing-state",
            },
        )


@pytest.mark.parametrize("terminal_id", ("terminal-discovery", "raw-terminal", "missing"))
def test_linear_issue_mutation_tools_fail_closed_for_unmapped_or_unauthorized_terminals(
    tmp_path,
    terminal_id,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_mutations]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}", "{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
update_fields = ["title"]
""",
    )

    _mcp, registered = _mcp_for_provider(provider, terminal_id)

    assert registered == []
    with pytest.raises(ProviderMediatedToolAccessDenied):
        _service(provider).invoke(
            terminal_id=terminal_id,
            provider_name="linear",
            tool_name=CREATE_ISSUE_TOOL,
            arguments={"team_id": "team-cao", "title": "Denied"},
        )


@pytest.mark.parametrize(
    ("tool_name", "arguments", "presence_patch", "expected"),
    (
        (
            CREATE_ISSUE_TOOL,
            {"team_id": "team-cao", "title": "Credential check"},
            {"access_token": None, "refresh_token": None},
            "linear_credentials_missing",
        ),
        (
            UPDATE_ISSUE_TOOL,
            {"issue": "CAO-51", "title": "Credential check"},
            {
                "access_token": "expired-token",
                "refresh_token": None,
                "token_expires_at": "2026-05-01T00:00:00+00:00",
            },
            "linear_credentials_expired",
        ),
    ),
)
def test_linear_issue_mutation_tools_report_missing_or_expired_credentials_before_graphql(
    tmp_path,
    monkeypatch,
    tool_name,
    arguments,
    presence_patch,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_mutations]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}", "{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
update_fields = ["title"]
""",
    )
    config = provider.config
    assert config is not None
    presence = config.presences["implementation_partner"]
    config.presences["implementation_partner"] = type(presence)(
        **{**presence.__dict__, **presence_patch}
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=tool_name,
            arguments=arguments,
        )


@pytest.mark.parametrize(
    ("tool_name", "mutation_response", "raised", "expected"),
    (
        (
            CREATE_ISSUE_TOOL,
            {"data": {"issueCreate": {"success": False, "issue": None}}},
            None,
            "linear_issueCreate_failed",
        ),
        (
            UPDATE_ISSUE_TOOL,
            None,
            RuntimeError("Linear GraphQL request failed: upstream exploded"),
            "linear_api_failure",
        ),
    ),
)
def test_linear_issue_mutation_tools_report_provider_api_failures(
    tmp_path,
    monkeypatch,
    tool_name,
    mutation_response,
    raised,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_issue_mutations]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}", "{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51", "issue-51"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
update_fields = ["title"]
""",
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        if "CaoLinearTeams" in query:
            return {"data": {"teams": _teams_payload()}}
        if "issueCreate" in query or "issueUpdate" in query:
            if raised is not None:
                raise raised
            return mutation_response
        if "CaoLinearReference" in query:
            return _linear_reference_payload(variables["id"])
        return {"data": {"issue": _mutated_issue_payload()}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)
    arguments = (
        {"team_id": "team-cao", "title": "Failure path"}
        if tool_name == CREATE_ISSUE_TOOL
        else {"issue": "CAO-51", "title": "Failure path"}
    )

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=tool_name,
            arguments=arguments,
        )


@pytest.mark.asyncio
async def test_linear_comment_tool_registers_and_creates_authorized_comment(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50", "issue-50"]
""",
    )
    calls: list[dict[str, Any]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        calls.append({"query": query, "variables": variables, "app_key": app_key})
        assert app_key == "implementation_partner"
        if "commentCreate" in query:
            assert variables == {
                "input": {"issueId": "issue-50", "body": "  Implementation complete.  "}
            }
            return {
                "data": {"commentCreate": {"success": True, "comment": _created_comment_payload()}}
            }
        assert variables == {"id": "CAO-50"}
        return {"data": {"issue": _issue_payload(id="issue-50", identifier="CAO-50")}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    # Given the Linear provider grants comment-write access to one issue.
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    # When the identity-managed terminal creates a comment on that issue.
    result = await mcp.call_tool(
        CREATE_COMMENT_TOOL,
        {"issue": "CAO-50", "body": "  Implementation complete.  "},
    )

    # Then the governed write tool is registered and returns a compact success payload.
    payload = json.loads(result.content[0].text)
    assert registered == [CREATE_COMMENT_TOOL]
    assert payload == {
        "status": "created",
        "id": "comment-created",
        "url": "https://linear.app/yards-framework/issue/CAO-50/example#comment-created",
        "issue": {
            "id": "issue-50",
            "identifier": "CAO-50",
            "url": "https://linear.app/yards-framework/issue/CAO-50/example",
        },
        "created_at": "2026-05-09T04:10:00.000Z",
        "updated_at": "2026-05-09T04:10:00.000Z",
    }
    assert ["commentCreate" in call["query"] for call in calls] == [False, True]


@pytest.mark.asyncio
async def test_linear_comment_tool_creates_authorized_comment_from_issue_ref(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["issue-50"]
""",
    )
    calls: list[dict[str, Any]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        calls.append({"query": query, "variables": variables})
        if "commentCreate" in query:
            assert variables == {"input": {"issueId": "issue-50", "body": "Ref path."}}
            return {
                "data": {"commentCreate": {"success": True, "comment": _created_comment_payload()}}
            }
        assert variables == {"id": "issue-50"}
        return {"data": {"issue": _issue_payload(id="issue-50", identifier="CAO-50")}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    result = await mcp.call_tool(
        CREATE_COMMENT_TOOL,
        {
            "issue_ref": {"provider": "linear", "id": "issue-50"},
            "body": "Ref path.",
        },
    )

    assert registered == [CREATE_COMMENT_TOOL]
    assert json.loads(result.content[0].text)["id"] == "comment-created"
    assert ["commentCreate" in call["query"] for call in calls] == [False, True]


@pytest.mark.asyncio
async def test_linear_comment_tool_denies_unauthorized_issue_before_graphql(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50"]
reason = "Implementation Partner may only comment on assigned smoke issues."
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert registered == [CREATE_COMMENT_TOOL]
    with pytest.raises(ToolError) as exc_info:
        await mcp.call_tool(
            CREATE_COMMENT_TOOL,
            {"issue": "CAO-51", "body": "This should be denied."},
        )
    message = str(exc_info.value)
    assert "unauthorized_linear_issue" in message
    assert "'CAO-51' is not authorized by tool_access.implementation_partner_comments" in message
    assert "Implementation Partner may only comment on assigned smoke issues." in message
    with pytest.raises(ToolError, match="wrong_provider_ref"):
        await mcp.call_tool(
            CREATE_COMMENT_TOOL,
            {
                "issue_ref": {"provider": "github", "id": "CAO-50"},
                "body": "This should be denied.",
            },
        )


@pytest.mark.parametrize("body", ("", "   ", 123))
def test_linear_comment_tool_rejects_invalid_body_before_graphql(
    tmp_path,
    monkeypatch,
    body,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    with pytest.raises(ProviderMediatedToolAccessDenied, match="invalid_linear_comment_body"):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_COMMENT_TOOL,
            arguments={"issue": "CAO-50", "body": body},
        )


@pytest.mark.parametrize("terminal_id", ("terminal-discovery", "raw-terminal", "missing"))
def test_linear_comment_tool_fail_closed_for_unmapped_or_unauthorized_terminals(
    tmp_path,
    terminal_id,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50"]
""",
    )

    _mcp, registered = _mcp_for_provider(provider, terminal_id)

    assert registered == []
    with pytest.raises(ProviderMediatedToolAccessDenied):
        _service(provider).invoke(
            terminal_id=terminal_id,
            provider_name="linear",
            tool_name=CREATE_COMMENT_TOOL,
            arguments={"issue": "CAO-50", "body": "Denied."},
        )


@pytest.mark.parametrize(
    ("presence_patch", "expected"),
    (
        ({"access_token": None, "refresh_token": None}, "linear_credentials_missing"),
        (
            {
                "access_token": "expired-token",
                "refresh_token": None,
                "token_expires_at": "2026-05-01T00:00:00+00:00",
            },
            "linear_credentials_expired",
        ),
    ),
)
def test_linear_comment_tool_reports_missing_or_expired_credentials_before_graphql(
    tmp_path,
    monkeypatch,
    presence_patch,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50"]
""",
    )
    config = provider.config
    assert config is not None
    presence = config.presences["implementation_partner"]
    config.presences["implementation_partner"] = type(presence)(
        **{**presence.__dict__, **presence_patch}
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_COMMENT_TOOL,
            arguments={"issue": "CAO-50", "body": "Credential check."},
        )


@pytest.mark.parametrize(
    ("mutation_response", "raised", "expected"),
    (
        (
            {"data": {"commentCreate": {"success": False, "comment": None}}},
            None,
            "linear_comment_create_failed",
        ),
        (
            None,
            RuntimeError("Linear GraphQL request failed: upstream exploded"),
            "linear_api_failure",
        ),
    ),
)
def test_linear_comment_tool_reports_provider_api_failures(
    tmp_path,
    monkeypatch,
    mutation_response,
    raised,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50"]
""",
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        if "commentCreate" in query:
            if raised is not None:
                raise raised
            return mutation_response
        return {"data": {"issue": _issue_payload(id="issue-50", identifier="CAO-50")}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_COMMENT_TOOL,
            arguments={"issue": "CAO-50", "body": "Failure path."},
        )


@pytest.mark.parametrize(
    ("resolved_issue", "expected"),
    (
        (None, "linear_issue_not_found"),
        (
            _issue_payload(id="issue-50", identifier="CAO-50", archived_at="2026-05-01T00:00:00Z"),
            "linear_issue_archived",
        ),
        (_issue_payload(id="issue-51", identifier="CAO-51"), "linear_issue_outside_policy"),
    ),
)
def test_linear_comment_tool_resolves_issue_failures_before_mutation(
    tmp_path,
    monkeypatch,
    resolved_issue,
    expected,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50", "issue-50"]
""",
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        assert "commentCreate" not in query
        return {"data": {"issue": resolved_issue}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_COMMENT_TOOL,
            arguments={"issue": "CAO-50", "body": "Must not mutate."},
        )


def test_linear_comment_tool_rejects_mutation_success_without_comment_id(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_comments]
agent_id = "implementation_partner"
tools = ["{CREATE_COMMENT_TOOL}"]
issues = ["CAO-50"]
""",
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        if "commentCreate" in query:
            return {
                "data": {
                    "commentCreate": {
                        "success": True,
                        "comment": {"url": "https://linear.app/comment-without-id"},
                    }
                }
            }
        return {"data": {"issue": _issue_payload(id="issue-50", identifier="CAO-50")}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    with pytest.raises(ProviderMediatedToolHandlerError, match="linear_comment_create_failed"):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name=CREATE_COMMENT_TOOL,
            arguments={"issue": "CAO-50", "body": "No id."},
        )


@pytest.mark.asyncio
async def test_linear_comment_tool_leaves_read_only_tools_unaffected(tmp_path, monkeypatch):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_linear_tools]
agent_id = "implementation_partner"
tools = ["{GET_ISSUE_TOOL}", "{LIST_COMMENTS_TOOL}", "{CREATE_COMMENT_TOOL}", "{CREATE_ISSUE_TOOL}", "{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-28", "issue-28"]
create_team_ids = ["team-cao"]
allow_top_level_create = true
update_fields = ["title"]
""",
    )

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        assert "commentCreate" not in query
        assert "issueCreate" not in query
        assert "issueUpdate" not in query
        issue = _comments_payload() if "comments" in query else _issue_payload()
        return {"data": {"issue": issue}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    issue_result = await mcp.call_tool(GET_ISSUE_TOOL, {"issue": "CAO-28"})
    comments_result = await mcp.call_tool(LIST_COMMENTS_TOOL, {"issue": "CAO-28"})

    assert registered == [
        CREATE_COMMENT_TOOL,
        CREATE_ISSUE_TOOL,
        GET_ISSUE_TOOL,
        LIST_COMMENTS_TOOL,
        UPDATE_ISSUE_TOOL,
    ]
    assert json.loads(issue_result.content[0].text)["identifier"] == "CAO-28"
    assert json.loads(comments_result.content[0].text)["comments"][0]["id"] == "comment-1"


@pytest.mark.asyncio
async def test_linear_read_tools_register_and_fetch_authorized_issue_context(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue", "cao_linear.list_comments"]
issues = ["CAO-28", "issue-28"]
""",
    )
    calls: list[dict[str, Any]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        calls.append({"variables": variables, "app_key": app_key, "query": query})
        issue_id = variables["id"]
        assert issue_id in {"CAO-28", "issue-28"}
        issue = _comments_payload() if "comments" in query else _issue_payload()
        return {"data": {"issue": issue}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)

    # Given the Linear provider grants read-only issue access to one identity.
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    # When the identity-managed terminal calls both CAO-mediated Linear tools.
    issue_result = await mcp.call_tool("cao_linear.get_issue", {"issue": "CAO-28"})
    comments_result = await mcp.call_tool(
        "cao_linear.list_comments",
        {"issue_ref": {"provider": "linear", "id": "issue-28"}},
    )

    # Then only the normalized read tools are registered and bounded payloads are returned.
    assert registered == ["cao_linear.get_issue", "cao_linear.list_comments"]
    issue = json.loads(issue_result.content[0].text)
    assert issue == {
        "id": "issue-28",
        "identifier": "CAO-28",
        "title": "Add read-only CAO-mediated Linear MCP tools",
        "status": {"name": "In Progress", "type": "started"},
        "team": {"key": "CAO", "name": "CAO"},
        "project": {"name": "Linear-backed CAO agent bridge"},
        "assignee": {"name": "Implementation Partner"},
        "description": "Expose read-only Linear context.",
        "url": "https://linear.app/yards-framework/issue/CAO-28/example",
        "created_at": "2026-05-06T09:03:14.941Z",
        "updated_at": "2026-05-09T02:41:53.100Z",
    }
    comments = json.loads(comments_result.content[0].text)
    assert comments["issue"] == {"id": "issue-28", "identifier": "CAO-28"}
    assert comments["comments"] == [
        {
            "id": "comment-1",
            "body": "First useful note.",
            "author": {"id": "user-1", "name": "RJ Wilson"},
            "created_at": "2026-05-07T10:00:00.000Z",
            "updated_at": "2026-05-07T10:01:00.000Z",
        },
        {
            "id": "comment-2",
            "body": "Second useful note.",
            "author": {"id": "user-2", "name": "AJ"},
            "created_at": "2026-05-08T10:00:00.000Z",
            "updated_at": "2026-05-08T10:01:00.000Z",
        },
    ]
    assert [call["app_key"] for call in calls] == [
        "implementation_partner",
        "implementation_partner",
    ]


@pytest.mark.parametrize("terminal_id", ("terminal-discovery", "raw-terminal", "missing"))
def test_linear_read_tools_fail_closed_at_registration_for_unauthorized_terminals(
    tmp_path,
    terminal_id,
):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )

    _mcp, registered = _mcp_for_provider(provider, terminal_id)

    assert registered == []


@pytest.mark.asyncio
async def test_linear_read_tools_reject_unauthorized_targets_before_graphql(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue", "cao_linear.list_comments"]
issues = ["CAO-28"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert registered == ["cao_linear.get_issue", "cao_linear.list_comments"]
    with pytest.raises(ToolError, match="unauthorized_linear_issue"):
        await mcp.call_tool("cao_linear.get_issue", {"issue": "CAO-29"})
    with pytest.raises(ToolError, match="wrong_provider_ref"):
        await mcp.call_tool(
            "cao_linear.list_comments",
            {"issue_ref": {"provider": "github", "id": "CAO-28"}},
        )


@pytest.mark.parametrize(
    ("issue", "expected"),
    (
        (None, "linear_issue_not_found"),
        (_issue_payload(archived_at="2026-05-01T00:00:00.000Z"), "linear_issue_archived"),
    ),
)
def test_linear_read_tools_report_missing_and_archived_issues(
    tmp_path,
    monkeypatch,
    issue,
    expected,
):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: {"data": {"issue": issue}},
    )
    service = _service(provider)

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        service.invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name="cao_linear.get_issue",
            arguments={"issue": "CAO-28"},
        )


def test_linear_read_tools_report_provider_api_failures(tmp_path, monkeypatch):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            app_client.LinearOAuthError("Linear OAuth token refresh failed: unauthorized")
        ),
    )
    service = _service(provider)

    with pytest.raises(ProviderMediatedToolHandlerError, match="linear_credentials_expired"):
        service.invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name="cao_linear.get_issue",
            arguments={"issue": "CAO-28"},
        )


@pytest.mark.parametrize(
    ("raised", "expected"),
    (
        (RuntimeError("Forbidden: issue cannot be accessed"), "linear_issue_inaccessible"),
        (RuntimeError("Linear GraphQL request failed: upstream exploded"), "linear_api_failure"),
    ),
)
def test_linear_read_tools_report_inaccessible_and_generic_api_failures(
    tmp_path,
    monkeypatch,
    raised,
    expected,
):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(raised),
    )

    with pytest.raises(ProviderMediatedToolHandlerError, match=expected):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name="cao_linear.get_issue",
            arguments={"issue": "CAO-28"},
        )


def test_linear_read_tools_report_missing_credentials_before_graphql(tmp_path, monkeypatch):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )
    config = provider.config
    assert config is not None
    config.presences["implementation_partner"] = type(config.presences["implementation_partner"])(
        **{
            **config.presences["implementation_partner"].__dict__,
            "access_token": None,
            "refresh_token": None,
        }
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )

    with pytest.raises(ProviderMediatedToolHandlerError, match="linear_credentials_missing"):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name="cao_linear.get_issue",
            arguments={"issue": "CAO-28"},
        )


def test_linear_read_tools_reject_returned_issue_outside_policy(tmp_path, monkeypatch):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: {
            "data": {"issue": _issue_payload(id="other-issue", identifier="CAO-29")}
        },
    )

    with pytest.raises(ProviderMediatedToolHandlerError, match="linear_issue_outside_policy"):
        _service(provider).invoke(
            terminal_id="terminal-impl",
            provider_name="linear",
            tool_name="cao_linear.get_issue",
            arguments={"issue": "CAO-28"},
        )


@pytest.mark.asyncio
async def test_linear_read_tools_bound_description_and_comment_bodies(tmp_path, monkeypatch):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue", "cao_linear.list_comments"]
issues = ["CAO-28"]
""",
    )
    long_text = "x" * 5000

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        issue = (
            {
                **_comments_payload(),
                "comments": {
                    "nodes": [
                        {
                            "id": "comment-long",
                            "body": long_text,
                            "createdAt": "2026-05-07T10:00:00.000Z",
                            "updatedAt": "2026-05-07T10:01:00.000Z",
                            "user": {"id": "user-1", "name": "RJ Wilson"},
                        }
                    ]
                },
            }
            if "comments" in query
            else _issue_payload(description=long_text)
        )
        return {"data": {"issue": issue}}

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)
    mcp, _registered = _mcp_for_provider(provider, "terminal-impl")

    issue_result = await mcp.call_tool("cao_linear.get_issue", {"issue": "CAO-28"})
    comments_result = await mcp.call_tool(
        "cao_linear.list_comments", {"issue": "CAO-28", "limit": 1}
    )

    issue = json.loads(issue_result.content[0].text)
    comments = json.loads(comments_result.content[0].text)
    assert len(issue["description"]) == 4000
    assert issue["description"].endswith("...[truncated]")
    assert len(comments["comments"][0]["body"]) == 4000
    assert comments["comments"][0]["body"].endswith("...[truncated]")


@pytest.mark.asyncio
async def test_linear_read_tools_reject_invalid_comment_limit_before_graphql(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        """
[tool_access.implementation_partner_reads]
agent_id = "implementation_partner"
tools = ["cao_linear.list_comments"]
issues = ["CAO-28"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert registered == ["cao_linear.list_comments"]
    with pytest.raises(ToolError, match="invalid_linear_comment_limit"):
        await mcp.call_tool("cao_linear.list_comments", {"issue": "CAO-28", "limit": 101})


@pytest.mark.asyncio
async def test_linear_exploration_tools_register_and_fetch_provider_context(
    tmp_path,
    monkeypatch,
):
    tools = sorted(LINEAR_EXPLORATION_READ_TOOLS)
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_exploration]
agent_id = "implementation_partner"
tools = {json.dumps(tools)}
""",
    )
    calls: list[dict[str, Any]] = []

    def fake_graphql(query, variables=None, *, access_token=None, app_key=None):
        calls.append({"query": query, "variables": variables, "app_key": app_key})
        assert app_key == "implementation_partner"
        if "CaoLinearListTeams" in query:
            return {"data": {"teams": _teams_payload()}}
        if "CaoLinearGetTeam" in query:
            return {"data": {"team": _teams_payload()["nodes"][0]}}
        if "CaoLinearListUsers" in query:
            return {"data": {"users": _users_payload()}}
        if "CaoLinearGetUser" in query:
            return {"data": {"user": _users_payload()["nodes"][0]}}
        if "CaoLinearListIssueStatuses" in query:
            return {"data": {"workflowStates": {"nodes": [_issue_status_payload()]}}}
        if "CaoLinearGetIssueStatus" in query:
            return {"data": {"workflowState": _issue_status_payload()}}
        if "CaoLinearListIssueLabels" in query:
            return {"data": {"issueLabels": {"nodes": [_issue_label_payload()]}}}
        if "CaoLinearGetIssueLabel" in query:
            return {"data": {"issueLabel": _issue_label_payload()}}
        if "CaoLinearListProjects" in query:
            assert "teams" not in (variables or {}).get("filter", {})
            return {"data": {"projects": {"nodes": [_project_payload()]}}}
        if "CaoLinearGetProject" in query:
            return {"data": {"project": _project_payload()}}
        if "CaoLinearListIssues" in query:
            return {
                "data": {"issues": {"nodes": [_issue_payload(id="issue-54", identifier="CAO-54")]}}
            }
        if "CaoLinearSearchIssues" in query:
            return {
                "data": {
                    "searchIssues": {"nodes": [_issue_payload(id="issue-54", identifier="CAO-54")]}
                }
            }
        if "CaoLinearGetComment" in query:
            return {
                "data": {
                    "comment": _comments_payload()["comments"]["nodes"][0]
                    | {"issue": _issue_payload()}
                }
            }
        if "CaoLinearGetAgentSessionActivity" in query:
            return {"data": {"agentActivity": _agent_activity_payload()}}
        if "CaoLinearListAgentSessionActivities" in query:
            return {
                "data": {
                    "agentSession": {
                        "id": "agent-session-1",
                        "activities": {"nodes": [_agent_activity_payload()]},
                    }
                }
            }
        if "CaoLinearGetAgentSession" in query:
            return {"data": {"agentSession": _agent_session_payload()}}
        if "CaoLinearListDocuments" in query:
            return {"data": {"documents": {"nodes": [_document_payload()]}}}
        if "CaoLinearGetDocument" in query:
            return {"data": {"document": _document_payload()}}
        if "CaoLinearSearchDocuments" in query:
            return {"data": {"searchDocuments": {"nodes": [_document_payload()]}}}
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(app_client, "linear_graphql", fake_graphql)
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert set(registered) == LINEAR_EXPLORATION_READ_TOOLS
    assert (
        json.loads((await mcp.call_tool(LIST_TEAMS_TOOL, {"limit": 2})).content[0].text)["teams"][
            0
        ]["key"]
        == "CAO"
    )
    assert (
        json.loads((await mcp.call_tool(GET_TEAM_TOOL, {"team_id": "CAO"})).content[0].text)["id"]
        == "team-cao"
    )
    assert (
        json.loads((await mcp.call_tool(LIST_USERS_TOOL, {"query": "RJ"})).content[0].text)[
            "users"
        ][0]["name"]
        == "RJ Wilson"
    )
    assert (
        json.loads((await mcp.call_tool(GET_USER_TOOL, {"user_id": "user-1"})).content[0].text)[
            "active"
        ]
        is True
    )
    statuses = json.loads(
        (await mcp.call_tool(LIST_ISSUE_STATUSES_TOOL, {"team_id": "team-cao"})).content[0].text
    )
    assert statuses["issue_statuses"][0]["id"] == "status-started"
    assert (
        json.loads(
            (await mcp.call_tool(GET_ISSUE_STATUS_TOOL, {"status_id": "status-started"}))
            .content[0]
            .text
        )["type"]
        == "started"
    )
    assert (
        json.loads((await mcp.call_tool(LIST_ISSUE_LABELS_TOOL, {})).content[0].text)[
            "issue_labels"
        ][0]["id"]
        == "label-provider"
    )
    assert (
        json.loads(
            (await mcp.call_tool(GET_ISSUE_LABEL_TOOL, {"label_id": "label-provider"}))
            .content[0]
            .text
        )["name"]
        == "provider"
    )
    assert (
        json.loads((await mcp.call_tool(LIST_PROJECTS_TOOL, {"query": "Bridge"})).content[0].text)[
            "projects"
        ][0]["id"]
        == "project-bridge"
    )
    assert (
        json.loads(
            (await mcp.call_tool(LIST_PROJECTS_TOOL, {"team_id": "team-cao"})).content[0].text
        )["projects"][0]["id"]
        == "project-bridge"
    )
    assert (
        json.loads(
            (await mcp.call_tool(GET_PROJECT_TOOL, {"project_id": "project-bridge"}))
            .content[0]
            .text
        )["name"]
        == "Linear-backed CAO agent bridge"
    )
    assert (
        json.loads(
            (await mcp.call_tool(LIST_ISSUES_TOOL, {"project_id": "project-bridge"}))
            .content[0]
            .text
        )["issues"][0]["identifier"]
        == "CAO-54"
    )
    assert (
        json.loads(
            (await mcp.call_tool(SEARCH_ISSUES_TOOL, {"term": "Linear tools"})).content[0].text
        )["issues"][0]["identifier"]
        == "CAO-54"
    )
    assert (
        json.loads(
            (await mcp.call_tool(GET_COMMENT_TOOL, {"comment_id": "comment-1"})).content[0].text
        )["id"]
        == "comment-2"
    )
    assert (
        json.loads(
            (await mcp.call_tool(GET_AGENT_SESSION_TOOL, {"agent_session_id": "agent-session-1"}))
            .content[0]
            .text
        )["issue"]["identifier"]
        == "CAO-54"
    )
    assert (
        json.loads(
            (
                await mcp.call_tool(
                    LIST_AGENT_SESSION_ACTIVITIES_TOOL,
                    {"agent_session_id": "agent-session-1", "limit": 1},
                )
            )
            .content[0]
            .text
        )["activities"][0]["content"]["body"]
        == "testing"
    )
    assert (
        json.loads(
            (await mcp.call_tool(GET_AGENT_SESSION_ACTIVITY_TOOL, {"activity_id": "activity-1"}))
            .content[0]
            .text
        )["content"]["body"]
        == "testing"
    )
    assert (
        json.loads(
            (await mcp.call_tool(LIST_DOCUMENTS_TOOL, {"project_id": "project-bridge"}))
            .content[0]
            .text
        )["documents"][0]["id"]
        == "document-1"
    )
    assert (
        json.loads(
            (await mcp.call_tool(GET_DOCUMENT_TOOL, {"document_id": "document-1"})).content[0].text
        )["title"]
        == "Planning document"
    )
    assert (
        json.loads(
            (await mcp.call_tool(SEARCH_DOCUMENTS_TOOL, {"term": "Planning"})).content[0].text
        )["documents"][0]["id"]
        == "document-1"
    )
    assert len(calls) == len(LINEAR_EXPLORATION_READ_TOOLS) + 1


def test_linear_exploration_tools_do_not_require_issue_scope(tmp_path):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_exploration]
agent_id = "implementation_partner"
tools = ["{LIST_TEAMS_TOOL}", "{LIST_PROJECTS_TOOL}", "{SEARCH_DOCUMENTS_TOOL}"]
""",
    )

    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert mcp is not None
    assert registered == [LIST_PROJECTS_TOOL, LIST_TEAMS_TOOL, SEARCH_DOCUMENTS_TOOL]


@pytest.mark.asyncio
async def test_linear_exploration_tools_reject_invalid_arguments_before_graphql(
    tmp_path,
    monkeypatch,
):
    provider = _provider(
        tmp_path,
        f"""
[tool_access.implementation_partner_exploration]
agent_id = "implementation_partner"
tools = ["{SEARCH_ISSUES_TOOL}", "{LIST_DOCUMENTS_TOOL}"]
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert registered == [LIST_DOCUMENTS_TOOL, SEARCH_ISSUES_TOOL]
    with pytest.raises(ToolError, match="invalid_linear_tool_argument"):
        await mcp.call_tool(SEARCH_ISSUES_TOOL, {"term": "   "})
    with pytest.raises(ToolError, match="invalid_linear_list_limit"):
        await mcp.call_tool(LIST_DOCUMENTS_TOOL, {"limit": 101})


def test_linear_exploration_tool_names_keep_list_get_parity():
    list_to_get = {
        LIST_TEAMS_TOOL: GET_TEAM_TOOL,
        LIST_USERS_TOOL: GET_USER_TOOL,
        LIST_ISSUE_STATUSES_TOOL: GET_ISSUE_STATUS_TOOL,
        LIST_ISSUE_LABELS_TOOL: GET_ISSUE_LABEL_TOOL,
        LIST_PROJECTS_TOOL: GET_PROJECT_TOOL,
        LIST_DOCUMENTS_TOOL: GET_DOCUMENT_TOOL,
        LIST_AGENT_SESSION_ACTIVITIES_TOOL: GET_AGENT_SESSION_ACTIVITY_TOOL,
    }

    assert all(get_tool in LINEAR_EXPLORATION_READ_TOOLS for get_tool in list_to_get.values())
    assert SEARCH_ISSUES_TOOL in LINEAR_EXPLORATION_READ_TOOLS
    assert SEARCH_DOCUMENTS_TOOL in LINEAR_EXPLORATION_READ_TOOLS


@pytest.mark.parametrize(
    ("tool_access_body", "expected"),
    (
        (
            """
[tool_access.bad]
agent_id = "implementation_partner"
tools = ["cao_linear.mutate_issue"]
issues = ["CAO-28"]
""",
            "tool_access.bad.tools[0] unknown Linear tool: cao_linear.mutate_issue",
        ),
        (
            """
[tool_access.bad]
agent_id = "implementation_partner"
tools = ["cao_linear.get_issue"]
issues = "CAO-28"
""",
            "tool_access.bad.issues must be a non-empty string list",
        ),
        (
            f"""
[tool_access.bad]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
allow_top_level_create = true
""",
            "tool_access.bad.create_team_ids must be a non-empty string list",
        ),
        (
            f"""
[tool_access.bad]
agent_id = "implementation_partner"
tools = ["{CREATE_ISSUE_TOOL}"]
create_team_ids = ["team-cao"]
""",
            "must allow top-level issue creation or configure create_parent_issues",
        ),
        (
            f"""
[tool_access.bad]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
""",
            "tool_access.bad.update_fields must be a non-empty string list",
        ),
        (
            f"""
[tool_access.bad]
agent_id = "implementation_partner"
tools = ["{UPDATE_ISSUE_TOOL}"]
issues = ["CAO-51"]
update_fields = ["raw"]
""",
            "tool_access.bad.update_fields[0] unknown Linear update field: raw",
        ),
    ),
)
def test_linear_tool_access_config_rejects_malformed_entries(
    tmp_path,
    tool_access_body,
    expected,
):
    config = _linear_config(
        tmp_path,
        f"""
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
access_token = "access-token"

{tool_access_body}
""",
    )

    provider = LinearWorkspaceProvider(
        agent_registry=_agents(),
        config_path=config,
        preflight_credentials=False,
    )

    with pytest.raises(LinearWorkspaceProviderConfigError) as exc_info:
        provider.initialize()

    assert expected in str(exc_info.value)


def test_linear_profile_tool_access_requires_presence_for_each_matching_identity(tmp_path):
    config = _linear_config(
        tmp_path,
        """
[presences.implementation_partner]
agent_id = "implementation_partner"
app_key = "implementation_partner"
access_token = "access-token"

[tool_access.reviewer_reads]
agent_profile = "reviewer"
tools = ["cao_linear.get_issue"]
issues = ["CAO-28"]
""",
    )
    provider = LinearWorkspaceProvider(
        agent_registry=_agents(),
        config_path=config,
        preflight_credentials=False,
    )
    provider.initialize()

    with pytest.raises(ProviderToolAccessConfigError) as exc_info:
        provider.provider_tool_access()

    assert "tool_access.reviewer_reads" in str(exc_info.value)
    assert "identity 'discovery_partner'" in str(exc_info.value)
    assert "no Linear presence" in str(exc_info.value)
