# Feature-Level Test Contract Criteria Catalog

This directory contains reusable criteria for the **feature-level Test
Contract** — the contract that names feature-wide proof obligations
sliced across tasks: shared harnesses, fixture patterns, preservation
baselines for refactor work, or proof shapes that no single task can
satisfy alone.

This catalog is for clauses evaluable without deep code context.
Lower-level proof-quality obligations that require codebase research
belong in the
[coding-level Test Contract catalog](../coding-test-contract/README.md),
selected when authoring the task-level Coding Test Contract.

A criterion has no authority until the feature-level Test Contract selects
it.

## How to use

1. Browse this catalog by reading each criterion's `when` field.
2. Select criteria that apply to the feature.
3. Persist the feature-level Test Contract at
   `docs/plans/<feature>/feature-test-contract.md`.
4. Add an `Applicable Feature-Level Test Criteria` table near the top with
   one-line rationale per selection.

See [creating-a-feature-test-contract](../../creating-a-feature-test-contract.md)
for full assembly guidance.

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [stable-test-clause-ids](stable-test-clause-ids.md) | Always |

## Adding new criteria

When feature-level work reveals a new class of cross-task proof obligation
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
