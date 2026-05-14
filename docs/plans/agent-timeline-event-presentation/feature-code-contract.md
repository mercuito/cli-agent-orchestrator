# Feature Code Contract — Agent Timeline Event Presentation

Cross-task implementation-steering obligations for the Agent Timeline
Event Presentation feature. Clauses ground in explicit user direction to
keep typed event presentation in frontend views and in the existing CAO
event-log shape where persisted records already preserve typed event
payloads.

A frontend layout reference for the timeline rows, entity-reference
chips, and expanded related-events sub-panel lives at
[`design/timeline-event-presentation-mock.png`](design/timeline-event-presentation-mock.png).
The mock is informative (not a methodology artifact); it grounds
frontend rendering expectations and gives task-level
implementers a concrete visual target without locking pixel-level
styling.

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Always applies; every clause below names the surface it governs and what counts as compliance. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Always applies; every clause carries a stable `F-CC-<n>` ID for slicing in `feature-tasks.md`, handoffs, and Code Contract Defences. |

## Architectural Commitments

- **F-CC-1 — Timeline APIs expose typed event payload data.** Identity
  timeline and related-event API responses include each event's stable
  envelope fields plus a JSON `event_data` payload for the persisted CAO
  event. The backend preserves event facts as data and does not author
  display titles, summaries, chips, entity-reference labels, or other
  UI presentation values for this feature.

- **F-CC-2 — Frontend event-view registry owns dispatch.** The dashboard
  owns a frontend event-view registry keyed by `event_type_key`. Timeline
  rows and related-event rows ask this registry for a view instead of
  scattering concrete event-kind branching through dashboard components.
  The registry dispatch surface is the only feature-level place where
  concrete timeline event type keys are matched to concrete views.

- **F-CC-3 — Known event views are frontend-owned and typed.** Taught
  presentations for Linear mention, runtime delivery, workspace context
  switch, and runtime lifecycle events live as frontend view code that
  reads the event envelope plus `event_data`. These views validate or
  narrow the payload fields they use and degrade to readable fallback
  content when an expected optional fact is absent.

- **F-CC-4 — Unknown event fallback is frontend-owned.** If
  `event_type_key` has no registered frontend view, the dashboard renders
  a generic fallback from the event name, envelope facts, watched
  identity participant role, and safely displayable `event_data` facts.
  Provider-defined events remain visible without backend presenter code.

- **F-CC-5 — Entity references are frontend view affordances with kind
  discrimination.** Entity references are produced by frontend event
  views from typed event data and rendered as structured UI affordances
  whose targets declare either `external` or `internal` navigation.
  External references open outside the dashboard, such as a Linear issue
  URL. Internal references focus CAO dashboard context, such as a
  terminal identifier. Free-form prose alone does not satisfy this
  clause.

## Feature-Specific Code Obligations

None beyond the architectural commitments above. Lower-level code-shape
obligations whose `when:` requires research to evaluate (helper
conventions, module file layout, fixture patterns, registry-instance
lifetime, payload guard implementation, frontend rendering primitives)
belong in each task's Coding Code Contract.
