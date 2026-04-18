import textwrap

from cli_agent_orchestrator.mcp_server import server as mcp_server
from cli_agent_orchestrator.utils import agent_profiles as agent_profiles_utils


def test_list_agent_profiles_includes_builtin(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    result = mcp_server._list_agent_profiles_impl()

    assert result["success"] is True
    profiles = result["profiles"]
    assert isinstance(profiles, list)
    names = {p["name"] for p in profiles}
    assert {"developer", "reviewer", "code_supervisor"} <= names


def test_get_agent_profile_excludes_prompt_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    result = mcp_server._get_agent_profile_impl("developer")

    assert result["success"] is True
    profile = result["profile"]
    assert profile["name"] == "developer"
    assert "system_prompt" not in profile


def test_get_agent_profile_can_include_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    result = mcp_server._get_agent_profile_impl("developer", include_prompt=True)

    assert result["success"] is True
    profile = result["profile"]
    assert profile["name"] == "developer"
    assert isinstance(profile.get("system_prompt"), str)
    assert profile["system_prompt"]


def test_local_profile_overrides_builtin(monkeypatch, tmp_path):
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

    list_result = mcp_server._list_agent_profiles_impl()
    assert list_result["success"] is True
    developer = next(p for p in list_result["profiles"] if p["name"] == "developer")
    assert developer["source"] == "local"
    assert developer["description"] == "Local developer override"
    assert developer["model"] == "my-model"
    assert developer["provider"] == "codex"
    assert developer["role"] == "developer"
    assert developer["tags"] == ["python"]
    assert developer["reasoning_effort"] == "medium"

    get_result = mcp_server._get_agent_profile_impl("developer", include_prompt=True)
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


def test_get_agent_profile_missing_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    result = mcp_server._get_agent_profile_impl("does_not_exist")

    assert result["success"] is False
    assert result["profile"] is None
    assert "error" in result
