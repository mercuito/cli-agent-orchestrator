# Feature Task Handoff: t-2 - Persistent Publication And Typed Reconstruction

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | This handoff depends on the `t-2` entry in `../tasks.md` resolving to complete slice acknowledgments. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The task must carry the slice reference, committed-decision reference, verification command, and deterministic artifact paths. |

## Task Brief

Record production CAO events from the central publication path and return
exact concrete typed events by event identifier. Done means Linear mention,
runtime delivery, and participantless production events can be persisted
and reconstructed with their original envelopes, typed bodies, and
participants.

## Slice Reference

See `../tasks.md#t-2---persistent-publication-and-typed-reconstruction` for
the authoritative task entry. Assigned slices:

- Behavioral slice: `B-2`, `B-3`, `B-5`, `B-6`, `B-7`, `C-2`
- Code slice: `F-CC-1`, `F-CC-2`
- Test slice: `F-TC-1`, `F-TC-5`

The universal `test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/cao-96-durable-typed-event-log/committed-implementation-decisions.md`.
All entries are in force for this task.

## Verification Command

```bash
uv run pytest test/events/test_cao_event_persistence.py test/events/test_core.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-96-durable-typed-event-log/tasks/t-2/test-contract-defence.md`
