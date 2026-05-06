"""CLI Agent Orchestrator MCP Server implementation."""

import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import requests
from fastmcp import FastMCP
from pydantic import Field

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.constants import API_BASE_URL, DEFAULT_PROVIDER
from cli_agent_orchestrator.mcp_server.models import HandoffResult
from cli_agent_orchestrator.models.baton import Baton, BatonEvent, BatonStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.presence.builtins import ensure_builtin_presence_provider
from cli_agent_orchestrator.presence.inbox_access import (
    InboxReadError,
    read_inbox_message as read_provider_inbox_message,
    read_result_to_dict,
)
from cli_agent_orchestrator.presence.manager import UnknownPresenceProviderError
from cli_agent_orchestrator.presence.reply_service import (
    PresenceReplyError,
    reply_to_inbox_message as route_provider_inbox_reply,
)
from cli_agent_orchestrator.services import baton_service
from cli_agent_orchestrator.services.baton_feature import BATON_MCP_TOOL_NAMES, is_baton_enabled
from cli_agent_orchestrator.utils import agent_profiles as agent_profiles_utils
from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
from cli_agent_orchestrator.utils.cao_tool_allowlist import resolve_cao_tool_allowlist
from cli_agent_orchestrator.utils.terminal import generate_session_name, wait_until_terminal_status

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

    - Use specific agent profiles (provider is inferred from profile metadata when set)
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
    allowlist: Optional[List[str]],
    mcp_instance: Any,
) -> List[str]:
    """Apply FastMCP's @mcp.tool() to each pending tool whose name is in the allowlist.

    Args:
        pending: Items from the deferred registry.
        allowlist: Tool names to register. ``None`` = register all (permissive
            fallback for agents without per-profile or per-role configuration).
            ``[]`` = register nothing (explicit deny-all).
        mcp_instance: The FastMCP instance to register against.

    Returns:
        Names of tools actually registered, in the order they appeared.
    """
    registered: List[str] = []
    allowed: Optional[set] = None if allowlist is None else set(allowlist)
    baton_enabled = is_baton_enabled()
    for tool_name, fn, kwargs in pending:
        if tool_name in BATON_MCP_TOOL_NAMES and not baton_enabled:
            logger.info(
                "Tool '%s' belongs to disabled baton feature — skipping registration",
                tool_name,
            )
            continue
        if allowed is not None and tool_name not in allowed:
            logger.info(f"Tool '{tool_name}' not in allowlist — skipping registration")
            continue
        mcp_instance.tool(**kwargs)(fn)
        registered.append(tool_name)
    return registered


# Hard budget for the HTTP call during MCP server startup. Provider MCP
# clients commonly kill the stdio connection after ~30s with no handshake
# response, so we must finish the whole startup (resolve + register +
# mcp.run()) well under that. Keep this short; on failure we fall open
# and register everything.
_ALLOWLIST_RESOLVE_TIMEOUT_SEC = 3.0


def _resolve_allowlist_for_terminal(terminal_id: str) -> Optional[List[str]]:
    """Ask cao-server which tools this terminal's agent profile permits.

    Fail-open on any error: a None return means "don't filter, register all
    tools." This keeps existing agents (no caoTools, no role mapping) working
    unchanged while users opt in to filtering by configuring their profiles.
    Fail-closed behavior is a later, opt-in choice (Phase 5).

    Any hang past the short budget also fails open — a slow API call at
    startup would otherwise exceed the provider MCP client's handshake
    timeout and kill the whole connection, which is strictly worse than
    not filtering.
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/terminals/{terminal_id}",
            timeout=_ALLOWLIST_RESOLVE_TIMEOUT_SEC,
        )
        response.raise_for_status()
        metadata = response.json()
        profile_name = metadata.get("agent_profile")
        if not profile_name:
            return None
        profile = load_agent_profile(profile_name)
        return resolve_cao_tool_allowlist(profile)
    except Exception as e:
        logger.warning(
            f"Failed to resolve tool allowlist for terminal {terminal_id!r}: {e}. "
            "Registering all tools (permissive fallback)."
        )
        return None


LOAD_SKILL_TOOL_DESCRIPTION = """Retrieve the full Markdown body of an available skill from cao-server.

Use this tool when your prompt lists a CAO skill and you need its full instructions at runtime.

Args:
    name: Name of the skill to retrieve

Returns:
    The skill content on success, or a dict with success=False and an error message on failure
"""


def _resolve_child_allowed_tools(
    parent_allowed_tools: Optional[list], child_profile_name: str
) -> Optional[str]:
    """Resolve allowed_tools for a child terminal via intersection.

    The child gets at most the union of: what the parent allows + what the
    child profile specifies. If the parent is unrestricted ("*"), the child
    profile's allowedTools are used as-is.

    Returns:
        Comma-separated string of allowed tools, or None for unrestricted.
    """
    from cli_agent_orchestrator.utils.agent_profiles import load_agent_profile
    from cli_agent_orchestrator.utils.tool_mapping import resolve_allowed_tools

    try:
        child_profile = load_agent_profile(child_profile_name)
        mcp_server_names = (
            list(child_profile.mcpServers.keys()) if child_profile.mcpServers else None
        )
        child_allowed = resolve_allowed_tools(
            child_profile.allowedTools, child_profile.role, mcp_server_names
        )
    except FileNotFoundError:
        child_allowed = None

    # If parent is unrestricted or has no restrictions, use child's tools
    if parent_allowed_tools is None or "*" in parent_allowed_tools:
        if child_allowed:
            return ",".join(child_allowed)
        return None

    # If child has no opinion (None), inherit parent's restrictions
    if child_allowed is None:
        return ",".join(parent_allowed_tools)

    # If child explicitly requests unrestricted ("*"), honor it
    if "*" in child_allowed:
        return None

    # Both have restrictions: child gets its own profile tools
    # (the child profile defines what it needs; parent's restrictions
    # are enforced by the parent not delegating unauthorized work)
    return ",".join(child_allowed)


def _create_terminal(
    agent_profile: str, working_directory: Optional[str] = None
) -> Tuple[str, str]:
    """Create a new terminal with the specified agent profile.

    Args:
        agent_profile: Agent profile for the terminal
        working_directory: Optional working directory for the terminal

    Returns:
        Tuple of (terminal_id, provider)

    Raises:
        Exception: If terminal creation fails
    """
    provider = DEFAULT_PROVIDER
    parent_allowed_tools = None

    # Get current terminal ID from environment
    current_terminal_id = os.environ.get("CAO_TERMINAL_ID")
    if current_terminal_id:
        # Get terminal metadata via API
        response = requests.get(f"{API_BASE_URL}/terminals/{current_terminal_id}")
        response.raise_for_status()
        terminal_metadata = response.json()

        provider = terminal_metadata["provider"]
        session_name = terminal_metadata["session_name"]
        parent_allowed_tools = terminal_metadata.get("allowed_tools")

        # If no working_directory specified, get conductor's current directory
        if working_directory is None:
            try:
                response = requests.get(
                    f"{API_BASE_URL}/terminals/{current_terminal_id}/working-directory"
                )
                if response.status_code == 200:
                    working_directory = response.json().get("working_directory")
                    logger.info(f"Inherited working directory from conductor: {working_directory}")
                else:
                    logger.warning(
                        f"Failed to get conductor's working directory (status {response.status_code}), "
                        "will use server default"
                    )
            except Exception as e:
                logger.warning(
                    f"Error fetching conductor's working directory: {e}, will use server default"
                )

        # Resolve child's allowed_tools via inheritance
        child_allowed_tools = _resolve_child_allowed_tools(parent_allowed_tools, agent_profile)

        # Create new terminal in existing session - always pass working_directory
        params = {"provider": provider, "agent_profile": agent_profile}
        if working_directory:
            params["working_directory"] = working_directory
        if child_allowed_tools:
            params["allowed_tools"] = child_allowed_tools

        response = requests.post(f"{API_BASE_URL}/sessions/{session_name}/terminals", params=params)
        response.raise_for_status()
        terminal = response.json()
    else:
        # Create new session with terminal
        session_name = generate_session_name()
        params = {
            "provider": provider,
            "agent_profile": agent_profile,
            "session_name": session_name,
        }
        if working_directory:
            params["working_directory"] = working_directory

        response = requests.post(f"{API_BASE_URL}/sessions", params=params)
        response.raise_for_status()
        terminal = response.json()

    return terminal["id"], provider


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

    _send_to_inbox(terminal_id, handoff_message)


def _deliver_assign_payload(terminal_id: str, message: str) -> None:
    """Deliver an assign payload through the worker's inbox.

    Routing via the inbox keeps assign on the same channel as send_message
    so monitoring sessions capture it. The supervisor is the sender (via
    CAO_TERMINAL_ID), matching what the worker would see for any hand-rolled
    send_message from the same supervisor.
    """
    # Auto-inject sender terminal ID suffix when enabled
    if ENABLE_SENDER_ID_INJECTION:
        sender_id = os.environ.get("CAO_TERMINAL_ID", "unknown")
        message += (
            f"\n\n[Assigned by terminal {sender_id}. "
            f"When done, send results back to terminal {sender_id} using send_message]"
        )

    _send_to_inbox(terminal_id, message)


def _send_to_inbox(receiver_id: str, message: str) -> Dict[str, Any]:
    """Send message to another terminal's inbox (queued delivery when IDLE).

    Args:
        receiver_id: Target terminal ID
        message: Message content

    Returns:
        Dict with message details

    Raises:
        ValueError: If CAO_TERMINAL_ID not set
        Exception: If API call fails
    """
    sender_id = os.getenv("CAO_TERMINAL_ID")
    if not sender_id:
        raise ValueError("CAO_TERMINAL_ID not set - cannot determine sender")

    response = requests.post(
        f"{API_BASE_URL}/terminals/{receiver_id}/inbox/messages",
        params={"sender_id": sender_id, "message": message},
    )
    response.raise_for_status()
    return response.json()


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


def _load_skill_impl(name: str) -> Union[str, Dict[str, Any]]:
    """Fetch a skill body from cao-server and return content or a structured error."""
    try:
        response = requests.get(f"{API_BASE_URL}/skills/{name}")
        response.raise_for_status()
        return response.json()["content"]
    except requests.HTTPError as exc:
        detail = str(exc)
        if exc.response is not None:
            detail = _extract_error_detail(exc.response, detail)
        return {"success": False, "error": detail}
    except requests.ConnectionError:
        return {
            "success": False,
            "error": "Failed to connect to cao-server. The server may not be running.",
        }
    except Exception as exc:
        return {"success": False, "error": f"Failed to retrieve skill: {str(exc)}"}


# Implementation functions
async def _handoff_impl(
    agent_profile: str, message: str, timeout: int = 600, working_directory: Optional[str] = None
) -> HandoffResult:
    """Implementation of handoff logic."""
    start_time = time.time()

    try:
        # Create terminal
        terminal_id, provider = _create_terminal(agent_profile, working_directory)

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
            message=f"Successfully handed off to {agent_profile} ({provider}) in {execution_time:.2f}s",
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
        agent_profile: str = Field(
            description='The agent profile to hand off to (e.g., "developer", "analyst")'
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
        1. Create a new terminal with the specified agent profile (provider inferred from profile/caller/default)
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
            agent_profile: The agent profile for the new terminal
            message: The task/message to send
            timeout: Maximum wait time in seconds
            working_directory: Optional directory path where agent should execute

        Returns:
            HandoffResult with success status, message, and agent output
        """
        return await _handoff_impl(agent_profile, message, timeout, working_directory)

else:

    @_deferred_tool()
    async def handoff(
        agent_profile: str = Field(
            description='The agent profile to hand off to (e.g., "developer", "analyst")'
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
        1. Create a new terminal with the specified agent profile (provider inferred from profile/caller/default)
        2. Send the message to the terminal (starts in supervisor's current directory)
        3. Monitor until completion
        4. Return the agent's response
        5. Clean up the terminal with /exit

        ## Requirements

        - Must be called from within a CAO terminal (CAO_TERMINAL_ID environment variable)
        - Target session must exist and be accessible

        Args:
            agent_profile: The agent profile for the new terminal
            message: The task/message to send
            timeout: Maximum wait time in seconds

        Returns:
            HandoffResult with success status, message, and agent output
        """
        return await _handoff_impl(agent_profile, message, timeout, None)


# Implementation function for assign
def _assign_impl(
    agent_profile: str, message: str, working_directory: Optional[str] = None
) -> Dict[str, Any]:
    """Implementation of assign logic."""
    try:
        # Create terminal
        terminal_id, _ = _create_terminal(agent_profile, working_directory)

        # Deliver via inbox (auto-injects sender terminal ID suffix when enabled)
        _deliver_assign_payload(terminal_id, message)

        return {
            "success": True,
            "terminal_id": terminal_id,
            "message": f"Task assigned to {agent_profile} (terminal: {terminal_id})",
        }

    except Exception as e:
        return {"success": False, "terminal_id": None, "message": f"Assignment failed: {str(e)}"}


def _build_assign_description(enable_sender_id: bool, enable_workdir: bool) -> str:
    """Build the assign tool description based on feature flags."""
    # Build tool description overview.
    if enable_sender_id:
        desc = """\
Assigns a task to another agent without blocking.

The sender's terminal ID and callback instructions will automatically be appended to the message."""
    else:
        desc = """\
Assigns a task to another agent without blocking.

In the message to the worker agent include instruction to send results back via send_message tool.
**IMPORTANT**: The terminal id of each agent is available in environment variable CAO_TERMINAL_ID.
When assigning, first find out your own CAO_TERMINAL_ID value, then include the terminal_id value in the message to the worker agent to allow callback.
Example message: "Analyze the logs. When done, send results back to terminal ee3f93b3 using send_message tool.\""""

    if enable_workdir:
        desc += """

## Working Directory

- By default, agents start in the supervisor's current working directory
- You can specify a custom directory via working_directory parameter
- Directory must exist and be accessible"""

    desc += """

Args:
    agent_profile: Agent profile for the worker terminal
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
        agent_profile: str = Field(
            description='The agent profile for the worker agent (e.g., "developer", "analyst")'
        ),
        message: str = Field(description=_assign_message_field_desc),
        working_directory: Optional[str] = Field(
            default=None, description="Optional working directory where the agent should execute"
        ),
    ) -> Dict[str, Any]:
        return _assign_impl(agent_profile, message, working_directory)

else:

    @_deferred_tool(description=_assign_description)
    async def assign(
        agent_profile: str = Field(
            description='The agent profile for the worker agent (e.g., "developer", "analyst")'
        ),
        message: str = Field(description=_assign_message_field_desc),
    ) -> Dict[str, Any]:
        return _assign_impl(agent_profile, message, None)


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

    Use after an ``assign``'d worker has delivered its callback via
    ``send_message`` and you no longer need it. ``handoff`` does this
    automatically, so don't call ``terminate`` on a handoff'd worker.

    Returns:
        Dict with ``success`` (bool), ``terminal_id``, and either a
        ``message`` on success or an ``error`` on failure.
    """
    return _terminate_impl(terminal_id)


# Implementation function for send_message
def _send_message_impl(receiver_id: str, message: str) -> Dict[str, Any]:
    """Implementation of send_message logic."""
    try:
        # Auto-inject sender terminal ID suffix when enabled
        if ENABLE_SENDER_ID_INJECTION:
            sender_id = os.environ.get("CAO_TERMINAL_ID", "unknown")
            message += (
                f"\n\n[Message from terminal {sender_id}. "
                "Use send_message MCP tool for any follow-up work.]"
            )

        return _send_to_inbox(receiver_id, message)
    except Exception as e:
        return {"success": False, "error": str(e)}


@_deferred_tool()
async def send_message(
    receiver_id: str = Field(description="Target terminal ID to send message to"),
    message: str = Field(description="Message content to send"),
) -> Dict[str, Any]:
    """Send a message to another terminal's inbox.

    The message will be delivered when the destination terminal is IDLE.
    Messages are delivered in order (oldest first).

    Args:
        receiver_id: Terminal ID of the receiver
        message: Message content to send

    Returns:
        Dict with success status and message details
    """
    return _send_message_impl(receiver_id, message)


def _read_inbox_message_impl(inbox_message_id: int) -> Dict[str, Any]:
    """Implementation of read_inbox_message logic."""
    try:
        return read_result_to_dict(read_provider_inbox_message(inbox_message_id))
    except InboxReadError as exc:
        return {"success": False, "error": str(exc), "error_type": type(exc).__name__}
    except Exception as exc:
        logger.exception("Failed to read inbox message %s", inbox_message_id)
        return {"success": False, "error": str(exc), "error_type": "InboxReadUnexpectedError"}


@_deferred_tool()
async def read_inbox_message(
    inbox_message_id: int = Field(description="CAO inbox message ID from a notification"),
) -> Dict[str, Any]:
    """Read the full provider-backed content/context for an inbox notification.

    Use this after receiving a compact CAO inbox notification. The terminal
    notification is only a pointer; this tool returns the durable backing
    message, thread/work context, raw provider snapshot, and replyability info.
    """
    return _read_inbox_message_impl(inbox_message_id)


def _reply_to_inbox_message_impl(inbox_message_id: int, body: str) -> Dict[str, Any]:
    """Implementation of reply_to_inbox_message logic."""
    try:
        try:
            _ensure_mcp_presence_provider_for_inbox(inbox_message_id)
        except (InboxReadError, UnknownPresenceProviderError):
            pass
        result = route_provider_inbox_reply(inbox_message_id, body)
        return {
            "success": True,
            "inbox_message_id": result.inbox_message.id,
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
    except PresenceReplyError as exc:
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
        logger.exception("Failed to reply to inbox message %s", inbox_message_id)
        return {"success": False, "error": str(exc), "error_type": "InboxReplyUnexpectedError"}


@_deferred_tool()
async def reply_to_inbox_message(
    inbox_message_id: int = Field(description="CAO inbox message ID to reply to"),
    body: str = Field(description="Reply body to send through the owning provider"),
) -> Dict[str, Any]:
    """Reply to a provider-backed inbox notification through CAO's inbox path."""
    return _reply_to_inbox_message_impl(inbox_message_id, body)


def _ensure_mcp_presence_provider_for_inbox(inbox_message_id: int) -> None:
    """Register the built-in provider needed by one provider-backed inbox reply."""
    read_result = read_provider_inbox_message(inbox_message_id)
    provider = read_result.thread.get("provider")
    if provider:
        ensure_builtin_presence_provider(str(provider))


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


@_deferred_tool(description=LOAD_SKILL_TOOL_DESCRIPTION)
async def load_skill(
    name: str = Field(description="Name of the skill to retrieve"),
) -> Any:
    """Retrieve skill content from cao-server."""
    return _load_skill_impl(name)


def _list_agent_profiles_impl() -> Dict[str, Any]:
    try:
        profiles = agent_profiles_utils.list_agent_profiles()
        return {"success": True, "profiles": profiles}
    except Exception as e:
        return {"success": False, "error": str(e), "profiles": []}


def _get_agent_profile_impl(agent_name: str, include_prompt: bool = False) -> Dict[str, Any]:
    try:
        profile = agent_profiles_utils.get_agent_profile(agent_name, include_prompt=include_prompt)
        return {"success": True, "profile": profile}
    except Exception as e:
        return {"success": False, "error": str(e), "profile": None}


@_deferred_tool()
async def list_agent_profiles() -> Dict[str, Any]:
    """List available CAO agent profiles (built-in + locally installed).

    Returns:
        Dict with `success` and `profiles` (name-sorted).
    """
    return _list_agent_profiles_impl()


@_deferred_tool()
async def get_agent_profile(
    agent_name: str = Field(description='Agent profile name (e.g., "developer")'),
    include_prompt: bool = Field(
        default=False,
        description="If true, include the profile's system prompt content in the response.",
    ),
) -> Dict[str, Any]:
    """Get a single CAO agent profile by name.

    Args:
        agent_name: Agent profile name
        include_prompt: Include system prompt content
    """
    return _get_agent_profile_impl(agent_name, include_prompt=include_prompt)


def main():
    """Main entry point for the MCP server.

    Resolves the per-terminal tool allowlist (if any) and registers the
    matching subset of tools with FastMCP, then starts the MCP loop.

    ``CAO_TERMINAL_ID`` is injected into this subprocess by the parent
    provider (codex/claude/etc.) via the ``env_vars`` directive in its
    MCP config. Without it (e.g. a developer invoking cao-mcp-server
    directly outside of CAO for testing) we register all tools.
    """
    terminal_id = os.environ.get("CAO_TERMINAL_ID")
    allowlist: Optional[List[str]] = None
    if terminal_id:
        allowlist = _resolve_allowlist_for_terminal(terminal_id)
    registered = _register_tools(_PENDING_TOOLS, allowlist, mcp)
    logger.info(
        f"Registered {len(registered)}/{len(_PENDING_TOOLS)} MCP tools "
        f"(allowlist={'permissive' if allowlist is None else sorted(allowlist)}): "
        f"{sorted(registered)}"
    )
    mcp.run()


if __name__ == "__main__":
    main()
