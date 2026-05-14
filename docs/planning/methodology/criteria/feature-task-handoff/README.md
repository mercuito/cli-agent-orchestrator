# Feature Task Handoff Criteria Catalog

Reusable criteria for the Feature Task Handoff — the per-task assignment
packet that turns a slice entry in `feature-tasks.md` into a startable task.

This catalog is a library. A criterion has no authority until a Feature
Feature Task Handoff selects it. Catalog authoring follows the rules in
[../README.md](../README.md).

## How to use

A Feature Task Handoff lives at
`docs/plans/<feature>/tasks/t-<n>/feature-task-handoff.md`. To assemble:

1. Browse this catalog — read each criterion's `when` field
2. Select criteria that apply
3. Add an **Applicable Criteria** table near the top of the handoff with
   one-line rationale per selection

See [creating-a-feature-task-handoff](../../creating-a-feature-task-handoff.md)
for full assembly guidance.

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [slice-reference-resolves](slice-reference-resolves.md) | Always |
| [operational-self-sufficiency](operational-self-sufficiency.md) | Always |
| [supporting-reference-sufficiency](supporting-reference-sufficiency.md) | Task entry says supporting references are required |
