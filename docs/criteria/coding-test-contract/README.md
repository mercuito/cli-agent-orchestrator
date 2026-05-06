# Coding-Level Test Contract Criteria Catalog

This directory contains reusable criteria for the **task-level Coding Test
Contract** — the contract that names proof-shape obligations for one
specific task after research and scoping.

This catalog is for proof-quality and test-design clauses evaluable because
the affected CAO codebase and test surfaces have been inspected. Use it when
writing Linear issues, task handoffs, implementer prompts, and reviewer
prompts.

A criterion has authority for a task when the task issue, handoff, or
implementer prompt selects it.
The universal `test-validity-preserved` criterion governs proof integrity
on every code-touching task and should be treated as selected by default.

## How to use

1. Browse this catalog by reading each criterion's `when` field.
2. Select criteria that apply to the task you are about to implement.
3. Name selected criteria in the Linear issue, repo-local plan, or implementer
   prompt with a one-line rationale for each selection.
4. Ask reviewers to treat selected criteria as review obligations, not
   optional style preferences.

## Adding new criteria

When task work reveals a new class of proof-quality or test-maintainability
obligation evaluable after research:

1. Create a new `.md` file in this directory.
2. Include `name` and `when` in the frontmatter, following the catalog
   authoring standard in [../README.md](../README.md).
3. Write the obligation clearly enough that two readers cannot disagree on
   what must be covered.
4. Include paired good/bad illustrations.

If the obligation is broadly useful across CAO implementation work, add it to
the default assignment list in [../README.md](../README.md).

## Catalog

| Criterion | When to apply |
|-----------|---------------|
| [test-validity-preserved](test-validity-preserved.md) | Always |
| [given-when-then-test-structure](given-when-then-test-structure.md) | Tests prove multi-step behavior |
| [public-boundary-proof](public-boundary-proof.md) | A task changes a public boundary |
| [real-surface-proof-discipline](real-surface-proof-discipline.md) | Confidence depends on an integration surface |
| [inspectable-authored-inputs](inspectable-authored-inputs.md) | Authored input affects assertions |
| [setup-invariant-ownership](setup-invariant-ownership.md) | Tests require valid setup |
| [reusable-test-state](reusable-test-state.md) | Tests repeat setup state |
| [test-through-owner-surfaces](test-through-owner-surfaces.md) | Tests depend on another subsystem's behavior |
| [test-artifact-containment](test-artifact-containment.md) | Tests create real artifacts |
| [test-file-organization](test-file-organization.md) | A file covers multiple behavior families |
| [verification-scope-discipline](verification-scope-discipline.md) | Focused and broader proof both apply |
