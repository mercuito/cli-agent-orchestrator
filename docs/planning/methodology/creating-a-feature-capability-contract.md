# Creating a Capability Contract

## Purpose

The Capability Contract derives the feature's capabilities from the
narrative and captures the cross-cutting domain structure that supports
them — invariants and domain-level graphs. It is the bridge between the
narrative (what the feature does, in motion) and the behavioral contract
(testable behaviors and constraints).

It is a single feature-level artifact for behavior-changing work. Tasks
reference it; they do not redraft it.

Pure refactor work has no capability contract — refactors enter at the
Code Contract and skip narrative and capability contract entirely.

Vocabulary does not live here. The narrative carries domain vocabulary
(see [creating-a-feature-narrative](./creating-a-feature-narrative.md))
because it is authored at the point the event timeline needs it. The
capability contract cites the narrative for canonical definitions.

## What it contains

- **Capabilities** — coherent concepts the feature provides, scoped tightly
  enough that one capability does not need "and also" to explain it. Each
  capability has a stable ID of the form `CAP-<n>`, is named in domain
  terms, and is grounded in narrative events where the capability is
  actively exercised. Capabilities are the
  structural backbone the behavioral contract decomposes into behaviors.
- **Invariants** — universal truths about the domain that must hold across
  the feature. Each invariant has a stable ID of the form `INV-<n>`.
  Stated in domain entities, not implementation artifacts. Universal across
  all scenarios; scenario-bound properties are constraints in the
  behavioral contract instead.
- **Domain-level graphs** — state diagrams, entity-relationship diagrams,
  or flow diagrams expressed in domain concepts. Boxes labeled `Session`
  belong here; boxes labeled `SessionManager` do not.

A feature with capabilities but no useful invariants or diagrams may carry
only the capability list. Light is fine for invariants and graphs;
capabilities are not optional.

## What it does not contain

- The narrative or any event timeline content. The narrative is its own
  artifact.
- Domain vocabulary. Vocabulary lives in the narrative.
- Behaviors or constraints. Those are decomposed from capabilities and
  invariants in the behavioral contract.
- Implementation guidance, code shapes, or concrete payload examples.
- Class names, module names, or any other implementation-side entities.

## Authoring order

1. **Read the completed narrative.** Capabilities, invariants, and graphs
   only make sense in the context of the event timeline they support.
2. **Derive capabilities from narrative events.** Give each capability a
   stable ID (`CAP-<n>`) and short domain title. Each capability maps to
   narrative events where the capability is actively exercised. Prior
   effects, hidden implementation requirements, and reader inference do
   not ground a capability — see
   [active-exercise-grounding](./criteria/feature-capability-contract/active-exercise-grounding.md).
3. **Extract invariants from cross-cutting properties.** Give each
   invariant a stable ID (`INV-<n>`) and short domain title. Properties
   that apply across multiple narrative flows belong here as invariants.
   Scenario-specific properties are constraints in the behavioral contract.
4. **Add domain graphs where they earn their space.** A state diagram or
   entity-relationship diagram should communicate shape that prose would
   repeat across multiple flows. If the narrative does not benefit from a
   structural view, no graph is needed.

## Applicable criteria

Browse the [capability contract criteria catalog](./criteria/feature-capability-contract/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table
near the top of the capability contract with one-line rationale per
selection.

## Document organization

```markdown
# Capability Contract — <feature>

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| ...       | ...            |

## Capabilities

### CAP-1 — <capability name>

Brief domain context. Narrative events that exercise this capability:
`E1`, `E2`.

## Invariants

### INV-1 — <invariant name>

<One-sentence universal property in domain terms.>

## Domain Graphs

(Diagrams in domain entities only; omit if none earn their space.)
```

## Artifact path

`docs/plans/<feature>/capability-contract.md`

The artifact is the feature-level Capability Contract; `feature` is not a
filename prefix. Do not name the file `feature-capability-contract.md`.

## Quality check

For each capability: does it map to a narrative event where the capability
is actively exercised, with no "and also" hiding a second capability? If
not, it is either ungrounded or compound and should be split.

For each invariant: is it a universal property, or actually a
scenario-specific behavior? If the latter, drop it here and let the
behavioral contract carry it as a behavior.

Could two materially different implementations both satisfy the capability
contract? They should be able to. If one implementation is favored by the
wording (a class shape, a payload format, a particular algorithm), the
contract is leaking implementation detail and should be revised back into
domain language.
