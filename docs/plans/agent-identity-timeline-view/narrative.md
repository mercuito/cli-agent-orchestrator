# Feature Narrative

Agent Identity Timeline View — Give CAO operators a place on the dashboard
to browse agent identities and review the recent CAO events involving any
one identity, drawing entirely on the durable event log and participant
index landed by CAO-96.

## Applicable Criteria

| Criterion | Rationale |
|-----------|-----------|
| [domain-language-only](../../planning/methodology/criteria/feature-narrative/domain-language-only.md) | Always applies; the narrative must speak in CAO event and dashboard-domain terms, not in UI component, route, or transport terms. |
| [event-timeline-granularity](../../planning/methodology/criteria/feature-narrative/event-timeline-granularity.md) | Always applies; the agents area appearing, an identity opening, the timeline surfacing events, drilling into causation, drilling into correlation, broadcasts, live updates, non-participant events, and the empty state are each their own beat. |
| [events-have-observable-outcomes](../../planning/methodology/criteria/feature-narrative/events-have-observable-outcomes.md) | Always applies; every event must show what the operator observes afterward — a roster, an identity view, an updated timeline, a related-event thread, or an unchanged timeline. |
| [scenario-grounding](../../planning/methodology/criteria/feature-narrative/scenario-grounding.md) | Always applies; the timeline follows one running scenario — an operator returning to the dashboard and investigating agent Aria after the Linear mention from the CAO-96 scenario — with branches for Cael's broadcast, a live new mention, a workspace-wide refresh, and an unused identity. |
| [vocabulary-grounded-in-event-timeline](../../planning/methodology/criteria/feature-narrative/vocabulary-grounded-in-event-timeline.md) | Always applies; the timeline introduces dashboard-side terms (agents area, identity view, identity timeline, related event thread, live timeline update, empty identity timeline) that need definitions in addition to the CAO event vocabulary inherited from CAO-96. |

## Event Timeline

Scenario frame: A CAO operator returns to their workstation and opens the
dashboard. Their workspace already runs the durable event log from CAO-96
and has produced real events: agent Aria was mentioned in a Linear issue
earlier today, Aria's runtime delivered the mention to her terminal, a
later broadcast mention involved both Aria and another agent Cael, and a
workspace-wide context refresh fired in between. A third configured agent
identity has not yet been involved in any recorded CAO event. The operator
opens the dashboard to find out what their agents have been doing and
walks through the new agents area one identity at a time. While the
operator watches Aria, a fresh Linear mention lands and another
workspace-wide refresh fires, each exercising the timeline from a
different angle.

### E1 — The dashboard gains an agents area

The operator opens the CAO dashboard for the first time after the feature
lands and finds a new top-level agents area alongside the existing session
and terminal views. The system presents an agent identity roster listing
every configured agent identity for the workspace, including Aria, Cael,
and the third configured identity, each shown by its identity rather than
by any one terminal it currently occupies. After this beat, the operator
can see and pick agent identities from the dashboard without having to
read through running terminals first.

### E2 — The operator opens Aria's identity view

The operator selects Aria from the identity roster. The system opens
Aria's agent identity view, which presents Aria's configured identity
details together with Aria's identity timeline — the recent CAO events
involving Aria drawn from the participant index. After this beat, the
operator is looking at Aria as a first-class subject on the dashboard
rather than at one of her terminals.

### E3 — The timeline surfaces Aria's mention and runtime delivery

Aria's identity timeline shows the runtime delivery from earlier and the
original Linear mention that triggered it, in occurrence order. Each
event appears as a row summarised by what kind of CAO event it was, when
it occurred, and Aria's participant role. After this beat, the operator
has a chronological picture of Aria's recent involvement without having
to open any individual event.

### E4 — The operator follows the runtime delivery's causation

The operator expands the runtime delivery row on Aria's identity timeline
to see what caused it. The system surfaces the original Linear mention
alongside the delivery as the directly causing event, drawn from the
delivery's causation identifier. After this beat, the operator can move
from a recorded effect to its direct cause without leaving Aria's
identity view.

### E5 — The operator follows the mention's correlation

The operator expands the Linear mention row instead and asks what else
shares its thread. The system surfaces every CAO event sharing the
mention's correlation identifier as one related event thread, including
the runtime delivery the operator just inspected. After this beat, the
operator can see the mention and its downstream effects grouped together
without inspecting any event's typed body.

### E6 — The broadcast mention appears on both Aria's and Cael's timelines

Earlier in the day, a teammate had mentioned both Aria and Cael in a
single Linear issue, and CAO had recorded one broadcast mention with two
agent participants. Aria's identity timeline surfaces that broadcast
mention with Aria's participant role visible, and when the operator
returns to the identity roster and opens Cael's agent identity view,
Cael's identity timeline surfaces the same canonical CAO event with
Cael's participant role visible. After this beat, the operator
understands that a single broadcast event lives once in the durable
event log and shows up on each involved identity's timeline as the same
event from each identity's point of view.

### E7 — A new mention lands and Aria's timeline updates live

The operator returns to Aria's agent identity view and keeps watching.
The teammate replies on the Linear issue and mentions Aria again, and
CAO records the new mention as a CAO event involving Aria. The system
applies a live timeline update so the new mention appears at the top of
Aria's identity timeline without the operator reloading. After this
beat, the operator's identity timeline reflects newly recorded events
involving Aria as they happen.

### E8 — A workspace-wide refresh fires and Aria's timeline stays put

While the operator continues watching Aria's identity timeline, a
workspace-wide context refresh fires and CAO records it as a CAO event
with no agent participants. The system does not surface the refresh on
Aria's identity timeline, because the refresh declares no agent
participants and Aria's timeline answers from the participant index.
After this beat, the operator can see that an identity timeline only
moves for events that actually involve the watched identity, even when
the durable event log is recording other workspace activity in the
background.

### E9 — A configured identity with no events reads as empty

The operator returns to the identity roster and opens the third
configured agent identity, who has not yet been involved in any recorded
CAO event. The system opens that identity's agent identity view and
shows the identity's configured details together with an empty identity
timeline that clearly reports no recent activity to display. After this
beat, the operator can tell the difference between an identity that has
done nothing yet and an identity whose timeline is loading or
unreachable.

## Domain Vocabulary

- **CAO event** — As defined in the CAO-96 narrative; a framework-wide
  typed event published through CAO's central event publication path,
  carrying an event envelope, a typed body, and zero or more agent
  participants.
- **Event envelope** — As defined in the CAO-96 narrative; the universal
  facts every CAO event carries, including its event identifier,
  occurrence time, correlation identifier, and causation identifier.
- **Agent identity** — As defined in the CAO-96 narrative; a
  CAO-recognised agent that can participate in events, configured for
  the workspace independently of any one terminal it currently occupies.
  Aria, Cael, and the third configured identity in this narrative are
  agent identities.
- **Agent participant** — As defined in the CAO-96 narrative; an agent
  identity that is involved in a given CAO event, together with its
  participant role.
- **Participant role** — As defined in the CAO-96 narrative; the kind of
  involvement an agent identity has in a CAO event, such as the agent
  that was mentioned or the agent that received a delivery.
- **Durable event log** — As defined in the CAO-96 narrative; the
  persistent record of CAO events that retains envelope and typed body
  for every event published through the central publication path.
- **Participant index** — As defined in the CAO-96 narrative; the
  first-class lookup that records each (event, agent identity,
  participant role) involvement; identity-scoped queries answer from
  this index.
- **Correlation identifier** — As defined in the CAO-96 narrative; an
  envelope fact that groups related CAO events together even when they
  were not directly caused by one another.
- **Causation identifier** — As defined in the CAO-96 narrative; an
  envelope fact that names the directly causing CAO event so causal
  chains can be traversed.
- **Operator** — A human using the CAO dashboard to inspect what their
  agent identities have been doing in the workspace.
- **Agents area** — A top-level place on the CAO dashboard where the
  operator browses agent identities and opens their identity views.
  Distinct from the existing session and terminal views, which remain
  oriented around running terminals rather than around identities.
- **Agent identity roster** — The listing of every configured agent
  identity for the workspace that the agents area presents to the
  operator. The roster lists identities even when they have not been
  involved in any recorded CAO event yet.
- **Agent identity view** — The per-identity page the operator opens
  from the roster. It presents one agent identity's configured details
  together with that identity's identity timeline.
- **Identity timeline** — The chronologically ordered presentation of
  recent CAO events involving a single agent identity, drawn from the
  participant index. Each row summarises the event by kind, occurrence
  time, and the identity's participant role in it.
- **Related event thread** — The set of CAO events the system surfaces
  when the operator follows a timeline row's correlation or causation;
  the events are grouped together by envelope facts alone, without
  inspecting typed bodies.
- **Live timeline update** — The property that newly recorded CAO
  events involving the watched agent identity appear on its identity
  timeline without the operator reloading the agent identity view.
- **Empty identity timeline** — The presentation an identity timeline
  takes when no CAO events involving that agent identity have been
  recorded yet; distinct from a timeline that is loading or
  unreachable.
