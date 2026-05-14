# Task Handoff: t-2 — Known Event Kind Presenters

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-2` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete event-source, domain, and proof references. |

## Task Brief

Teach the identity timeline how to present the exemplar CAO event kinds
from the narrative. Done means Linear mention, runtime delivery,
workspace context switch, and runtime lifecycle events each produce
kind-specific event presentations with the issue, mention, delivery,
terminal, workspace context, and lifecycle details named by the
behavioral slices.

## Slice Reference

See `../tasks.md#t-2--known-event-kind-presenters` for assigned
Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-timeline-event-presentation/committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### Product / Domain References

- `docs/plans/agent-timeline-event-presentation/narrative.md`: concrete Aria, Nia, `OPS-417`, `term-aria-main`, `cli-agent-orchestrator`, and `yards` scenario details that the presenters must make readable.
- `docs/plans/agent-timeline-event-presentation/behavioral-contract.md`: exact behavior slices for Linear mention, runtime delivery, workspace context switch, and runtime lifecycle presentations.
- `docs/plans/agent-timeline-event-presentation/code-contract.md`: feature-level presenter-registration and presenter-authoring locality obligations.
- `docs/plans/agent-timeline-event-presentation/test-contract.md`: feature-level proof slice for known event presenters.

### Existing Code References

- `src/cli_agent_orchestrator/linear/workspace_events.py`: Linear CAO event definitions and the `register_linear_cao_events` convention the presenter registration function must parallel.
- `src/cli_agent_orchestrator/runtime/events.py`: runtime delivery, lifecycle, workspace context switch, and runtime event registration patterns.
- `src/cli_agent_orchestrator/events/serialization.py`: existing event type key and typed-event serialization behavior needed to recover typed body facts from persisted events.
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`: timeline read composition surface introduced or extended by `t-1`.
- `test/linear/test_webhook_ingestion.py`: Linear event fixture examples and published event assertions.
- `test/runtime/test_agent_runtime.py`: runtime event fixture/proof examples.
- `test/api/test_agent_identity_routes.py`: backend timeline API assertions that should cover presenter output.

## Verification Command

```bash
uv run pytest test/api/test_agent_identity_routes.py test/linear/test_webhook_ingestion.py test/runtime/test_agent_runtime.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-timeline-event-presentation/tasks/t-2/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-2/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-2/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-timeline-event-presentation/tasks/t-2/test-contract-defence.md`
