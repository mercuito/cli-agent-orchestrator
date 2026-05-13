# Behavioral Contract — Agent Identity Timeline View

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [given-when-then-verifiability](../../planning/methodology/criteria/feature-behavioral-contract/given-when-then-verifiability.md) | Every behavior and constraint must be precise enough to test from its text. |
| [behavior-is-action](../../planning/methodology/criteria/feature-behavioral-contract/behavior-is-action.md) | Behavior clauses must describe concrete operator or system actions and observable outcomes. |
| [behavior-outcome-titles](../../planning/methodology/criteria/feature-behavioral-contract/behavior-outcome-titles.md) | Behavior titles must name the observable outcome rather than the trigger or implementation mechanism. |
| [stable-behavior-ids](../../planning/methodology/criteria/feature-behavioral-contract/stable-behavior-ids.md) | Tasks, handoffs, and defences need stable behavior and constraint identifiers. |

## Capability: CAP-1 — Identity Roster Browsing

The dashboard gives the operator an agents area where configured agent
identities are browsable as dashboard subjects.

### B-1 — Roster Lists Configured Agent Identities

Given the workspace has configured agent identities Aria, Cael, and a
third identity with no recorded CAO events,
When the operator opens the dashboard agents area,
Then the agent identity roster lists Aria, Cael, and the third identity
by agent identity, whether or not any identity currently occupies a
terminal or has recorded CAO events.

### B-2 — Roster Selection Opens The Chosen Identity

Given the agent identity roster is visible,
When the operator selects one listed agent identity,
Then the dashboard opens the agent identity view for that selected
identity and keeps the operator oriented around that identity rather than
around a terminal.

## Capability: CAP-2 — Agent Identity View

The operator can open one agent identity and inspect that identity's
configured details together with its identity timeline.

### B-3 — Identity View Shows Details And Timeline

Given a configured agent identity is listed in the roster,
When the operator opens that identity,
Then the agent identity view presents that identity's configured details
and that identity's identity timeline together.

### B-4 — Identity View Changes To The Newly Selected Identity

Given the operator is viewing one agent identity,
When the operator returns to the roster and opens a different configured
agent identity,
Then the dashboard presents the newly selected identity's configured
details and identity timeline instead of continuing to show the prior
identity.

## Capability: CAP-3 — Participant-Scoped Identity Timeline

An identity timeline presents recent CAO events involving the selected
agent identity, ordered by occurrence and summarized with event kind,
occurrence time, and the selected identity's participant role.

### B-5 — Timeline Shows Involved Events In Recent Occurrence Order

Given Aria has recorded CAO events for a Linear mention, its runtime
delivery, and a broadcast mention involving Aria,
When the operator opens Aria's identity timeline,
Then the timeline shows those Aria-involving CAO events in recent
occurrence order.

### B-6 — Timeline Rows Summarize Identity Participation

Given an identity timeline contains CAO events involving the selected
agent identity,
When the operator reads the timeline rows,
Then each row shows the event kind, the occurrence time, and the selected
identity's participant role for that event.

### B-7 — Non-Participant Workspace Events Stay Off The Timeline

Given the operator is viewing Aria's identity timeline and CAO records a
workspace-wide context refresh with no agent participants,
When the dashboard refreshes the watched identity timeline,
Then Aria's identity timeline does not show the workspace-wide refresh
and otherwise remains on the Aria-involving CAO events.

## Capability: CAP-4 — Related Event Thread Exploration

The operator can expand a timeline row and see related CAO events through
that row's causation identifier or correlation identifier.

### B-8 — Causation Expansion Shows The Direct Cause

Given Aria's identity timeline includes a runtime delivery row with a
causation identifier naming the original Linear mention,
When the operator expands the runtime delivery row to inspect its cause,
Then the agent identity view shows the original Linear mention as the
directly causing CAO event alongside the delivery.

### B-9 — Correlation Expansion Shows The Shared Thread

Given Aria's identity timeline includes a Linear mention row with a
correlation identifier shared by downstream CAO events,
When the operator expands the Linear mention row to inspect its related
thread,
Then the agent identity view shows the CAO events sharing that
correlation identifier as one related event thread.

## Capability: CAP-5 — Broadcast Participant Viewpoints

A single broadcast CAO event can appear on each involved agent identity's
timeline while preserving the identity-specific participant role for the
view the operator is inspecting.

### B-10 — Broadcast Event Appears On Each Participant Timeline

Given one broadcast mention declares both Aria and Cael as agent
participants,
When the operator views Aria's identity timeline and then Cael's identity
timeline,
Then both timelines surface the same canonical CAO event, with Aria's
participant role visible on Aria's timeline and Cael's participant role
visible on Cael's timeline.

## Capability: CAP-6 — Live Timeline Refresh

The watched identity timeline updates while the operator remains on the
agent identity view, adding newly recorded CAO events involving that
identity without requiring a dashboard reload.

### B-11 — New Involved Event Appears Without Reload

Given the operator is watching Aria's identity timeline,
When CAO records a new Linear mention involving Aria,
Then the new mention appears on Aria's identity timeline without the
operator reloading the dashboard or reopening Aria's identity view.

## Capability: CAP-7 — Empty Identity Activity

The dashboard communicates when a configured agent identity has no recent
CAO events to display, distinct from loading or unreachable timeline
states.

### B-12 — Empty Timeline Reports No Recent Activity

Given a configured agent identity has no recorded CAO events involving
that identity,
When the operator opens that identity's agent identity view,
Then the identity timeline reports that there is no recent activity to
display and does not present the state as loading or unreachable.

## Invariant: INV-1 — Agent Identity Independence

### C-1 — Identity Visibility Does Not Depend On A Terminal

Given an agent identity is configured for the workspace,
When the dashboard presents the agents area or an agent identity view,
Then the identity is represented as the same dashboard subject whether or
not it currently occupies a terminal.

## Invariant: INV-2 — Participant-Index Timeline Membership

### C-2 — Timeline Membership Follows Declared Participants

Given a CAO event exists in the durable event log,
When an identity timeline is resolved for one agent identity,
Then the event appears on that timeline only if the event declares that
agent identity as an agent participant, and the shown participant role is
the role declared for that identity.

## Invariant: INV-3 — Canonical Event Identity

### C-3 — Multi-Identity Visibility Does Not Duplicate The Event

Given one CAO event declares multiple agent participants,
When the operator reaches that event through more than one participant's
identity timeline,
Then each timeline points to the same canonical CAO event rather than
creating a separate event per identity.

## Invariant: INV-4 — Envelope-Based Relatedness

### C-4 — Related Threads Use Envelope Facts

Given CAO events have event envelope facts and typed bodies,
When the operator opens a causation-based or correlation-based related
event thread,
Then thread membership is determined from the relevant causation
identifier or correlation identifier in the event envelope, not from
agent names or other details inside typed event bodies.
