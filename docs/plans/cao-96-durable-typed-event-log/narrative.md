# Narrative

CAO-96 — Persist typed CAO events in a durable, queryable event log so the
exact typed event that was emitted can be retrieved later, listed by the
agent identities it involves, and joined to other events through its
envelope facts.

## Applicable Criteria

| Criterion | Rationale |
|-----------|-----------|
| [domain-language-only](../../planning/methodology/criteria/feature-narrative/domain-language-only.md) | Always applies; the narrative must speak in CAO event terms, not in storage or serialization terms. |
| [event-timeline-granularity](../../planning/methodology/criteria/feature-narrative/event-timeline-granularity.md) | Always applies; event-log readiness, publication, reconstruction, identity-scoped queries, envelope queries, broadcasts, and retries each occupy their own beat. |
| [events-have-observable-outcomes](../../planning/methodology/criteria/feature-narrative/events-have-observable-outcomes.md) | Always applies; every event must show what a downstream consumer can observe afterward — a recorded event, a reconstructed event, a query result. |
| [scenario-grounding](../../planning/methodology/criteria/feature-narrative/scenario-grounding.md) | Always applies; the timeline follows one running scenario — a Linear mention of agent Aria flowing through CAO and surfacing later in a timeline viewer — with retries, broadcasts, and workspace-wide events branching from it. |
| [vocabulary-grounded-in-event-timeline](../../planning/methodology/criteria/feature-narrative/vocabulary-grounded-in-event-timeline.md) | Always applies; the timeline depends on terms such as event envelope, participant index, timeline viewer, and causation identifier that need definitions. |

## Event Timeline

Scenario frame: A teammate mentions an agent named Aria in a Linear issue
on a CAO workspace whose event history now includes a durable event log.
The mention arrives at CAO through Linear's webhook, Aria's runtime acts
on it, and later a timeline viewer — a downstream consumer of CAO events
— asks the durable event log what happened to Aria. Around that central
thread, a broadcast mention also involves another agent named Cael, a
workspace-wide runtime event fires without participants, and Linear
retries the webhook for the original mention, each branch exercising the
durable event log from a different angle.

### E1 — The workspace gains a durable event history

The CAO workspace enters the new release with no prior durable event
history. The system establishes a durable event log and participant index
for the workspace before new CAO events arrive. After that moment, the
workspace can retain every production CAO event published through the
central publication path.

### E2 — Aria's mention is published and recorded

Linear's webhook reports that the teammate mentioned Aria in an issue, and
CAO publishes the mention as a CAO event through the central publication
path. The system records the event in the durable event log as part of
that publication, storing its envelope, its typed body, and Aria as a
participant in the mentioned role. From this point on, the mention exists
as a retrievable CAO event independently of whether any subscriber
remembers receiving it.

### E3 — Aria's runtime acts and publishes a causation-linked event

Aria's runtime accepts the mention and delivers it to her terminal, then
publishes a runtime event reporting that delivery. The system records the
runtime event in the durable event log with its own envelope, including a
causation identifier that links it back to the original mention and a
correlation identifier shared with it. After this beat, the durable event
log holds two CAO events about Aria — the inbound mention and the runtime
delivery — joined to one another through envelope facts.

### E4 — The timeline viewer reconstructs the original mention

Hours later, the timeline viewer asks the durable event log for the
original mention by its event identifier. The system reconstructs the
mention as the exact concrete typed event type that was first published,
with its original envelope, typed body, and Aria as participant. The
timeline viewer receives an event indistinguishable from what subscribers
received at publication time, even though no subscriber is still holding
it in memory.

### E5 — The timeline viewer lists every event involving Aria

The timeline viewer asks for every CAO event that involves Aria. The
system answers from the participant index and returns the mention from E2
and the runtime delivery from E3 in occurrence order. Events that do not
list Aria as a participant are absent from the result, regardless of what
their typed bodies contain.

### E6 — The timeline viewer follows the mention's correlation

The timeline viewer asks for every CAO event sharing the original
mention's correlation identifier. The system answers from envelope facts
alone, so the query does not have to read typed bodies, and it returns
the mention together with the runtime delivery linked to it. The timeline
viewer can now show the related events as one thread without inspecting
event-specific details.

### E7 — The timeline viewer follows the mention's causation

The timeline viewer asks for every CAO event directly caused by the
original mention. The system answers from the runtime delivery's
causation identifier and surfaces the delivery as a direct child of the
mention. The timeline viewer can now distinguish events that merely share
a broader correlation from events directly caused by the mention.

### E8 — A broadcast mention involves Aria and Cael together

The teammate later mentions both Aria and Cael in a single Linear issue,
and CAO publishes one broadcast mention event with two participants. The
system records the broadcast as a single canonical CAO event in the
durable event log and writes one participant entry per identity and role
in the participant index. Aria's identity-scoped timeline and Cael's
identity-scoped timeline both surface the same single canonical event,
without the typed body being duplicated per participant.

### E9 — A workspace-wide runtime event records with no participants

A workspace-wide runtime event fires that does not involve any specific
agent identity — for example, a workspace context refresh — and CAO
publishes it through the same central publication path. The system
records the event in the durable event log so envelope queries can find
it, but writes nothing to the participant index for it. Aria's
identity-scoped timeline does not surface this event, while a query by
event name or source does.

### E10 — Linear retries the original mention webhook

Linear redelivers the original mention webhook because its first delivery
was not acknowledged in time, and CAO republishes the mention with the
same event identifier through the central publication path. The system
treats the republication as idempotent: the durable event log keeps a
single canonical event for that identifier, and the participant index
keeps a single entry for Aria in the mentioned role. The timeline
viewer's reconstruction and queries from earlier beats continue to return
the same single canonical event.

## Domain Vocabulary

- **CAO event** — A framework-wide typed event published through CAO's
  central event publication path. Each CAO event has an envelope and a
  typed body, and may have zero or more agent participants.
- **Event envelope** — The universal facts every CAO event carries
  alongside its typed body: event identifier, event name, concrete-type
  discriminator, source type and source identifier, occurrence time,
  correlation identifier, and causation identifier.
- **Typed body** — The concrete-event-specific information a CAO event
  carries in addition to its envelope; the part that distinguishes, for
  example, an agent-mentioned event from a runtime-delivery event.
- **Concrete typed event type** — The specific kind of CAO event that was
  published, such as an agent-mentioned event or a runtime-delivery
  event. Reconstruction must recover this exact type, not a generic
  envelope-only stand-in.
- **Agent identity** — A CAO-recognised agent that can participate in
  events; the unit by which identity-scoped event histories are scoped.
  Aria and Cael are agent identities in this narrative.
- **Agent participant** — An agent identity that is involved in a given
  CAO event, together with the participant role describing how it is
  involved.
- **Participant role** — The kind of involvement an agent identity has in
  a CAO event; for example, the agent that was mentioned, or the agent
  that received a delivery. A single event may have several participants
  with different roles.
- **Event publication path** — The central place through which CAO
  events are published. Persistence attaches here rather than at each
  individual publisher, so every event published in production flows
  through the same boundary.
- **Durable event log** — The persistent record of CAO events. It
  retains the envelope and typed body of every event published through
  the central publication path, sufficient to reconstruct the exact
  concrete typed event later.
- **Participant index** — A first-class lookup that records each
  (event, agent identity, participant role) involvement. Identity-scoped
  queries answer from this index rather than by reading typed bodies.
- **Event reconstruction** — Recovering the exact concrete typed event
  instance, with its original envelope, typed body, and participants,
  from what was recorded in the durable event log.
- **Correlation identifier** — An envelope fact that groups related CAO
  events together — for example, a Linear mention and the runtime
  delivery it triggers — even when they were not directly caused by one
  another.
- **Causation identifier** — An envelope fact on a CAO event that names
  the directly causing CAO event, allowing causal chains to be
  traversed.
- **Idempotent publication** — The property that republishing a CAO
  event with the same event identifier — for example, when Linear
  retries a webhook — neither duplicates the event in the durable event
  log nor duplicates entries in the participant index.
- **Timeline viewer** — A downstream consumer of CAO events that asks
  the durable event log what happened to a given agent identity or
  along a given correlation. It stands in for any later feature, such
  as an agent timeline view, that depends on this slice rather than
  inventing its own event persistence.
