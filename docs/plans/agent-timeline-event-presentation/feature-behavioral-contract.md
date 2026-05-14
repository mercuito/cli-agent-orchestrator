# Feature Behavioral Contract — Agent Timeline Event Presentation

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [given-when-then-verifiability](../../planning/methodology/criteria/feature-behavioral-contract/given-when-then-verifiability.md) | Every behavior and constraint must be precise enough to test from its text. |
| [behavior-is-action](../../planning/methodology/criteria/feature-behavioral-contract/behavior-is-action.md) | Behavior clauses must describe concrete operator or system actions and observable outcomes. |
| [behavior-outcome-titles](../../planning/methodology/criteria/feature-behavioral-contract/behavior-outcome-titles.md) | Behavior titles must name the observable outcome rather than the trigger or implementation mechanism. |
| [stable-behavior-ids](../../planning/methodology/criteria/feature-behavioral-contract/stable-behavior-ids.md) | Tasks, handoffs, and defences need stable behavior and constraint identifiers. |

## Capability: CAP-1 — Kind-Specific Timeline Event Presentation

An identity timeline can present a CAO event using details that belong to
that concrete typed event type instead of showing only event-envelope facts.

### B-1 — Known Event Kinds Read As Distinct Presentations

Given Aria's identity timeline contains a Linear mention, a runtime
delivery, a workspace context switch, and a runtime lifecycle event,
When the operator opens Aria's identity timeline,
Then those rows use distinct event presentations whose visible content
lets the operator distinguish what each concrete event kind means without
expanding the row.

### B-2 — Linear Mention Presentation Shows Issue Context

Given Aria's identity timeline contains a Linear mention event naming an
issue, a mentioner, mention text, and the Linear issue itself,
When the operator reads the Linear mention row,
Then the row shows the issue title, the teammate who wrote the mention, a
short snippet from the mention text, and an external entity reference for
the Linear issue.

### B-3 — Runtime Delivery Presentation Shows Delivery Context

Given Aria's identity timeline contains a runtime delivery event caused by
an earlier Linear mention and naming the terminal that received the
delivery,
When the operator reads the runtime delivery row,
Then the row shows the source kind that triggered the delivery, the
message that was delivered, and an internal entity reference for the
receiving terminal.

### B-4 — Workspace Context Switch Presentation Shows Movement

Given Aria's identity timeline contains a workspace context switch event
naming the workspace context before the switch and the workspace context
after the switch,
When the operator reads the workspace context switch row,
Then the row shows the from-context and to-context so the operator can see
which workspace Aria left and which one she moved into.

### B-5 — Runtime Lifecycle Presentation Shows Runtime State

Given Aria's identity timeline contains a runtime lifecycle event naming a
lifecycle phase and workspace context,
When the operator reads the runtime lifecycle row,
Then the row shows the lifecycle phase and the workspace context where it
happened so the operator can tell whether Aria's runtime was healthy or
had a hiccup.

## Capability: CAP-2 — Related Event Presentation Continuity

The related events panel can present related CAO events with the same
event presentation those events would receive on the main identity
timeline.

### B-6 — Related Events Keep Their Event Presentations

Given the operator expands a Linear mention row whose related events
include a runtime delivery, a workspace context switch, and an untaught
event kind,
When the related events panel appears,
Then each related event is shown with the same event presentation it
would receive on the main identity timeline, including the generic
fallback presentation for the untaught event kind.

## Capability: CAP-3 — Entity Reference Navigation

The operator can follow entity references surfaced by event presentations
into the referenced external or internal context.

### B-7 — External Entity Reference Opens The Linear Issue

Given the Linear mention row shows an external entity reference for the
Linear issue,
When the operator follows that entity reference,
Then the Linear issue opens in its own external context without the
operator copying an identifier or manually searching for the issue.

### B-8 — Internal Entity Reference Focuses The Receiving Terminal

Given the runtime delivery row shows an internal entity reference for the
terminal that received the delivery,
When the operator follows that entity reference,
Then the dashboard focuses the referenced terminal so the operator can
see where Aria received the delivery without leaving the dashboard.

## Capability: CAP-4 — Generic Fallback Presentation

A CAO event whose kind has no taught event presentation remains visible
through a generic fallback presentation.

### B-9 — Untaught Event Kind Uses Generic Fallback

Given Aria's identity timeline contains a CAO event whose kind has no
taught event presentation,
When the operator views that event on the main identity timeline or in a
related events panel,
Then the event is visible through a generic fallback presentation showing
the event name, event-envelope facts, and Aria's participant role, without
kind-specific detail.

## Invariant: INV-1 — Presentation Truthfulness

### C-1 — Presentations Do Not Invent Event Facts

Given an event presentation appears on an identity timeline surface,
When the operator reads its kind-specific details, entity references, or
fallback facts,
Then every visible event fact comes from that CAO event or from the
watched identity's participant role for that event.

## Invariant: INV-2 — Same-Context Presentation Consistency

### C-2 — Same Event Presentation Appears In One Identity Context

Given the same CAO event appears both on a main identity timeline and in
the related events panel for that same watched identity timeline context,
When the operator compares the two appearances,
Then the event presentation is the same in both places, aside from
layout differences required by the surrounding surface.

## Invariant: INV-3 — Entity Reference Target Integrity

### C-3 — Entity References Preserve Target Kind

Given an event presentation includes entity references,
When the operator sees or follows each reference,
Then each reference names exactly one target context, preserves whether
that target is external to CAO or internal to the dashboard, and sends
the operator to that named context when followed.

## Invariant: INV-4 — Untaught Event Visibility

### C-4 — Fallback Events Remain Related And Visible

Given a CAO event has no taught event presentation but has envelope facts
that place it on an identity timeline or in a related events panel,
When that identity timeline surface is shown,
Then the event remains visible through the generic fallback presentation
and still participates in correlation or causation relatedness.
