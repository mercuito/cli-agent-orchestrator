import shlex
from unittest.mock import patch

from cli_agent_orchestrator.models.agent_profile import AgentProfile
from cli_agent_orchestrator.providers.claude_code import ClaudeCodeProvider


def test_build_command_includes_reasoning_effort_when_set():
    provider = ClaudeCodeProvider("t1", "s1", "w1", agent_profile="worker")

    with patch(
        "cli_agent_orchestrator.providers.claude_code.load_agent_profile",
        return_value=AgentProfile(
            name="worker",
            description="Worker",
            system_prompt="SYSTEM PROMPT",
            reasoning_effort="high",
        ),
    ):
        command = provider._build_claude_command()

    argv = shlex.split(command)
    assert argv[:1] == ["claude"]
    assert "--reasoning-effort" in argv
    assert argv[argv.index("--reasoning-effort") + 1] == "high"


def test_build_command_omits_reasoning_effort_when_unset():
    provider = ClaudeCodeProvider("t1", "s1", "w1", agent_profile="worker")

    with patch(
        "cli_agent_orchestrator.providers.claude_code.load_agent_profile",
        return_value=AgentProfile(
            name="worker",
            description="Worker",
            system_prompt="SYSTEM PROMPT",
            reasoning_effort=None,
        ),
    ):
        command = provider._build_claude_command()

    argv = shlex.split(command)
    assert argv[:1] == ["claude"]
    assert "--reasoning-effort" not in argv

