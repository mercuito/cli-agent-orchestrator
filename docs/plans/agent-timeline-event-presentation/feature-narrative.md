# Feature Narrative — Agent Timeline Event Presentation

Agent Timeline Event Presentation — Replace today's generic, envelope-only
identity timeline rows with kind-specific event presentations that the
operator can actually read at a glance and follow into the contexts those
events name. The system that queries and assembles events for an identity
remains generic; this feature teaches the identity timeline how each
concrete CAO event kind should appear to the operator.

## Applicable Criteria

| Criterion | Rationale |
|-----------|-----------|
| [domain-language-only](../../planning/methodology/criteria/feature-narrative/domain-language-only.md) | Always applies; the narrative must speak in CAO event and identity-timeline domain terms, not in component, registry, route, or DTO terms. |
| [event-timeline-granularity](../../planning/methodology/criteria/feature-narrative/event-timeline-granularity.md) | Always applies; the timeline turning rich, each exemplar event kind acquiring its own presentation, the related-events panel adopting the same presentations, each kind of cross-context navigation, and the untaught-kind fallback are each their own beat. |
| [events-have-observable-outcomes](../../planning/methodology/criteria/feature-narrative/events-have-observable-outcomes.md) | Always applies; every beat must show what the operator observes — a kind-specific row, an opened Linear issue, a focused terminal, a generic fallback row. |
| [scenario-grounding](../../planning/methodology/criteria/feature-narrative/scenario-grounding.md) | Always applies; the timeline follows one running scenario — the operator opening Aria's identity timeline after returning to the dashboard — with branches for four exemplar event kinds, two cross-context navigations, and one untaught event kind. |
| [vocabulary-grounded-in-event-timeline](../../planning/methodology/criteria/feature-narrative/vocabulary-grounded-in-event-timeline.md) | Always applies; the timeline introduces presentation-side terms (event presentation, generic fallback presentation, entity reference, external entity reference, internal entity reference, workspace context) that need definitions in addition to the CAO event and identity-timeline vocabulary inherited from CAO-96 and the agent identity timeline view feature. |

## Event Timeline

Scenario frame: A CAO operator returns to the dashboard and opens Aria's
agent identity view to find out what Aria has been doing today. Aria's
identity timeline already lists the recent CAO events involving her, but
until now every row showed only the event name, source, time, and Aria's
participant role. Today Nia mentioned Aria on the Linear issue
`OPS-417` "Restore dashboard event detail," writing "Aria, can you trace
the stuck inbox delivery?"; CAO delivered that message to Aria's
`term-aria-main` terminal, Aria moved from the `cli-agent-orchestrator`
workspace context into the `yards` workspace context, that terminal
restarted once, and the workspace also recorded an experimental audit
event whose kind CAO has not yet been taught how to present. The operator
both reads the timeline rows directly and expands some of them to inspect
the related events those rows connect to.

### E1 — Aria's identity timeline reads as kind-specific instead of generic

The operator opens Aria's agent identity view and looks at her identity
timeline. The system now renders each row using an event presentation
tailored to that event's kind, so the Linear mention row, the runtime
delivery row, the workspace context switch row, and the runtime lifecycle
row each look distinct and carry information specific to their kind.
After this beat, the operator can read what each event was without
expanding it or relying on the event name alone.

### E2 — The Linear mention's presentation surfaces the issue, the mentioner, and a snippet

The operator looks at the Linear mention row. Its event presentation
shows the `OPS-417` issue title, Nia as the teammate who wrote the
mention, the snippet "Aria, can you trace the stuck inbox delivery?", and
an external entity reference naming the Linear issue itself. After this
beat, the operator can see why Aria was pulled in — what was said, by
whom, and on what — without opening anything.

### E3 — The runtime delivery's presentation surfaces what was delivered and which terminal received it

The operator looks at the runtime delivery row. Its event presentation
shows the source kind that triggered the delivery (the Linear mention
from earlier), the delivered message "Aria, can you trace the stuck inbox
delivery?", and an internal entity reference naming `term-aria-main` as
the terminal where Aria received it. After this beat, the operator can
see how the mention flowed into Aria's runtime and exactly which of
Aria's terminals took the delivery.

### E4 — The workspace context switch's presentation surfaces the from and to contexts

The operator looks at the workspace context switch row. Its event
presentation shows `cli-agent-orchestrator` as the workspace context
Aria was operating in before the switch and `yards` as the workspace
context she moved into. After this beat, the operator can see that Aria
moved between two specific repositories and which one she is currently
working from, without inspecting any other event.

### E5 — The runtime lifecycle event's presentation surfaces the phase and surrounding context

The operator looks at the runtime lifecycle row. Its event presentation
shows the lifecycle phase Aria's runtime moved through — `term-aria-main`
restarted — together with the `yards` workspace context the runtime was
in at the time. After this beat, the operator can tell at a glance
whether Aria's runtime is in a healthy state or had a hiccup, and where
it happened.

### E6 — The related events panel uses the same kind-specific presentations

The operator expands the Linear mention row to inspect its related
events — its direct cause, its direct effects, and the events sharing
its correlation thread. The system surfaces each related event using
the same event presentation its kind would receive on the main timeline,
so a runtime delivery sitting in the related-events panel still shows
what was delivered and which terminal received it, and a workspace
context switch still shows the from and to workspace contexts. After
this beat, the operator can read the related-events panel as easily
as the main timeline, rather than seeing the related thread degrade
into envelope-only rows.

### E7 — The operator opens the Linear issue from the mention row

The operator follows the external entity reference on the Linear
mention row. The system opens the Linear issue named by that reference
in its own context, outside the dashboard, so the operator can read the
full issue thread there. After this beat, the operator has crossed from
Aria's identity timeline into the live Linear issue without having to
copy identifiers or hunt for the issue manually.

### E8 — The operator jumps from the delivery row to the receiving terminal

The operator returns to Aria's identity timeline and follows the
internal entity reference on the runtime delivery row. The system focuses
the dashboard on the terminal named by that reference, so the operator
sees Aria's actual terminal where the delivery landed. After this beat,
the operator has crossed from a recorded delivery on the timeline to the
live terminal that received it without leaving the dashboard.

### E9 — An event of an untaught kind falls back to a generic row

Aria's identity timeline also contains one CAO event whose kind has no
event presentation knowledge. The system renders that row using a
generic fallback presentation — the event name, envelope facts such as
occurrence time and correlation identifier, and Aria's participant role
— the same shape every row had before this feature. The same fallback
applies wherever that event appears, including the related-events panel
when another row points to it. The operator can still see the event
sitting on Aria's timeline and can still follow its correlation or
causation through the related-events behavior, but no row for it
carries any kind-specific detail. After this beat, the operator
understands that newly added event kinds remain visible on identity
timelines even before a presentation has been taught for them.

## Domain Vocabulary

- **CAO event** — As defined in the CAO-96 narrative; a framework-wide
  typed event published through CAO's central event publication path,
  carrying an event envelope, a typed body, and zero or more agent
  participants.
- **Event envelope** — As defined in the CAO-96 narrative; the universal
  facts every CAO event carries, including its event identifier,
  occurrence time, correlation identifier, and causation identifier.
- **Typed body** — As defined in the CAO-96 narrative; the
  concrete-event-specific information a CAO event carries in addition to
  its envelope.
- **Concrete typed event type** — As defined in the CAO-96 narrative;
  the specific kind of CAO event that was published, such as a Linear
  mention event or a runtime delivery event.
- **Agent identity** — As defined in the CAO-96 narrative; a
  CAO-recognised agent that can participate in events. Aria is the
  agent identity at the centre of this narrative.
- **Agent participant** — As defined in the CAO-96 narrative; an agent
  identity that is involved in a given CAO event together with its
  participant role.
- **Participant role** — As defined in the CAO-96 narrative; the kind
  of involvement an agent identity has in a CAO event.
- **Durable event log** — As defined in the CAO-96 narrative; the
  persistent record of CAO events.
- **Participant index** — As defined in the CAO-96 narrative; the
  first-class lookup that records each (event, agent identity,
  participant role) involvement; identity-scoped queries answer from
  this index.
- **Correlation identifier** — As defined in the CAO-96 narrative; an
  envelope fact that groups related CAO events together.
- **Causation identifier** — As defined in the CAO-96 narrative; an
  envelope fact that names the directly causing CAO event.
- **Operator** — As defined in the agent identity timeline view
  narrative; a human using the CAO dashboard to inspect what their
  agent identities have been doing in the workspace.
- **Agent identity view** — As defined in the agent identity timeline
  view narrative; the per-identity page on the CAO dashboard that
  presents one agent identity's configured details together with that
  identity's identity timeline.
- **Identity timeline** — As defined in the agent identity timeline
  view narrative; the chronologically ordered presentation of recent
  CAO events involving a single agent identity, drawn from the
  participant index.
- **Related events panel** — The part of an agent identity view that
  appears when the operator expands a timeline row and shows CAO events
  related to that row by direct cause, direct effect, or correlation
  thread.
- **Direct cause** — The one CAO event named by another event's
  causation identifier.
- **Direct effect** — A CAO event whose causation identifier names the
  expanded timeline row's CAO event.
- **Correlation thread** — The group of CAO events that share a
  correlation identifier and therefore belong to the same recorded work
  thread.
- **Runtime delivery** — A CAO event recording that a message or
  notification was delivered into an agent identity's runtime, including
  the terminal that received it.
- **Runtime lifecycle event** — A CAO event recording a lifecycle phase
  of an agent identity's runtime, such as starting, restarting, stopping,
  or becoming unavailable in a workspace context.
- **Workspace context** — A configured workspace an agent identity
  operates in, such as a specific repository or project root. An agent
  identity has at most one current workspace context at a time and may
  switch between workspace contexts.
- **Event presentation** — The kind-specific rendering of one CAO event
  on an identity timeline. An event presentation reflects what the
  event's typed body actually carries — for example, a Linear mention's
  presentation shows the issue, the mentioner, and a snippet, while a
  runtime delivery's presentation shows what was delivered and which
  terminal received it. The system has presentation knowledge for some
  CAO event kinds and lacks it for others.
- **Generic fallback presentation** — The minimal event presentation
  the system uses when CAO has not yet been taught presentation
  knowledge for a CAO event's kind.
  It shows only the event name, envelope facts, and the watched
  identity's participant role — the same row shape every event used
  before this feature.
- **Entity reference** — A reference an event presentation surfaces to
  a specific context the event names — for example, the Linear issue a
  mention was made in, or the terminal a delivery landed in. An entity
  reference can be followed by the operator to navigate into that
  context.
- **External entity reference** — An entity reference whose target lives
  outside CAO. Following an external entity reference takes the operator
  out of the dashboard and into the third-party context — for example,
  opening the Linear issue in Linear.
- **Internal entity reference** — An entity reference whose target is a
  CAO context, such as one of Aria's terminals. Following an internal
  entity reference focuses the dashboard on that CAO context without
  leaving the dashboard.
