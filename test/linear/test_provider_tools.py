"""Tests for CAO-mediated Linear read-only provider tools."""

from __future__ import annotations

import json
from typing import Any, Mapping

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry
from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear.workspace_provider import (
    LinearWorkspaceProvider,
    LinearWorkspaceProviderConfigError,
)
from cli_agent_orchestrator.mcp_server.provider_tools import (
    register_provider_mediated_mcp_tools,
)
from cli_agent_orchestrator.workspace_providers.invocation import (
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


def _service(provider: LinearWorkspaceProvider) -> ProviderMediatedToolInvocationService:
    return ProviderMediatedToolInvocationService(
        policies={"linear": provider.provider_tool_access()},
        agent_registry=_agents(),
        terminal_metadata_resolver=_terminal_metadata,
    )


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
            "tool_access.bad.tools[0] unknown Linear read tool: cao_linear.mutate_issue",
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
