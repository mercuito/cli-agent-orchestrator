from __future__ import annotations


def test_extract_mcp_server_names_from_list_shape():
    from cli_agent_orchestrator.diagnostics.providers.codex import _extract_mcp_server_names

    payload = [
        {"name": "a"},
        {"name": "b"},
    ]
    assert _extract_mcp_server_names(payload) == ["a", "b"]


def test_extract_mcp_server_names_from_dict_mcp_servers_shape():
    from cli_agent_orchestrator.diagnostics.providers.codex import _extract_mcp_server_names

    payload = {"mcp_servers": {"a": {}, "b": {}}}
    assert _extract_mcp_server_names(payload) == ["a", "b"]


def test_extract_mcp_server_names_from_dict_servers_shape():
    from cli_agent_orchestrator.diagnostics.providers.codex import _extract_mcp_server_names

    payload = {"servers": [{"name": "a"}, {"name": "b"}]}
    assert _extract_mcp_server_names(payload) == ["a", "b"]


def test_extract_mcp_server_names_ignores_unknown_shapes():
    from cli_agent_orchestrator.diagnostics.providers.codex import _extract_mcp_server_names

    assert _extract_mcp_server_names({"x": 1}) == []
    assert _extract_mcp_server_names("nope") == []
