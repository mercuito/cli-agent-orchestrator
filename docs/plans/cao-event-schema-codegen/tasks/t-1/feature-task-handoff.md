# Feature Task Handoff: t-1 — Kinded Event Persistence Foundation

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff points to the approved `t-1` entry in `feature-tasks.md`. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff carries slice, committed-decision, verification, and coding-artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task entry requires backend event declaration, serializer, migration, and persistence proof references. |

## Task Brief

Convert CAO event declarations, serialization, and storage internals to the
stable `kind` discriminator while preserving event reconstruction equality,
protocol attributes, and backend persistence behavior. Done means the backend
event system can persist, migrate, and reconstruct all Linear and runtime CAO
events through the new kind-keyed storage path without relying on the legacy
storage discriminator column or dynamic import fallback.

## Slice Reference

See `../feature-tasks.md#t-1--kinded-event-persistence-foundation` for assigned
Behavioral, Code, and Test slices. The universal `test-validity-preserved`
criterion applies regardless.

## Committed Implementation Decisions

See `../../feature-committed-implementation-decisions.md`. All entries are in
force for this task.

## Supporting References

Use these references during task research and implementation planning.

### Existing Code References

- `src/cli_agent_orchestrator/runtime/events.py`: runtime-owned CAO event
  declarations, factories, and registration entry point.
- `src/cli_agent_orchestrator/linear/workspace_events.py`: Linear-owned CAO
  event declarations, factories, and registration entry point.
- `src/cli_agent_orchestrator/events/__init__.py`: `CaoEvent` protocol,
  dispatcher registration, and event participant helpers.
- `src/cli_agent_orchestrator/events/serialization.py`: current type-key
  serializer registry, dynamic import fallback, and encode/decode helpers.
- `src/cli_agent_orchestrator/clients/cao_event_store.py`: `cao_events` ORM
  model, persistence/write path, reconstruction/read paths, and participant
  index behavior.
- `src/cli_agent_orchestrator/services/agent_identity_timeline.py`: timeline
  reconstruction consumer of persisted `CaoEventRecord` values.

### Test And Proof References

- `test/events/test_cao_event_persistence.py`: existing persistence,
  participant, query, and migration proof patterns.
- `test/api/test_agent_identity_routes.py`: API route baseline affected by
  timeline event persistence and response construction.
- `test/runtime/test_agent_runtime.py`: runtime event publication baseline.

## Verification Command

```bash
uv run pytest test/events/test_cao_event_persistence.py test/api/test_agent_identity_routes.py test/runtime/test_agent_runtime.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-code-contract.md`
- Coding Test Contract: `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/cao-event-schema-codegen/tasks/t-1/coding-completion-report.md`
- Behavioral Contract Defence: not applicable; no Behavioral Contract slice is assigned for this pure refactor task.
- Code Contract Defence: `docs/plans/cao-event-schema-codegen/tasks/t-1/code-contract-defence.md`
- Test Contract Defence: `docs/plans/cao-event-schema-codegen/tasks/t-1/test-contract-defence.md`
