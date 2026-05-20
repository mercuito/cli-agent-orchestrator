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

## Out of scope

- Real tool handlers — Task 08 fills them in.
- Tool gating via role grants — relies on existing team role machinery,
  no new work here.

## Definition of Done

1. `default_workspace_registry().get("local_planning")` returns the new
   workspace with the correct id, display_name, providers tuple,
   resolver, and `require_active_workspace_context=True`.
2. `default_workspace_tool_provider_registry()` can construct
   `LocalPlanningWorkspaceToolProvider`.
3. `LocalPlanningWorkspaceToolProvider.provider_tool_access()` returns a
   valid `ProviderToolAccessPolicy` declaring the five plan tools with
   stub `NotImplementedError` handlers (Task 08 fills them in).
4. `LocalPlanningWorkspaceAdapter` returns empty candidate mappings, a
   provider view with `value=None`, and raises on
   `resolve_event_agent_id`.
5. `resolve_local_planning_event` returns context resolutions for the
   eight sent-side collaboration events and for
   `LocalPlanningPlanActivatedEvent`; returns `None` for the eight
   received-side events and for any unrecognized event type.
6. Existing `linear_delivery` flows untouched. Linear resolver tests
   pass unchanged (the new local_planning resolver doesn't claim Linear
   event types), and Linear's `LinearWorkspaceAdapter` remains the
   registered adapter for `provider_name="linear"` in
   `default_workspace_collaboration_manager`.
7. `LocalPlanningWorkspaceAdapter` is registered alongside
   `LinearWorkspaceAdapter` under `provider_name="local_planning"` in
   the default collaboration manager.
8. Registry tests assert workspace + provider visibility.
9. Resolver tests (parametrized, one per event family).
10. Tool access policy structure test (five tools declared with stubs).
11. Linear non-regression: Linear resolver still returns its expected
    resolutions for Linear events when consulted directly.

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
