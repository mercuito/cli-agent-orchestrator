---
name: coding-discipline
description: Use whenever editing CAO production code or tests, making quick code changes, fixing bugs, refactoring, or adding verification so docs/criteria entries are selected and checked during implementation.
---

# Coding Discipline

Use this skill when making CAO code or test changes, including quick edits that
do not have a concrete written plan.

The project keeps implementation and testing criteria in `docs/criteria/`.
Each criteria file has frontmatter with a `name` and `when` clause.

## Workflow

1. Before or early in the edit, run the criteria catalog script from the
   repository root:

   ```bash
   uv run python scripts/catalog_criteria.py
   ```

   Use `--kind implementation` for production-only edits, `--kind tests` for
   test-only edits, or `--format json` when structured output is easier to scan.

2. Select criteria from the `when` clauses based on the actual files,
   behavior, and pending diff being changed. If you are implementing from a
   plan, treat any criteria named there as hints rather than an exhaustive list.

3. Load the full markdown for selected criteria by reading the catalog `path`.
   Keep this selective:

   - production code changes should consider matching implementation criteria
   - test changes should consider matching test criteria
   - mixed code/test changes should consider both
   - `when: Always.` criteria apply within the relevant catalog type

4. Use the selected criteria as implementation guardrails while editing. Let
   them influence code shape, test boundaries, mocks, seams, verification, and
   scope control.

5. Before finalizing, self-check the pending diff against the criteria catalog.
   No criteria applicable to the completed diff may be violated. If a criterion
   is not satisfied, fix it or clearly report the reason.

## Reporting

Do not produce a long criteria report for ordinary quick edits. In the final
answer, mention criteria only when they materially shaped the change, exposed a
tradeoff, blocked the request, or explain the verification approach.

If the user asks for a review, findings should still lead the response; use the
criteria to sharpen the review rather than replacing normal code-review
judgment.
