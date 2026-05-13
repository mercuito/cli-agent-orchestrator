# Behavioral Contract Criteria Catalog

Reusable criteria for assembling feature-level behavioral contracts. These are
a curated checklist of common behavioral dimensions so important user-visible
behaviors do not stay implicit.

This catalog is a library. A criterion has no authority until a behavioral
contract selects it.

Each criterion has frontmatter (`name`, `when`), a body defining the behavioral
completeness obligation, and paired good/bad illustrations.

## How to use

The behavioral contract is a single feature-level artifact at
`docs/plans/<feature>/behavioral-contract.md`. To assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply to the feature
3. Add an **Applicable Criteria** table near the top of the contract with
   links and one-line rationale
4. Use those criteria to drive the feature-specific behaviors and constraints

The criteria are prompts for what the contract must cover. The feature's
behavioral contract remains the authority for the exact behaviors.

### Example preamble

```markdown
# Behavioral Contract — <feature>

## Applicable Criteria

| Criterion | Why it applies |
|-----------|----------------|
| [given-when-then-verifiability](given-when-then-verifiability.md) | Every behavior must be a verifiable Given/When/Then scenario |
| [configured-input-error-surfacing](configured-input-error-surfacing.md) | Users provide config that can be invalid |
```

### Adding new criteria

When a feature reveals a recurring behavioral omission useful across future
features:

1. Create a new `.md` file here with `name` and `when` in frontmatter
2. Write the criterion clearly enough that two readers cannot disagree on
   what must be covered
3. Include paired good/bad illustrations

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [given-when-then-verifiability](given-when-then-verifiability.md) | Always |
| [behavior-is-action](behavior-is-action.md) | Always |
| [behavior-outcome-titles](behavior-outcome-titles.md) | Always |
| [configured-input-error-surfacing](configured-input-error-surfacing.md) | Users provide consumed inputs |
| [operation-outcome-signaling](operation-outcome-signaling.md) | Public operations report structured outcomes |
| [public-surface-encapsulation](public-surface-encapsulation.md) | A service wraps a third-party surface |
| [lifecycle-boundary-operation-admissibility](lifecycle-boundary-operation-admissibility.md) | Lifecycle state gates operation validity |
| [named-registration-collision](named-registration-collision.md) | Consumers register named entities |
| [stable-behavior-ids](stable-behavior-ids.md) | Always |
