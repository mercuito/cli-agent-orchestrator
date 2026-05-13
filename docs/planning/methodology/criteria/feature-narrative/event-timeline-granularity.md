---
name: event-timeline-granularity
when: Always.
---

# Event Timeline Granularity

The narrative is structured as a timeline of short, discrete, referenceable
events with stable event IDs. Each event captures one meaningful moment and
states what happened, what the system recognized or presented in domain
terms, and what changed observably.

Do not write the event timeline as free-form prose paragraphs. If one event
needs a large paragraph or combines multiple user actions, system
recognitions, state changes, retries, or later queries, split it into
multiple events.

## Illustrations

**Bad — bundled paragraph.** "When the user opens the app, signs in, joins a
workspace, and later returns, the system restores everything and records the
session." This hides several moments in one paragraph.
**Good:** `E1` shows the login screen when the user first opens the app.
`E2` records the successful sign-in. `E3` restores the user's prior
workspace when the user returns.

**Bad — unreferenceable flow.** The narrative has six paragraphs but no event
IDs, so a reviewer cannot point at the exact event that grounds a capability.
**Good:** Each timeline entry has a stable ID such as `E1`, `E2`, and `E3`
with a short title and observable outcome.
