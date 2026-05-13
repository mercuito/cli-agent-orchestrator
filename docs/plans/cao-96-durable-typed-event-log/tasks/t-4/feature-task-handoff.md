# Feature Task Handoff: t-4 - Idempotent Retry And Dispatcher Persistence Boundaries

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | This handoff depends on the `t-4` entry in `../tasks.md` resolving to complete slice acknowledgments. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The task must carry the slice reference, committed-decision reference, verification command, and deterministic artifact paths. |

## Task Brief

Preserve one canonical durable event when Linear retries a publication and
keep non-persistent local dispatchers isolated from the shared durable
event log. Done means duplicate event identifiers do not change the
canonical event or add conflicting participants, and persistence happens
only when persistent publication is explicitly selected.

## Slice Reference

See `../tasks.md#t-4---idempotent-retry-and-dispatcher-persistence-boundaries`
for the authoritative task entry. Assigned slices:

- Behavioral slice: `B-16`, `C-1`
- Code slice: `F-CC-6`, `F-CC-7`
- Test slice: `F-TC-4`

The universal `test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/cao-96-durable-typed-event-log/committed-implementation-decisions.md`.
All entries are in force for this task.

## Verification Command

```bash
uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-4/test-contract-defence.md`
