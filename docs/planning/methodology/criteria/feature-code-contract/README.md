# Feature-Level Code Contract Criteria Catalog

This directory contains reusable criteria for the **feature-level Code
Contract** — the contract that names cross-task code obligations:
dependency rules, refactor direction, public surface rules, architectural
commitments, and other clauses scoped to the whole feature.

This catalog is for clauses evaluable without deep code context.
Lower-level obligations that require codebase research belong in the
[coding-level Code Contract catalog](../coding-code-contract/README.md),
selected when authoring the task-level Coding Code Contract.

A criterion has no authority until the feature-level Code Contract selects
it.

## How to use

1. Browse this catalog by reading each criterion's `when` field.
2. Select criteria that apply to the feature.
3. Persist the feature-level Code Contract at
   `docs/plans/<feature>/feature-code-contract.md`.
4. Add an `Applicable Feature-Level Criteria` table near the top with
   one-line rationale per selection.

See [creating-a-feature-code-contract](../../creating-a-feature-code-contract.md)
for full assembly guidance.

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [implementation-clause-verifiability](implementation-clause-verifiability.md) | Always |
| [stable-code-clause-ids](stable-code-clause-ids.md) | Always |

## Adding new criteria

When feature-level work reveals a new class of cross-task code obligation
evaluable without deep code context:

1. Create a new `.md` file in this directory.
2. Include `name` and `when` in the frontmatter, following the catalog
   authoring standard in [../README.md](../README.md).
3. Write the obligation clearly enough that two readers cannot disagree on
   compliance.
4. Include paired good/bad illustrations.

If the obligation requires codebase research to evaluate `when:`
applicability or compliance, it belongs in the coding-level catalog
instead.
