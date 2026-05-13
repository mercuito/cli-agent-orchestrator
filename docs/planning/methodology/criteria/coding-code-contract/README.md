# Coding-Level Code Contract Criteria Catalog

This directory contains reusable criteria for the **task-level Coding Code
Contract** — the contract that names the code-shape obligations for one
specific task after research and scoping.

This catalog is for clauses evaluable because the affected CAO codebase has
been inspected. Use it when writing Linear issues, task handoffs, implementer
prompts, and reviewer prompts.

A criterion has authority for a task when the task issue, handoff, or
implementer prompt selects it. The default criteria in
[../README.md](../README.md) should be treated as selected for code-changing
work unless explicitly waived.

## How to use

1. Browse this catalog by reading each criterion's `when` field.
2. Select criteria that apply to the task you are about to implement,
   based on what your research surfaced about the affected code.
3. Name selected criteria in the Linear issue, repo-local plan, or implementer
   prompt with a one-line rationale for each selection.
4. Ask reviewers to treat selected criteria as review obligations, not
   optional style preferences.

## Adding new criteria

When task work reveals a new class of code-shape obligation evaluable
after research:

1. Create a new `.md` file in this directory.
2. Include `name` and `when` in the frontmatter, following the catalog
   authoring standard in [../README.md](../README.md).
3. Write the obligation clearly enough that two readers cannot disagree on
   compliance.
4. Include paired good/bad illustrations.

If the obligation is broadly useful across CAO implementation work, add it to
the default assignment list in [../README.md](../README.md).

## Relationship to test criteria

This catalog is for production-code shape only. Use the
[coding-level Test Contract catalog](../coding-test-contract/README.md)
for proof-quality, helper/fixture discipline, and verification-design
obligations at the coding altitude.

## Catalog

| Criterion | When to apply |
|-----------|--------------|
| [full-verification-required](full-verification-required.md) | Code changes are produced |
| [red-green-refactor](red-green-refactor.md) | Behavior changes are testable |
| [boundary-and-failure-testing](boundary-and-failure-testing.md) | Boundaries accept input or claim composition |
| [authored-document-edit-preservation](authored-document-edit-preservation.md) | Authored documents are mutated |
| [semantic-continuity](semantic-continuity.md) | Existing paths are extended |
| [minimal-cohesive-changes](minimal-cohesive-changes.md) | Non-refactor code changes are made |
| [no-unnecessary-duplication](no-unnecessary-duplication.md) | Code, helpers, fixtures, or abstractions are added |
| [no-test-only-production-seams](no-test-only-production-seams.md) | Tests motivate production seam changes |
| [respect-ownership-boundaries](respect-ownership-boundaries.md) | Code crosses file, package, service, system, or other ownership boundaries |
| [centralized-vocabulary](centralized-vocabulary.md) | Named syntax changes |
| [path-utils-required](path-utils-required.md) | Paths are manipulated |
| [filesystem-boundary-required](filesystem-boundary-required.md) | Production code performs filesystem I/O |
| [environment-variable-policy](environment-variable-policy.md) | Code reads environment or global state |
| [prefer-public-surfaces](prefer-public-surfaces.md) | Another boundary is consumed |
| [respect-standing-decisions](respect-standing-decisions.md) | Committed decisions are in force |
| [readable-and-explicit](readable-and-explicit.md) | Any implementation task |
| [service-definition-surface](service-definition-surface.md) | A public/shared service is created or reshaped |
| [service-export-discipline](service-export-discipline.md) | Service exports change |
| [well-defined-service](well-defined-service.md) | A service is created or reshaped |
| [migration-discipline](migration-discipline.md) | Existing code migrates to a new shape |
| [no-assumed-backwards-compatibility](no-assumed-backwards-compatibility.md) | Old shapes could be preserved |
