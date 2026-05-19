"""CAO-owned invocation lifecycle for provider-mediated tools."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from cli_agent_orchestrator.agent import AgentRegistry
from cli_agent_orchestrator.services.agent_manager import (
    AgentManager,
    default_agent_manager,
)
from cli_agent_orchestrator.services.tool_service import ToolService
from cli_agent_orchestrator.workspace_providers.tool_access import (
    ProviderMediatedToolDefinition,
    ProviderToolAccess,
    ProviderToolAccessPolicy,
    ProviderToolHookDefinition,
    ProviderToolHookPhase,
    ProviderToolInvocationContext,
    ProviderToolPreCallResult,
)

logger = logging.getLogger(__name__)

TerminalMetadataResolver = Callable[[str], Mapping[str, Any] | None]
_MAX_REASON_CHARS = 240
_MAX_DIAGNOSTIC_ENTRIES = 8
_MAX_DIAGNOSTIC_KEY_CHARS = 80
_MAX_DIAGNOSTIC_VALUE_CHARS = 300
_TRUNCATED = "...[truncated]"


class ProviderMediatedToolInvocationError(RuntimeError):
    """Base error for provider-mediated invocation failures."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.reason = _bounded_text(reason, limit=_MAX_REASON_CHARS)
        self.diagnostics = _bounded_diagnostics(diagnostics or {})
        super().__init__(message)


class ProviderMediatedToolAccessDenied(ProviderMediatedToolInvocationError):
    """Raised when a mediated provider tool call is denied before handling."""


class ProviderMediatedToolHandlerError(ProviderMediatedToolInvocationError):
    """Raised when the provider-owned tool handler fails."""


@dataclass(frozen=True)
class ProviderMediatedToolInvocationService:
    """Resolve agent access and run the provider-mediated call lifecycle."""

    policies: Mapping[str, ProviderToolAccessPolicy]
    agent_registry: AgentRegistry | None = None
    agent_manager: AgentManager | None = None
    terminal_metadata_resolver: TerminalMetadataResolver | None = None
    tool_service: ToolService | None = None
    built_in_tool_names: Iterable[str] = ()

    def invoke(
        self,
        *,
        terminal_id: str,
        provider_name: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Invoke a provider-mediated tool for an agent-managed terminal."""
        normalized_tool_name = tool_name.strip()
        agent = self._resolve_agent_for_terminal(terminal_id)
        policy = self._resolve_policy(provider_name, agent.id)
        tool = self._resolve_tool(policy, normalized_tool_name)
        access = self._resolve_access(policy, agent.id, normalized_tool_name)
        decision = self._tool_service().can_invoke(
            agent.id,
            normalized_tool_name,
            provider_name=policy.provider_name,
            built_in_tool_names=self.built_in_tool_names,
            context={"terminal_id": terminal_id},
        )
        if not decision.allowed:
            raise ProviderMediatedToolAccessDenied(
                "Provider-mediated tool call denied by ToolService",
                reason=decision.reason,
                diagnostics=decision.diagnostics,
            )
        context = ProviderToolInvocationContext(
            provider_name=policy.provider_name,
            tool_name=normalized_tool_name,
            terminal_id=terminal_id,
            agent=agent,
            arguments=arguments,
            access=access,
        )

        self._run_pre_call_hooks(policy, context)
        result = self._run_handler(tool, context, arguments)
        self._run_post_call_hooks(policy, context, result)
        return result

    def accessible_tools_for_terminal(
        self, terminal_id: str
    ) -> tuple[tuple[str, ProviderMediatedToolDefinition], ...]:
        """Return provider-mediated tools visible to an agent-managed terminal.

        The same terminal-to-agent resolution used for invocation is used
        here so MCP registration fails closed for raw, unknown, or unmapped
        terminals without widening provider access.
        """
        agent = self._resolve_agent_for_terminal(terminal_id)
        return self._tool_service().provider_mediated_tools_for_agent(
            agent.id,
            built_in_tool_names=self.built_in_tool_names,
        )

    def _resolve_policy(self, provider_name: str, agent_id: str) -> ProviderToolAccessPolicy:
        normalized = provider_name.strip()
        policy = self._tool_service().provider_policies_for_agent(agent_id).get(normalized)
        if policy is None:
            raise ProviderMediatedToolAccessDenied(
                f"Provider-mediated tool call denied: unknown or unavailable provider {normalized!r}",
                reason="unknown_or_unavailable_provider",
                diagnostics={"provider_name": normalized},
            )
        return policy

    def _resolve_tool(
        self, policy: ProviderToolAccessPolicy, tool_name: str
    ) -> ProviderMediatedToolDefinition:
        normalized = tool_name.strip()
        tool = policy.tools.get(normalized)
        if tool is None:
            raise ProviderMediatedToolAccessDenied(
                f"Provider-mediated tool call denied: unknown tool {normalized!r}",
                reason="unknown_tool",
                diagnostics={"provider_name": policy.provider_name, "tool_name": normalized},
            )
        return tool

    def _resolve_agent_for_terminal(self, terminal_id: str):
        metadata = self._terminal_metadata_resolver()(terminal_id)
        if metadata is None:
            raise ProviderMediatedToolAccessDenied(
                "Provider-mediated tool call denied: terminal is unknown",
                reason="unknown_terminal",
                diagnostics={"terminal_id": terminal_id},
            )

        agent_id = metadata["agent_id"]
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise RuntimeError(f"Terminal {terminal_id!r} has invalid agent_id metadata")
        normalized_agent_id = agent_id.strip()
        try:
            return self._agent_manager().resolve_agent(normalized_agent_id)
        except Exception as exc:
            raise ProviderMediatedToolAccessDenied(
                "Provider-mediated tool call denied: terminal agent is not configured",
                reason="unmapped_agent",
                diagnostics={
                    "terminal_id": terminal_id,
                    "agent_id": normalized_agent_id,
                },
            ) from exc

    def _agent_manager(self) -> AgentManager:
        if self.agent_manager is not None:
            return self.agent_manager
        if self.agent_registry is not None:
            return AgentManager(configured_agents=self.agent_registry)
        return default_agent_manager()

    def _resolve_access(
        self, policy: ProviderToolAccessPolicy, agent_id: str, tool_name: str
    ) -> ProviderToolAccess:
        for entry in policy.access:
            if entry.agent_id == agent_id and entry.tool_name == tool_name:
                return entry
        raise ProviderMediatedToolAccessDenied(
            "Provider-mediated tool call denied: agent has no configured tool access",
            reason="missing_tool_access",
            diagnostics={
                "provider_name": policy.provider_name,
                "agent_id": agent_id,
                "tool_name": tool_name,
            },
        )

    def _run_pre_call_hooks(
        self,
        policy: ProviderToolAccessPolicy,
        context: ProviderToolInvocationContext,
    ) -> None:
        for hook_name in context.access.pre_hooks:
            hook = self._resolve_hook(policy, hook_name, ProviderToolHookPhase.PRE_CALL)
            hook_context = context.for_hook(
                hook_name=hook_name,
                phase=ProviderToolHookPhase.PRE_CALL,
            )
            try:
                decision = hook.handler(hook_context)
            except Exception as exc:
                raise ProviderMediatedToolAccessDenied(
                    "Provider-mediated tool call denied: pre-call hook failed",
                    reason="pre_call_hook_failed",
                    diagnostics={
                        "provider_name": policy.provider_name,
                        "tool_name": context.tool_name,
                        "hook_name": hook_name,
                        "error": str(exc),
                    },
                ) from exc

            if not isinstance(decision, ProviderToolPreCallResult):
                raise ProviderMediatedToolAccessDenied(
                    "Provider-mediated tool call denied: pre-call hook returned an invalid decision",
                    reason="invalid_pre_call_hook_result",
                    diagnostics={
                        "provider_name": policy.provider_name,
                        "tool_name": context.tool_name,
                        "hook_name": hook_name,
                    },
                )
            if not decision.allowed:
                message = "Provider-mediated tool call denied by pre-call hook"
                if decision.reason:
                    message = f"{message}: {decision.reason}"
                message = _append_display_denial_context(
                    message,
                    decision.diagnostics or {},
                )
                raise ProviderMediatedToolAccessDenied(
                    message,
                    reason=decision.reason or "pre_call_hook_denied",
                    diagnostics={
                        "provider_name": policy.provider_name,
                        "tool_name": context.tool_name,
                        "hook_name": hook_name,
                        **dict(decision.diagnostics or {}),
                    },
                )

    def _run_handler(
        self,
        tool: ProviderMediatedToolDefinition,
        context: ProviderToolInvocationContext,
        arguments: Mapping[str, Any],
    ) -> Any:
        try:
            return tool.handler(context, arguments)
        except Exception as exc:
            raise ProviderMediatedToolHandlerError(
                f"Provider-mediated tool handler failed for {context.tool_name!r}: {exc}",
                reason="handler_failed",
                diagnostics={
                    "provider_name": context.provider_name,
                    "tool_name": context.tool_name,
                    "error": str(exc),
                },
            ) from exc

    def _run_post_call_hooks(
        self,
        policy: ProviderToolAccessPolicy,
        context: ProviderToolInvocationContext,
        result: Any,
    ) -> None:
        for hook_name in context.access.post_hooks:
            try:
                hook = self._resolve_hook(policy, hook_name, ProviderToolHookPhase.POST_CALL)
                hook_context = context.for_hook(
                    hook_name=hook_name,
                    phase=ProviderToolHookPhase.POST_CALL,
                    handler_result=_copy_for_post_hook(result),
                )
                hook.handler(hook_context)
            except Exception:
                logger.exception(
                    "Post-call hook %r failed for mediated provider tool %r",
                    hook_name,
                    context.tool_name,
                )

    def _resolve_hook(
        self,
        policy: ProviderToolAccessPolicy,
        hook_name: str,
        phase: ProviderToolHookPhase,
    ) -> ProviderToolHookDefinition:
        hook = policy.hooks.get(hook_name)
        if hook is None or phase not in hook.phases:
            raise ProviderMediatedToolAccessDenied(
                "Provider-mediated tool call denied: configured hook is unavailable",
                reason="unavailable_hook",
                diagnostics={
                    "provider_name": policy.provider_name,
                    "hook_name": hook_name,
                    "phase": phase.value,
                },
            )
        return hook

    def _terminal_metadata_resolver(self) -> TerminalMetadataResolver:
        if self.terminal_metadata_resolver is not None:
            return self.terminal_metadata_resolver
        from cli_agent_orchestrator.clients.database import get_terminal_metadata

        return get_terminal_metadata

    def _tool_service(self) -> ToolService:
        if self.tool_service is not None:
            return self.tool_service
        manager = self.agent_manager
        if manager is None and self.agent_registry is not None:
            manager = AgentManager(configured_agents=self.agent_registry)
        return ToolService(
            agent_manager=manager or default_agent_manager(),
            terminal_metadata_resolver=self._terminal_metadata_resolver(),
            provider_policy_loader=lambda _registry: self.policies,
        )


def _bounded_text(value: Any, *, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(_TRUNCATED))] + _TRUNCATED


def _bounded_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, str]:
    bounded: dict[str, str] = {}
    for index, (key, value) in enumerate(diagnostics.items()):
        if index >= _MAX_DIAGNOSTIC_ENTRIES:
            bounded["diagnostics_truncated"] = "true"
            break
        bounded[_bounded_text(key, limit=_MAX_DIAGNOSTIC_KEY_CHARS)] = _bounded_text(
            value,
            limit=_MAX_DIAGNOSTIC_VALUE_CHARS,
        )
    return bounded


def _append_display_denial_context(message: str, diagnostics: Mapping[str, Any]) -> str:
    """Append only provider-vetted, agent-visible denial context."""
    display_detail = diagnostics.get("display_detail")
    policy_reason = diagnostics.get("policy_reason")
    parts: list[str] = []
    if display_detail:
        parts.append(
            f"Detail: {_bounded_text(str(display_detail), limit=_MAX_DIAGNOSTIC_VALUE_CHARS)}"
        )
    if policy_reason:
        parts.append(
            f"Policy reason: {_bounded_text(str(policy_reason), limit=_MAX_DIAGNOSTIC_VALUE_CHARS)}"
        )
    if not parts:
        return message
    return f"{message}. {' '.join(parts)}"


def _copy_for_post_hook(result: Any) -> Any:
    try:
        return deepcopy(result)
    except Exception:
        return None


__all__ = [
    "ProviderMediatedToolAccessDenied",
    "ProviderMediatedToolHandlerError",
    "ProviderMediatedToolInvocationError",
    "ProviderMediatedToolInvocationService",
    "TerminalMetadataResolver",
]
