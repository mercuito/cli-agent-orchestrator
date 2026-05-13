# Feature Task Handoff: t-2 — Agents Roster And Identity Timeline UI

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-reference-resolves](../../../../planning/methodology/criteria/feature-task-handoff/slice-reference-resolves.md) | The handoff must point to the `t-2` entry that owns this task's feature-level slices. |
| [operational-self-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/operational-self-sufficiency.md) | The handoff must carry slice, committed-decision, verification, and coding artifact pointers. |
| [supporting-reference-sufficiency](../../../../planning/methodology/criteria/feature-task-handoff/supporting-reference-sufficiency.md) | The task requires concrete UI, product, dashboard code, and frontend test references. |

## Task Brief

Build the dashboard Agents-area UI for selecting configured identities and
reviewing an identity timeline. Done means the operator can browse the
roster, open identity views, read timeline rows, inspect causation and
correlation related threads, see broadcast events from each participant's
viewpoint, and distinguish an empty identity timeline from loading or
unreachable states.

## Slice Reference

See `../tasks.md#t-2--agents-roster-and-identity-timeline-ui` for assigned
Behavioral, Code, and Test slices. The universal
`test-validity-preserved` criterion applies regardless.

## Committed Implementation Decisions

See `docs/plans/agent-identity-timeline-view/committed-implementation-decisions.md`.
All entries are in force.

## Supporting References

Use these references during task research and implementation planning.

### UI / Design References

- `docs/plans/agent-identity-timeline-view/ui-mockup.png`: target
  dashboard composition for the identity roster, selected identity detail,
  timeline rows, and related-event inspection.

### Product / Domain References

- `docs/plans/agent-identity-timeline-view/narrative.md`: domain story for
  roster browsing, Aria and Cael identity views, related-event threads,
  broadcast viewpoints, and empty identity timelines.
- `docs/plans/agent-identity-timeline-view/behavioral-contract.md`: exact
  user-visible behavior and invariant slices owned by this task.

### Existing Code References

- `web/src/App.tsx`: existing top-level dashboard tab structure and Agents
  area wiring.
- `web/src/components/AgentPanel.tsx`: existing Agents dashboard component
  structure, route-initialization behavior, polling style, and visual
  conventions.
- `web/src/api.ts`: dashboard API wrapper where new data access functions
  must be added.
- `web/src/store.ts`: existing dashboard state and reconciliation patterns.
- `web/src/test/components.test.tsx`: frontend component test patterns with
  React Testing Library.
- `web/src/test/api.test.ts`: API wrapper test patterns.

## Verification Command

```bash
cd web && npm test -- --run && npm run build
```

## Coding-Level Artifact Locations

- Coding Code Contract: `docs/plans/agent-identity-timeline-view/tasks/t-2/coding-code-contract.md`
- Coding Test Contract: `docs/plans/agent-identity-timeline-view/tasks/t-2/coding-test-contract.md`
- Coding Implementation Plan: `docs/plans/agent-identity-timeline-view/tasks/t-2/coding-implementation-plan.md`
- Coding Completion Report: `docs/plans/agent-identity-timeline-view/tasks/t-2/coding-completion-report.md`
- Behavioral Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-2/behavioral-contract-defence.md`
- Code Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-2/code-contract-defence.md`
- Test Contract Defence: `docs/plans/agent-identity-timeline-view/tasks/t-2/test-contract-defence.md`
