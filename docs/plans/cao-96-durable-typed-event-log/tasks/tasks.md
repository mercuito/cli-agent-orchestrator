# Tasks - CAO-96 Durable Typed Event Log

Tasks for the CAO-96 durable typed event log feature. See
`../behavioral-contract.md`, `../code-contract.md`, and
`../test-contract.md` for the slice IDs referenced below.

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-acknowledgment-completeness](../../../planning/methodology/criteria/feature-tasks/slice-acknowledgment-completeness.md) | Every task must name or explicitly rule out Behavioral, Code, and Test slices. |
| [slice-coverage-uniqueness](../../../planning/methodology/criteria/feature-tasks/slice-coverage-uniqueness.md) | Every feature-level behavior, constraint, code clause, and test clause must have exactly one owning task. |
| [scope-handoffability](../../../planning/methodology/criteria/feature-tasks/scope-handoffability.md) | Each task entry must be sufficient to draft a startable handoff. |
| [explicit-dependencies](../../../planning/methodology/criteria/feature-tasks/explicit-dependencies.md) | Later tasks depend on the durable event-log foundation and publication boundary landing first. |

## t-1 - Durable Event Log Readiness

Establish the durable event-log foundation for a workspace, including the
canonical event table and participant-index shape needed before production
publication can retain events.

- Behavioral slice: `B-1`
- Code slice: `F-CC-5`
- Test slice: `F-TC-3`

## t-2 - Persistent Publication And Typed Reconstruction

Record production CAO events through the central publication path and
return exact concrete typed events by event identifier, including
single-participant, participantless, Linear mention, and runtime-event
families.

- Behavioral slice: `B-2`, `B-3`, `B-5`, `B-6`, `B-7`, `C-2`
- Code slice: `F-CC-1`, `F-CC-2`
- Test slice: `F-TC-1`, `F-TC-5`
- Depends on: `t-1`

## t-3 - Participant And Envelope Query Surface

Provide durable event-log queries for participant histories and envelope
facts, including broadcast participants, participantless events,
occurrence ordering, direct-causation filtering, and empty query results.

- Behavioral slice: `B-4`, `B-8`, `B-9`, `B-10`, `B-11`, `B-12`, `B-13`, `B-14`, `B-15`, `C-3`, `C-4`
- Code slice: `F-CC-3`, `F-CC-4`
- Test slice: `F-TC-2`
- Depends on: `t-1`, `t-2`

## t-4 - Idempotent Retry And Dispatcher Persistence Boundaries

Preserve one canonical event when a previously recorded event identifier
is republished, and keep isolated local dispatchers from writing to the
shared durable event log unless persistent publication is explicitly
selected.

- Behavioral slice: `B-16`, `C-1`
- Code slice: `F-CC-6`, `F-CC-7`
- Test slice: `F-TC-4`
- Depends on: `t-1`, `t-2`, `t-3`
