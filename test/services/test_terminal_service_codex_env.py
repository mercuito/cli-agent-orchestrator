from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_create_terminal_codex_sets_codex_home_env(tmp_path: Path):
    from cli_agent_orchestrator.models.terminal import TerminalStatus
    from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
    from cli_agent_orchestrator.services import terminal_service

    codex_home = tmp_path / "codex-home" / ".codex"
    codex_home.mkdir(parents=True)

    provider = MagicMock()
    provider.initialize.return_value = True

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
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.prepare_terminal_runtime",
            return_value=ProviderRuntimePreparation(environment={"CODEX_HOME": str(codex_home)}),
        ),
    ):
        mock_tmux.session_exists.return_value = False

        terminal = terminal_service.create_terminal(
            provider="codex",
            agent_profile="developer",
            session_name=None,
            new_session=True,
            working_directory=str(tmp_path),
        )

        assert terminal.id == "abcd1234"
        assert terminal.status == TerminalStatus.IDLE

        # Expect CODEX_HOME env to be passed through to tmux create_session
        create_kwargs = mock_tmux.create_session.call_args.kwargs
        assert create_kwargs["environment"]["CODEX_HOME"] == str(codex_home)


def test_create_terminal_raw_codex_runtime_has_no_identity_launch_context(tmp_path: Path):
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

        terminal_service.create_terminal(
            provider="codex",
            agent_profile="developer",
            session_name=None,
            new_session=True,
            working_directory=str(tmp_path),
        )

    assert prepare_runtime.call_args.kwargs["launch_context"] is None


def test_create_terminal_identity_codex_runtime_passes_provider_data_dir(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_identity_factory,
):
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent_identity.AGENT_IDENTITY_DATA_ROOT",
        tmp_path / "agents",
    )
    identity = implementation_partner_identity_factory()
    provider = MagicMock()
    codex_home = tmp_path / "agents" / "implementation_partner" / "providers" / "codex" / ".codex"

    with (
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_terminal_id",
            return_value="terminal-a",
        ),
        patch(
            "cli_agent_orchestrator.services.terminal_service.generate_window_name",
            return_value="developer-0000",
        ),
        patch("cli_agent_orchestrator.services.terminal_service.db_create_terminal") as db_create,
        patch(
            "cli_agent_orchestrator.services.terminal_service.provider_manager.create_provider",
            return_value=provider,
        ),
        patch(
            "cli_agent_orchestrator.providers.codex.prepare_identity_codex_home",
            return_value=codex_home,
        ) as prepare_identity_codex_home,
        patch("cli_agent_orchestrator.services.terminal_service.tmux_client") as mock_tmux,
    ):
        mock_tmux.session_exists.return_value = False

        terminal_service.create_terminal(
            provider="codex",
            agent_profile="developer",
            session_name="cao-implementation-partner",
            new_session=True,
            working_directory=str(tmp_path / "repo"),
            agent_identity=identity,
        )

    prepare_identity_codex_home.assert_called_once()
    assert prepare_identity_codex_home.call_args.args[0] == (
        tmp_path / "agents" / "implementation_partner" / "providers" / "codex"
    )
    assert prepare_identity_codex_home.call_args.args[1:] == (
        "terminal-a",
        "developer",
        str(tmp_path / "repo"),
    )
    assert db_create.call_args.kwargs["agent_identity_id"] == "implementation_partner"
    create_kwargs = mock_tmux.create_session.call_args.kwargs
    assert create_kwargs["environment"]["CODEX_HOME"] == str(codex_home)


def test_create_terminal_identity_launch_context_uses_resolved_launch_values(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_identity_factory,
):
    from cli_agent_orchestrator.models.agent_profile import AgentProfile
    from cli_agent_orchestrator.providers.base import ProviderRuntimePreparation
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent_identity.AGENT_IDENTITY_DATA_ROOT",
        tmp_path / "agents",
    )
    identity = implementation_partner_identity_factory()
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
            "cli_agent_orchestrator.services.terminal_service.load_agent_profile",
            return_value=AgentProfile(
                name="developer",
                description="Developer",
                runtimeCapabilities=["fs_read"],
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

        terminal_service.create_terminal(
            provider="codex",
            agent_profile="developer",
            session_name="implementation-partner",
            new_session=True,
            working_directory=str(tmp_path / "repo"),
            agent_identity=identity,
        )

    launch_context = prepare_runtime.call_args.kwargs["launch_context"]
    assert launch_context.session_name == "cao-implementation-partner"
    assert launch_context.allowed_tools == ["fs_read"]


def test_create_terminal_deserializes_provider_runtime_and_passes_resume_args(
    tmp_path: Path,
    monkeypatch,
    implementation_partner_identity_factory,
):
    from cli_agent_orchestrator.providers.base import (
        ProviderRuntimePreparation,
        ProviderRuntimeState,
    )
    from cli_agent_orchestrator.services import terminal_service

    monkeypatch.setattr(
        "cli_agent_orchestrator.agent_identity.AGENT_IDENTITY_DATA_ROOT",
        tmp_path / "agents",
    )
    identity = implementation_partner_identity_factory()
    provider = MagicMock()
    runtime_state = ProviderRuntimeState(
        provider_type="codex",
        provider_data_dir=tmp_path / "agents" / "implementation_partner" / "providers" / "codex",
        payload={"schema_version": "test-runtime-state.v1", "thread_id": "session-a"},
    )
    capability = MagicMock()
    capability.deserialize_runtime_state.return_value = runtime_state
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

        terminal_service.create_terminal(
            provider="codex",
            agent_profile="developer",
            session_name="cao-implementation-partner",
            new_session=True,
            working_directory=str(tmp_path / "repo"),
            agent_identity=identity,
            provider_runtime={"schema_version": "test-runtime-state.v1", "thread_id": "session-a"},
        )

    provider_data_dir = tmp_path / "agents" / "implementation_partner" / "providers" / "codex"
    capability.deserialize_runtime_state.assert_called_once_with(
        {"schema_version": "test-runtime-state.v1", "thread_id": "session-a"},
        provider_data_dir=provider_data_dir,
    )
    capability.launch_resume_args.assert_called_once_with(
        runtime_state,
        provider_data_dir=provider_data_dir,
    )
    assert create_provider.call_args.kwargs["runtime_resume_args"] == [
        "--resume-thread",
        "session-a",
    ]
    assert create_provider.call_args.kwargs["provider_data_dir"] == str(provider_data_dir)
