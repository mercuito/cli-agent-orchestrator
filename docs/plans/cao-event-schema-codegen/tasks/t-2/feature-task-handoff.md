# Feature Task Handoff: t-2 — Generated Event Payload Types

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff points to the approved `t-2` entry in `feature-tasks.md`. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff carries slice, committed-decision, verification, and coding-artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task entry requires backend schema-generation, frontend typing, and frontend codegen proof references. |

## Task Brief

Replace the hand-rolled frontend event type artifact with schema-generated
event payload declarations and migrate known event-view typing and codegen
wiring to the new artifact. Done means frontend event views consume generated
payload typing, retired codegen surfaces are removed or replaced as required,
and the public timeline API response envelope remains unchanged.

## Slice Reference

See `../feature-tasks.md#t-2--generated-event-payload-types` for assigned
Behavioral, Code, and Test slices. The universal `test-validity-preserved`
criterion applies regardless.

## Committed Implementation Decisions

See `../../feature-committed-implementation-decisions.md`. All entries are in
force for this task.

## Supporting References

Use these references during task research and implementation planning.

### Existing Code References

- `scripts/generate_cao_event_type_keys.py`: retired hand-rolled generator
  whose call sites and output are replaced by the new schema-driven pipeline.
- `web/package.json` and `web/package-lock.json`: frontend codegen command,
  pretest/prebuild wiring, and dependency lockfile surface.
- `web/src/generated/caoEventTypeKeys.ts`: current generated event key artifact
  consumed by frontend tests and event views.
- `web/src/components/timelineEventViews.tsx`: event-view registry and fallback
  view surface that consumes event metadata and payloads.
- `web/src/components/timelineEventViews/knownCaoEventViews.tsx`: known event
  view modules currently consuming generated event key constants and raw
  payload field access.
- `src/cli_agent_orchestrator/runtime/events.py` and
  `src/cli_agent_orchestrator/linear/workspace_events.py`: backend event
  declarations used as the schema source after `t-1` lands.

### Test And Proof References

- `web/src/test/agent-identity-timeline-panel.test.tsx`: frontend timeline
  rendering and known-event view baseline.
- `web/src/test/agent-panel-deeplink.test.tsx`: frontend event key/deeplink
  baseline affected by generated compatibility constants.
- `web/src/test/api.test.ts`: frontend API client baseline for timeline event
  response shape and generated type consumption.

## Verification Command

```bash
cd web && npm test -- agent-identity-timeline-panel.test.tsx agent-panel-deeplink.test.tsx api.test.ts
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-event-schema-codegen/tasks/t-2/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-event-schema-codegen/tasks/t-2/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-event-schema-codegen/tasks/t-2/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-event-schema-codegen/tasks/t-2/coding-completion-report.md`
- Behavioral Contract Defence: not applicable; no Behavioral Contract slice is assigned for this pure refactor task.
- Code Contract Defence: `docs/plans/cao-event-schema-codegen/tasks/t-2/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-event-schema-codegen/tasks/t-2/test-contract-defence.md`

## Dependencies

This task depends on `t-1`; do not start until the kinded persistence foundation
has completed or the dependency is explicitly reissued.
