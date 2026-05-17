"""Linear mediated-tool workspace context resolution."""

from __future__ import annotations

from cli_agent_orchestrator.linear.provider_tools import CREATE_ISSUE_TOOL
from cli_agent_orchestrator.linear.workspace_context_resolver import (
    register_linear_workspace_context_resolver,
)
from cli_agent_orchestrator.linear.workspace_events import (
    publish_linear_issue_created_event,
)
from cli_agent_orchestrator.workspace_contexts import (
    WorkspaceContextResolution,
    resolve_workspace_context_for_agent,
)
from cli_agent_orchestrator.workspace_providers.tool_access import ProviderToolInvocationContext


def resolve_linear_tool_result_workspace_context(
    context: ProviderToolInvocationContext,
) -> WorkspaceContextResolution | None:
    """Resolve workspace context mappings implied by a Linear mediated tool result."""

    if context.tool_name != CREATE_ISSUE_TOOL:
        return None
    publication = publish_linear_issue_created_event(context)
    if publication is None:
        return None
    register_linear_workspace_context_resolver()
    return resolve_workspace_context_for_agent(context.agent, publication.event)
