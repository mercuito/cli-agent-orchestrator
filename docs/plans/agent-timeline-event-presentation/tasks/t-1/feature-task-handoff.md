# Task Handoff: t-1 — Timeline Presentation Framework And Fallback

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-1` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete backend, frontend, design, and test references. |

## Task Brief

Create the generic event presentation surface for identity timeline rows.
Done means timeline and related-event reads return a presentation value
for every CAO event, untaught event kinds receive the generic fallback
presentation, and the dashboard renders timeline rows from that value
without concrete event-kind branching.

## Slice Reference

See `../tasks.md#t-1--timeline-presentation-framework-and-fallback` for
assigned Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-timeline-event-presentation/committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### UI / Design References

- `docs/plans/agent-timeline-event-presentation/design/timeline-event-presentation-mock.png`: visual target for richer timeline rows, fallback row layout, entity-reference chips, and expanded related-event sub-panel composition.

### Product / Domain References

- `docs/plans/agent-timeline-event-presentation/narrative.md`: domain story for kind-specific event presentations, generic fallback presentation, and timeline/related-events surfaces.
- `docs/plans/agent-timeline-event-presentation/behavioral-contract.md`: exact user-visible behavior and invariant slices owned by this task.
- `docs/plans/agent-timeline-event-presentation/code-contract.md`: feature-level code clauses governing backend-owned presentation values and fallback ownership.
- `docs/plans/agent-timeline-event-presentation/test-contract.md`: feature-level proof slice for core presentation framework and fallback behavior.

### Existing Code References

- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`: backend service that currently returns envelope-only timeline and related-event reads.
- `src/cli_agent_orchestrator/api/main.py`: FastAPI response models and routes for identity timeline and related-event reads.
- `web/src/api.ts`: frontend API types for identity timeline events and related events.
- `web/src/components/AgentIdentityTimelinePanel.tsx`: dashboard timeline row and related-events rendering that must move to generic presentation rendering.
- `test/api/test_agent_identity_routes.py`: backend identity timeline API proof pattern.
- `test/events/test_cao_event_persistence.py`: event-log fixture/proof patterns for persisted CAO events and untaught event kinds.
- `web/src/test/agent-identity-timeline-panel.test.tsx`: frontend timeline component proof pattern.
- `web/src/test/api.test.ts`: frontend API wrapper proof pattern.

## Verification Command

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py && cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx && npm run build
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-timeline-event-presentation/tasks/t-1/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-1/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-1/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-1/test-contract-defence.md`
