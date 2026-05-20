# Task 10: Wire agent-start endpoint with handoff/assign events + MCP propagation

Part of: [../plan.md](../plan.md) — Event Emission and Resolver
Consultation in API Endpoints → site #2 + MCP-side propagation.

## Goal

When `/agents/{id}/start` is hit by a handoff or assign action (not a
dashboard direct start), the API constructs the appropriate sent event,
runs it through the resolver, applies the resolved
`workspace_context_id` to the new `AgentRuntimeHandle`, and after the
terminal starts successfully, emits the matching received event.

Also: the MCP server propagates `CAO_TERMINAL_ID` and a `trigger_action`
discriminator so the API knows it's a handoff vs assign and has the
sender info.

## Dependencies

- Task 03 (`AgentHandoffInitiatedEvent`, `AgentHandoffAcceptedEvent`,
  `AgentAssignInitiatedEvent`, `AgentAssignAcceptedEvent` exist).
- Task 04 (`apply_outbound_resolution`).

## Files Touched

- `src/cli_agent_orchestrator/api/main.py:1752` —
  `start_agent_endpoint`.
- `src/cli_agent_orchestrator/mcp_server/server.py` — `_handoff_impl`,
  `_assign_impl`, `_create_terminal`. Propagate sender info + trigger
  kind in the POST.
- `test/api/` and `test/mcp_server/`.

## What to do

In MCP `_create_terminal`:

1. Read `os.environ["CAO_TERMINAL_ID"]` as `sender_terminal_id`. If
   present, include in the POST as a query param.
2. Add a `trigger_action` query param. Callers pass `"handoff"` or
   `"assign"`. `_handoff_impl` passes `"handoff"`; `_assign_impl` passes
   `"assign"`.
3. If the env var is not set (which shouldn't normally happen, but
   handle defensively), do not pass `sender_terminal_id` or
   `trigger_action`. The endpoint falls back to existing dashboard-direct
   behavior.

In API `start_agent_endpoint`:

4. Accept optional `sender_terminal_id: str | None = None` and
   `trigger_action: str | None = None` query params.
5. When `sender_terminal_id` is present:
   - Look up sender terminal metadata. If missing, reject with 400.
   - Resolve sender_agent_id, sender_workspace_context_id.
   - Build the appropriate event based on `trigger_action`:
     - `"handoff"` → `AgentHandoffInitiatedEvent`.
     - `"assign"` → `AgentAssignInitiatedEvent`.
     - Anything else → 400.
   - Publish the event.
   - Call `manager.apply_outbound_resolution(target_agent, event)` →
     resolution. If the workspace flag enforces and resolution is None,
     surface as 400 (same as Task 09).
6. Apply resolution to the runtime handle:
   - `AgentRuntimeHandle(target_agent,
     workspace_context_id=resolution.workspace_context_id)` when
     resolution exists.
   - `AgentRuntimeHandle(target_agent)` (sentinel default) when no
     event was built or resolution is None.
7. Existing `ensure_started()` flow continues.
8. After the terminal returns (start succeeded), publish the matching
   received event (`AgentHandoffAcceptedEvent` or
   `AgentAssignAcceptedEvent`) with the new terminal_id and matching
   correlation_id from the sent event's event_id.
9. Preserve the existing 409 behavior when the target agent already has
   a live terminal — the sent event still publishes (so the timeline
   shows the attempt), then 409 propagates. Received event does NOT
   publish in the 409 case.

## Out of scope

- handoff to already-running target on a different plan: stays as 409
  per the plan's design (out of scope for v1).
- The MCP `send_message` path (Task 09) — separate endpoint.

## Definition of Done

1. MCP `_create_terminal` reads `os.environ["CAO_TERMINAL_ID"]` and
   passes it as `sender_terminal_id` query param. `_handoff_impl` and
   `_assign_impl` pass `trigger_action="handoff"` and
   `trigger_action="assign"` respectively. If the env var is missing,
   neither param is passed (defensive fallback to dashboard-direct
   behavior).
2. API `start_agent_endpoint` accepts optional `sender_terminal_id` and
   `trigger_action` query params.
3. With sender info present and a valid `trigger_action`: API builds
   `AgentHandoffInitiatedEvent` or `AgentAssignInitiatedEvent`,
   publishes it, calls `manager.apply_outbound_resolution`, applies
   the resolution to the `AgentRuntimeHandle`.
4. Dashboard direct start (no sender info): existing sentinel default
   behavior preserved; no sent event published.
5. After successful terminal start with sender info: matching
   `AgentHandoffAcceptedEvent` / `AgentAssignAcceptedEvent` published
   with the new `terminal_id` and `correlation_id` referencing the sent
   event's `event_id`.
6. 409 on already-running target: sent event still published (timeline
   shows attempt), 409 returned, received event NOT published.
7. Sender on sentinel + `require_active_workspace_context=True`: 400
   with the sent event published before rejection.
8. Invalid `trigger_action` value: 400.
9. Invalid `sender_terminal_id` (no matching terminal): 400.
10. Tests cover MCP handoff, MCP assign, dashboard direct, 409,
    sentinel + flag, invalid trigger_action, invalid sender_terminal_id.
11. Correlation-id pairing test: received event's `correlation_id`
    references sent event's `event_id`.

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
