# Tasks — Agent Identity Timeline View

Tasks for the Agent Identity Timeline View feature. See
`../behavioral-contract.md`, `../code-contract.md`, and
`../test-contract.md` for the slice IDs referenced below.

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-acknowledgment-completeness](../../../planning/methodology/criteria/feature-tasks/slice-acknowledgment-completeness.md) | Every task must explicitly name or explain the absence of Behavioral, Code, and Test slices. |
| [slice-coverage-uniqueness](../../../planning/methodology/criteria/feature-tasks/slice-coverage-uniqueness.md) | Each feature-level behavior, constraint, code clause, and test clause must have exactly one owning task. |
| [scope-handoffability](../../../planning/methodology/criteria/feature-tasks/scope-handoffability.md) | Each task scope must be specific enough to draft a self-sufficient handoff. |
| [supporting-reference-acknowledgment](../../../planning/methodology/criteria/feature-tasks/supporting-reference-acknowledgment.md) | Each task must state whether its handoff needs UI, product, domain, or existing-code references. |
| [explicit-dependencies](../../../planning/methodology/criteria/feature-tasks/explicit-dependencies.md) | The UI and live-refresh tasks depend on earlier feature surfaces landing first. |

## t-1 — Backend Identity Timeline Read Surface

Deliver the backend dashboard read surface for agent identity timelines and
related event threads, backed by configured agent identities and the durable
CAO event log.

- Behavioral slice: no Behavioral Contract slice for this task: this task
  provides the backend read surface; user-visible dashboard behavior is owned
  by later UI tasks.
- Code slice: `F-CC-1`, `F-CC-2`
- Test slice: `F-TC-1`
- Supporting references: required for existing identity manager, event store,
  API route, and backend test patterns.

## t-2 — Agents Roster And Identity Timeline UI

Deliver the dashboard Agents-area experience for browsing configured
identities, opening identity views, inspecting existing identity timeline
rows, exploring related event threads, seeing broadcast viewpoints, and
seeing empty identity timelines.

- Behavioral slice: `B-1`, `B-2`, `B-3`, `B-4`, `B-5`, `B-6`, `B-7`,
  `B-8`, `B-9`, `B-10`, `B-12`, `C-1`, `C-2`, `C-3`, `C-4`
- Code slice: `F-CC-3`, `F-CC-4`, `F-CC-5`
- Test slice: `F-TC-2`
- Supporting references: required for UI mockup, existing Agents dashboard
  structure, dashboard API client conventions, and frontend test patterns.
- Depends on: `t-1`

## t-3 — Live Identity Timeline Refresh

Deliver live refresh for the watched identity timeline so newly recorded
participant events appear without a dashboard reload while non-participant
workspace events stay out.

- Behavioral slice: `B-11`
- Code slice: `F-CC-6`
- Test slice: `F-TC-3`
- Supporting references: required for existing dashboard polling and store
  reconciliation patterns.
- Depends on: `t-1`, `t-2`
