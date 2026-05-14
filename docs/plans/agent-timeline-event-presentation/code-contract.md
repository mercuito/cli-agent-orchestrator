# Code Contract — Agent Timeline Event Presentation

Cross-task implementation-steering obligations for the Agent Timeline
Event Presentation feature. Authored in parallel with the Feature
Narrative; clauses ground in explicit user direction and the established
event-source-module pattern at
[`linear/workspace_events.py`](../../../src/cli_agent_orchestrator/linear/workspace_events.py),
not in narrative or behavioral derivations.

A frontend layout reference for the timeline rows, entity-reference
chips, and expanded related-events sub-panel lives at
[`design/timeline-event-presentation-mock.png`](design/timeline-event-presentation-mock.png).
The mock is informative (not a methodology artifact); it grounds
F-CC-1's frontend rendering expectations and gives task-level
implementers a concrete visual target without locking pixel-level
styling.

## Applicable Feature-Level Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [implementation-clause-verifiability](../../planning/methodology/criteria/feature-code-contract/implementation-clause-verifiability.md) | Always applies; every clause below names the surface it governs and what counts as compliance. |
| [stable-code-clause-ids](../../planning/methodology/criteria/feature-code-contract/stable-code-clause-ids.md) | Always applies; every clause carries a stable `F-CC-<n>` ID for slicing in `tasks.md`, handoffs, and Code Contract Defences. |

## Architectural Commitments

- **F-CC-1 — Backend-owned timeline event presentation.** The timeline
  API embeds a `TimelineEventPresentation` value on each event it
  returns. The frontend timeline panel and related-events panel render
  `TimelineEventPresentation` generically: they do not branch on
  concrete event kind, do not import or inspect concrete event-class
  types, and do not duplicate kind-specific rendering logic. Any new
  kind-specific information surfaced on the timeline is added by
  authoring or amending an event presenter on the backend, not by
  changing the frontend.

- **F-CC-2 — Per-source presenter-registration function.** Each event
  source module that publishes CAO events for which a timeline
  presentation is authored exposes a
  `register_<source>_event_presenters(registry)` function. The function
  registers exactly that source's presenters with the timeline
  presentation registry and parallels the existing
  `register_<source>_cao_events(dispatcher)` convention used today by
  [`register_linear_cao_events`](../../../src/cli_agent_orchestrator/linear/workspace_events.py)
  and the equivalent functions in other event-source modules. A source
  module that publishes events but has no presenter authored yet is not
  required to expose this function.

- **F-CC-3 — Presenter authoring locality and form.** Each timeline
  event presenter is authored as a module-local function in the same
  module as its event-class definition, registered with the timeline
  presentation registry via a `@timeline_presenter_for(EventClass)`
  decorator (or an equivalently named explicit registration helper).
  Presenters are functions of one positional event argument, not
  methods on the event class. An event class does not gain a
  `to_timeline_presentation` method, and the events module does not
  carry presenter-registration code beyond the per-source
  `register_<source>_event_presenters(registry)` function described in
  F-CC-2.

- **F-CC-4 — Fallback presentation lives in the registry.** The generic
  fallback presentation used when an event has no registered presenter
  is produced by the timeline presentation registry itself. Source
  modules do not author, import, declare, or duplicate any fallback
  presentation. The fallback's content matches what an identity
  timeline row showed before this feature: event name, envelope facts,
  and the watched identity's participant role.

- **F-CC-5 — Entity references are a structured field with kind
  discrimination.** `TimelineEventPresentation` carries entity
  references as a structured field whose entries each declare an
  `internal` or `external` kind and a navigation target sufficient for
  the frontend to render a consistent affordance and follow the
  reference. An external entity reference carries a target the
  frontend can open outside the dashboard (e.g., a Linear issue URL).
  An internal entity reference carries a CAO-side target the dashboard
  can focus on (e.g., a CAO terminal identifier). Free-form text
  references embedded in a presentation's title, summary, or other
  prose fields are not entity references and do not satisfy this
  clause.

## Feature-Specific Code Obligations

None beyond the architectural commitments above. Lower-level code-shape
obligations whose `when:` requires research to evaluate (helper
conventions, module file layout, fixture patterns, registry-instance
lifetime, frontend rendering primitives) belong in each task's
Coding Code Contract.
