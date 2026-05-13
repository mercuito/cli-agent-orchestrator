# Feature Task Handoff: t-1 — Backend Identity Timeline Read Surface

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-1` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete backend API, identity, event-store, and test references. |

## Task Brief

Create the backend dashboard read surface that later UI work can use to
list one agent identity's timeline and inspect causation/correlation
related event threads. Done means the backend resolves configured
identities through the existing identity manager surface and answers
timeline membership from the durable CAO event log and participant index.

## Slice Reference

See `../tasks.md#t-1--backend-identity-timeline-read-surface` for assigned
Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-identity-timeline-view/committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### Product / Domain References

- `docs/plans/agent-identity-timeline-view/narrative.md`: domain story for
  identity timelines, related threads, broadcast viewpoints, and
  non-participant workspace events.
- `docs/plans/agent-identity-timeline-view/behavioral-contract.md`:
  downstream user-visible behavior the backend surface must enable.

### Existing Code References

- `src/cli_agent_orchestrator/api/main.py`: existing dashboard route
  placement and `/agents/identities` identity response pattern.
- `src/cli_agent_orchestrator/services/agent_identity_manager.py`: manager
  surface for configured identity status and identity resolution.
- `src/cli_agent_orchestrator/clients/cao_event_store.py`: durable CAO
  event log, participant index, correlation lookup, and causation lookup.
- `src/cli_agent_orchestrator/events/__init__.py`: CAO event and agent
  participant domain primitives.
- `test/api/test_agent_identity_routes.py`: existing agent identity API
  route test style.
- `test/events/test_cao_event_persistence.py`: existing event-log proof
  patterns for participant timelines, broadcasts, correlation, causation,
  and zero-participant events.

## Verification Command

```bash
uv run pytest test/api/test_agent_identity_routes.py test/events/test_cao_event_persistence.py
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-identity-timeline-view/tasks/t-1/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-identity-timeline-view/tasks/t-1/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-identity-timeline-view/tasks/t-1/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-identity-timeline-view/tasks/t-1/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-1/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-1/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-1/test-contract-defence.md`
