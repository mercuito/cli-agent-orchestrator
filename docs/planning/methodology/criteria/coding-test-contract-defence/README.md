# Test Contract Defence Criteria Catalog

Reusable criteria for the Test Contract Defence — the per-task
evidence-backed proof that the assigned slice of the feature-level Test
Contract and the task-level Coding Test Contract are satisfied.

This catalog is a library. A criterion has no authority until a Test
Contract Defence selects it. Catalog authoring follows the rules in
[../README.md](../README.md).

## How to use

A Test Contract Defence lives at
`docs/plans/<feature>/tasks/t-<n>/test-contract-defence.md`. To assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply
3. Add an **Applicable Criteria** table near the top of the defence with
   one-line rationale per selection

See [creating-a-coding-test-contract-defence](../../creating-a-coding-test-contract-defence.md)
for full assembly guidance.

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [claim-evidence-verifiability](claim-evidence-verifiability.md) | Always |
