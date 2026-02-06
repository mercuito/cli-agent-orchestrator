import json
import textwrap

import pytest

from cli_agent_orchestrator.mcp_server import server as mcp_server
from cli_agent_orchestrator.utils import agent_profiles as agent_profiles_utils


def _tool_result_to_json_dict(tool_result):
    assert tool_result.content
    assert hasattr(tool_result.content[0], "text")
    return json.loads(tool_result.content[0].text)


@pytest.mark.asyncio
async def test_list_agent_profiles_includes_builtin(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    tool_result = await mcp_server.list_agent_profiles.run({})
    result = _tool_result_to_json_dict(tool_result)

    assert result["success"] is True
    profiles = result["profiles"]
    assert isinstance(profiles, list)
    names = {p["name"] for p in profiles}
    assert {"developer", "reviewer", "code_supervisor"} <= names


@pytest.mark.asyncio
async def test_get_agent_profile_excludes_prompt_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    tool_result = await mcp_server.get_agent_profile.run({"agent_name": "developer"})
    result = _tool_result_to_json_dict(tool_result)

    assert result["success"] is True
    profile = result["profile"]
    assert profile["name"] == "developer"
    assert "system_prompt" not in profile


@pytest.mark.asyncio
async def test_get_agent_profile_can_include_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    tool_result = await mcp_server.get_agent_profile.run(
        {"agent_name": "developer", "include_prompt": True}
    )
    result = _tool_result_to_json_dict(tool_result)

    assert result["success"] is True
    profile = result["profile"]
    assert profile["name"] == "developer"
    assert isinstance(profile.get("system_prompt"), str)
    assert profile["system_prompt"]


@pytest.mark.asyncio
async def test_local_profile_overrides_builtin(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    (tmp_path / "developer.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: developer
            description: Local developer override
            provider: codex
            role: developer
            tags: [python]
            reasoning_effort: medium
            model: my-model
            ---

            LOCAL PROMPT
            """
        )
    )

    list_tool_result = await mcp_server.list_agent_profiles.run({})
    list_result = _tool_result_to_json_dict(list_tool_result)
    assert list_result["success"] is True
    developer = next(p for p in list_result["profiles"] if p["name"] == "developer")
    assert developer["source"] == "local"
    assert developer["description"] == "Local developer override"
    assert developer["model"] == "my-model"
    assert developer["provider"] == "codex"
    assert developer["role"] == "developer"
    assert developer["tags"] == ["python"]
    assert developer["reasoning_effort"] == "medium"

    get_tool_result = await mcp_server.get_agent_profile.run(
        {"agent_name": "developer", "include_prompt": True}
    )
    get_result = _tool_result_to_json_dict(get_tool_result)
    assert get_result["success"] is True
    profile = get_result["profile"]
    assert profile["source"] == "local"
    assert profile["description"] == "Local developer override"
    assert profile["model"] == "my-model"
    assert profile["provider"] == "codex"
    assert profile["role"] == "developer"
    assert profile["tags"] == ["python"]
    assert profile["reasoning_effort"] == "medium"
    assert profile["system_prompt"] == "LOCAL PROMPT"


@pytest.mark.asyncio
async def test_get_agent_profile_missing_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    tool_result = await mcp_server.get_agent_profile.run({"agent_name": "does_not_exist"})
    result = _tool_result_to_json_dict(tool_result)

    assert result["success"] is False
    assert result["profile"] is None
    assert "error" in result
