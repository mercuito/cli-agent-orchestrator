# Feature Tasks — Agent Timeline Event Presentation

Tasks for the Agent Timeline Event Presentation feature. See
`../feature-behavioral-contract.md`, `../feature-code-contract.md`, and
`../feature-test-contract.md` for the slice IDs referenced below.

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [slice-acknowledgment-completeness](../../../planning/methodology/criteria/feature-tasks/slice-acknowledgment-completeness.md) | Every task must explicitly name or explain the absence of Behavioral, Code, and Test slices. |
| [slice-coverage-uniqueness](../../../planning/methodology/criteria/feature-tasks/slice-coverage-uniqueness.md) | Each feature-level behavior, constraint, code clause, and test clause must have exactly one owning task. |
| [scope-handoffability](../../../planning/methodology/criteria/feature-tasks/scope-handoffability.md) | Each task scope must be specific enough to draft a self-sufficient handoff. |
| [supporting-reference-acknowledgment](../../../planning/methodology/criteria/feature-tasks/supporting-reference-acknowledgment.md) | Each task must state whether its handoff needs UI, product, domain, design, or existing-code references. |
| [explicit-dependencies](../../../planning/methodology/criteria/feature-tasks/explicit-dependencies.md) | Known-view and navigation tasks depend on the typed event payload and frontend fallback surface landing first. |
| [acyclic-dependencies](../../../planning/methodology/criteria/feature-tasks/acyclic-dependencies.md) | Known-view and navigation task dependencies, including slice-implied dependencies, must remain acyclic. |

## t-1 — Typed Timeline Payload Surface And Fallback View

Expose typed CAO event payload data on identity timeline and
related-event read surfaces, add the frontend event-view registry, and
preserve generic fallback visibility for untaught event kinds.

- Behavioral slice: `B-9`, `C-1`, `C-4`
- Code slice: `F-CC-1`, `F-CC-2`, `F-CC-4`
- Test slice: `F-TC-1`
- Supporting references: required for existing identity timeline backend
  service/API shapes, frontend identity timeline rendering, UI mockup, and
  backend/frontend test patterns.

## t-2 — Known Frontend Event Views

Deliver frontend typed views for Linear mention, runtime delivery,
workspace context switch, and runtime lifecycle events so their rows show
the kind-specific details named by the narrative. Wire those views through
generated backend event type constants and module self-registration.

- Behavioral slice: `B-1`, `B-2`, `B-3`, `B-4`, `B-5`
- Code slice: `F-CC-3`, `F-CC-6`
- Test slice: `F-TC-2`
- Supporting references: required for Linear and runtime CAO event
  definitions, frontend event-view patterns, domain examples, and known
  view proof patterns.
- Depends on: `t-1`

## t-3 — Related View Continuity And Entity References

Deliver same-view related-event rendering and entity-reference navigation
so related events keep their main-timeline presentations, external
references open their outside context, and internal references focus the
referenced dashboard context.

- Behavioral slice: `B-6`, `B-7`, `B-8`, `C-2`, `C-3`
- Code slice: `F-CC-5`
- Test slice: `F-TC-3`
- Supporting references: required for UI mockup, existing related-events
  panel behavior, dashboard terminal focus/deep-link behavior, and
  frontend test patterns.
- Depends on: `t-1`, `t-2`
