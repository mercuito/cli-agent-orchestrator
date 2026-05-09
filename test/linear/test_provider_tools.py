"""Tests for CAO-mediated Linear provider tools."""

from __future__ import annotations

import json
from typing import Any, Mapping

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.provider_tools import (
    CREATE_COMMENT_TOOL,
    CREATE_ISSUE_TOOL,
    GET_ISSUE_TOOL,
    LIST_COMMENTS_TOOL,
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
            return {"data": {"node": {"id": variables["id"]}}}
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
            return {"data": {"node": {"id": variables["id"]}}}
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
        return {"data": {"node": None}}

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
            return {"data": {"node": {"id": variables["id"]}}}
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
""",
    )
    monkeypatch.setattr(
        app_client,
        "linear_graphql",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GraphQL called")),
    )
    mcp, registered = _mcp_for_provider(provider, "terminal-impl")

    assert registered == [CREATE_COMMENT_TOOL]
    with pytest.raises(ToolError, match="unauthorized_linear_issue"):
        await mcp.call_tool(
            CREATE_COMMENT_TOOL,
            {"issue": "CAO-51", "body": "This should be denied."},
        )
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
