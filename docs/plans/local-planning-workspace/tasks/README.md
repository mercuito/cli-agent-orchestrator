# Local Planning Workspace — Tasks

Execution-ready breakdown of [../plan.md](../plan.md). Each task is a
self-contained unit; the master plan remains the authoritative design
source. Read the plan first; tasks reference back to it for context.

## Order and dependencies

Tasks are numbered to suggest a feasible order but several can be done in
parallel. Hard dependencies are noted per task.

```
01 workspace-flag                ─┐
02 workspace-context-status-completed
02a workspace-context-store-helpers
03 runtime-collaboration-events  ─┼─→ 04 apply-outbound-resolution
                                   │
                                   ├─→ 05 promote-helper
                                   │   06 deferred-switch-firing
                                   │
                                   ├─→ 07 local-planning-package
                                   │       │
                                   │       └─→ 08 plan-tools
                                   │
                                   ├─→ 09 wire-inbox-endpoint
                                   ├─→ 10 wire-agent-start-endpoint
                                   └─→ 10b baton-agent-ownership
                                           │
                                           └─→ 11 wire-baton-service
                                       │
                                       └─→ 12 tests
                                           13 docs
```

Foundational pieces (01–04, including 02a) land first. Runtime hooks
(05, 06) can run in parallel with the local_planning package skeleton (07).
Task 08 depends on 05, 06, and 07 because it wires real handlers that arm
metadata consumed by the promote and deferred-switch paths.
Endpoint/service wiring (09–11) depends on 03 + 04; Task 11 also depends
on 10b so baton ownership survives receiver terminal replacement. Tests
(12) compose everything; docs (13) come last.

## Tasks

- [01-workspace-flag.md](01-workspace-flag.md) — Add
  `Workspace.require_active_workspace_context` field.
- [02-workspace-context-status-completed.md](02-workspace-context-status-completed.md)
  — Add `WORKSPACE_CONTEXT_STATUS_COMPLETED` constant + transition helper.
- [02a-workspace-context-store-helpers.md](02a-workspace-context-store-helpers.md)
  — Add by-id lookup, resolver-filtered listing, metadata patch/clear,
  pending metadata lookup, database migration support, and database
  re-exports.
- [03-runtime-collaboration-events.md](03-runtime-collaboration-events.md)
  — Define 16 agent collaboration events plus
  `AgentTerminalStatusChangeEvent`; register helpers.
- [04-apply-outbound-resolution.md](04-apply-outbound-resolution.md) —
  `WorkspaceCollaborationManager.apply_outbound_resolution(agent, event)`.
- [05-promote-helper.md](05-promote-helper.md) — Promote-path code in
  terminal-start flow driven by agent-scoped context-workspace metadata.
- [06-deferred-switch-firing.md](06-deferred-switch-firing.md) — Two-phase
  watchdog emission + `apply_pending_workspace_context_switches` helper.
- [07-local-planning-package.md](07-local-planning-package.md) — Package
  skeleton: adapter, provider, resolver, plan-activation event, registry
  + workspace registration.
- [08-plan-tools.md](08-plan-tools.md) — Implement create_plan,
  activate_plan, list_plans, complete_plan, get_active_plan handlers.
- [09-wire-inbox-endpoint.md](09-wire-inbox-endpoint.md) — Emit sent +
  received message events; route delivery through `handle.notify`.
- [10-wire-agent-start-endpoint.md](10-wire-agent-start-endpoint.md) —
  Handoff/assign sent + received events; MCP-side sender-info propagation.
- [10b-baton-agent-ownership.md](10b-baton-agent-ownership.md) — Move baton
  ownership to durable agent ids so terminal replacement does not change the
  holder/originator.
- [11-wire-baton-service.md](11-wire-baton-service.md) — Emit sent +
  received events for each of the 5 baton transitions.
- [12-tests.md](12-tests.md) — Test plan.
- [13-docs.md](13-docs.md) — Update current docs.

## Definition of Done

Each task carries its own concentrated Definition of Done section listing
behavior + test acceptance criteria. The master plan's overall
Definition of Done remains authoritative — when all tasks complete, the
plan-level DoD should be satisfied.

## Review Gate

Each task carries its own Review Gate. Two successive clean review
passes are required to mark a task complete; review findings are
recorded under the task's heading in
[../completion-report.md](../completion-report.md). The plan as a whole
is complete only when all tasks have completed their Review Gates.
