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
2. **Event-type discovery** — the 17 runtime-owned events are listed by
   `dispatcher.published_events()` after framework startup; the
   `LocalPlanningPlanActivatedEvent` is registered during API startup and
   through the plan-tool publish path. Parametrized publish + round-trip
   tests assert no `UnknownCaoEventError`.
3. **Resolver matrix** — assert one resolution per recognized event type
   and `None` for unrecognized. Verify the eight sent-side events
   recognized, the eight received-side events return `None`, and Linear
   events return `None` through the local_planning resolver.
4. **create_plan from sentinel** — writes file, registers context and
   agent-scoped context-workspace metadata fields, uses
   `boundary_object_id=<workdir_scope>:<slug>`, builds + publishes event,
   triggers deferred switch. After watchdog drives idle, terminal has
   restarted in the new context with promoted state (Claude Code + Codex).
   Plan.md exists.
5. **create_plan from existing plan A (wrap-up flow)** — same flow with
   agent-scoped `promote_from_context_id` pointing to A. Target dir gets
   A's state.
6. **Promote helper matrix** — Claude Code/Codex copies, no-op for other
   providers, no-op when target dir populated, no-op when source dir
   empty, no-op when arming absent; agent/context metadata cleared after
   copy. Two agents sharing a plan do not consume or clear each other's
   arming.
7. **complete_plan + list_plans** — completed plans appear in list with
   status=completed for the caller's workdir scope; same slug in a
   different workdir scope is isolated; agent stays on the (now completed)
   plan context.
8. **Sender guardrail** — sentinel sender on `local_planning` team
   rejected for send_message, handoff, assign, and each of the five baton
   transitions; corresponding sent event still published before
   rejection. Same scenarios on `linear_delivery` team succeed.
8a. **Same-team authorization** — cross-team send_message/handoff/assign
    and baton transitions still reject before routing; context resolution
    does not bypass existing same-team collaboration policy.
9. **Inheritance via handoff** — worker terminal lands in sender's plan
   context (assert via terminal metadata). Sent + received events match
   on correlation_id.
10. **send_message receiver-side switch** — receiver currently on plan B
    receives a message from sender on plan A; inbox notification created
    against `agent:<id>:context:<plan_A_context_id>`, terminal restarts in
    plan A, no message loss. Sent + received events both fire.
10a. **Batched received message events** — when
     `check_and_send_pending_messages` delivers multiple collaboration
     inbox deliveries in one batch, one `AgentMessageReceivedEvent` fires
     per delivered `InboxDelivery`, each with its own inbox id and
     correlation metadata.
11. **send_message with stale `sender_id`** — 400, actionable error.
12. **Baton transitions across plans** — same context-switching behavior
    as send_message for each of the five transitions. When notify replaces
    the receiver terminal, baton `originator_agent_id`,
    `current_holder_agent_id`, and `return_stack_agent_ids_json` continue to
    identify the same durable agents, the new holder can take the next baton
    action from the replacement terminal, and the watchdog does not orphan the
    baton because an old terminal id disappeared.
13. **handoff target already running on different plan** — 409
    preserved; sent event published, no received event, no force-switch
    attempted.
14. **Deferred-switch fires on next idle** — after `create_plan`
    returns "queued" while agent is BUSY, log change to IDLE triggers
    `apply_pending_workspace_context_switches`, switch lands, promote
    fires (for supported providers), seed-less new terminal exists, ready
    for next user message. `AgentTerminalStatusChangeEvent` published
    with settled state.
14a. **Agent-scoped arming isolation** — two agents sharing the same plan
     context can arm pending switch/promote independently; firing one
     agent's switch does not clear or consume the other's metadata.
14b. **Context-keyed inbox idle-fire** — a BUSY receiver with a pending
     `agent:<id>:context:<ctx>` message/baton notification but no
     `pending_for_agent_id` metadata is discovered by the watchdog on IDLE;
     `try_deliver_pending()` runs for `<ctx>` and the notification is not
     stranded.
15. **No Linear regression** — existing Linear suites pass unchanged.
16. **Shared workdir invariant** — `local_planning` teams whose members do
    not share the same normalized `workdir` produce a blocking diagnostic
    and collaboration routing rejects inheritance into that team.

## Out of scope

- Manual browser verification (covered in Required Verification at
  plan level).
- Performance / load tests.

## Definition of Done

1. Workspace + provider registration scenario passes: both registries
   return the new entries; existing `linear_delivery` still present.
2. Event-type discovery scenario passes: all 17 runtime-owned events listed
   by `dispatcher.published_events()` after framework startup; local
   planning activation event registration is verified at API startup and
   through the plan-tool publish path; parametrized publish + round-trip
   assertion succeeds for all 18 introduced event types.
3. Resolver matrix scenario passes: one resolution per recognized event
   type, `None` for unrecognized. Sent-side recognized; received-side
   returns `None`; Linear events return `None`.
4. `create_plan` from sentinel scenario passes: file written, context
   registered with scoped `boundary_object_id=<workdir_scope>:<slug>` and
   agent-scoped context-workspace metadata fields, deferred switch triggered,
   after idle the terminal has restarted in the new context with
   promoted state for Claude Code + Codex.
5. `create_plan` from existing plan A scenario passes: target dir
   receives A's state after the switch.
6. Promote helper matrix scenario passes: Claude Code/Codex copy,
   no-op for other providers, no-op when target populated, no-op when
   source empty, no-op when arming absent; agent/context metadata cleared
   after copy and not cleared for another agent sharing the plan.
7. `complete_plan` + `list_plans` scenario passes: completed plans
   appear in list with `status="completed"` for the caller's workdir scope;
   same slug in a different workdir scope is allowed and not listed; agent
   stays on the (now completed) plan context.
8. Sender guardrail scenario passes for all four actions and five
   baton transitions: sentinel sender on `local_planning` rejected with
   sent event still published; sentinel sender on `linear_delivery`
   succeeds.
8a. Same-team authorization scenario passes for send_message, handoff,
    assign, and baton transitions: cross-team sender/receiver pairs reject
    before routing and do not create delivery records.
9. Handoff inheritance scenario passes: worker lands in sender's plan
   context; sent + received events match on `correlation_id`.
10. send_message receiver-side switch scenario passes: cross-plan
    notification keyed `agent:<id>:context:<plan_A_context_id>`; receiver
    restarts in plan A; no message loss; both events fire.
10a. Batched received message event scenario passes: a batch with multiple
     collaboration deliveries publishes one received event per delivered
     `InboxDelivery`, preserving each delivery's inbox id and correlation.
11. send_message with stale `sender_id` scenario passes: 400 with
    actionable error.
12. Baton cross-plan scenario passes for all five transitions, including a
    follow-up holder action from the receiver's replacement terminal after a
    context switch and a watchdog scan that does not orphan an agent-owned
    baton because an old terminal id disappeared.
13. handoff target already running on different plan scenario passes:
    409 preserved; sent event published, no received event, no
    force-switch.
14. Deferred-switch idle-fire scenario passes: BUSY-at-create →
    finish-turn → IDLE → watchdog drives switch + promote → new
    terminal in new context; `AgentTerminalStatusChangeEvent` published
    with settled state.
14b. Context-keyed inbox idle-fire scenario passes: pending
     `agent:<id>:context:<ctx>` notification from send_message/baton is
     discovered on IDLE even without `pending_for_agent_id`; watchdog calls
     `try_deliver_pending()` for `<ctx>` and delivery completes when ready.
15. No Linear regression: existing Linear suites pass unchanged.
15a. Shared workdir invariant scenario passes: mixed-workdir
     `local_planning` teams produce a diagnostic and are rejected before a
     receiver can inherit a plan context whose file tree is absent locally.
16. The plan's "Required backend checks" run green:
    - `uv run pytest test/workspaces`
    - `uv run pytest test/clients/test_workspace_context_store.py`
    - `uv run pytest test/local_planning`
    - `uv run pytest test/api`
    - `uv run pytest test/mcp_server/test_handoff.py test/mcp_server/test_assign.py`
    - `uv run pytest test/services/test_inbox_service.py`
    - `uv run pytest test/services/test_baton_service.py`
    - `uv run pytest test/runtime`
    - `uv run pytest test/linear`
17. **Criteria-catalog gate (blocking)**: `uv run python
    scripts/catalog_criteria.py` evaluated against the full
    implementation diff. For each criterion whose `when` clause matches,
    document evaluation in the completion report. No applicable
    criterion may be violated. This is plan-level DoD #15 enforced here
    as a blocking acceptance gate for the test task.

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
