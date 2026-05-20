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

## Out of scope

- Wiring this into the inbox/start/baton call sites (Tasks 09–11).
- Changing `resolve_event_context` itself.

## Definition of Done

1. `WorkspaceCollaborationManager.apply_outbound_resolution(agent,
   event)` exists with documented semantics.
2. Workspace with `require_active_workspace_context=False`: sentinel
   sender → returns `None` (existing semantics preserved).
3. Workspace with `require_active_workspace_context=True`: sentinel
   sender → raises `WorkspaceConfigError` with an actionable message
   ("sender has no active plan; create or activate one before
   collaborating" or equivalent).
4. Both flag states: resolved sender → returns a
   `WorkspaceContextResolution`.
5. Agent without workspace team membership: documented edge-case
   behavior (resolver returns None → matches
   `require_active_workspace_context=False` semantics unless the
   workspace flag is set).
6. Workspace not in registry: existing error path still fires.
7. Parametrized tests cover the four combinations: flag True/False
   × sentinel/active sender.
8. Edge tests cover agent without team and workspace not in registry.

## Review Gate

After implementing this task, run a review loop. The reviewer compares
the landed implementation against each item in Definition of Done above
plus all applicable entries in the `docs/criteria` catalog (run
`uv run python scripts/catalog_criteria.py` and load any criterion whose
`when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the
review loop restarts with a fresh reviewer. For every review finding
that requires an implementation change, the implementer updates
[../completion-report.md](../completion-report.md) under this task's
heading, recording what the reviewer found, why it was accepted as
valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero
valid findings for this task, and those two clean review passes are
recorded in the completion report.
