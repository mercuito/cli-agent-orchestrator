# Feature Task Handoff: t-1 - Durable Event Log Readiness

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | This handoff depends on the `t-1` entry in `../tasks.md` resolving to complete slice acknowledgments. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The task must carry the slice reference, committed-decision reference, verification command, and deterministic artifact paths. |

## Task Brief

Establish the durable event-log foundation for a CAO workspace. Done means
the workspace can gain the durable event log and participant-index shape
through the repo's established initialization or migration path before
production CAO events are published.

## Slice Reference

See `../tasks.md#t-1---durable-event-log-readiness` for the authoritative
task entry. Assigned slices:

- Behavioral slice: `B-1`
- Code slice: `F-CC-5`
- Test slice: `F-TC-3`

The universal `test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/cao-96-durable-typed-event-log/committed-implementation-decisions.md`.
All entries are in force for this task.

## Verification Command

```bash
uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-1/test-contract-defence.md`
