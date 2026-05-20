# Task 07: local_planning package skeleton

Part of: [../plan.md](../plan.md) — Target Shape → New Package, Workspace
Definition, Event Types (local planning events), Resolver, Adapter,
Provider.

## Goal

Stand up the new workspace tool provider package and register it with both
the workspace tool provider registry and the workspace registry. Includes
the adapter (minimal), the provider, the local-planning event type, the
resolver, and the registration glue.

Plan tools themselves are Task 08 — this task delivers the package shape
and registration, with stub tool handlers that can be filled in.

## Dependencies

- Task 01 (`Workspace.require_active_workspace_context` field exists).
- Task 03 (collaboration events exist so the resolver's `isinstance` check
  has real types to reference).

## Files Touched

New files under `src/cli_agent_orchestrator/local_planning/`:

- `__init__.py`
- `workspace_tool_provider.py` — `LocalPlanningWorkspaceToolProvider`.
- `workspace_adapter.py` — `LocalPlanningWorkspaceAdapter`.
- `workspace_context_resolver.py` — `resolve_local_planning_event`.
- `workspace_events.py` — `LocalPlanningPlanActivatedEvent`.

Modified files:

- `src/cli_agent_orchestrator/workspace_tool_providers/registry.py` —
  register the new provider in `default_workspace_tool_provider_registry`.
- `src/cli_agent_orchestrator/workspaces/manager.py` — register the
  `local_planning` workspace in `default_workspace_registry`.

New tests under `test/local_planning/`.

## What to do

1. `workspace_events.py`:
   - Define `LocalPlanningPlanActivatedEvent` with standard envelope plus
     `agent_id: str`, `plan_slug: str`,
     `workspace_context_id: str`.
   - Add `LOCAL_PLANNING_CAO_EVENTS` tuple containing this event.

2. `workspace_adapter.py`:
   - `LocalPlanningWorkspaceAdapter` mirrors `LinearWorkspaceAdapter`
     (`linear/workspace_adapter.py`) but with empty external identity:
     - `provider_name = "local_planning"`.
     - `build_candidate_mappings(agent_registry)` → returns `()`.
     - `build_provider_view(...)` returns a `WorkspaceToolProviderView`
       with `value=None` (or a small sentinel object).
     - `resolve_event_agent_id(...)` raises `WorkspaceConfigError`
       (this workspace doesn't process inbound external events).
     - `candidate_mappings_for_event(...)` returns `()`.
     - `describe_event_identity(event)` returns `"local_planning"` or
       similar.

3. `workspace_context_resolver.py`:
   - Implement `resolve_local_planning_event(event)` per the plan's
     Resolver section. The function:
     - Returns a `WorkspaceContextResolution` for the 8 sent-side
       collaboration events when the sender is not on the sentinel
       context.
     - Returns `None` when the sender is on the sentinel context.
     - Returns a `WorkspaceContextResolution` for
       `LocalPlanningPlanActivatedEvent` mapped to the target plan's
       context.
     - Returns `None` for any other event type (received-side events,
       Linear events, etc.).
   - Helper `_slug_for_context(context_id)` reads the context's
     `boundary_object_id`. Or accept that the resolver constructs the
     resolution from the event's own fields and doesn't always need a DB
     lookup.

4. `workspace_tool_provider.py`:
   - `LocalPlanningWorkspaceToolProvider`:
     - `name = "local_planning"`.
     - `initialize()` — no-op (no external state).
     - `published_cao_events()` — returns `LOCAL_PLANNING_CAO_EVENTS`.
     - `provider_tool_access()` — returns a `ProviderToolAccessPolicy`.
       For this task, declare the five tool names with stub handlers
       (raise `NotImplementedError`) so Task 08 can wire them up. The
       policy itself should be well-formed.

5. Register provider in
   `workspace_tool_providers/registry.py:default_workspace_tool_provider_registry`
   with a factory that constructs `LocalPlanningWorkspaceToolProvider`.

6. Register workspace in
   `workspaces/manager.py:default_workspace_registry`:
   ```
   Workspace(
       id="local_planning",
       display_name="Local Planning",
       providers=("local_planning",),
       resolver=resolve_local_planning_event,
       require_active_workspace_context=True,
   )
   ```

7. Also register the workspace's adapter in
   `default_workspace_collaboration_manager`:
   ```
   provider_adapters={"linear": LinearWorkspaceAdapter(),
                       "local_planning": LocalPlanningWorkspaceAdapter()}
   ```

## Acceptance

- `default_workspace_registry().get("local_planning")` returns the new
  workspace.
- `default_workspace_tool_provider_registry()` can create the provider.
- `LocalPlanningWorkspaceToolProvider.provider_tool_access()` returns a
  valid `ProviderToolAccessPolicy` declaring the five plan tools.
- Resolver returns expected resolutions for the eight sent-side
  collaboration events (the 8 from Task 03), the plan activation event,
  and `None` for unrecognized events.
- Existing `linear_delivery` workspace flows untouched.

## Tests

- Registry returns the workspace and the provider.
- Resolver tests (one per event family).
- Tool access policy structure (five tools declared with stub handlers).

## Out of scope

- Real tool handlers — Task 08 fills them in.
- Tool gating via role grants — relies on existing team role machinery,
  no new work here.
