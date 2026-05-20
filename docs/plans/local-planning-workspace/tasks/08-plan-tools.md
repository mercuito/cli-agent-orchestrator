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
`promote_from_context_id` metadata fields) on the workspace contexts they
register.

## Dependencies

- Task 02 (`WORKSPACE_CONTEXT_STATUS_COMPLETED` exists for `complete_plan`).
- Task 03 (events) — `LocalPlanningPlanActivatedEvent` exists.
- Task 04 (`apply_outbound_resolution` — though plan tools call
  `resolve_event_context` directly for the activation event, they don't
  need flag-enforced consultation since they emit their own activation
  events).
- Task 05 (promote helper exists; arming reads `promote_from_context_id`
  metadata).
- Task 06 (deferred-switch firing exists; arming reads
  `pending_for_agent_id` metadata).
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
2. Validate slug uniqueness: query workspace contexts where
   `resolver_id == "local_planning"` and `object_id == slug`. If exists,
   reject with a clear error.
3. Create directory `<agent.workdir>/docs/plans/<slug>/` (mkdir -p).
4. Write `plan.md` containing `body`.
5. Call `ensure_workspace_context_for_boundary(resolver_id="local_planning",
   provider_id="local_planning", object_type="plan", object_id=slug,
   metadata={"promote_from_context_id": caller_current_context_id,
   "pending_for_agent_id": caller_agent_id})`.
6. Build `LocalPlanningPlanActivatedEvent` and publish it via the default
   dispatcher (so the event hits the persistence layer and any listeners).
7. Call `manager.resolve_event_context(caller_agent, event)` for protocol
   consistency (resolver returns the new plan's context); use this result
   to construct `AgentRuntimeHandle(caller_agent,
   workspace_context_id=resolution.workspace_context_id)` and call
   `ensure_started()` once. The handle will defer if BUSY (it is — the
   tool is mid-call); the watchdog will drive the actual switch later.
8. Return `{"plan_id": slug, "status": "queued", "message": "Plan
   created. Context switch will take effect on your next idle moment."}`.

### `activate_plan(plan_id)`

1. Look up the plan's workspace context by `(resolver_id="local_planning",
   object_type="plan", object_id=plan_id)`. If missing, reject.
2. If the target plan's provider data dir is empty AND the caller has a
   non-sentinel current context (i.e., they're transitioning from another
   plan), set `promote_from_context_id = caller_current_context_id` on
   the target's metadata. If the target already has prior state, skip
   this (the target's own history resumes).
3. Always set `pending_for_agent_id = caller_agent_id` on the target. If
   the target already had a `pending_for_agent_id` set (e.g., a stale
   prior arm that hasn't fired yet), overwrite it. "Latest arm wins" —
   idempotent.
4. Build and publish `LocalPlanningPlanActivatedEvent`.
5. Call resolve + `AgentRuntimeHandle.ensure_started` once. Same
   deferred-on-busy semantics.
6. Return acknowledgment dict.

### `list_plans()`

1. Query workspace contexts where `resolver_id == "local_planning"` and
   `object_type == "plan"`.
2. Return a list of `{plan_id (slug), display_name (slug as fallback),
   status, created_at, updated_at}`.
3. May include completed plans; the caller filters.

### `get_active_plan()`

1. Read caller terminal's `workspace_context_id` from metadata.
2. Look up the workspace context. If it's a `local_planning` plan
   (`resolver_id == "local_planning"`), return its details. Otherwise
   return `{"active_plan": null}`.

### `complete_plan(plan_id)`

1. Look up the plan's workspace context. Reject if missing.
2. Call `mark_workspace_context_completed(context_id)` (from Task 02).
3. Return `{"plan_id": plan_id, "status": "completed"}`.
4. Do **not** transition the caller off the plan. The agent stays on the
   (now completed) context until they explicitly transition via
   `create_plan` or `activate_plan`.

## Acceptance

- `create_plan("My Plan", "Body...")`: file at
  `<workdir>/docs/plans/my-plan/plan.md` exists with body; workspace
  context registered with both metadata fields set; tool returns "queued"
  dict.
- `activate_plan("existing-plan")`: existing workspace context is
  re-armed; tool returns "queued" dict.
- `activate_plan("does-not-exist")`: rejects cleanly.
- `list_plans()`: enumerates registered plans, including completed.
- `get_active_plan()`: returns the current plan, or null for sentinel.
- `complete_plan(slug)`: flips status; subsequent `list_plans` reflects.
- All handlers reject when the calling terminal lacks an agent_id (i.e.,
  invariant violation) with a clear error.

## Tests

- Each handler with success cases.
- Validation/error cases per handler.
- End-to-end: create → activate (already active so no-op) → complete →
  list shows completed.
- Slug collision rejection.
- Plan directory creation idempotence (don't fail if `docs/plans/` exists
  already from a prior run).

## Out of scope

- Auto-deletion or archival of completed plans.
- Sub-plans / nested plans.
- Plan metadata beyond the title and body (e.g., owner, tags) — can be
  added in followup.
