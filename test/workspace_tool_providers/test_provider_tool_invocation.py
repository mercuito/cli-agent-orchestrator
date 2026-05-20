"""Tests for provider-mediated invocation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pytest

from cli_agent_orchestrator.agent import Agent, AgentRegistry
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.workspace_tool_providers import (
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessPolicy,
    ProviderToolAccessRequest,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
    normalize_provider_tool_access,
)
from cli_agent_orchestrator.workspace_tool_providers.invocation import (
    ProviderMediatedToolAccessDenied,
    ProviderMediatedToolHandlerError,
    ProviderMediatedToolInvocationService,
)


@dataclass
class InvocationRecorder:
    events: list[str] = field(default_factory=list)
    fail_handler: bool = False
    fail_post_hook: bool = False
    mutate_post_result: bool = False
    handler_result: dict[str, Any] = field(default_factory=lambda: {"provider": "result"})
    denial_reason: str = "agent is not allowed to perform this fake action"
    denial_diagnostics: Mapping[str, Any] | None = None

    def handler(
        self, context: ProviderToolInvocationContext, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.events.append(f"handler:{context.agent.id}:{context.tool_name}:{arguments['query']}")
        if self.fail_handler:
            raise ValueError("provider handler exploded")
        return self.handler_result

    def allow_hook(
        self, context: ProviderToolInvocationContext
    ) -> ProviderToolPreCallResult | None:
        assert context.phase is not None
        self.events.append(f"{context.phase.value}:{context.hook_name}")
        if context.phase == ProviderToolHookPhase.PRE_CALL:
            return ProviderToolPreCallResult.allow()
        return None

    def deny_hook(self, context: ProviderToolInvocationContext) -> ProviderToolPreCallResult | None:
        assert context.phase is not None
        self.events.append(f"{context.phase.value}:{context.hook_name}")
        return ProviderToolPreCallResult.deny(
            self.denial_reason,
            self.denial_diagnostics or {"agent": context.agent.id, "tool": context.tool_name},
        )

    def post_hook(self, context: ProviderToolInvocationContext) -> ProviderToolPreCallResult | None:
        assert context.phase is not None
        self.events.append(
            f"{context.phase.value}:{context.hook_name}:{context.handler_result['provider']}"
        )
        if self.fail_post_hook:
            raise RuntimeError("post hook exploded")
        if self.mutate_post_result and isinstance(context.handler_result, dict):
            context.handler_result["provider"] = "mutated"
        return ProviderToolPreCallResult.deny("post hooks cannot deny")


def _agents() -> AgentRegistry:
    return AgentRegistry(
        {
            "agent_a": Agent(
                id="agent_a",
                display_name="Agent A",
                cli_provider="codex",
                workdir="/repo",
                session_name="agent-a",
                prompt="Developer agent.",
            ),
            "agent_b": Agent(
                id="agent_b",
                display_name="Agent B",
                cli_provider="codex",
                workdir="/repo",
                session_name="agent-b",
                prompt="Reviewer agent.",
            ),
        }
    )


def _service(
    recorder: InvocationRecorder,
    *,
    terminal_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    agent_id: str = "agent_a",
    pre_hooks: tuple[str, ...] = ("always_allow",),
    post_hooks: tuple[str, ...] = ("record_after",),
    policies_enabled: bool = True,
    use_default_terminal_metadata: bool = False,
) -> ProviderMediatedToolInvocationService:
    agents = _agents()
    policy = _policy(
        recorder,
        agents=agents,
        agent_id=agent_id,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
    )
    metadata = terminal_metadata or {
        "terminal-a": {"id": "terminal-a", "agent_id": "agent_a"},
        "terminal-b": {"id": "terminal-b", "agent_id": "agent_b"},
    }
    return ProviderMediatedToolInvocationService(
        policies={"fake": policy} if policies_enabled else {},
        agent_registry=agents,
        terminal_metadata_resolver=(
            None if use_default_terminal_metadata else lambda terminal_id: metadata.get(terminal_id)
        ),
    )


def _policy(
    recorder: InvocationRecorder,
    *,
    agents: AgentRegistry | None = None,
    agent_id: str = "agent_a",
    pre_hooks: tuple[str, ...] = ("always_allow",),
    post_hooks: tuple[str, ...] = ("record_after",),
) -> ProviderToolAccessPolicy:
    return normalize_provider_tool_access(
        provider_name="fake",
        tools=_tools(recorder),
        hooks=_hooks(recorder),
        access_requests=(
            ProviderToolAccessRequest(
                tool_name="cao_fake.lookup",
                agent_id=agent_id,
                pre_hooks=pre_hooks,
                post_hooks=post_hooks,
                location="partners.discovery",
            ),
        ),
        agent_registry=agents or _agents(),
    )


def _tools(recorder: InvocationRecorder) -> tuple[ProviderMediatedToolDefinition, ...]:
    return (
        ProviderMediatedToolDefinition(
            name="cao_fake.lookup",
            description="Lookup fake provider data",
            input_schema={"type": "object"},
            handler=recorder.handler,
        ),
    )


def _hooks(recorder: InvocationRecorder) -> tuple[ProviderToolHookDefinition, ...]:
    return (
        ProviderToolHookDefinition(
            name="always_allow",
            phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
            handler=recorder.allow_hook,
        ),
        ProviderToolHookDefinition(
            name="deny_before",
            phases=frozenset({ProviderToolHookPhase.PRE_CALL}),
            handler=recorder.deny_hook,
        ),
        ProviderToolHookDefinition(
            name="record_after",
            phases=frozenset({ProviderToolHookPhase.POST_CALL}),
            handler=recorder.post_hook,
        ),
    )


def test_allowed_invocation_runs_pre_hook_handler_and_post_hook_without_changing_result():
    recorder = InvocationRecorder()
    service = _service(recorder)

    result = service.invoke(
        terminal_id="terminal-a",
        provider_name="fake",
        tool_name="cao_fake.lookup",
        arguments={"query": "alpha"},
    )

    assert result is recorder.handler_result
    assert recorder.events == [
        "pre_call:always_allow",
        "handler:agent_a:cao_fake.lookup:alpha",
        "post_call:record_after:result",
    ]


def test_pre_call_denial_prevents_handler_execution_with_bounded_diagnostics():
    recorder = InvocationRecorder()
    service = _service(recorder, pre_hooks=("deny_before",), post_hooks=())

    with pytest.raises(ProviderMediatedToolAccessDenied) as exc_info:
        service.invoke(
            terminal_id="terminal-a",
            provider_name="fake",
            tool_name="cao_fake.lookup",
            arguments={"query": "alpha"},
        )

    assert exc_info.value.reason == "agent is not allowed to perform this fake action"
    assert exc_info.value.diagnostics == {
        "provider_name": "fake",
        "tool_name": "cao_fake.lookup",
        "hook_name": "deny_before",
        "agent": "agent_a",
        "tool": "cao_fake.lookup",
    }
    assert recorder.events == ["pre_call:deny_before"]


@pytest.mark.parametrize(
    ("terminal_id", "provider_name", "tool_name", "policies_enabled", "reason"),
    (
        ("missing-terminal", "fake", "cao_fake.lookup", True, "unknown_terminal"),
        ("terminal-b", "fake", "cao_fake.lookup", True, "missing_tool_access"),
        ("terminal-a", "missing", "cao_fake.lookup", True, "unknown_or_unavailable_provider"),
        ("terminal-a", "fake", "cao_fake.missing", True, "unknown_tool"),
        ("terminal-a", "fake", "cao_fake.lookup", False, "unknown_or_unavailable_provider"),
    ),
)
def test_provider_mediated_tools_fail_closed_before_provider_code_runs(
    terminal_id: str,
    provider_name: str,
    tool_name: str,
    policies_enabled: bool,
    reason: str,
):
    recorder = InvocationRecorder()
    service = _service(recorder, policies_enabled=policies_enabled)

    with pytest.raises(ProviderMediatedToolAccessDenied) as exc_info:
        service.invoke(
            terminal_id=terminal_id,
            provider_name=provider_name,
            tool_name=tool_name,
            arguments={"query": "alpha"},
        )

    assert exc_info.value.reason == reason
    assert recorder.events == []


def test_provider_mediated_tools_reject_invalid_terminal_agent_metadata():
    recorder = InvocationRecorder()
    service = _service(
        recorder,
        terminal_metadata={"terminal-invalid": {"id": "terminal-invalid"}},
    )

    with pytest.raises(KeyError, match="agent_id"):
        service.invoke(
            terminal_id="terminal-invalid",
            provider_name="fake",
            tool_name="cao_fake.lookup",
            arguments={"query": "alpha"},
        )

    assert recorder.events == []


def test_pre_call_denial_reason_and_diagnostics_are_bounded():
    recorder = InvocationRecorder(
        denial_reason="x" * 400,
        denial_diagnostics={f"key-{index}": "y" * 500 for index in range(12)},
    )
    service = _service(recorder, pre_hooks=("deny_before",), post_hooks=())

    with pytest.raises(ProviderMediatedToolAccessDenied) as exc_info:
        service.invoke(
            terminal_id="terminal-a",
            provider_name="fake",
            tool_name="cao_fake.lookup",
            arguments={"query": "alpha"},
        )

    assert len(exc_info.value.reason) <= 240
    assert exc_info.value.reason.endswith("...[truncated]")
    assert len(exc_info.value.diagnostics) == 9
    assert exc_info.value.diagnostics["diagnostics_truncated"] == "true"
    assert all(len(value) <= 300 for value in exc_info.value.diagnostics.values())
    assert recorder.events == ["pre_call:deny_before"]


def test_pre_call_denial_surfaces_only_provider_vetted_display_context():
    recorder = InvocationRecorder(
        denial_reason="not_allowed",
        denial_diagnostics={
            "display_detail": "The requested target is outside the configured scope.",
            "policy_reason": "This reviewer only works on assigned review issues.",
            "internal_note": "this should stay in diagnostics only",
        },
    )
    service = _service(recorder, pre_hooks=("deny_before",), post_hooks=())

    with pytest.raises(ProviderMediatedToolAccessDenied) as exc_info:
        service.invoke(
            terminal_id="terminal-a",
            provider_name="fake",
            tool_name="cao_fake.lookup",
            arguments={"query": "alpha"},
        )

    message = str(exc_info.value)
    assert "not_allowed" in message
    assert "Detail: The requested target is outside the configured scope." in message
    assert "Policy reason: This reviewer only works on assigned review issues." in message
    assert "internal_note" not in message
    assert exc_info.value.diagnostics["internal_note"] == "this should stay in diagnostics only"


def test_unconfigured_terminal_agent_fails_closed_before_provider_code_runs():
    recorder = InvocationRecorder()
    service = _service(
        recorder,
        terminal_metadata={"terminal-z": {"id": "terminal-z", "agent_id": "missing"}},
    )

    with pytest.raises(ProviderMediatedToolAccessDenied) as exc_info:
        service.invoke(
            terminal_id="terminal-z",
            provider_name="fake",
            tool_name="cao_fake.lookup",
            arguments={"query": "alpha"},
        )

    assert exc_info.value.reason == "unmapped_agent"
    assert exc_info.value.diagnostics["agent_id"] == "missing"
    assert recorder.events == []


def test_handler_failure_is_reported_cleanly_and_skips_post_hooks():
    recorder = InvocationRecorder(fail_handler=True)
    service = _service(recorder)

    with pytest.raises(ProviderMediatedToolHandlerError) as exc_info:
        service.invoke(
            terminal_id="terminal-a",
            provider_name="fake",
            tool_name="cao_fake.lookup",
            arguments={"query": "alpha"},
        )

    assert exc_info.value.reason == "handler_failed"
    assert exc_info.value.diagnostics["error"] == "provider handler exploded"
    assert recorder.events == [
        "pre_call:always_allow",
        "handler:agent_a:cao_fake.lookup:alpha",
    ]


def test_post_call_hook_failures_do_not_change_handler_result_or_roll_back():
    recorder = InvocationRecorder(fail_post_hook=True)
    service = _service(recorder)

    result = service.invoke(
        terminal_id="terminal-a",
        provider_name="fake",
        tool_name="cao_fake.lookup",
        arguments={"query": "alpha"},
    )

    assert result is recorder.handler_result
    assert recorder.events == [
        "pre_call:always_allow",
        "handler:agent_a:cao_fake.lookup:alpha",
        "post_call:record_after:result",
    ]


def test_post_call_hooks_cannot_mutate_returned_handler_result():
    recorder = InvocationRecorder(mutate_post_result=True)
    service = _service(recorder)

    result = service.invoke(
        terminal_id="terminal-a",
        provider_name="fake",
        tool_name="cao_fake.lookup",
        arguments={"query": "alpha"},
    )

    assert result == {"provider": "result"}
    assert recorder.handler_result == {"provider": "result"}


def test_unavailable_post_call_hook_does_not_change_handler_result():
    recorder = InvocationRecorder()
    agents = _agents()
    policy = ProviderToolAccessPolicy(
        provider_name="fake",
        tools={tool.name: tool for tool in _tools(recorder)},
        hooks={hook.name: hook for hook in _hooks(recorder)},
        access=(
            ProviderToolAccess(
                provider_name="fake",
                tool_name="cao_fake.lookup",
                agent_id="agent_a",
                pre_hooks=("always_allow",),
                post_hooks=("missing_after",),
                source_location="partners.discovery",
            ),
        ),
    )
    service = ProviderMediatedToolInvocationService(
        policies={"fake": policy},
        agent_registry=agents,
        terminal_metadata_resolver=lambda terminal_id: {
            "id": terminal_id,
            "agent_id": "agent_a",
        },
    )

    result = service.invoke(
        terminal_id="terminal-a",
        provider_name="fake",
        tool_name="cao_fake.lookup",
        arguments={"query": "alpha"},
    )

    assert result == {"provider": "result"}
    assert recorder.events == [
        "pre_call:always_allow",
        "handler:agent_a:cao_fake.lookup:alpha",
    ]


def test_tool_access_without_pre_call_hooks_runs_handler_directly():
    recorder = InvocationRecorder()
    agents = _agents()
    policy = ProviderToolAccessPolicy(
        provider_name="fake",
        tools={tool.name: tool for tool in _tools(recorder)},
        hooks={hook.name: hook for hook in _hooks(recorder)},
        access=(
            ProviderToolAccess(
                provider_name="fake",
                tool_name="cao_fake.lookup",
                agent_id="agent_a",
                pre_hooks=(),
                post_hooks=(),
                source_location="partners.discovery",
            ),
        ),
    )
    service = ProviderMediatedToolInvocationService(
        policies={"fake": policy},
        agent_registry=agents,
        terminal_metadata_resolver=lambda terminal_id: {
            "id": terminal_id,
            "agent_id": "agent_a",
        },
    )

    result = service.invoke(
        terminal_id="terminal-a",
        provider_name="fake",
        tool_name="cao_fake.lookup",
        arguments={"query": "alpha"},
    )

    assert result == {"provider": "result"}
    assert recorder.events == ["handler:agent_a:cao_fake.lookup:alpha"]


def test_default_terminal_metadata_path_resolves_persisted_agent(
    runtime_inbox_db_session,
):
    recorder = InvocationRecorder()
    db_module.create_terminal(
        "terminal-db",
        "cao-session",
        "window-0",
        "codex",
        "agent_a",
        workspace_context_id=db_module.ensure_default_workspace_context("agent_a").id,
    )
    service = _service(recorder, use_default_terminal_metadata=True)

    result = service.invoke(
        terminal_id="terminal-db",
        provider_name="fake",
        tool_name="cao_fake.lookup",
        arguments={"query": "alpha"},
    )

    assert result == {"provider": "result"}
    assert recorder.events == [
        "pre_call:always_allow",
        "handler:agent_a:cao_fake.lookup:alpha",
        "post_call:record_after:result",
    ]
