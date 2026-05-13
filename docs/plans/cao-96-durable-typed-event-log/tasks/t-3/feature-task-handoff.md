# Feature Task Handoff: t-3 - Participant And Envelope Query Surface

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | This handoff depends on the `t-3` entry in `../tasks.md` resolving to complete slice acknowledgments. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The task must carry the slice reference, committed-decision reference, verification command, and deterministic artifact paths. |

## Task Brief

Provide the durable event-log query surface for participant histories and
envelope facts. Done means downstream consumers can query by agent
identity, event name, source, correlation identifier, and causation
identifier with correct ordering, empty outcomes, broadcast handling, and
participantless-event behavior.

## Slice Reference

See `../tasks.md#t-3---participant-and-envelope-query-surface` for the
authoritative task entry. Assigned slices:

- Behavioral slice: `B-4`, `B-8`, `B-9`, `B-10`, `B-11`, `B-12`, `B-13`, `B-14`, `B-15`, `C-3`, `C-4`
- Code slice: `F-CC-3`, `F-CC-4`
- Test slice: `F-TC-2`

The universal `test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/cao-96-durable-typed-event-log/committed-implementation-decisions.md`.
All entries are in force for this task.

## Verification Command

```bash
uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-3/test-contract-defence.md`
