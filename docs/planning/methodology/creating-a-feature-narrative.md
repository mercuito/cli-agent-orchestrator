# Creating a Narrative

## Purpose

The narrative is the first feature-level artifact for behavior-changing
work. It is a domain-language event timeline — what users do, what the
system recognizes, what changes, and what outcomes are visible. The narrative
seeds every other feature-level artifact: capabilities, invariants, and
domain graphs are derived from it in the capability contract, and the
behavioral contract formalizes its events into testable behaviors.

Pure refactor work has no narrative. It enters the methodology at the
Code Contract instead — see
[creating-a-feature-code-contract](./creating-a-feature-code-contract.md).

## What it contains

- **Event timeline.** A sequence of short, discrete, referenceable
  user-facing events. Each event describes one meaningful moment: what
  happened, what the system recognized or presented in domain terms, and
  what changed observably as a result.
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

## Document organization

```markdown
# Narrative

## Event Timeline

### E1 — <short event title>

**When:** <the user-facing event or system-recognized moment>
**System response:** <what the system presents, recognizes, or records in domain terms>
**Observable outcome:** <what changed or became visible>

### E2 — <short event title>

...

## Domain Vocabulary

- **<Term>** — definition.
- **<Term>** — definition.
```

## Authoring order

1. **Sketch the event timeline.** Write the flow as discrete events with
   stable IDs (`E1`, `E2`, ...), short outcome-focused titles, and no
   multi-paragraph event bodies. If an event needs a large paragraph, split
   it into smaller events.
2. **Keep each event single-purpose.** Each event captures one meaningful
   moment on the timeline. Do not bundle multiple user actions, system
   recognitions, state changes, retries, and later queries into one event.
3. **State outcomes for every event.** Each significant event must have an
   observable outcome — what changed in domain terms. An event without an
   outcome is unverifiable and cannot ground a behavior.
4. **Define vocabulary as the timeline reaches for it.** When the timeline
   uses a domain term that is not common English, add it to
   the Domain Vocabulary section with a precise definition. The
   timeline may then use the term freely.
5. **Stay implementation-free.** Reread the narrative looking for any
   implementation-side artifact (class, module, payload, file, library)
   and replace it with the domain term. If no domain term exists, add one
   to the vocabulary.

## Applicable criteria

Browse the [narrative criteria catalog](./criteria/feature-narrative/README.md) and
select the criteria that apply. Add an `Applicable Criteria` table near the
top of the narrative with one-line rationale per selection.

## Artifact path

`docs/plans/<feature>/narrative.md`

## Quality check

Can a reader derive candidate capabilities and affected domain concepts
from this narrative without inventing hidden steps or guessing outcomes? If
not, the narrative is too vague — events are missing their outcomes, scope
is too broad, too much is packed into a single event, or implementation
language has crept in.
