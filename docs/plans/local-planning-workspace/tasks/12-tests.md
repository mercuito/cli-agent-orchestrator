# Task 12: Cross-cutting tests

Part of: [../plan.md](../plan.md) — Implementation Tasks → Tests.

## Goal

Tests directly tied to a single Implementation task are owned by that
task and listed there. This task owns the cross-cutting integration tests
that compose multiple pieces of the implementation, plus the
end-to-end flows that exercise the full workspace.

## Dependencies

All prior tasks (01–11) complete.

## Files Touched

- `test/local_planning/` — integration tests.
- `test/workspaces/` — additions exercising the new flag end-to-end.
- `test/api/` — endpoint flow tests not covered by per-task scope.

## What to do

Implement integration coverage per the plan's Tests bullet list:

1. **Workspace + provider registration** — both registries return the new
   entries; existing `linear_delivery` still present.
2. **Event-type discovery** — all 18 events listed by
   `dispatcher.published_events()` after framework startup; one
   parametrized publish + round-trip test asserts no `UnknownCaoEventError`.
3. **Resolver matrix** — assert one resolution per recognized event type
   and `None` for unrecognized. Verify the eight sent-side events
   recognized, the eight received-side events return `None`, and Linear
   events return `None` through the local_planning resolver.
4. **create_plan from sentinel** — writes file, registers context with
   both metadata fields, builds + publishes event, triggers deferred
   switch. After watchdog drives idle, terminal has restarted in the new
   context with promoted state (Claude Code + Codex). Plan.md exists.
5. **create_plan from existing plan A (wrap-up flow)** — same flow with
   `promote_from_context_id` pointing to A. Target dir gets A's state.
6. **Promote helper matrix** — Claude Code/Codex copies, no-op for other
   providers, no-op when target dir populated, no-op when source dir
   empty, no-op when arming absent; metadata cleared after copy.
7. **complete_plan + list_plans** — completed plans appear in list with
   status=completed; agent stays on the (now completed) plan context.
8. **Sender guardrail** — sentinel sender on `local_planning` team
   rejected for send_message, handoff, assign, and each of the five baton
   transitions; corresponding sent event still published before
   rejection. Same scenarios on `linear_delivery` team succeed.
9. **Inheritance via handoff** — worker terminal lands in sender's plan
   context (assert via terminal metadata). Sent + received events match
   on correlation_id.
10. **send_message receiver-side switch** — receiver currently on plan B
    receives a message from sender on plan A; inbox notification created
    against `agent:<id>:context:plan_A`, terminal restarts in plan A, no
    message loss. Sent + received events both fire.
11. **send_message with stale `sender_id`** — 400, actionable error.
12. **Baton transitions across plans** — same context-switching behavior
    as send_message for each of the five transitions.
13. **handoff target already running on different plan** — 409
    preserved; sent event published, no received event, no force-switch
    attempted.
14. **Deferred-switch fires on next idle** — after `create_plan`
    returns "queued" while agent is BUSY, log change to IDLE triggers
    `apply_pending_workspace_context_switches`, switch lands, promote
    fires (for supported providers), seed-less new terminal exists, ready
    for next user message. `AgentTerminalStatusChangeEvent` published
    with settled state.
15. **No Linear regression** — existing Linear suites pass unchanged.

## Acceptance

- All listed scenarios have at least one passing test.
- `uv run pytest test/` green.
- `uv run python scripts/catalog_criteria.py` — for each criterion whose
  `when` clause matches the actual diff, document evaluation in the
  completion report (Task 13 / DoD).

## Out of scope

- Manual browser verification (covered in Required Verification at
  plan level).
- Performance / load tests.
