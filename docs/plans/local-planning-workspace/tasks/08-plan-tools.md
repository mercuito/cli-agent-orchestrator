# Task 08: Plan tool handlers

Part of: [../plan.md](../plan.md) — Target Shape → Plan Tools.

## Goal

Implement the five plan-lifecycle tool handlers exposed by the
`local_planning` workspace tool provider:

- `create_plan(title, body)`
- `activate_plan(plan_id)`
- `list_plans()`
- `get_active_plan()`
- `complete_plan(plan_id)`

Includes the deferred-switch arming (`pending_for_agent_id` and
`promote_from_context_id` metadata fields) on the caller's agent-local
context workspace row for the target plan.

## Dependencies

- Task 02 (`WORKSPACE_CONTEXT_STATUS_COMPLETED` exists for `complete_plan`).
- Task 02a (workspace-context lookup/list/metadata helpers exist).
- Task 03 (events) — `LocalPlanningPlanActivatedEvent` exists.
- Task 04 (`apply_outbound_resolution` — though plan tools call
  `resolve_event_context` directly for the activation event, they don't
  need flag-enforced consultation since they emit their own activation
  events).
- Task 05 (promote helper exists; arming reads agent-scoped
  `promote_from_context_id` metadata).
- Task 06 (deferred-switch firing exists; arming reads
  agent-scoped `pending_for_agent_id` metadata).
- Task 07 (package skeleton exists; tools get wired into the provider's
  policy).

## Files Touched

- `src/cli_agent_orchestrator/local_planning/plans.py` (new) — handler
  implementations.
- `src/cli_agent_orchestrator/local_planning/workspace_tool_provider.py`
  — wire the real handlers into `provider_tool_access()` replacing the
  Task 07 stubs.
- `test/local_planning/test_plans.py` (new).

## What to do

For each handler, conform to `ProviderToolHandler` Protocol from
`workspace_tool_providers/tool_access.py:25`:

```
def handler(
    context: ProviderToolInvocationContext, arguments: Mapping[str, Any]
) -> Any: ...
```

Resolve the calling agent + terminal via `context.agent` and
`context.terminal_id`, the workspace_context_id via terminal metadata
lookup. Use the appropriate `db_module` helpers for context store.

### `create_plan(title, body)`

1. Generate slug from title (kebab-case; alphanumeric + hyphen only).
2. Compute `workdir_scope = sha256(normalized agent.workdir)[:16]` (or a
   similarly stable deterministic scope) and
   `plan_object_id = f"{workdir_scope}:{slug}"`.
3. Validate slug uniqueness in the caller's shared workdir: query workspace
   contexts where `resolver_id == "local_planning"` and
   `object_id == plan_object_id`. If exists, reject with a clear error.
4. Create directory `<agent.workdir>/docs/plans/<slug>/` (mkdir -p).
5. Write `plan.md` containing `body`.
6. Call `ensure_workspace_context_for_boundary(resolver_id="local_planning",
   provider_id="local_planning", object_type="plan",
   object_id=plan_object_id, metadata={"plan_slug": slug,
   "workdir_scope": workdir_scope, "workdir": normalized_workdir})`,
   ensure the caller's context workspace row exists, then set
   `promote_from_context_id` and `pending_for_agent_id` with the
   context-workspace metadata patch helper. Do not store these fields on the
   global workspace context row.
7. Build `LocalPlanningPlanActivatedEvent(plan_slug=slug,
   workdir_scope=workdir_scope, ...)` and publish it via the default
   dispatcher (so the event hits the persistence layer and any listeners).
8. Call `manager.resolve_event_context(caller_agent, event)` for protocol
   consistency (resolver returns the new plan's context); use this result
   to construct `AgentRuntimeHandle(caller_agent,
   workspace_context_id=resolution.workspace_context_id)` and call
   `ensure_fresh_started(causing_event=event)` once. Do not use
   `ensure_started()` for this path because it raises when the context
   switch is deferred. Map `AgentRuntimeFreshnessAction.DEFERRED` to queued
   success; map `STARTED`, `REUSED`, and `RESTARTED` to active success. The
   watchdog will drive the actual switch later only for DEFERRED.
9. Return `{"plan_id": slug, "status": "queued" | "active", "message": ...}`:
   queued message when deferred, active message when the runtime switch
   already landed.

### `activate_plan(plan_id)`

1. Compute the caller's `workdir_scope` and
   `plan_object_id = f"{workdir_scope}:{plan_id}"`; look up the plan's
   workspace context by `(resolver_id="local_planning", object_type="plan",
   object_id=plan_object_id)`. If missing, reject.
2. If the target plan's provider data dir is empty AND the caller has a
   non-sentinel current context (i.e., they're transitioning from another
   plan), set `promote_from_context_id = caller_current_context_id` on
   the caller's target context-workspace metadata. If the target already
   has prior state, clear any stale `promote_from_context_id` on that
   caller/context instead (the target's own history resumes).
3. Always set `pending_for_agent_id = caller_agent_id` on the caller's
   target context-workspace metadata. If that same agent/context already had
   a `pending_for_agent_id` set (e.g., a stale prior arm that hasn't fired
   yet), overwrite it. "Latest arm wins" — idempotent.
4. Build and publish
   `LocalPlanningPlanActivatedEvent(plan_slug=plan_id,
   workdir_scope=workdir_scope, ...)`.
5. Call resolve + `AgentRuntimeHandle.ensure_fresh_started(causing_event=event)`
   once. Same deferred-on-busy semantics: map
   `AgentRuntimeFreshnessAction.DEFERRED` to queued success and
   STARTED/REUSED/RESTARTED to active success rather than surfacing an
   exception.
6. Return acknowledgment dict.

### `list_plans()`

1. Compute the caller's `workdir_scope`, then query workspace contexts where
   `resolver_id == "local_planning"` and `object_type == "plan"` and filter
   to `boundary_object_id` values prefixed by `f"{workdir_scope}:"`.
2. Return a list of `{plan_id (slug), display_name (slug as fallback),
   status, created_at, updated_at}`.
3. May include completed plans; the caller filters.

### `get_active_plan()`

1. Read caller terminal's `workspace_context_id` from metadata.
2. Look up the workspace context. If it's a `local_planning` plan
   (`resolver_id == "local_planning"`) and its `boundary_object_id` belongs
   to the caller's `workdir_scope`, return its details. Otherwise return
   `{"active_plan": null}`.

### `complete_plan(plan_id)`

1. Compute the caller's `workdir_scope` and look up the plan context by
   `object_id=f"{workdir_scope}:{plan_id}"`. Reject if missing.
2. Call `mark_workspace_context_completed(context_id)` (from Task 02).
3. Return `{"plan_id": plan_id, "status": "completed"}`.
4. Do **not** transition the caller off the plan. The agent stays on the
   (now completed) context until they explicitly transition via
   `create_plan` or `activate_plan`.

## Out of scope

- Auto-deletion or archival of completed plans.
- Sub-plans / nested plans.
- Plan metadata beyond the title and body (e.g., owner, tags) — can be
  added in followup.

## Definition of Done

1. `create_plan(title, body)` writes
   `<agent.workdir>/docs/plans/<slug>/plan.md` with the body, registers
   the workspace context with `boundary_object_id=<workdir_scope>:<slug>`
   and metadata containing `plan_slug` / `workdir_scope`, registers the
   caller's agent-local context-workspace row with both
   `promote_from_context_id` and `pending_for_agent_id` metadata fields set,
   publishes `LocalPlanningPlanActivatedEvent`, calls `ensure_fresh_started`
   once on a handle bound to the new context, maps DEFERRED to queued
   success and STARTED/REUSED/RESTARTED to active success, and returns an
   ack dict whose `status` is `"queued"` or `"active"` accordingly.
2. `activate_plan(plan_id)` re-arms an existing plan with
   `pending_for_agent_id` on the caller's target context-workspace row
   (overwriting any prior stale arm for that same agent/context — "latest
   arm wins"), conditionally sets `promote_from_context_id` only when the
   target dir is empty, publishes the activation event, calls
   `ensure_fresh_started` once and maps DEFERRED to queued success.
   STARTED/REUSED/RESTARTED map to active success.
   When the target dir already has prior state, it clears any stale
   `promote_from_context_id` for that caller/context instead of leaving an
   old promotion arm behind.
3. `list_plans()` enumerates only `local_planning` workspace contexts for
   the caller's `workdir_scope`, including completed ones, returning slug,
   display name, status, created_at, updated_at.
4. `get_active_plan()` returns the caller terminal's current plan
   details or `{"active_plan": null}` for sentinel.
5. `complete_plan(plan_id)` calls
   `mark_workspace_context_completed` and returns
   `{"plan_id": plan_id, "status": "completed"}` without transitioning
   the caller off the plan.
6. `create_plan` rejects on slug collision within the caller's
   `workdir_scope` with a clear error, while the same slug in another
   workdir scope is allowed.
7. Plan directory creation is idempotent — pre-existing `docs/plans/`
   does not cause failure.
8. All handlers reject with a clear error when the calling terminal
   lacks an `agent_id` (invariant violation).
9. Provider tool policy from Task 07 is updated to wire the real
   handlers in place of the stub `NotImplementedError` ones.
10. Per-handler success tests for each of the five tools.
11. Per-handler validation/error tests (collisions, missing plans,
    missing terminal context).
12. End-to-end test: create → activate (already active no-op) →
    complete → list shows completed.
13. Two agents sharing the same plan context can arm create/activate
    independently; one agent's arm does not overwrite or clear the other's
    metadata.

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
