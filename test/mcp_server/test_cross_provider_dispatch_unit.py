import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from cli_agent_orchestrator.mcp_server import server as mcp_server
from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.models.provider import ProviderType


@dataclass
class _FakeResponse:
    payload: Dict[str, Any]
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self.payload


def _make_profile(*, provider: Optional[ProviderType]) -> AgentProfile:
    return AgentProfile(
        name="test_profile",
        description="test",
        provider=provider,
        system_prompt="prompt",
    )


def test_create_terminal_uses_profile_provider_when_set(monkeypatch):
    monkeypatch.setenv("CAO_TERMINAL_ID", "conductor-terminal")

    def fake_load_agent_profile(name: str) -> AgentProfile:
        assert name == "worker"
        return _make_profile(provider=ProviderType.CODEX)

    monkeypatch.setattr(mcp_server.agent_profiles_utils, "load_agent_profile", fake_load_agent_profile)

    def fake_get(url: str, *args, **kwargs):
        assert url.endswith("/terminals/conductor-terminal")
        return _FakeResponse({"provider": ProviderType.Q_CLI.value, "session_name": "sess"})

    post_calls = []

    def fake_post(url: str, *args, **kwargs):
        post_calls.append((url, kwargs))
        assert url.endswith("/sessions/sess/terminals")
        return _FakeResponse({"id": "worker-terminal"})

    monkeypatch.setattr(mcp_server.requests, "get", fake_get)
    monkeypatch.setattr(mcp_server.requests, "post", fake_post)

    terminal_id, provider = mcp_server._create_terminal("worker", working_directory="/tmp")

    assert terminal_id == "worker-terminal"
    assert provider == ProviderType.CODEX.value
    assert len(post_calls) == 1
    _, post_kwargs = post_calls[0]
    assert post_kwargs["params"]["provider"] == ProviderType.CODEX.value


def test_create_terminal_falls_back_to_conductor_provider_when_profile_has_none(monkeypatch):
    monkeypatch.setenv("CAO_TERMINAL_ID", "conductor-terminal")

    monkeypatch.setattr(
        mcp_server.agent_profiles_utils,
        "load_agent_profile",
        lambda _name: _make_profile(provider=None),
    )

    def fake_get(url: str, *args, **kwargs):
        assert url.endswith("/terminals/conductor-terminal")
        return _FakeResponse({"provider": ProviderType.KIRO_CLI.value, "session_name": "sess"})

    post_calls = []

    def fake_post(url: str, *args, **kwargs):
        post_calls.append((url, kwargs))
        return _FakeResponse({"id": "worker-terminal"})

    monkeypatch.setattr(mcp_server.requests, "get", fake_get)
    monkeypatch.setattr(mcp_server.requests, "post", fake_post)

    _terminal_id, provider = mcp_server._create_terminal("worker", working_directory="/tmp")

    assert provider == ProviderType.KIRO_CLI.value
    assert len(post_calls) == 1
    _, post_kwargs = post_calls[0]
    assert post_kwargs["params"]["provider"] == ProviderType.KIRO_CLI.value


def test_create_terminal_falls_back_to_default_provider_when_no_conductor_and_profile_has_none(
    monkeypatch,
):
    monkeypatch.delenv("CAO_TERMINAL_ID", raising=False)

    monkeypatch.setattr(
        mcp_server.agent_profiles_utils,
        "load_agent_profile",
        lambda _name: _make_profile(provider=None),
    )
    monkeypatch.setattr(mcp_server, "generate_session_name", lambda: "sess-new")

    post_calls = []

    def fake_post(url: str, *args, **kwargs):
        post_calls.append((url, kwargs))
        assert url.endswith("/sessions")
        return _FakeResponse({"id": "worker-terminal"})

    monkeypatch.setattr(mcp_server.requests, "post", fake_post)

    _terminal_id, provider = mcp_server._create_terminal("worker", working_directory="/tmp")

    assert provider == mcp_server.DEFAULT_PROVIDER
    assert len(post_calls) == 1
    _, post_kwargs = post_calls[0]
    assert post_kwargs["params"]["provider"] == mcp_server.DEFAULT_PROVIDER


@pytest.mark.asyncio
async def test_assign_and_handoff_fail_fast_on_profile_load_failure(monkeypatch):
    monkeypatch.delenv("CAO_TERMINAL_ID", raising=False)

    def fake_load_agent_profile(_name: str):
        raise RuntimeError("Failed to load agent profile 'bad': invalid YAML")

    monkeypatch.setattr(mcp_server.agent_profiles_utils, "load_agent_profile", fake_load_agent_profile)

    post_calls = []
    get_calls = []

    def fake_post(url: str, *args, **kwargs):
        post_calls.append((url, kwargs))
        return _FakeResponse({"id": "should-not-happen"})

    def fake_get(url: str, *args, **kwargs):
        get_calls.append((url, kwargs))
        return _FakeResponse({})

    monkeypatch.setattr(mcp_server.requests, "post", fake_post)
    monkeypatch.setattr(mcp_server.requests, "get", fake_get)

    assign_result = mcp_server._assign_impl("bad", "do the thing", working_directory="/tmp")
    assert assign_result["success"] is False
    assert assign_result["terminal_id"] is None
    assert "Assignment failed: Failed to load agent profile 'bad':" in assign_result["message"]
    assert post_calls == []
    assert get_calls == []

    handoff_result = await mcp_server._handoff_impl("bad", "do the thing", timeout=1, working_directory="/tmp")
    assert handoff_result.success is False
    assert handoff_result.terminal_id is None
    assert "Handoff failed: Failed to load agent profile 'bad':" in handoff_result.message
    assert post_calls == []
    assert get_calls == []

