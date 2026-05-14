# Feature Tasks Criteria Catalog

Reusable criteria for the Tasks artifact (`tasks.md`) — the
authoritative index of tasks, scopes, and slice ownership across a feature.

This catalog is a library. A criterion has no authority until the Feature
Tasks artifact selects it. Catalog authoring follows the rules in
[../README.md](../README.md).

## How to use

The Tasks artifact is at `docs/plans/<feature>/tasks/tasks.md`. To
assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply
3. Add an **Applicable Criteria** table near the top of the artifact with
   one-line rationale per selection

See [creating-a-feature-tasks](../../creating-a-feature-tasks.md) for full
assembly guidance.

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [slice-acknowledgment-completeness](slice-acknowledgment-completeness.md) | Always |
| [slice-coverage-uniqueness](slice-coverage-uniqueness.md) | Always |
| [scope-handoffability](scope-handoffability.md) | Always |
| [supporting-reference-acknowledgment](supporting-reference-acknowledgment.md) | Always |
| [explicit-dependencies](explicit-dependencies.md) | Tasks have ordering dependencies |
