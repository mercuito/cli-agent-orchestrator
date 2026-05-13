# Feature Task Handoff: t-3 — Live Identity Timeline Refresh

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-3` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete live dashboard state and polling references. |

## Task Brief

Add live refresh to the watched identity timeline. Done means that while
the operator remains on one agent identity view, new CAO events involving
that identity appear without a dashboard reload, while newly recorded
workspace events with no agent participants do not appear on that
identity timeline.

## Slice Reference

See `../tasks.md#t-3--live-identity-timeline-refresh` for assigned
Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-identity-timeline-view/committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### Product / Domain References

- `docs/plans/agent-identity-timeline-view/narrative.md`: domain story for
  live Aria timeline updates and non-participant workspace refreshes.
- `docs/plans/agent-identity-timeline-view/behavioral-contract.md`: exact
  `B-11` live-refresh behavior owned by this task.

### Existing Code References

- `web/src/components/AgentPanel.tsx`: existing polling patterns for
  terminal status, monitoring sessions, batons, and session detail refresh.
- `web/src/components/InboxPanel.tsx`: existing dashboard component pattern
  for periodic refresh inside a focused panel.
- `web/src/store.ts`: existing store reconciliation helpers for replacing
  dashboard state without unnecessary re-renders.
- `web/src/test/components.test.tsx`: existing tests for polling-triggered
  dashboard state changes.
- `web/src/test/store.test.ts`: store update and reconciliation test
  patterns.

## Verification Command

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run && npm run build
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-identity-timeline-view/tasks/t-3/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-identity-timeline-view/tasks/t-3/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-identity-timeline-view/tasks/t-3/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-identity-timeline-view/tasks/t-3/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-3/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-3/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-3/test-contract-defence.md`
