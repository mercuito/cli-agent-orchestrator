import textwrap

from cli_agent_orchestrator.models.provider import ProviderType
from cli_agent_orchestrator.utils import agent_profiles as agent_profiles_utils


def test_load_agent_profile_parses_provider_role_tags_and_reasoning_effort(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_profiles_utils, "LOCAL_AGENT_STORE_DIR", tmp_path)

    (tmp_path / "meta_agent.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: meta_agent
            description: Metadata agent
            provider: codex
            role: reviewer
            tags: [security, python]
            reasoning_effort: high
            ---

            SYSTEM PROMPT
            """
        )
    )

    profile = agent_profiles_utils.load_agent_profile("meta_agent")
    assert profile.name == "meta_agent"
    assert profile.provider == ProviderType.CODEX
    assert profile.role == "reviewer"
    assert profile.tags == ["security", "python"]
    assert profile.reasoning_effort == "high"

