# Creating a Narrative

## Purpose

The narrative is the first feature-level artifact for behavior-changing
work. It is a domain-language event timeline: short story beats that show
something happening in the domain, how the system responds, and what is
different afterward. The narrative
seeds every other feature-level artifact: capabilities, invariants, and
domain graphs are derived from it in the capability contract, and the
behavioral contract formalizes its events into testable behaviors.

Pure refactor work has no narrative. It enters the methodology at the
Code Contract instead — see
[creating-a-feature-code-contract](./creating-a-feature-code-contract.md).

## What it contains

- **Scenario frame.** A concrete, plausible setup for the timeline: who or
  what starts the sequence, which named domain actors or representative
  systems are involved, what concrete thing moves through the system, and
  who or what later observes the result. Names may be invented when the
  exact integration is hypothetical, but they must feel like real domain
  participants rather than abstract placeholders.
- **Event timeline.** A sequence of short, discrete, referenceable
  user-facing or system-visible events. Each event is a short prose beat
  that describes one meaningful moment: what happened, how the system
  responded in domain terms, and what changed. The consequence must be
  visible in the prose; do not add separate outcome fields.
- **Domain vocabulary.** Definitions of the domain entities and concepts
  the timeline uses. Vocabulary lives here because the timeline needs
  it at the point it is being authored. Other feature-level artifacts cite
  the narrative for canonical definitions.

## What it does not contain

- Class names, module names, function names, file paths, payload shapes,
  library names, framework concepts, or any other implementation-side
  artifacts
- Capability inventory — capabilities are derived later, in the capability
  contract
- Invariants or domain-level graphs — those are cross-cutting structure
  and live in the capability contract
- Acceptance criteria phrased as Given/When/Then — those are behaviors, not
  narrative

## Applicable criteria
<IMPORTANT> Do not draft the document until you have read and understood applicible criteria<IMPORTANT>

Browse the [narrative criteria catalog](./criteria/feature-narrative/README.md) and
select the criteria that apply. Add an `Applicable Criteria` table near the
top of the narrative with one-line rationale per selection.

## Document organization

```markdown
# Narrative

## Event Timeline

Scenario frame: <one short paragraph describing the concrete running
scenario and representative actors.>

### E1 — <short event title>

<Two to four sentences of natural domain prose. The first sentence names
what happens. The next sentence describes how the system responds in
domain terms. The final sentence makes the changed domain state visible
without turning it into a requirement or capability statement.>

### E2 — <short event title>

...

## Domain Vocabulary

- **<Term>** — definition.
- **<Term>** — definition.
```

## Authoring order

1. **Choose the scenario frame.** Name the concrete domain situation the
   feature will follow. Identify the user, provider, agent, workspace,
   consumer, system, message, request, or other domain object that makes
   the feature move. The scenario may use representative or invented names,
   but it must be specific enough to feel like a real thing happening.
2. **Sketch the event timeline.** Write the flow as discrete events with
   stable IDs (`E1`, `E2`, ...), short natural titles, and no field labels
   such as `When`, `System response`, or `Observable outcome`. If an event
   needs a large paragraph, split it into smaller events.
3. **Keep each event single-purpose.** Each event captures one meaningful
   moment on the timeline. Do not bundle multiple user actions, system
   recognitions, state changes, retries, and later queries into one event.
4. **Write each event as a story beat.** Use two to four sentences of
   natural prose. The first sentence names what happens, the next sentence
   describes the system response in domain terms, and the final sentence
   makes the changed domain state visible.
5. **Keep the beats connected.** Later events should follow from, branch
   from, or intentionally contrast with earlier events. Avoid an abstract
   inventory where each event could be reordered without changing the
   story.
6. **Define vocabulary as the timeline reaches for it.** When the timeline
   uses a domain term that is not common English, add it to
   the Domain Vocabulary section with a precise definition. The
   timeline may then use the term freely.
7. **Stay implementation-free.** Reread the narrative looking for any
   implementation-side artifact (class, module, payload, file, library)
   and replace it with the domain term. If no domain term exists, add one
   to the vocabulary.

## Artifact path

`docs/plans/<feature>/narrative.md`

The artifact is the feature-level Narrative; `feature` is not a filename
prefix.

## Quality check

Can a reader derive candidate capabilities and affected domain concepts
from this narrative without inventing hidden steps or guessing what changed?
If not, the narrative is too vague — events do not show their consequences,
scope is too broad, the scenario is too abstract, too much is packed into a
single event, or implementation language has crept in.
