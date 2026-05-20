# Task 04: WorkspaceCollaborationManager.apply_outbound_resolution

Part of: [../plan.md](../plan.md) — Target Shape →
`Workspace.require_active_workspace_context` Flag and the manager method
that consumes it.

## Goal

Add the single seam that all outbound-action call sites use to consult
the workspace's resolver AND enforce the
`require_active_workspace_context` flag. This is what task 09, 10, 11 will
call.

## Dependencies

- Task 01 (flag must exist on Workspace).
- Task 03 (the sent-side event types must exist so callers can construct
  them).

## Files Touched

- `src/cli_agent_orchestrator/workspaces/manager.py` —
  `WorkspaceCollaborationManager` class.
- `test/workspaces/test_collaboration_manager.py` (or equivalent).

## What to do

1. Add the method, signature roughly:

   ```python
   def apply_outbound_resolution(
       self, agent: Agent, event: CaoEvent
   ) -> WorkspaceContextResolution:
       """Resolve outbound action context, enforcing workspace flag.

       Calls self.workspace_for_agent(agent), then resolve_event_context.
       If the workspace's require_active_workspace_context is True and the
       resolution is None, raise WorkspaceConfigError with an actionable
       message ("sender has no active plan; create or activate one before
       collaborating"). Otherwise returns the resolution (which may be
       None for workspaces that allow sentinel senders).
       """
   ```

2. Choose the error semantics carefully: today `resolve_event_context`
   returns `WorkspaceContextResolution | None`. The new method returns
   `WorkspaceContextResolution` (non-optional) when the flag is True, and
   `WorkspaceContextResolution | None` when the flag is False. Pick one
   return type — recommend `WorkspaceContextResolution | None` and document
   that the manager raises before returning when the flag fires; callers
   that need a non-None always-use-the-resolution semantic can assert in
   their own code.

3. The error type stays `WorkspaceConfigError` to fit the rest of the
   workspace module's error vocabulary.

## Acceptance

- Workspace with `require_active_workspace_context=False`: sentinel sender
  → returns `None` (existing semantics preserved).
- Workspace with `require_active_workspace_context=True`: sentinel sender
  → raises `WorkspaceConfigError` with actionable message.
- Both: resolved sender → returns a `WorkspaceContextResolution`.
- Method works when the agent has no workspace team (no team membership →
  resolver returns None → behaves like `require_active_workspace_context=False`
  unless the workspace flag is set; document the edge case).

## Tests

- Parametrized over the four combinations: flag True/False × sentinel/active sender.
- Edge: agent with no team membership.
- Edge: workspace not in registry (existing error path should still fire).

## Out of scope

- Wiring this into the inbox/start/baton call sites (Tasks 09–11).
- Changing `resolve_event_context` itself.
