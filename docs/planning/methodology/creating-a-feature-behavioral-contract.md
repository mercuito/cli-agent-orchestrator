# Creating a Behavioral Contract

## Purpose

The behavioral contract is the feature-level definition of user-visible
correctness for behavior-changing work. It is a single feature-level artifact,
and tasks reference slices of it rather than redrafting it.

Pure refactor features do not have a behavioral contract. The Code
Contract is their entry artifact, and the universal `test-validity-preserved`
criterion (with an optional Test Contract) protects proof integrity for
existing behavior.

## Derivation chain

For behavior-changing work, the contract is derived in this order:

1. Start from the narrative artifact and its domain vocabulary (see
   [creating-a-feature-narrative](./creating-a-feature-narrative.md)). The
   narrative is the canonical source for terminology used throughout the
   contract.
2. Read the capability contract for the feature's capabilities,
   invariants, and domain graphs (see
   [creating-a-feature-capability-contract](./creating-a-feature-capability-contract.md)).
   Capabilities are inputs here; the capability contract owns their
   derivation.
3. Decompose each capability into testable Given/When/Then behaviors.
4. Decompose each invariant into verfiable constraints.

The capability contract owns the structural backbone (capabilities,
invariants); the behavioral contract owns the testable decomposition
(behaviors, constraints). Each capability and invariant is referenced
here, not redefined.

## Document organization

Behaviors are grouped under their parent capability heading; constraints are
grouped under their parent invariant heading. The document structure itself is
the traceability — there is no need for separate ID-based cross-references.

```markdown
# Behavioral Contract

## Capability: <capability name>

Brief domain context for this capability.

### Behavior: <outcome-focused title>

Given ...
When ...
Then ...

## Invariant: <invariant name>

### Constraint: <outcome-focused title>

Given ...
When ...
Then ...
```

## Applicable criteria

Browse the [behavioral contract criteria catalog](./criteria/feature-behavioral-contract/README.md)
and select the criteria that apply. Add an `Applicable Criteria` table near the
top of the contract with one-line rationale per selection.

Capability-derivation criteria live in the
[capability contract criteria catalog](./criteria/feature-capability-contract/README.md)
and apply when authoring the capability contract, not here.

## Quality check

For each behavior: can a reader write a test from the statement without making
assumptions about what "correct" means? If not, the behavior is insufficiently
precise.

For each constraint: is it a universal property, or actually a scenario-specific
behavior? If the latter, rewrite it as a Given/When/Then behavior under a
capability.

Could two materially different implementations both satisfy the contract? They
should be able to. If one implementation is favored by the wording, the contract
is leaking implementation detail.
