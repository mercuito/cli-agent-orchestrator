# Tasks — Agent Timeline Event Presentation

Tasks for the Agent Timeline Event Presentation feature. See
`../behavioral-contract.md`, `../code-contract.md`, and
`../test-contract.md` for the slice IDs referenced below.

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-acknowledgment-completeness](../../../planning/methodology/criteria/feature-tasks/slice-acknowledgment-completeness.md) | Every task must explicitly name or explain the absence of Behavioral, Code, and Test slices. |
| [slice-coverage-uniqueness](../../../planning/methodology/criteria/feature-tasks/slice-coverage-uniqueness.md) | Each feature-level behavior, constraint, code clause, and test clause must have exactly one owning task. |
| [scope-handoffability](../../../planning/methodology/criteria/feature-tasks/scope-handoffability.md) | Each task scope must be specific enough to draft a self-sufficient handoff. |
| [supporting-reference-acknowledgment](../../../planning/methodology/criteria/feature-tasks/supporting-reference-acknowledgment.md) | Each task must state whether its handoff needs UI, product, domain, design, or existing-code references. |
| [explicit-dependencies](../../../planning/methodology/criteria/feature-tasks/explicit-dependencies.md) | Presenter and navigation tasks depend on the core presentation value and rendering surface landing first. |

## t-1 — Timeline Presentation Framework And Fallback

Deliver the generic presentation value for identity timeline events, carry
that value through the backend timeline and related-event read surfaces,
render it generically in the dashboard timeline UI, and preserve generic
fallback visibility for untaught event kinds.

- Behavioral slice: `B-1`, `B-9`, `C-1`, `C-4`
- Code slice: `F-CC-1`, `F-CC-4`
- Test slice: `F-TC-1`
- Supporting references: required for existing identity timeline backend
  service/API shapes, frontend identity timeline rendering, UI mockup, and
  backend/frontend test patterns.

## t-2 — Known Event Kind Presenters

Deliver taught event presentations for Linear mention, runtime delivery,
workspace context switch, and runtime lifecycle events so their rows show
the kind-specific details named by the narrative.

- Behavioral slice: `B-2`, `B-3`, `B-4`, `B-5`
- Code slice: `F-CC-2`, `F-CC-3`
- Test slice: `F-TC-2`
- Supporting references: required for Linear and runtime CAO event
  definitions, event-source registration conventions, domain examples,
  and presenter proof patterns.
- Depends on: `t-1`

## t-3 — Related Presentation Continuity And Entity References

Deliver same-presentation related-event rendering and entity-reference
navigation so related events keep their main-timeline presentations,
external references open their outside context, and internal references
focus the referenced dashboard context.

- Behavioral slice: `B-6`, `B-7`, `B-8`, `C-2`, `C-3`
- Code slice: `F-CC-5`
- Test slice: `F-TC-3`
- Supporting references: required for UI mockup, existing related-events
  panel behavior, dashboard terminal focus/deep-link behavior, and
  frontend test patterns.
- Depends on: `t-1`, `t-2`
