# Capability Contract Criteria Catalog

Reusable criteria for authoring the capability contract — the artifact
that derives capabilities from the narrative and captures cross-cutting
invariants and domain graphs. Vocabulary lives in the narrative itself,
not here.

This catalog is a library. A criterion has no authority until a capability
contract selects it. Catalog authoring follows the rules in
[../README.md](../README.md).

## How to use

The capability contract is a feature-level artifact at
`docs/plans/<feature>/capability-contract.md`. To assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply
3. Add an **Applicable Criteria** table near the top of the capability
   contract with one-line rationale per selection
4. Author the capability contract against the selected criteria

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [active-exercise-grounding](active-exercise-grounding.md) | Capabilities are mapped to narrative events |
| [implementation-neutrality](implementation-neutrality.md) | Always |
| [invariant-universality](invariant-universality.md) | The capability contract declares invariants |
| [stable-capability-ids](stable-capability-ids.md) | Always |
