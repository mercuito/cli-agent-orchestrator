# Feature Task Handoff: t-2 — Known Frontend Event Views

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-2` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete event-source, frontend, domain, and proof references. |

## Task Brief

Teach the frontend identity timeline how to render the exemplar CAO event
kinds from the narrative. Done means Linear mention, runtime delivery,
workspace context switch, and runtime lifecycle events each have
registered frontend views that read typed `event_data` and show the
issue, mention, delivery, terminal, workspace context, and lifecycle
details named by the behavioral slices.

## Slice Reference

See `../feature-tasks.md#t-2--known-frontend-event-views` for assigned
Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-timeline-event-presentation/feature-committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### Product / Domain References

- `docs/plans/agent-timeline-event-presentation/feature-narrative.md`: concrete Aria, Nia, `OPS-417`, `term-aria-main`, `cli-agent-orchestrator`, and `yards` scenario details that the frontend views must make readable.
- `docs/plans/agent-timeline-event-presentation/feature-behavioral-contract.md`: exact behavior slices for Linear mention, runtime delivery, workspace context switch, and runtime lifecycle presentations.
- `docs/plans/agent-timeline-event-presentation/feature-code-contract.md`: feature-level frontend typed-view ownership and payload narrowing obligations.
- `docs/plans/agent-timeline-event-presentation/feature-test-contract.md`: feature-level proof slice for known frontend event views.

### Existing Code References

- `src/cli_agent_orchestrator/linear/workspace_events.py`: Linear CAO event definitions and payload fields the Linear mention frontend view must read.
- `src/cli_agent_orchestrator/runtime/events.py`: runtime delivery, lifecycle, workspace context switch, and runtime payload fields the frontend views must read.
- `src/cli_agent_orchestrator/events/serialization.py`: existing event type key and typed-event serialization behavior behind the `event_data` shape exposed by `t-1`.
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`: timeline read composition surface introduced or extended by `t-1`.
- `web/src/api.ts`: frontend typed timeline event shape from `t-1`.
- `web/src/components/AgentIdentityTimelinePanel.tsx`: frontend event-view registry and row rendering surface introduced by `t-1`.
- `web/src/test/agent-identity-timeline-panel.test.tsx`: frontend component proof pattern for kind-specific timeline row content.
- `web/src/test/api.test.ts`: frontend API wrapper proof pattern for typed `event_data`.
- `test/linear/test_webhook_ingestion.py`: Linear event fixture examples and published event assertions.
- `test/runtime/test_agent_runtime.py`: runtime event fixture/proof examples.
- `test/api/test_agent_identity_routes.py`: backend timeline API assertions that should cover any payload facts needed by frontend views.

## Verification Command

```bash
uv run pytest test/api/test_agent_identity_routes.py test/linear/test_webhook_ingestion.py test/runtime/test_agent_runtime.py && cd web && npm test -- --run src/test/api.test.ts src/test/agent-identity-timeline-panel.test.tsx && npm run build
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-2/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-2/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-2/test-contract-defence.md`
