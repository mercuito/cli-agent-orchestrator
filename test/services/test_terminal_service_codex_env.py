from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

OLD_TERMINAL_ENV = "CAO_" + "TERMINAL_ID"


def test_create_terminal_codex_sets_codex_home_env(
    tmp_path: Path,
    implementation_partner_agent_factory,
    runtime_inbox_db_session,
):
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.models.terminal import TerminalStatus
    from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
    from cli_agent_orchestrator.services import terminal_service

    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)
    workspace_context_id = db_module.default_workspace_context_id("implementation_partner")
    agent = implementation_partner_agent_factory(workdir=str(tmp_path)).for_workspace_context(
        workspace_context_id
    )

    provider = MagicMock()
    provider.initialize.return_value = True

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="abcd1234",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal"),
        patch(
            "cli_agent_orchestrator.services.terminal_service.load_agent",
            return_value=agent,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            return_value=provider,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            return_value=ProviderRuntimePreparation(environment={"CODEX_HOME": str(codex_home)}),
        ),
    ):
        mock_tmux.session_exists.return_value = False

        terminal = terminal_service.create_terminal_for_agent(agent)

        assert terminal.id == "abcd1234"
        assert terminal.status == TerminalStatus.IDLE

        # Expect CODEX_HOME env to be passed through to tmux create_session
        create_kwargs = mock_tmux.create_session.call_args.kwargs
        create_args = mock_tmux.create_session.call_args.args
        assert create_args[2] == agent.id
        assert create_kwargs["environment"]["CODEX_HOME"] == str(codex_home)
        # TmuxClient injects CAO_AGENT_ID after merging provider runtime env.
        assert "CAO_AGENT_ID" not in create_kwargs["environment"]
        assert OLD_TERMINAL_ENV not in create_kwargs["environment"]


def test_create_terminal_raw_codex_runtime_has_no_agent_launch_context(tmp_path: Path):
    from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
    from cli_agent_orchestrator.services import terminal_service

    provider = MagicMock()
    prepare_runtime = MagicMock(return_value=ProviderRuntimePreparation())

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="abcd1234",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_session_name",
            return_value="cao-test",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal"),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            return_value=provider,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            prepare_runtime,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        with pytest.raises(ValueError, match="configured agent"):
            terminal_service.create_terminal(
                provider="codex",
                agent_id="developer",
                session_name=None,
                new_session=True,
                working_directory=str(tmp_path),
            )

    prepare_runtime.assert_not_called()


def test_create_terminal_rejects_agent_kwargs_before_persisting(
    tmp_path: Path,
    implementation_partner_agent_factory,
):
    import pytest

    from cli_agent_orchestrator.services import terminal_service

    agent = implementation_partner_agent_factory(workdir=str(tmp_path / "repo"))

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="terminal-a",
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal") as db_create,
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False
        with pytest.raises(TypeError):
            terminal_service.create_terminal(
                provider="codex",
                agent_id="developer",
                session_name="cao-implementation-partner",
                new_session=True,
                working_directory=str(tmp_path / "repo"),
                agent=agent,
            )

    db_create.assert_not_called()
    mock_tmux.create_session.assert_not_called()


def test_create_terminal_agent_codex_runtime_passes_provider_data_dir(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_agent_factory,
    runtime_inbox_db_session,
):
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        tmp_path / "agents",
    )
    default_context_id = db_module.default_workspace_context_id("implementation_partner")
    agent = implementation_partner_agent_factory(
        workdir=str(tmp_path / "repo")
    ).for_workspace_context(default_context_id)
    provider = MagicMock()
    provider_dir = (
        tmp_path
        / "agents"
        / "implementation_partner"
        / "contexts"
        / default_context_id
        / "runtime"
        / "codex"
    )
    codex_home = provider_dir / ".codex"

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="terminal-a",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.load_agent",
            return_value=agent,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal") as db_create,
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            return_value=provider,
        ),
        patch(
            "cli_agent_orchestrator.providers.codex.prepare_agent_codex_home",
            return_value=codex_home,
        ) as prepare_agent_codex_home,
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        terminal_service.create_terminal_for_agent(
            agent,
        )

    prepare_agent_codex_home.assert_called_once()
    assert prepare_agent_codex_home.call_args.args[0] == provider_dir
    assert prepare_agent_codex_home.call_args.args[1:] == (
        "terminal-a",
        "implementation_partner",
        str(tmp_path / "repo"),
    )
    assert db_create.call_args.kwargs["agent_id"] == "implementation_partner"
    assert db_create.call_args.kwargs["workspace_context_id"] == default_context_id
    create_kwargs = mock_tmux.create_session.call_args.kwargs
    create_args = mock_tmux.create_session.call_args.args
    assert create_args[2] == "implementation_partner"
    assert create_kwargs["environment"]["CODEX_HOME"] == str(codex_home)
    # TmuxClient injects CAO_AGENT_ID after merging provider runtime env.
    assert "CAO_AGENT_ID" not in create_kwargs["environment"]
    assert OLD_TERMINAL_ENV not in create_kwargs["environment"]


def test_create_terminal_agent_launch_context_uses_resolved_launch_values(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_agent_factory,
    runtime_inbox_db_session,
):
    from test.support.agent_factory import Agent

    from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        tmp_path / "agents",
    )
    agent = implementation_partner_agent_factory(
        workdir=str(tmp_path / "repo")
    ).for_workspace_context("wctx_launch")
    provider = MagicMock()
    prepare_runtime = MagicMock(return_value=ProviderRuntimePreparation())

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="terminal-a",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.load_agent",
            return_value=Agent(
                name="developer",
                description="Developer",
                runtime_capabilities=["fs_read"],
            ),
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal"),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            return_value=provider,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            prepare_runtime,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        terminal_service.create_terminal_for_agent(
            agent,
        )

    launch_context = prepare_runtime.call_args.kwargs["launch_context"]
    assert launch_context.session_name == "cao-implementation-partner"
    assert launch_context.allowed_tools == ["fs_read", "@cao-mcp-server"]
    assert launch_context.provider_data_dir == (
        tmp_path
        / "agents"
        / "implementation_partner"
        / "contexts"
        / "wctx_launch"
        / "runtime"
        / "codex"
    )


def test_create_terminal_context_launch_context_uses_context_provider_data_dir(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_agent_factory,
):
    from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        tmp_path / "agents",
    )
    agent = implementation_partner_agent_factory(workdir=str(tmp_path / "repo"))
    provider = MagicMock()
    prepare_runtime = MagicMock(return_value=ProviderRuntimePreparation())

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="terminal-a",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.load_agent",
            return_value=agent,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal") as db_create,
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            return_value=provider,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            prepare_runtime,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        terminal_service.create_terminal_for_agent(agent.for_workspace_context("wctx_123"))

    launch_context = prepare_runtime.call_args.kwargs["launch_context"]
    expected_provider_dir = (
        tmp_path
        / "agents"
        / "implementation_partner"
        / "contexts"
        / "wctx_123"
        / "runtime"
        / "codex"
    )
    assert launch_context.provider_data_dir == expected_provider_dir
    assert db_create.call_args.kwargs["workspace_context_id"] == "wctx_123"


def test_create_terminal_deserializes_provider_runtime_and_passes_resume_args(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_agent_factory,
    runtime_inbox_db_session,
):
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.providers.base import (
        ProviderRuntimePreparation,
        ProviderRuntimeState,
    )
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        tmp_path / "agents",
    )
    default_context_id = db_module.default_workspace_context_id("implementation_partner")
    agent = implementation_partner_agent_factory(
        workdir=str(tmp_path / "repo")
    ).for_workspace_context(default_context_id)
    provider = MagicMock()
    provider_data_dir = (
        tmp_path
        / "agents"
        / "implementation_partner"
        / "contexts"
        / default_context_id
        / "runtime"
        / "codex"
    )
    runtime_state = ProviderRuntimeState(
        provider_type="codex",
        provider_data_dir=provider_data_dir,
        payload={"schema_version": "test-runtime-state.v1", "thread_id": "session-a"},
    )
    capability = MagicMock()
    capability.load_runtime_state.return_value = runtime_state
    capability.launch_resume_args.return_value = ["--resume-thread", "session-a"]
    create_provider = MagicMock(return_value=provider)

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="terminal-a",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.load_agent",
            return_value=agent,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            return_value=ProviderRuntimePreparation(),
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.runtime_state_capability",
            return_value=capability,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            create_provider,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal"),
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        terminal_service.create_terminal_for_agent(agent)

    capability.load_runtime_state.assert_called_once_with(provider_data_dir=provider_data_dir)
    capability.launch_resume_args.assert_called_once_with(
        runtime_state,
        provider_data_dir=provider_data_dir,
    )
    assert create_provider.call_args.kwargs["runtime_resume_args"] == [
        "--resume-thread",
        "session-a",
    ]
    assert create_provider.call_args.kwargs["provider_data_dir"] == str(provider_data_dir)


def test_create_terminal_clears_stale_resume_state_and_retries_cold_start(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_agent_factory,
    runtime_inbox_db_session,
):
    from cli_agent_orchestrator.clients import database as db_module
    from cli_agent_orchestrator.providers.base import (
        ProviderRuntimePreparation,
        ProviderRuntimeState,
    )
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent.AGENTS_ROOT",
        tmp_path / "agents",
    )
    default_context_id = db_module.default_workspace_context_id("implementation_partner")
    agent = implementation_partner_agent_factory(
        workdir=str(tmp_path / "repo")
    ).for_workspace_context(default_context_id)
    provider_data_dir = (
        tmp_path
        / "agents"
        / "implementation_partner"
        / "contexts"
        / default_context_id
        / "runtime"
        / "codex"
    )
    runtime_state = ProviderRuntimeState(
        provider_type="codex",
        provider_data_dir=provider_data_dir,
        payload={"schema_version": "test-runtime-state.v1", "thread_id": "missing-session"},
    )
    capability = MagicMock()
    capability.load_runtime_state.side_effect = [runtime_state, None]
    capability.launch_resume_args.return_value = ["resume", "missing-session"]

    stale_resume_provider = MagicMock()
    stale_resume_provider.initialize.side_effect = RuntimeError(
        "No saved session found with ID missing-session"
    )
    cold_start_provider = MagicMock()
    cold_start_provider.initialize.return_value = True
    create_provider = MagicMock(side_effect=[stale_resume_provider, cold_start_provider])

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            side_effect=["terminal-a", "terminal-b"],
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.load_agent",
            return_value=agent,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            return_value=ProviderRuntimePreparation(),
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.runtime_state_capability",
            return_value=capability,
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            create_provider,
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal"),
        patch("cli_agent_orchestrator.services.terminal_service.db_delete_terminal") as db_delete,
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        terminal = terminal_service.create_terminal_for_agent(agent)

    assert terminal.id == "terminal-b"
    assert create_provider.call_args_list[0].kwargs["runtime_resume_args"] == [
        "resume",
        "missing-session",
    ]
    assert create_provider.call_args_list[1].kwargs["runtime_resume_args"] is None
    capability.clear_runtime_state.assert_called_once_with(provider_data_dir=provider_data_dir)
    db_delete.assert_called_once_with("terminal-a")
    mock_tmux.kill_session.assert_called_once_with("cao-implementation-partner")


def test_create_terminal_for_agent_requires_bound_workspace_context(
    implementation_partner_agent_factory,
):
    from cli_agent_orchestrator.services import terminal_service

    agent = implementation_partner_agent_factory()

    with pytest.raises(ValueError, match="current_workspace_context_id"):
        terminal_service.create_terminal_for_agent(agent)
