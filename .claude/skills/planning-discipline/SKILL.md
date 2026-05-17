---
name: planning-discipline
description: Use whenever planning CAO work, creating or updating a plan, drafting tasks, or shaping an implementation/test approach so docs/criteria entries are cataloged and post-implementation criteria compliance is made an acceptance condition.
---

# Planning Discipline

Use this skill whenever planning CAO work. This includes drafting, reviewing,
or revising a plan, task breakdown, design handoff, implementation approach,
or test approach.

Plans that guide implementation or review must be persisted under
`docs/plans/`. Do not leave implementation plans only in chat: reviewers and
downstream implementers need a durable artifact they can open independently.

The project keeps implementation and test criteria in `docs/criteria/implementation/` and
`docs/criteria/tests/`. Each criteria file has frontmatter with:

- `name`: the criteria identifier
- `when`: when the criteria should be considered

## Workflow

1. From the repository root, run the criteria catalog script:

   ```bash
   uv run python scripts/catalog_criteria.py
   ```

   Use `--kind implementation`, `--kind tests`, or `--format json` when a
   narrower or machine-readable catalog is useful.

2. Create or update a durable plan file under `docs/plans/`. Prefer a
   feature- or task-specific subdirectory when the work has multiple artifacts,
   contracts, or follow-up review needs.

3. Read the catalog before planning so the plan accounts for the universe of
   criteria that may come into force during implementation.

4. Do not make final applicability judgments from the plan alone. Planning
   usually happens before the exact diff exists, so the planner can identify
   likely criteria areas but must not claim the final set of applicable criteria
   is known.

5. Load full markdown only for criteria that clearly shape the plan. Use the
   catalog `path`. Keep this selective:

   - implementation `when: Always.` applies to plans that change production
     code, architecture, migrations, configuration, provider behavior, runtime
     services, or shared utilities.
   - tests `when: Always.` applies to plans that add, update, or rely on tests.

6. Incorporate criteria as implementation obligations, not as planner-certified
   conclusions. The plan should instruct the implementer to consult the catalog
   and load criteria whose `when` clauses match the actual code/test changes.

7. Add this acceptance condition, adapted to the plan format:

   ```text
   After implementation, evaluate the pending changes against the criteria
   catalog. No criteria applicable to the completed diff may be violated.
   ```

8. If a criteria file changes the shape of the plan, make that visible in the
   relevant plan section. Examples:

   - design constraints reflect implementation criteria
   - test strategy reflects test criteria
   - task ordering calls out migrations, seams, or public surfaces when relevant

9. If criteria appear to conflict with the requested approach, state the
   conflict before finalizing the plan and ask for a decision when needed.

## Planning Output

A disciplined plan should make criteria obligations traceable without pretending
the planner has complete implementation context. Use a short section such as
`Criteria Catalog` or `Criteria Acceptance` when the plan format allows it, or
attach the acceptance condition to affected design/test tasks.

The final planning response should include the persisted plan path, using the
`docs/plans/...` location that reviewers should inspect.

Do not say that no criteria are relevant unless the work truly cannot produce
code, test, configuration, migration, documentation-of-contract, or runtime
behavior changes. When in doubt, require the implementer to evaluate the
completed diff against the catalog.
