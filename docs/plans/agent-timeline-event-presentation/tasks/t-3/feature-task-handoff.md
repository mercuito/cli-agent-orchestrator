# Feature Task Handoff: t-3 — Related Presentation Continuity And Entity References

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-3` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete UI, navigation, product, and frontend proof references. |

## Task Brief

Complete the presentation behavior around related events and entity
references. Done means related events keep the same event presentations
they would have on the main timeline, external Linear issue references
open the issue context, and internal terminal references focus the
referenced CAO dashboard terminal.

## Slice Reference

See `../feature-tasks.md#t-3--related-presentation-continuity-and-entity-references`
for assigned Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-timeline-event-presentation/feature-committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### UI / Design References

- `docs/plans/agent-timeline-event-presentation/design/timeline-event-presentation-mock.png`: visual target for entity-reference chips and related-events sub-panel presentation.

### Product / Domain References

- `docs/plans/agent-timeline-event-presentation/feature-narrative.md`: domain story for related-event continuity, opening the Linear issue, and focusing the receiving terminal.
- `docs/plans/agent-timeline-event-presentation/feature-behavioral-contract.md`: exact behavior and invariant slices for related-event presentation continuity and entity-reference target integrity.
- `docs/plans/agent-timeline-event-presentation/feature-code-contract.md`: feature-level structured entity-reference obligation.
- `docs/plans/agent-timeline-event-presentation/feature-test-contract.md`: feature-level proof slice for related-event and entity-reference behavior.

### Existing Code References

- `web/src/components/AgentIdentityTimelinePanel.tsx`: related-events panel rendering, timeline row interactions, and identity timeline state management.
- `web/src/components/AgentPanel.tsx`: existing Agents dashboard boundary and terminal focus/deep-link behavior.
- `web/src/dashboardLink.ts`: dashboard link parsing used by existing focus/navigation flows.
- `web/src/store.ts`: dashboard state and terminal reconciliation used when focusing a CAO dashboard context.
- `web/src/api.ts`: frontend API types for presentation entity references returned by the backend.
- `web/src/test/agent-identity-timeline-panel.test.tsx`: component proof pattern for related-event expansion and stale related-event requests.
- `web/src/test/agent-panel-deeplink.test.tsx`: existing terminal/dashboard focus proof pattern.
- `web/src/test/api.test.ts`: API type/shape proof pattern for structured entity references.

## Verification Command

```bash
cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx src/test/agent-panel-deeplink.test.tsx && npm run build
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-3/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-3/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-timeline-event-presentation/tasks/t-3/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-timeline-event-presentation/tasks/t-3/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-3/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-3/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-3/test-contract-defence.md`
