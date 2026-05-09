"""Provider-mediated MCP tool access contract.

Workspace providers own provider-specific configuration and vocabulary. This
module owns the CAO-neutral contract providers use after parsing that config:
declared tools, declared hooks, requested access targets, and preflight
normalization into identity-scoped access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol

from cli_agent_orchestrator.agent_identity import AgentIdentity, AgentIdentityRegistry


class ProviderToolHookPhase(str, Enum):
    """CAO-understood hook phases for provider-mediated tool calls."""

    PRE_CALL = "pre_call"
    POST_CALL = "post_call"


class ProviderToolHandler(Protocol):
    """Provider-owned handler boundary for a candidate mediated tool."""

    def __call__(
        self, context: "ProviderToolInvocationContext", arguments: Mapping[str, Any]
    ) -> Any:
        """Execute a provider-owned tool handler."""


class ProviderToolHookHandler(Protocol):
    """Provider-owned hook boundary for a mediated tool call."""

    def __call__(
        self, context: "ProviderToolInvocationContext"
    ) -> "ProviderToolPreCallResult | None":
        """Run a provider-owned hook."""


@dataclass(frozen=True)
class ProviderMediatedToolDefinition:
    """A provider-declared candidate MCP-style tool."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: ProviderToolHandler
    runtime_generation: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderToolHookDefinition:
    """A provider-declared hook name and its supported phases."""

    name: str
    phases: frozenset[ProviderToolHookPhase]
    handler: ProviderToolHookHandler


@dataclass(frozen=True)
class ProviderToolAccessRequest:
    """CAO-neutral access request produced from provider-specific config."""

    tool_name: str
    location: str
    agent_identity_id: str | None = None
    agent_profile: str | None = None
    pre_hooks: tuple[str, ...] = ()
    post_hooks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderToolAccess:
    """Validated provider-mediated tool access for a CAO agent identity."""

    provider_name: str
    tool_name: str
    agent_identity_id: str
    agent_profile: str
    pre_hooks: tuple[str, ...]
    post_hooks: tuple[str, ...]
    source_location: str


@dataclass(frozen=True)
class ProviderMediatedToolSurfaceDescriptor:
    """Stable agent-facing provider-mediated MCP tool contract."""

    provider_name: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    pre_hooks: tuple[str, ...]
    post_hooks: tuple[str, ...]


@dataclass(frozen=True)
class ProviderMediatedToolRuntimeGenerationDescriptor:
    """Stable provider-owned runtime material for a visible mediated tool."""

    provider_name: str
    name: str
    runtime_generation: Mapping[str, Any]


@dataclass(frozen=True)
class ProviderToolInvocationContext:
    """CAO-neutral context for provider-mediated handlers and hooks."""

    provider_name: str
    tool_name: str
    terminal_id: str
    agent_identity: AgentIdentity
    arguments: Mapping[str, Any]
    access: ProviderToolAccess
    hook_name: str | None = None
    phase: ProviderToolHookPhase | None = None
    handler_result: Any = None

    def for_hook(
        self,
        *,
        hook_name: str,
        phase: ProviderToolHookPhase,
        handler_result: Any = None,
    ) -> "ProviderToolInvocationContext":
        """Return this invocation context annotated for one hook call."""
        return ProviderToolInvocationContext(
            provider_name=self.provider_name,
            tool_name=self.tool_name,
            terminal_id=self.terminal_id,
            agent_identity=self.agent_identity,
            arguments=self.arguments,
            access=self.access,
            hook_name=hook_name,
            phase=phase,
            handler_result=handler_result,
        )


@dataclass(frozen=True)
class ProviderToolPreCallResult:
    """Provider hook decision for the pre-call phase."""

    allowed: bool
    reason: str = ""
    diagnostics: Mapping[str, Any] | None = None

    @classmethod
    def allow(cls) -> "ProviderToolPreCallResult":
        return cls(allowed=True)

    @classmethod
    def deny(
        cls, reason: str, diagnostics: Mapping[str, Any] | None = None
    ) -> "ProviderToolPreCallResult":
        return cls(allowed=False, reason=reason.strip(), diagnostics=diagnostics)


@dataclass(frozen=True)
class ProviderToolAccessIssue:
    """One provider config preflight issue with a user-actionable location."""

    location: str
    reason: str

    def format(self) -> str:
        return f"{self.location}: {self.reason}"


class ProviderToolAccessConfigError(ValueError):
    """Raised when provider-mediated tool access config fails preflight."""

    def __init__(self, provider_name: str, issues: list[ProviderToolAccessIssue]) -> None:
        self.provider_name = provider_name
        self.issues = tuple(issues)
        formatted = "; ".join(issue.format() for issue in self.issues)
        super().__init__(f"{provider_name} provider tool access config is invalid: {formatted}")


@dataclass(frozen=True)
class ProviderToolAccessPolicy:
    """Validated provider-mediated tools, hooks, and identity-scoped access."""

    provider_name: str
    tools: Mapping[str, ProviderMediatedToolDefinition]
    hooks: Mapping[str, ProviderToolHookDefinition]
    access: tuple[ProviderToolAccess, ...]

    def access_for_identity(self, identity: AgentIdentity) -> tuple[ProviderToolAccess, ...]:
        """Return the provider tool access entries for one CAO identity instance."""
        return tuple(entry for entry in self.access if entry.agent_identity_id == identity.id)

    def can_identity_access_tool(self, identity: AgentIdentity, tool_name: str) -> bool:
        """Return whether an identity has normalized access to a provider tool."""
        return any(entry.tool_name == tool_name for entry in self.access_for_identity(identity))

    def surface_descriptors_for_identity(
        self, identity: AgentIdentity
    ) -> tuple[ProviderMediatedToolSurfaceDescriptor, ...]:
        """Return stable visible tool contracts for one identity.

        Provider access owns the mapping from identity to tool plus configured
        hooks, so this projection intentionally lives beside that access policy.
        Handler callables, source locations, credentials, and runtime data are
        excluded because they are not part of the agent-visible MCP contract.
        """
        descriptors: list[ProviderMediatedToolSurfaceDescriptor] = []
        for access in self.access_for_identity(identity):
            tool = self.tools.get(access.tool_name)
            if tool is None:
                continue
            descriptors.append(
                ProviderMediatedToolSurfaceDescriptor(
                    provider_name=self.provider_name,
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    pre_hooks=access.pre_hooks,
                    post_hooks=access.post_hooks,
                )
            )
        return tuple(sorted(descriptors, key=lambda item: (item.provider_name, item.name)))

    def runtime_generation_descriptors_for_identity(
        self, identity: AgentIdentity
    ) -> tuple[ProviderMediatedToolRuntimeGenerationDescriptor, ...]:
        """Return visible tool implementation/runtime material for one identity."""
        descriptors: list[ProviderMediatedToolRuntimeGenerationDescriptor] = []
        for access in self.access_for_identity(identity):
            tool = self.tools.get(access.tool_name)
            if tool is None:
                continue
            descriptors.append(
                ProviderMediatedToolRuntimeGenerationDescriptor(
                    provider_name=self.provider_name,
                    name=tool.name,
                    runtime_generation=tool.runtime_generation,
                )
            )
        return tuple(sorted(descriptors, key=lambda item: (item.provider_name, item.name)))


def normalize_provider_tool_access(
    *,
    provider_name: str,
    tools: tuple[ProviderMediatedToolDefinition, ...],
    hooks: tuple[ProviderToolHookDefinition, ...],
    access_requests: tuple[ProviderToolAccessRequest, ...],
    agent_registry: AgentIdentityRegistry,
    profile_exists: Callable[[str], bool],
) -> ProviderToolAccessPolicy:
    """Validate provider declarations and normalize config to identity access.

    Providers call this after translating provider-specific user config into
    ``ProviderToolAccessRequest`` records. CAO then consumes the returned policy
    without knowing any provider-native config vocabulary.
    """
    issues: list[ProviderToolAccessIssue] = []
    normalized_provider = _normalize_required_name(
        provider_name,
        location="provider",
        label="provider name",
        issues=issues,
    )
    tool_by_name = _index_tools(tools, issues)
    hook_by_name = _index_hooks(hooks, issues)
    access: list[ProviderToolAccess] = []
    seen_effective_entries: dict[tuple[str, str], ProviderToolAccess] = {}

    identities_by_profile = _identities_by_profile(agent_registry)
    identity_by_id = agent_registry.all()

    for request_index, request in enumerate(access_requests):
        request_issue_count = len(issues)
        request_location = request.location or f"tool_access[{request_index}]"
        tool_name = request.tool_name.strip()
        if not tool_name:
            issues.append(ProviderToolAccessIssue(request_location, "tool name must be non-empty"))
        elif tool_name not in tool_by_name:
            issues.append(
                ProviderToolAccessIssue(
                    request_location,
                    f"unknown provider-mediated tool: {tool_name}",
                )
            )

        pre_hooks = _validate_hooks(
            hook_names=request.pre_hooks,
            hook_by_name=hook_by_name,
            phase=ProviderToolHookPhase.PRE_CALL,
            location=f"{request_location}.pre_hooks",
            issues=issues,
        )
        post_hooks = _validate_hooks(
            hook_names=request.post_hooks,
            hook_by_name=hook_by_name,
            phase=ProviderToolHookPhase.POST_CALL,
            location=f"{request_location}.post_hooks",
            issues=issues,
        )
        target_id = request.agent_identity_id.strip() if request.agent_identity_id else None
        target_profile = request.agent_profile.strip() if request.agent_profile else None
        target_identities = _resolve_target_identities(
            identity_by_id=identity_by_id,
            identities_by_profile=identities_by_profile,
            agent_identity_id=target_id,
            agent_profile=target_profile,
            location=request_location,
            profile_exists=profile_exists,
            issues=issues,
        )

        if len(issues) > request_issue_count:
            continue

        for identity in target_identities:
            entry = ProviderToolAccess(
                provider_name=normalized_provider,
                tool_name=tool_name,
                agent_identity_id=identity.id,
                agent_profile=identity.agent_profile,
                pre_hooks=pre_hooks,
                post_hooks=post_hooks,
                source_location=request_location,
            )
            key = (entry.agent_identity_id, entry.tool_name)
            previous = seen_effective_entries.get(key)
            if previous is not None:
                issues.append(
                    ProviderToolAccessIssue(
                        request_location,
                        "duplicates or conflicts with provider tool access entry at "
                        f"{previous.source_location} for identity {entry.agent_identity_id} "
                        f"and tool {entry.tool_name}",
                    )
                )
                continue
            seen_effective_entries[key] = entry
            access.append(entry)

    if issues:
        raise ProviderToolAccessConfigError(normalized_provider or provider_name, issues)

    return ProviderToolAccessPolicy(
        provider_name=normalized_provider,
        tools=tool_by_name,
        hooks=hook_by_name,
        access=tuple(access),
    )


def _normalize_required_name(
    value: str,
    *,
    location: str,
    label: str,
    issues: list[ProviderToolAccessIssue],
) -> str:
    normalized = value.strip()
    if not normalized:
        issues.append(ProviderToolAccessIssue(location, f"{label} must be non-empty"))
    return normalized


def _index_tools(
    tools: tuple[ProviderMediatedToolDefinition, ...],
    issues: list[ProviderToolAccessIssue],
) -> dict[str, ProviderMediatedToolDefinition]:
    indexed: dict[str, ProviderMediatedToolDefinition] = {}
    for index, tool in enumerate(tools):
        location = f"tools[{index}]"
        name = _normalize_required_name(
            tool.name,
            location=f"{location}.name",
            label="tool name",
            issues=issues,
        )
        if not name:
            continue
        if name in indexed:
            issues.append(
                ProviderToolAccessIssue(
                    f"{location}.name",
                    f"duplicate provider-mediated tool definition: {name}",
                )
            )
            continue
        indexed[name] = tool
    return indexed


def _index_hooks(
    hooks: tuple[ProviderToolHookDefinition, ...],
    issues: list[ProviderToolAccessIssue],
) -> dict[str, ProviderToolHookDefinition]:
    indexed: dict[str, ProviderToolHookDefinition] = {}
    for index, hook in enumerate(hooks):
        location = f"hooks[{index}]"
        name = _normalize_required_name(
            hook.name,
            location=f"{location}.name",
            label="hook name",
            issues=issues,
        )
        if not name:
            continue
        if not hook.phases:
            issues.append(
                ProviderToolAccessIssue(
                    f"{location}.phases",
                    f"hook {name} must support at least one phase",
                )
            )
        if name in indexed:
            issues.append(
                ProviderToolAccessIssue(
                    f"{location}.name",
                    f"duplicate provider hook definition: {name}",
                )
            )
            continue
        indexed[name] = hook
    return indexed


def _validate_hooks(
    *,
    hook_names: tuple[str, ...],
    hook_by_name: Mapping[str, ProviderToolHookDefinition],
    phase: ProviderToolHookPhase,
    location: str,
    issues: list[ProviderToolAccessIssue],
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_name in enumerate(hook_names):
        hook_location = f"{location}[{index}]"
        name = raw_name.strip()
        if not name:
            issues.append(ProviderToolAccessIssue(hook_location, "hook name must be non-empty"))
            continue
        hook = hook_by_name.get(name)
        if hook is None:
            issues.append(ProviderToolAccessIssue(hook_location, f"unknown hook: {name}"))
            continue
        if phase not in hook.phases:
            issues.append(
                ProviderToolAccessIssue(
                    hook_location,
                    f"hook {name} does not support phase {phase.value}",
                )
            )
            continue
        if name in seen:
            issues.append(ProviderToolAccessIssue(hook_location, f"duplicate hook entry: {name}"))
            continue
        seen.add(name)
        normalized.append(name)
    return tuple(normalized)


def _resolve_target_identities(
    *,
    identity_by_id: Mapping[str, AgentIdentity],
    identities_by_profile: Mapping[str, tuple[AgentIdentity, ...]],
    agent_identity_id: str | None,
    agent_profile: str | None,
    location: str,
    profile_exists: Callable[[str], bool],
    issues: list[ProviderToolAccessIssue],
) -> tuple[AgentIdentity, ...]:
    if bool(agent_identity_id) == bool(agent_profile):
        issues.append(
            ProviderToolAccessIssue(
                location,
                "exactly one of agent_identity_id or agent_profile must be configured",
            )
        )
        return ()

    if agent_identity_id:
        identity = identity_by_id.get(agent_identity_id)
        if identity is None:
            issues.append(
                ProviderToolAccessIssue(
                    f"{location}.agent_identity_id",
                    f"unknown CAO agent identity: {agent_identity_id}",
                )
            )
            return ()
        return (identity,)

    assert agent_profile is not None
    if not profile_exists(agent_profile):
        issues.append(
            ProviderToolAccessIssue(
                f"{location}.agent_profile",
                f"unknown CAO agent profile: {agent_profile}",
            )
        )
        return ()

    identities = identities_by_profile.get(agent_profile, ())
    if not identities:
        issues.append(
            ProviderToolAccessIssue(
                f"{location}.agent_profile",
                f"no configured CAO agent identities use profile: {agent_profile}",
            )
        )
    return identities


def _identities_by_profile(
    agent_registry: AgentIdentityRegistry,
) -> dict[str, tuple[AgentIdentity, ...]]:
    grouped: dict[str, list[AgentIdentity]] = {}
    for identity in agent_registry.all().values():
        grouped.setdefault(identity.agent_profile, []).append(identity)
    return {profile: tuple(identities) for profile, identities in grouped.items()}


__all__ = [
    "ProviderMediatedToolDefinition",
    "ProviderMediatedToolRuntimeGenerationDescriptor",
    "ProviderMediatedToolSurfaceDescriptor",
    "ProviderToolAccess",
    "ProviderToolAccessConfigError",
    "ProviderToolAccessIssue",
    "ProviderToolAccessPolicy",
    "ProviderToolAccessRequest",
    "ProviderToolHandler",
    "ProviderToolHookHandler",
    "ProviderToolHookDefinition",
    "ProviderToolHookPhase",
    "ProviderToolInvocationContext",
    "ProviderToolPreCallResult",
    "normalize_provider_tool_access",
]
