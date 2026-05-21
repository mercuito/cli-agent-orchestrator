"""CLI Agent Orchestrator MCP Server implementation."""

import asyncio
import functools
import inspect
import logging
import os
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

import requests  # type: ignore[import-untyped]
from fastmcp import FastMCP
from pydantic import Field

from cli_agent_orchestrator.agent import (
    Agent,
    AgentConfigError,
    AgentRegistry,
    load_agent,
    load_agent_registry,
)
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.constants import API_BASE_URL
from cli_agent_orchestrator.mcp_server.freshness import (
    build_agent_mcp_runtime_generation_descriptor,
    build_agent_mcp_surface_descriptor,
    callable_runtime_fingerprint,
    fingerprint_agent_mcp_surface,
)
from cli_agent_orchestrator.mcp_server.models import HandoffResult
from cli_agent_orchestrator.mcp_server.provider_tools import (
    register_provider_mediated_mcp_tools_for_terminal,
)
from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.provider_conversations.inbox_access import (
    InboxReadError,
)
from cli_agent_orchestrator.provider_conversations.inbox_access import (
    read_inbox_message as read_provider_inbox_message,
)
from cli_agent_orchestrator.provider_conversations.inbox_access import (
    read_result_to_dict,
)
from cli_agent_orchestrator.provider_conversations.reply_service import (
    ProviderConversationReplyError,
)
from cli_agent_orchestrator.provider_conversations.reply_service import (
    reply_to_inbox_message as route_provider_inbox_reply,
)
from cli_agent_orchestrator.services import baton_service
from cli_agent_orchestrator.services.agent_manager import AgentManager
from cli_agent_orchestrator.services.baton_feature import BATON_MCP_TOOL_NAMES, is_baton_enabled
from cli_agent_orchestrator.services.tool_service import ToolService, default_tool_service
from cli_agent_orchestrator.utils.terminal import wait_until_terminal_status
from cli_agent_orchestrator.workspaces import (
    WorkspaceConfigError,
    default_workspace_collaboration_manager,
)
from cli_agent_orchestrator.workspace_tool_providers.registry import (
    WorkspaceToolProviderConfigError,
)
from cli_agent_orchestrator.workspace_tool_providers.tool_access import (
    ProviderToolAccessConfigError,
    ProviderToolAccessPolicy,
)

logger = logging.getLogger(__name__)

# Environment variable to enable/disable working_directory parameter
ENABLE_WORKING_DIRECTORY = os.getenv("CAO_ENABLE_WORKING_DIRECTORY", "false").lower() == "true"

# Environment variable to enable/disable automatic sender terminal ID injection
ENABLE_SENDER_ID_INJECTION = os.getenv("CAO_ENABLE_SENDER_ID_INJECTION", "false").lower() == "true"

# Create MCP server
mcp = FastMCP(
    "cao-mcp-server",
    instructions="""
    # CLI Agent Orchestrator MCP Server

    This server provides tools to facilitate terminal delegation within CLI Agent Orchestrator sessions.

    ## Best Practices

    - Use specific agents (provider is inferred from profile metadata when set)
    - Provide clear and concise messages
    - Ensure you're running within a CAO terminal (CAO_TERMINAL_ID must be set)
    """,
)

# Deferred tool registry. Each @_deferred_tool(...) decoration records its
# function here at import time; actual FastMCP tool registration happens in
# main() after the per-terminal allowlist has been resolved. This lets us
# gate which tools the LLM sees (and can call) based on the agent's profile
# without changing any tool implementation bodies.
_PENDING_TOOLS: List[Tuple[str, Callable, Dict[str, Any]]] = []


def pending_builtin_mcp_tools() -> tuple[tuple[str, Callable, Dict[str, Any]], ...]:
    """Return built-in MCP tool definitions owned by the MCP server."""
    return tuple(_PENDING_TOOLS)


def built_in_cao_tool_names(
    pending: Iterable[Tuple[str, Callable, Dict[str, Any]]] | None = None,
    *,
    include_disabled: bool = False,
) -> tuple[str, ...]:
    """Return currently available CAO-owned built-in MCP tool definition names."""
    tools = _PENDING_TOOLS if pending is None else pending
    baton_enabled = is_baton_enabled()
    return tuple(
        name
        for name, _, _ in tools
        if include_disabled or baton_enabled or name not in BATON_MCP_TOOL_NAMES
    )


def built_in_cao_tool_descriptors() -> tuple[dict[str, str], ...]:
    """Return backend-owned descriptors for grantable built-in CAO MCP tools."""
    grantable = set(built_in_cao_tool_names(include_disabled=True))
    return tuple(
        {
            "name": name,
            "description": str(kwargs.get("description", "")),
        }
        for name, _fn, kwargs in _PENDING_TOOLS
        if name in grantable
    )


def _deferred_tool(name: Optional[str] = None, **tool_kwargs: Any) -> Callable:
    """Drop-in replacement for FastMCP's @mcp.tool() that defers registration.

    The wrapped function is returned unchanged (so other call sites and
    tests can still import and invoke it directly) and recorded in
    _PENDING_TOOLS for later registration via _register_tools().
    """

    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        _PENDING_TOOLS.append((tool_name, fn, dict(tool_kwargs)))
        return fn

    return decorator


def _register_tools(
    pending: List[Tuple[str, Callable, Dict[str, Any]]],
    mcp_instance: Any,
    *,
    terminal_id: str | None = None,
    tool_service: ToolService | None = None,
) -> List[str]:
    """Apply FastMCP's @mcp.tool() to tools registered by ToolService.

    Args:
        pending: Items from the deferred registry.
        mcp_instance: The FastMCP instance to register against.

    Returns:
        Names of tools actually registered, in the order they appeared.
    """
    registered: List[str] = []
    service = tool_service or default_tool_service()
    built_in_names = built_in_cao_tool_names(pending)
    if not terminal_id:
        logger.warning(
            "No CAO_TERMINAL_ID is available; ToolService cannot resolve MCP "
            "tool registration, so built-in CAO MCP tools are not registered"
        )
        allowed: set[str] = set()
    else:
        try:
            registration = service.registered_tools_for_terminal(
                terminal_id,
                built_in_tool_names=built_in_names,
            )
            allowed = set(registration.built_in_tools)
        except Exception as exc:
            logger.warning(
                "Failed to resolve ToolService registration for terminal %r: %s. "
                "Registering no built-in CAO MCP tools.",
                terminal_id,
                exc,
            )
            allowed = set()
    for tool_name, fn, kwargs in pending:
        if tool_name not in allowed:
            logger.info("Tool %r denied by ToolService registration decision", tool_name)
            continue
        mcp_instance.tool(**kwargs)(
            _toolservice_authorized_callable(
                tool_name=tool_name,
                fn=fn,
                terminal_id=terminal_id,
                tool_service=service,
                built_in_tool_names=lambda: built_in_cao_tool_names(pending),
            )
        )
        registered.append(tool_name)
    return registered


def _toolservice_authorized_callable(
    *,
    tool_name: str,
    fn: Callable,
    terminal_id: str | None,
    tool_service: ToolService,
    built_in_tool_names: Callable[[], Iterable[str]],
) -> Callable:
    """Wrap a FastMCP callable with per-invocation ToolService authorization."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not terminal_id:
            raise PermissionError(
                f"CAO MCP tool {tool_name!r} denied by ToolService: " "missing terminal context"
            )
        if tool_name == "terminate":
            target_terminal_id = _bound_tool_argument(fn, args, kwargs, "terminal_id")
            if not isinstance(target_terminal_id, str) or not target_terminal_id.strip():
                raise PermissionError(
                    "CAO MCP tool 'terminate' denied by ToolService: " "missing target terminal"
                )
            decision = tool_service.can_invoke_for_terminal_target(
                terminal_id,
                tool_name,
                target_terminal_id=target_terminal_id.strip(),
                built_in_tool_names=built_in_tool_names(),
            )
        else:
            decision = tool_service.can_invoke_for_terminal(
                terminal_id,
                tool_name,
                built_in_tool_names=built_in_tool_names(),
            )
        if not decision.allowed:
            raise PermissionError(
                f"CAO MCP tool {tool_name!r} denied by ToolService: {decision.reason}"
            )
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
    return wrapper


def _bound_tool_argument(
    fn: Callable, args: tuple[Any, ...], kwargs: dict[str, Any], name: str
) -> Any:
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
    except TypeError:
        return kwargs.get(name)
    return bound.arguments.get(name)


def build_mcp_surface_descriptor_for_agent(
    agent: Agent,
    *,
    agent_registry: Optional[AgentRegistry] = None,
    provider_policies: Optional[Dict[str, ProviderToolAccessPolicy]] = None,
) -> Dict[str, Any]:
    """Build the stable MCP surface descriptor for one agent."""
    service = ToolService(
        agent_manager=AgentManager(
            configured_agents=agent_registry or AgentRegistry({agent.id: agent})
        )
    )
    if provider_policies is None:
        return dict(
            service.mcp_surface_descriptor_for_agent(
                agent.id,
                built_in_tools=_PENDING_TOOLS,
                built_in_tool_names=built_in_cao_tool_names(),
                baton_enabled=True,
            )
        )
    access = service.tools_for_agent(agent.id, built_in_tool_names=built_in_cao_tool_names())
    return build_agent_mcp_surface_descriptor(
        agent=agent,
        built_in_tools=_PENDING_TOOLS,
        built_in_tool_allowlist=list(access.built_in_cao_tools),
        provider_policies=provider_policies,
        baton_enabled=True,
        provider_tool_allowlist=access.provider_mediated_tools,
    )


def build_mcp_runtime_generation_descriptor_for_agent(
    agent: Agent,
    *,
    agent_registry: Optional[AgentRegistry] = None,
    provider_policies: Optional[Dict[str, ProviderToolAccessPolicy]] = None,
) -> Dict[str, Any]:
    """Build runtime-generation material for one agent's visible MCP tools."""
    service = ToolService(
        agent_manager=AgentManager(
            configured_agents=agent_registry or AgentRegistry({agent.id: agent})
        )
    )
    if provider_policies is None:
        return dict(
            service.mcp_runtime_generation_descriptor_for_agent(
                agent.id,
                built_in_tools=_PENDING_TOOLS,
                built_in_tool_names=built_in_cao_tool_names(),
                built_in_runtime_generation=_built_in_mcp_runtime_generation_material(),
                baton_enabled=True,
            )
        )
    access = service.tools_for_agent(agent.id, built_in_tool_names=built_in_cao_tool_names())
    return build_agent_mcp_runtime_generation_descriptor(
        agent=agent,
        built_in_tools=_PENDING_TOOLS,
        built_in_tool_allowlist=list(access.built_in_cao_tools),
        provider_policies=provider_policies,
        baton_enabled=True,
        built_in_runtime_generation=_built_in_mcp_runtime_generation_material(),
        provider_tool_allowlist=access.provider_mediated_tools,
    )


def build_mcp_surface_fingerprint_for_agent(
    agent: Agent,
    *,
    agent_registry: Optional[AgentRegistry] = None,
    provider_policies: Optional[Dict[str, ProviderToolAccessPolicy]] = None,
) -> str:
    """Return the deterministic hash for one agent's visible MCP tool surface."""
    return fingerprint_agent_mcp_surface(
        build_mcp_surface_descriptor_for_agent(
            agent,
            agent_registry=agent_registry,
            provider_policies=provider_policies,
        )
    )


def build_mcp_runtime_generation_fingerprint_for_agent(
    agent: Agent,
    *,
    agent_registry: Optional[AgentRegistry] = None,
    provider_policies: Optional[Dict[str, ProviderToolAccessPolicy]] = None,
) -> str:
    """Return deterministic hash of runtime material behind visible MCP tools."""
    return fingerprint_agent_mcp_surface(
        build_mcp_runtime_generation_descriptor_for_agent(
            agent,
            agent_registry=agent_registry,
            provider_policies=provider_policies,
        )
    )


def _load_provider_policies_for_freshness(
    agent_registry: Optional[AgentRegistry],
) -> Dict[str, ProviderToolAccessPolicy]:
    registry = agent_registry or load_agent_registry()
    try:
        return dict(
            ToolService(agent_manager=AgentManager(configured_agents=registry)).provider_policies()
        )
    except (ProviderToolAccessConfigError, WorkspaceToolProviderConfigError):
        logger.exception("Provider-mediated MCP tool configuration is invalid")
        raise
    except Exception:
        logger.exception(
            "Provider-mediated MCP freshness descriptor failed while loading provider "
            "access; fingerprinting built-in CAO MCP tools only"
        )
        return {}


def _built_in_mcp_runtime_generation_material() -> Dict[str, Any]:
    """Return runtime-generation material for built-in CAO MCP tools."""
    return {
        "schema_version": "cao-built-in-mcp-runtime-generation.v1",
        "tools": {
            tool_name: {
                "handler": callable_runtime_fingerprint(fn),
            }
            for tool_name, fn, _ in _PENDING_TOOLS
        },
    }


def _create_terminal(agent_id: str, working_directory: Optional[str] = None) -> Tuple[str, str]:
    """Create a new terminal with the specified agent.

    Args:
        agent_id: Agent for the terminal
        working_directory: Unsupported override; agents start in their configured workdir

    Returns:
        Tuple of (terminal_id, provider)

    Raises:
        Exception: If terminal creation fails
    """
    if working_directory is not None:
        raise ValueError(
            "working_directory overrides are not supported by durable agent start; "
            "configure the agent workdir instead"
        )

    response = requests.post(f"{API_BASE_URL}/agents/{quote(agent_id, safe='')}/start")
    response.raise_for_status()
    terminal = response.json()["terminal"]

    return terminal["id"], terminal["provider"]


def _require_workspace_team_collaboration(receiver_agent_id: str) -> None:
    sender_agent_id = _sender_agent_id_for_workspace_team_guard()
    registry = load_agent_registry()
    manager = default_workspace_collaboration_manager(agent_registry=registry)
    manager.require_same_team_collaboration(
        sender=registry.get(sender_agent_id),
        receiver=registry.get(receiver_agent_id.strip()),
    )


def _sender_agent_id_for_workspace_team_guard() -> str:
    sender_terminal_id = os.getenv("CAO_TERMINAL_ID")
    if not sender_terminal_id:
        raise WorkspaceConfigError(
            "Workspace team collaboration rejected: sender terminal is unknown"
        )
    sender_metadata = db_module.get_terminal_metadata(sender_terminal_id)
    if sender_metadata is None:
        raise WorkspaceConfigError(
            f"Workspace team collaboration rejected: sender terminal {sender_terminal_id} "
            "is unknown"
        )
    sender_agent_id = sender_metadata.get("agent_id")
    if not isinstance(sender_agent_id, str) or not sender_agent_id.strip():
        raise WorkspaceConfigError(
            f"Workspace team collaboration rejected: sender terminal {sender_terminal_id} "
            "has no CAO agent"
        )
    return sender_agent_id.strip()


def _require_workspace_team_terminal_collaboration(receiver_terminal_id: str) -> None:
    sender_agent_id = _sender_agent_id_for_workspace_team_guard()
    receiver_metadata = db_module.get_terminal_metadata(receiver_terminal_id)
    if receiver_metadata is None:
        raise WorkspaceConfigError(
            f"Workspace team collaboration rejected: receiver terminal {receiver_terminal_id} "
            "is unknown"
        )
    receiver_agent_id = receiver_metadata.get("agent_id")
    if not isinstance(receiver_agent_id, str) or not receiver_agent_id.strip():
        raise WorkspaceConfigError(
            f"Workspace team collaboration rejected: receiver terminal {receiver_terminal_id} "
            "has no CAO agent"
        )
    registry = load_agent_registry()
    manager = default_workspace_collaboration_manager(agent_registry=registry)
    manager.require_same_team_collaboration(
        sender=registry.get(sender_agent_id),
        receiver=registry.get(receiver_agent_id),
    )


def _deliver_handoff_payload(terminal_id: str, provider: str, message: str) -> None:
    """Deliver a handoff payload through the worker's inbox.

    Routing via the inbox (rather than typing straight into the tmux pane)
    keeps all inter-agent communication on a single channel, so monitoring
    sessions capture the supervisor → worker handoff just like any other
    send_message. The worker is still instructed not to reply via
    send_message — the supervisor is blocked until the worker completes.
    """
    # For Codex provider: prepend handoff context so the worker agent knows
    # this is a blocking handoff and should simply output results rather than
    # attempting to call send_message back to the supervisor.
    if provider == "codex":
        supervisor_id = os.environ.get("CAO_TERMINAL_ID", "unknown")
        handoff_message = (
            f"[CAO Handoff] Supervisor terminal ID: {supervisor_id}. "
            "This is a blocking handoff — the orchestrator will automatically "
            "capture your response when you finish. Complete the task and output "
            "your results directly. Do NOT use send_message to notify the supervisor "
            "unless explicitly needed — just do the work and present your deliverables.\n\n"
            f"{message}"
        )
    else:
        handoff_message = message

    _send_to_inbox(_agent_id_for_terminal(terminal_id), handoff_message)


def _deliver_assign_payload(terminal_id: str, message: str) -> None:
    """Deliver an assign payload through the worker's inbox.

    Routing via the inbox keeps assign on the same channel as send_message
    so monitoring sessions capture it. The supervisor is the sender (via
    CAO_TERMINAL_ID). Callback guidance is appended only when ToolService says
    the receiving terminal can invoke send_message.
    """
    # Auto-inject sender terminal ID suffix when enabled
    if ENABLE_SENDER_ID_INJECTION:
        sender_id = os.environ.get("CAO_TERMINAL_ID", "unknown")
        if _terminal_can_invoke_builtin(terminal_id, "send_message"):
            message += (
                f"\n\n[Assigned by terminal {sender_id}. "
                f"When done, send results back to terminal {sender_id} using send_message]"
            )
        else:
            message += f"\n\n[Assigned by terminal {sender_id}.]"

    _send_to_inbox(_agent_id_for_terminal(terminal_id), message)


def _send_to_inbox(receiver_agent_id: str, body: str) -> Dict[str, Any]:
    """Send message to another agent's inbox (queued delivery when IDLE).

    Args:
        receiver_agent_id: Target durable agent ID
        body: Message content

    Returns:
        Dict with message details

    Raises:
        ValueError: If CAO_TERMINAL_ID not set
        Exception: If API call fails
    """
    sender_agent_id = _sender_agent_id_for_workspace_team_guard()
    _require_workspace_team_collaboration(receiver_agent_id)

    response = requests.post(
        f"{API_BASE_URL}/agents/{quote(receiver_agent_id, safe='')}/inbox/messages",
        params={"sender_agent_id": sender_agent_id, "body": body},
    )
    response.raise_for_status()
    return response.json()


def _agent_id_for_terminal(terminal_id: str) -> str:
    metadata = db_module.get_terminal_metadata(terminal_id)
    if metadata is None:
        raise ValueError(f"Terminal {terminal_id!r} is unknown")
    agent_id = metadata.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError(f"Terminal {terminal_id!r} has no CAO agent")
    return agent_id.strip()


def _extract_error_detail(response: requests.Response, fallback: str) -> str:
    """Extract a human-readable error detail from an API response."""
    try:
        payload = response.json()
    except ValueError:
        return fallback

    detail = payload.get("detail")
    if isinstance(detail, str) and detail:
        return detail
    return fallback


# Implementation functions
async def _handoff_impl(
    agent_id: str, message: str, timeout: int = 600, working_directory: Optional[str] = None
) -> HandoffResult:
    """Implementation of handoff logic."""
    start_time = time.time()

    try:
        _require_workspace_team_collaboration(agent_id)
        # Create terminal
        terminal_id, provider = _create_terminal(agent_id, working_directory)

        # Wait for terminal to be ready (IDLE or COMPLETED) before sending
        # the handoff message. Accept COMPLETED in addition to IDLE because
        # providers that use an initial prompt flag process the system prompt
        # as the first user message and produce a response, reaching COMPLETED
        # without ever showing a bare IDLE state.
        # Both states indicate the provider is ready to accept input.
        #
        # Use a generous timeout (120s) because provider initialization can be
        # slow: shell warm-up (~5s), CLI startup with MCP server registration
        # (~10-30s), and API authentication (~5-10s). If the provider's own
        # initialize() timed out (60-90s), this acts as a fallback to catch
        # cases where the CLI starts slightly after the provider timeout.
        # Provider initialization can be slow (~15-45s depending on provider).
        if not wait_until_terminal_status(
            terminal_id,
            {TerminalStatus.IDLE, TerminalStatus.COMPLETED},
            timeout=120.0,
        ):
            return HandoffResult(
                success=False,
                message=f"Terminal {terminal_id} did not reach ready status within 120 seconds",
                output=None,
                terminal_id=terminal_id,
            )

        await asyncio.sleep(2)  # wait another 2s

        # Deliver handoff payload via the worker's inbox so monitoring
        # captures it (injects handoff instructions for codex if needed).
        _deliver_handoff_payload(terminal_id, provider, message)

        # Monitor until completion with timeout
        if not wait_until_terminal_status(
            terminal_id, TerminalStatus.COMPLETED, timeout=timeout, polling_interval=1.0
        ):
            return HandoffResult(
                success=False,
                message=f"Handoff timed out after {timeout} seconds",
                output=None,
                terminal_id=terminal_id,
            )

        # Get the response
        response = requests.get(
            f"{API_BASE_URL}/terminals/{terminal_id}/output", params={"mode": "last"}
        )
        response.raise_for_status()
        output_data = response.json()
        output = output_data["output"]

        # Send provider-specific exit command to cleanup terminal
        response = requests.post(f"{API_BASE_URL}/terminals/{terminal_id}/exit")
        response.raise_for_status()

        execution_time = time.time() - start_time

        return HandoffResult(
            success=True,
            message=f"Successfully handed off to {agent_id} ({provider}) in {execution_time:.2f}s",
            output=output,
            terminal_id=terminal_id,
        )

    except Exception as e:
        return HandoffResult(
            success=False, message=f"Handoff failed: {str(e)}", output=None, terminal_id=None
        )


# Conditional tool registration based on environment variable
if ENABLE_WORKING_DIRECTORY:

    @_deferred_tool()
    async def handoff(
        agent_id: str = Field(
            description='The agent to hand off to (e.g., "developer", "analyst")'
        ),
        message: str = Field(description="The message/task to send to the target agent"),
        timeout: int = Field(
            default=600,
            description="Maximum time to wait for the agent to complete the task (in seconds)",
            ge=1,
            le=3600,
        ),
        working_directory: Optional[str] = Field(
            default=None,
            description='Optional working directory where the agent should execute (e.g., "/path/to/workspace/src/Package")',
        ),
    ) -> HandoffResult:
        """Hand off a task to another agent via CAO terminal and wait for completion.

        This tool allows handing off tasks to other agents by creating a new terminal
        in the same session. It sends the message, waits for completion, and captures the output.

        ## Usage

        Use this tool to hand off tasks to another agent and wait for the results.
        The tool will:
        1. Create a new terminal with the specified agent (provider inferred from profile/caller/default)
        2. Set the working directory for the terminal (defaults to supervisor's cwd)
        3. Send the message to the terminal
        4. Monitor until completion
        5. Return the agent's response
        6. Clean up the terminal with /exit

        ## Working Directory

        - By default, agents start in the supervisor's current working directory
        - You can specify a custom directory via working_directory parameter
        - Directory must exist and be accessible

        ## Requirements

        - Must be called from within a CAO terminal (CAO_TERMINAL_ID environment variable)
        - Target session must exist and be accessible
        - If working_directory is provided, it must exist and be accessible

        Args:
            agent_id: The agent for the new terminal
            message: The task/message to send
            timeout: Maximum wait time in seconds
            working_directory: Optional directory path where agent should execute

        Returns:
            HandoffResult with success status, message, and agent output
        """
        return await _handoff_impl(agent_id, message, timeout, working_directory)

else:

    @_deferred_tool()
    async def handoff(
        agent_id: str = Field(
            description='The agent to hand off to (e.g., "developer", "analyst")'
        ),
        message: str = Field(description="The message/task to send to the target agent"),
        timeout: int = Field(
            default=600,
            description="Maximum time to wait for the agent to complete the task (in seconds)",
            ge=1,
            le=3600,
        ),
    ) -> HandoffResult:
        """Hand off a task to another agent via CAO terminal and wait for completion.

        This tool allows handing off tasks to other agents by creating a new terminal
        in the same session. It sends the message, waits for completion, and captures the output.

        ## Usage

        Use this tool to hand off tasks to another agent and wait for the results.
        The tool will:
        1. Create a new terminal with the specified agent (provider inferred from profile/caller/default)
        2. Send the message to the terminal (starts in supervisor's current directory)
        3. Monitor until completion
        4. Return the agent's response
        5. Clean up the terminal with /exit

        ## Requirements

        - Must be called from within a CAO terminal (CAO_TERMINAL_ID environment variable)
        - Target session must exist and be accessible

        Args:
            agent_id: The agent for the new terminal
            message: The task/message to send
            timeout: Maximum wait time in seconds

        Returns:
            HandoffResult with success status, message, and agent output
        """
        return await _handoff_impl(agent_id, message, timeout, None)


# Implementation function for assign
def _assign_impl(
    agent_id: str, message: str, working_directory: Optional[str] = None
) -> Dict[str, Any]:
    """Implementation of assign logic."""
    try:
        _require_workspace_team_collaboration(agent_id)
        # Create terminal
        terminal_id, _ = _create_terminal(agent_id, working_directory)

        # Deliver via inbox (auto-injects sender terminal ID suffix when enabled)
        _deliver_assign_payload(terminal_id, message)

        return {
            "success": True,
            "terminal_id": terminal_id,
            "message": f"Task assigned to {agent_id} (terminal: {terminal_id})",
        }

    except Exception as e:
        return {"success": False, "terminal_id": None, "message": f"Assignment failed: {str(e)}"}


def _build_assign_description(enable_sender_id: bool, enable_workdir: bool) -> str:
    """Build the assign tool description based on feature flags."""
    # Build tool description overview.
    if enable_sender_id:
        desc = """\
Assigns a task to another agent without blocking.

The sender's terminal ID will automatically be appended to the message. Callback instructions
are appended only when the receiving terminal is allowed to invoke the callback tool. Callback
delivery still goes through workspace team message policy and may be rejected if the agents are
not in the same workspace team."""
    else:
        desc = """\
Assigns a task to another agent without blocking.

In the message to the worker agent include the terminal ID that should receive results. Tell the
worker to use send_message only when that tool is available to them; otherwise they should provide
results through their normal visible response channel.
**IMPORTANT**: The terminal id of each agent is available in environment variable CAO_TERMINAL_ID.
When assigning, first find out your own CAO_TERMINAL_ID value, then include the terminal_id value in the message to the worker agent for callback routing. Terminal id possession is not authorization; send_message is subject to same-workspace-team policy and may be rejected.
Example message: "Analyze the logs. When done, send results back to terminal ee3f93b3 if send_message is available; otherwise provide the result in your normal response.\""""

    if enable_workdir:
        desc += """

## Working Directory

- By default, agents start in the supervisor's current working directory
- You can specify a custom directory via working_directory parameter
- Directory must exist and be accessible"""

    desc += """

Args:
    agent_id: Agent for the worker terminal
    message: Task message (include callback instructions)"""

    if enable_workdir:
        desc += """
    working_directory: Optional working directory where the agent should execute"""

    desc += """

Returns:
    Dict with success status, worker terminal_id, and message"""

    return desc


_assign_description = _build_assign_description(
    ENABLE_SENDER_ID_INJECTION, ENABLE_WORKING_DIRECTORY
)
_assign_message_field_desc = (
    "The task message to send to the worker agent."
    if ENABLE_SENDER_ID_INJECTION
    else "The task message to send. Include callback instructions for the worker to send results back."
)

if ENABLE_WORKING_DIRECTORY:

    @_deferred_tool(description=_assign_description)
    async def assign(
        agent_id: str = Field(
            description='The agent for the worker agent (e.g., "developer", "analyst")'
        ),
        message: str = Field(description=_assign_message_field_desc),
        working_directory: Optional[str] = Field(
            default=None, description="Optional working directory where the agent should execute"
        ),
    ) -> Dict[str, Any]:
        return _assign_impl(agent_id, message, working_directory)

else:

    @_deferred_tool(description=_assign_description)
    async def assign(
        agent_id: str = Field(
            description='The agent for the worker agent (e.g., "developer", "analyst")'
        ),
        message: str = Field(description=_assign_message_field_desc),
    ) -> Dict[str, Any]:
        return _assign_impl(agent_id, message, None)


def _terminate_impl(terminal_id: str) -> Dict[str, Any]:
    """Gracefully exit a terminal via the existing REST endpoint.

    Used by a supervisor to clean up a worker it no longer needs (typically
    an ``assign``'d worker after it delivers its callback). ``handoff``
    already self-cleans, so this is primarily for the async flow.

    Degrades gracefully: any HTTP failure (unknown terminal, server error,
    network issue) is returned as a structured ``{success: False, error: ...}``
    rather than raised, so the calling agent gets a dict it can reason about.
    """
    try:
        response = requests.post(f"{API_BASE_URL}/terminals/{terminal_id}/exit")
        response.raise_for_status()
        return {
            "success": True,
            "terminal_id": terminal_id,
            "message": f"Sent exit command to terminal {terminal_id}",
        }
    except Exception as e:
        return {
            "success": False,
            "terminal_id": terminal_id,
            "error": str(e),
        }


@_deferred_tool()
async def terminate(
    terminal_id: str = Field(description="Terminal ID to gracefully exit and clean up"),
) -> Dict[str, Any]:
    """Gracefully exit an existing terminal.

    Sends the provider-specific exit command (e.g. ``/exit`` for Codex and
    Claude Code, ``C-d`` for some others). The tmux window dies, the
    provider's cleanup hooks run, and the terminal is removed from the
    database.

    Use after an ``assign``'d worker has delivered its result through an
    available response channel and you no longer need it. ``handoff`` does
    this automatically, so don't call ``terminate`` on a handoff'd worker.

    Returns:
        Dict with ``success`` (bool), ``terminal_id``, and either a
        ``message`` on success or an ``error`` on failure.
    """
    return _terminate_impl(terminal_id)


# Implementation function for send_message
def _send_message_impl(receiver_agent_id: str, body: str) -> Dict[str, Any]:
    """Implementation of send_message logic."""
    try:
        # Auto-inject sender terminal ID suffix when enabled
        if ENABLE_SENDER_ID_INJECTION:
            sender_id = os.environ.get("CAO_TERMINAL_ID", "unknown")
            if _agent_can_invoke_builtin(receiver_agent_id, "send_message"):
                body += (
                    f"\n\n[Message from terminal {sender_id}. "
                    "Use send_message MCP tool for any follow-up work.]"
                )
            else:
                body += f"\n\n[Message from terminal {sender_id}.]"

        return _send_to_inbox(receiver_agent_id, body)
    except Exception as e:
        return {"success": False, "error": str(e)}


def _terminal_can_invoke_builtin(terminal_id: str, tool_name: str) -> bool:
    try:
        decision = default_tool_service().can_invoke_for_terminal(
            terminal_id,
            tool_name,
            built_in_tool_names=built_in_cao_tool_names(),
        )
    except Exception:
        return False
    return decision.allowed


def _agent_can_invoke_builtin(agent_id: str, tool_name: str) -> bool:
    terminals = db_module.list_terminals_by_agent(agent_id)
    if not terminals:
        return False
    terminal_id = terminals[0].get("id")
    return isinstance(terminal_id, str) and _terminal_can_invoke_builtin(terminal_id, tool_name)


@_deferred_tool()
async def send_message(
    receiver_agent_id: str = Field(
        description="Target CAO agent ID to send message to, subject to same-workspace-team policy"
    ),
    body: str = Field(description="Message content to send"),
) -> Dict[str, Any]:
    """Send a message to another agent's inbox.

    The message is accepted only when sender and receiver belong to the same workspace team.
    It will be delivered when the destination agent's live terminal is IDLE.
    Messages are delivered in order (oldest first).

    Args:
        receiver_agent_id: Durable CAO agent ID of the receiver
        body: Message content to send

    Returns:
        Dict with success status and message details
    """
    return _send_message_impl(receiver_agent_id, body)


def _read_inbox_message_impl(notification_id: int) -> Dict[str, Any]:
    """Implementation of read_inbox_message logic."""
    try:
        caller_terminal_id = _require_cao_terminal_id()
        return read_result_to_dict(
            read_provider_inbox_message(
                notification_id,
                caller_terminal_id=caller_terminal_id,
            )
        )
    except InboxReadError as exc:
        return {"success": False, "error": str(exc), "error_type": type(exc).__name__}
    except Exception as exc:
        logger.exception("Failed to read inbox notification %s", notification_id)
        return {"success": False, "error": str(exc), "error_type": "InboxReadUnexpectedError"}


@_deferred_tool()
async def read_inbox_message(
    notification_id: int = Field(description="CAO inbox notification ID"),
) -> Dict[str, Any]:
    """Read a slim message-first payload for a CAO inbox notification.

    Use this after receiving a compact CAO inbox notification. The terminal
    notification may only be a pointer; this tool returns the backing message
    body and replyability without exposing provider internals by default.
    """
    return _read_inbox_message_impl(notification_id)


def _reply_to_inbox_message_impl(notification_id: int, body: str) -> Dict[str, Any]:
    """Implementation of reply_to_inbox_message logic."""
    try:
        caller_terminal_id = _require_cao_terminal_id()
        result = route_provider_inbox_reply(
            notification_id,
            body,
            caller_terminal_id=caller_terminal_id,
        )
        return {
            "success": True,
            "notification_id": result.delivery.notification.id,
            "provider": result.thread.provider,
            "thread_id": result.thread.external_id,
            "outbound_message": {
                "id": result.outbound_message.id,
                "external_id": result.outbound_message.external_id,
                "state": result.outbound_message.state,
                "kind": result.outbound_message.kind,
                "body": result.outbound_message.body,
            },
        }
    except ProviderConversationReplyError as exc:
        payload: Dict[str, Any] = {
            "success": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
        failed_message = getattr(exc, "failed_message", None)
        if failed_message is not None:
            payload["failed_message_id"] = failed_message.id
            payload["failed_message_state"] = failed_message.state
        return payload
    except Exception as exc:
        logger.exception("Failed to reply to inbox notification %s", notification_id)
        return {"success": False, "error": str(exc), "error_type": "InboxReplyUnexpectedError"}


@_deferred_tool()
async def reply_to_inbox_message(
    notification_id: int = Field(description="CAO inbox notification ID to reply to"),
    body: str = Field(description="Reply body to send through the owning provider"),
) -> Dict[str, Any]:
    """Reply to a provider-backed inbox notification through CAO's inbox path."""
    return _reply_to_inbox_message_impl(notification_id, body)


def _require_cao_terminal_id() -> str:
    terminal_id = os.getenv("CAO_TERMINAL_ID")
    if not terminal_id:
        raise ValueError("CAO_TERMINAL_ID not set - baton tools must run inside a CAO terminal")
    return terminal_id


def _baton_to_dict(baton: Baton) -> Dict[str, Any]:
    return baton.model_dump(mode="json")


def _baton_event_to_dict(event: BatonEvent) -> Dict[str, Any]:
    return event.model_dump(mode="json")


def _baton_success(baton: Baton, message: str) -> Dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "baton": _baton_to_dict(baton),
        "baton_id": baton.id,
        "status": baton.status,
        "current_holder_id": baton.current_holder_id,
    }


def _baton_error(exc: Exception) -> Dict[str, Any]:
    if isinstance(exc, ValueError):
        error_type = "missing_context" if "CAO_TERMINAL_ID" in str(exc) else "invalid_request"
    elif isinstance(exc, baton_service.BatonNotFound):
        error_type = "not_found"
    elif isinstance(exc, baton_service.BatonAuthorizationError):
        error_type = "authorization_error"
    elif isinstance(exc, baton_service.BatonInvalidTransition):
        error_type = "invalid_transition"
    else:
        error_type = "baton_error"

    return {
        "success": False,
        "error_type": error_type,
        "error": str(exc),
    }


def _parse_baton_status(status: Optional[str]) -> Optional[BatonStatus]:
    if status is None:
        return None
    try:
        return BatonStatus(status)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in BatonStatus)
        raise ValueError(f"invalid baton status {status!r}; expected one of: {allowed}") from exc


def _actor_can_view_baton(actor_id: str, baton: Baton) -> bool:
    return (
        actor_id == baton.originator_id
        or actor_id == baton.current_holder_id
        or actor_id in baton.return_stack
    )


def _create_baton_impl(
    title: str,
    holder_id: str,
    message: str,
    expected_next_action: Optional[str] = None,
    artifact_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        _require_workspace_team_terminal_collaboration(holder_id)
        baton = baton_service.create_baton(
            title=title,
            originator_id=actor_id,
            holder_id=holder_id,
            message=message,
            expected_next_action=expected_next_action,
            artifact_paths=artifact_paths,
        )
        return _baton_success(baton, f"Created baton {baton.id} for holder {holder_id}")
    except Exception as exc:
        return _baton_error(exc)


def _pass_baton_impl(
    baton_id: str,
    receiver_id: str,
    message: str,
    expected_next_action: Optional[str] = None,
    artifact_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        _require_workspace_team_terminal_collaboration(receiver_id)
        baton = baton_service.pass_baton(
            baton_id=baton_id,
            actor_id=actor_id,
            receiver_id=receiver_id,
            message=message,
            expected_next_action=expected_next_action,
            artifact_paths=artifact_paths,
        )
        return _baton_success(baton, f"Passed baton {baton_id} to {receiver_id}")
    except Exception as exc:
        return _baton_error(exc)


def _return_baton_impl(
    baton_id: str,
    message: str,
    expected_next_action: Optional[str] = None,
    artifact_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        existing = db_module.get_baton_record(baton_id)
        if existing is None:
            raise baton_service.BatonNotFound(baton_id)
        receiver_id = existing.return_stack[-1] if existing.return_stack else existing.originator_id
        _require_workspace_team_terminal_collaboration(receiver_id)
        baton = baton_service.return_baton(
            baton_id=baton_id,
            actor_id=actor_id,
            message=message,
            expected_next_action=expected_next_action,
            artifact_paths=artifact_paths,
        )
        return _baton_success(baton, f"Returned baton {baton_id} to {baton.current_holder_id}")
    except Exception as exc:
        return _baton_error(exc)


def _complete_baton_impl(
    baton_id: str,
    message: str,
    artifact_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        existing = db_module.get_baton_record(baton_id)
        if existing is None:
            raise baton_service.BatonNotFound(baton_id)
        _require_workspace_team_terminal_collaboration(existing.originator_id)
        baton = baton_service.complete_baton(
            baton_id=baton_id,
            actor_id=actor_id,
            message=message,
            artifact_paths=artifact_paths,
        )
        return _baton_success(baton, f"Completed baton {baton_id}")
    except Exception as exc:
        return _baton_error(exc)


def _block_baton_impl(
    baton_id: str,
    reason: str,
    artifact_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        existing = db_module.get_baton_record(baton_id)
        if existing is None:
            raise baton_service.BatonNotFound(baton_id)
        _require_workspace_team_terminal_collaboration(existing.originator_id)
        baton = baton_service.block_baton(
            baton_id=baton_id,
            actor_id=actor_id,
            reason=reason,
            artifact_paths=artifact_paths,
        )
        return _baton_success(baton, f"Blocked baton {baton_id}")
    except Exception as exc:
        return _baton_error(exc)


def _get_my_batons_impl(status: Optional[str] = None) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        status_filter = _parse_baton_status(status)
        batons = db_module.list_batons_held_by(actor_id, status=status_filter)
        return {
            "success": True,
            "terminal_id": actor_id,
            "batons": [_baton_to_dict(baton) for baton in batons],
            "count": len(batons),
        }
    except Exception as exc:
        return _baton_error(exc)


def _get_baton_impl(baton_id: str) -> Dict[str, Any]:
    try:
        actor_id = _require_cao_terminal_id()
        baton = db_module.get_baton_record(baton_id)
        if baton is None:
            raise baton_service.BatonNotFound(baton_id)
        if not _actor_can_view_baton(actor_id, baton):
            raise baton_service.BatonAuthorizationError(
                f"actor {actor_id} is not allowed to view baton {baton_id}"
            )
        events = db_module.list_baton_events(baton_id)
        return {
            "success": True,
            "baton": _baton_to_dict(baton),
            "events": [_baton_event_to_dict(event) for event in events],
        }
    except Exception as exc:
        return _baton_error(exc)


@_deferred_tool()
async def create_baton(
    title: str = Field(description="Human-readable baton title"),
    holder_id: str = Field(description="Terminal ID that should hold the new baton"),
    message: str = Field(description="Self-contained message to queue for the initial holder"),
    expected_next_action: Optional[str] = Field(
        default=None, description="What the holder is expected to do next"
    ),
    artifact_paths: Optional[List[str]] = Field(
        default=None, description="Absolute artifact paths relevant to this baton"
    ),
) -> Dict[str, Any]:
    """Create a baton and queue the initial holder message as one operation."""
    return _create_baton_impl(title, holder_id, message, expected_next_action, artifact_paths)


@_deferred_tool()
async def pass_baton(
    baton_id: str = Field(description="Baton ID to pass"),
    receiver_id: str = Field(description="Terminal ID that should receive the baton"),
    message: str = Field(description="Self-contained message to queue for the receiver"),
    expected_next_action: Optional[str] = Field(
        default=None, description="What the receiver is expected to do next"
    ),
    artifact_paths: Optional[List[str]] = Field(
        default=None, description="Absolute artifact paths relevant to this transfer"
    ),
) -> Dict[str, Any]:
    """Pass a baton to another terminal and queue the transfer message."""
    return _pass_baton_impl(baton_id, receiver_id, message, expected_next_action, artifact_paths)


@_deferred_tool()
async def return_baton(
    baton_id: str = Field(description="Baton ID to return"),
    message: str = Field(description="Self-contained message to queue for the previous holder"),
    expected_next_action: Optional[str] = Field(
        default=None, description="What the receiving holder is expected to do next"
    ),
    artifact_paths: Optional[List[str]] = Field(
        default=None, description="Absolute artifact paths relevant to this return"
    ),
) -> Dict[str, Any]:
    """Return a baton to the previous holder, or originator if the stack is empty."""
    return _return_baton_impl(baton_id, message, expected_next_action, artifact_paths)


@_deferred_tool()
async def complete_baton(
    baton_id: str = Field(description="Baton ID to complete"),
    message: str = Field(description="Completion message to queue for the originator"),
    artifact_paths: Optional[List[str]] = Field(
        default=None, description="Absolute artifact paths relevant to completion"
    ),
) -> Dict[str, Any]:
    """Complete a baton and notify the originator."""
    return _complete_baton_impl(baton_id, message, artifact_paths)


@_deferred_tool()
async def block_baton(
    baton_id: str = Field(description="Baton ID to block"),
    reason: str = Field(description="Why the baton is blocked and what input is needed"),
    artifact_paths: Optional[List[str]] = Field(
        default=None, description="Absolute artifact paths relevant to the blocker"
    ),
) -> Dict[str, Any]:
    """Mark a baton blocked and notify the originator."""
    return _block_baton_impl(baton_id, reason, artifact_paths)


@_deferred_tool()
async def get_my_batons(
    status: Optional[str] = Field(
        default=None,
        description="Optional status filter: active, completed, blocked, canceled, or orphaned",
    ),
) -> Dict[str, Any]:
    """List batons currently held by this terminal."""
    return _get_my_batons_impl(status)


@_deferred_tool()
async def get_baton(
    baton_id: str = Field(description="Baton ID to inspect"),
) -> Dict[str, Any]:
    """Get baton details and audit events for a baton involving this terminal."""
    return _get_baton_impl(baton_id)


def main():
    """Main entry point for the MCP server.

    Resolves the per-terminal tool allowlist (if any) and registers the
    matching subset of tools with FastMCP, then starts the MCP loop.

    ``CAO_TERMINAL_ID`` is injected into this subprocess by the parent
    provider (codex/claude/etc.) via the ``env_vars`` directive in its MCP
    config. Without it, ToolService cannot resolve agent access and startup
    fails closed by registering no agent-facing MCP tools.
    """
    terminal_id = os.environ.get("CAO_TERMINAL_ID")
    service = default_tool_service()
    provider_registered: list[str] = []
    if terminal_id:
        provider_registered = register_provider_mediated_mcp_tools_for_terminal(
            terminal_id=terminal_id,
            mcp_instance=mcp,
            reserved_tool_names=built_in_cao_tool_names(),
            tool_service=service,
        )
    registered = _register_tools(
        _PENDING_TOOLS,
        mcp,
        terminal_id=terminal_id,
        tool_service=service,
    )
    logger.info(
        f"Registered {len(registered)}/{len(_PENDING_TOOLS)} MCP tools "
        f"(terminal_id={terminal_id or 'missing-terminal'}): "
        f"{sorted(registered)}; provider-mediated={sorted(provider_registered)}"
    )
    mcp.run()


if __name__ == "__main__":
    main()
