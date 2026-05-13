# Behavioral Contract - CAO-96 Durable Typed Event Log

Derived from the approved Feature Narrative at `narrative.md` and the
approved Feature Capability Contract at `capability-contract.md`.

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [given-when-then-verifiability](../../planning/methodology/criteria/feature-behavioral-contract/given-when-then-verifiability.md) | Every behavior and constraint must be directly testable from its text. |
| [behavior-is-action](../../planning/methodology/criteria/feature-behavioral-contract/behavior-is-action.md) | Behaviors must describe event publication or consumer query actions, not standing rules. |
| [behavior-outcome-titles](../../planning/methodology/criteria/feature-behavioral-contract/behavior-outcome-titles.md) | Behavior titles must name the observable outcome established by each event-log action. |
| [operation-outcome-signaling](../../planning/methodology/criteria/feature-behavioral-contract/operation-outcome-signaling.md) | Event reconstruction and event-log queries are public operations whose success and empty-result outcomes must be explicit. |
| [stable-behavior-ids](../../planning/methodology/criteria/feature-behavioral-contract/stable-behavior-ids.md) | Task slicing and defences need stable behavior and constraint IDs. |

## Capability: CAP-1 - Durable Event History Readiness

### B-1 - Workspace Events Become Durable

Given a CAO workspace whose event history has not yet included a durable
event log,
When the workspace enters the release that provides the durable event log,
Then production CAO events published afterward can be retained in the
durable event log and agent involvement can be represented in the
participant index.

## Capability: CAP-2 - Production CAO Event Recording

### B-2 - Mention Publication Records One Participant

Given Linear reports that a teammate mentioned Aria in an issue,
When CAO publishes the mention as a production CAO event,
Then the durable event log records the mention with its event envelope,
typed body, and Aria as a participant in the mentioned role.

### B-3 - Runtime Delivery Records Envelope Links

Given Aria's runtime has delivered the original mention,
When CAO publishes the runtime delivery as a production CAO event,
Then the durable event log records the runtime delivery with its own
event envelope, typed body, Aria as a participant in the delivered role,
the original mention as its causation identifier, and the original
mention's correlation identifier.

### B-4 - Broadcast Records One Event For Multiple Participants

Given a teammate mentions both Aria and Cael in a single Linear issue,
When CAO publishes the broadcast mention as one production CAO event,
Then the durable event log records one canonical broadcast event and the
participant index represents Aria and Cael as participants in their
declared roles.

### B-5 - Workspace Event Records Without Agent Participants

Given a workspace-wide runtime event involves no specific agent identity,
When CAO publishes that event as a production CAO event,
Then the durable event log records the event and the participant index
has no participant entries for it.

## Capability: CAP-3 - Typed Event Reconstruction

### B-6 - Event Identifier Returns Original Typed Event

Given the original mention was recorded in the durable event log,
When a downstream consumer asks for that mention by event identifier,
Then the consumer receives the concrete typed event that was originally
published, including its original event envelope, typed body, and Aria as
participant.

### B-7 - Unknown Event Identifier Returns No Event

Given no recorded CAO event has a requested event identifier,
When a downstream consumer asks for an event by that identifier,
Then the consumer receives a no-event outcome and no other recorded CAO
event is returned in its place.

## Capability: CAP-4 - Agent-Scoped Event History

### B-8 - Agent History Returns Participant Events In Order

Given the durable event log contains the original mention and runtime
delivery involving Aria,
When a downstream consumer asks for every CAO event involving Aria,
Then the result contains those Aria participant events in occurrence
order.

### B-9 - Agent History Excludes Nonparticipant Events

Given the durable event log contains events that do and do not declare
Aria as a participant,
When a downstream consumer asks for every CAO event involving Aria,
Then the result excludes every event that does not declare Aria as a
participant, even when its typed body contains other information.

### B-10 - Shared Broadcast Appears In Each Participant History

Given one broadcast mention declares both Aria and Cael as participants,
When a downstream consumer asks for Aria's event history and then asks
for Cael's event history,
Then both histories include the same canonical broadcast event rather
than separate per-agent copies.

### B-11 - Agent History Can Return An Empty Result

Given no recorded CAO event declares a requested agent identity as a
participant,
When a downstream consumer asks for every CAO event involving that agent
identity,
Then the consumer receives an empty result and no unrelated recorded CAO
event is returned.

## Capability: CAP-5 - Envelope-Scoped Event Discovery

### B-12 - Correlation Query Returns Related Events

Given the original mention and runtime delivery share a correlation
identifier,
When a downstream consumer asks for every CAO event with that correlation
identifier,
Then the result contains the original mention and runtime delivery
without requiring typed-body inspection.

### B-13 - Causation Query Returns Direct Children

Given the runtime delivery names the original mention as its causation
identifier,
When a downstream consumer asks for every CAO event directly caused by
the original mention,
Then the result contains the runtime delivery as a direct child of the
mention and excludes events whose causation identifier does not directly
name the original mention.

### B-14 - Envelope Query Finds Participantless Events

Given a workspace-wide runtime event has no agent participants but has
event envelope facts,
When a downstream consumer asks for events by that event name or source,
Then the result includes the workspace-wide runtime event even though
identity-scoped histories do not include it.

### B-15 - Envelope Query Can Return An Empty Result

Given no recorded CAO event has a requested envelope fact,
When a downstream consumer asks for events by that envelope fact,
Then the consumer receives an empty result and no unrelated recorded CAO
event is returned.

## Capability: CAP-6 - Idempotent Event Republishing

### B-16 - Retried Publication Keeps One Canonical Event

Given the original Linear mention was already recorded,
When Linear redelivers the original mention webhook and CAO republishes
the mention with the same event identifier,
Then the durable event log still contains one canonical event for that
identifier and the participant index still contains one Aria entry in the
mentioned role for that event.

## Invariant: INV-1 - Event Identifier Canonicality

### C-1 - One Identifier Cannot Name Multiple Events

Given any event identifier in the durable event log,
When a consumer reconstructs or queries by that identifier after any
number of publications with the same identifier,
Then the identifier resolves to at most one canonical CAO event.

## Invariant: INV-2 - Recorded Event Reconstruction Fidelity

### C-2 - Recorded Events Retain Typed Fidelity

Given any recorded CAO event,
When a downstream consumer reconstructs that event from the durable event
log,
Then the reconstructed event preserves the original concrete typed event
type, event envelope, typed body, and declared participants.

## Invariant: INV-3 - Participant Index Represents Declared Involvement

### C-3 - Participant Index Mirrors Declared Participants Only

Given any recorded CAO event,
When a downstream consumer asks for identity-scoped histories,
Then the event appears only in histories for agent identities declared as
participants on that event and never appears in histories for
nonparticipants.

## Invariant: INV-4 - Envelope Facts Remain Queryable Independently

### C-4 - Envelope Queries Do Not Depend On Typed Bodies

Given any recorded CAO event with envelope facts,
When a downstream consumer asks for events by event identifier,
correlation identifier, causation identifier, event name, or source,
Then the query can be answered from envelope facts without requiring the
consumer to inspect typed-body contents.
