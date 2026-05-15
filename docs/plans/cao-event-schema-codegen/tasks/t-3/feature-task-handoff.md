# Feature Task Handoff: t-3 — Compatibility And Replacement Sweep

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff points to the approved `t-3` entry in `feature-tasks.md`. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff carries slice, committed-decision, verification, and coding-artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task entry requires public timeline compatibility, caller discovery, and full preservation baseline references. |

## Task Brief

Complete the public timeline compatibility sweep after backend persistence and
frontend codegen replacements have landed. Done means the public timeline API
response envelope remains compatible, remaining `event_type_key` observations
are classified and defended, and the full backend/frontend preservation
baseline passes.

## Slice Reference

See `../feature-tasks.md#t-3--compatibility-and-replacement-sweep` for assigned
Behavioral, Code, and Test slices. The universal `test-validity-preserved`
criterion applies regardless.

## Committed Implementation Decisions

See `../../feature-committed-implementation-decisions.md`. All entries are in
force for this task.

## Supporting References

Use these references during task research and implementation planning.

### Existing Code References

- `src/cli_agent_orchestrator/api/main.py`: timeline response models and route
  conversion surfaces that must preserve the public response envelope.
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`: service
  layer producing timeline reads from persisted CAO event records.
- `src/cli_agent_orchestrator/clients/cao_event_store.py`: post-`t-1`
  persistence record shape and read-path source for public compatibility.
- `web/src/api.ts`: frontend API type surface that consumes timeline event
  response fields.
- `web/src/components/AgentIdentityTimelinePanel.tsx`: frontend timeline
  consumer of `event_type_key`, `event_data`, and related event payloads.
- `web/src/components/timelineEventViews.tsx`: frontend event-view registry
  lookup behavior to preserve after codegen migration.

### Test And Proof References

- `test/events/test_cao_event_persistence.py`: backend persistence baseline
  from the kinded storage task.
- `test/api/test_agent_identity_routes.py`: public API response compatibility
  baseline.
- `test/runtime/test_agent_runtime.py`: runtime event publication baseline.
- `web/src/test/agent-identity-timeline-panel.test.tsx`: frontend timeline
  rendering baseline.
- `web/src/test/agent-panel-deeplink.test.tsx`: frontend related/deeplink
  baseline.
- `web/src/test/api.test.ts`: frontend API client response-shape baseline.

## Verification Command

```bash
uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py && cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-event-schema-codegen/tasks/t-3/coding-completion-report.md`
- Behavioral Contract Defence: not applicable; no Behavioral Contract slice is assigned for this pure refactor task.
- Code Contract Defence: `docs/plans/cao-event-schema-codegen/tasks/t-3/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-event-schema-codegen/tasks/t-3/test-contract-defence.md`

## Dependencies

This task depends on `t-1` and `t-2`; do not start until both are complete or
the dependency graph is explicitly reissued.
