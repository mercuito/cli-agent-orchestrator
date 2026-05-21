# Task 02 — Delete the `linear/` Package and `test/linear/` Suite

## Goal

Physically remove `src/cli_agent_orchestrator/linear/` and `test/linear/` from
the tree. After this task, no Python file in the repository carries the name
`linear` in its module path.

## Preconditions

- Task 01 is complete and committed: every external importer of `linear.*`
  has been decoupled.
- `grep -rn "from cli_agent_orchestrator.linear\|import cli_agent_orchestrator.linear" src/ test/` returns matches only inside `src/cli_agent_orchestrator/linear/` and `test/linear/`.
- Branch `delete-linear-provider` is current.

## Scope

1. `git rm -r src/cli_agent_orchestrator/linear/` — 28 source files plus the
   package's `__init__.py`.
2. `git rm -r test/linear/` — 12 test modules plus their `__init__.py` if
   present.
3. Remove any pytest fixtures, conftests, or test helpers in `test/` that
   still import from `linear.*`. Find them with:

   ```bash
   grep -rln "cli_agent_orchestrator.linear" test/
   ```

   If a hit is purely an import that supported deleted tests, delete the
   helper too. If a hit is in a shared conftest used by non-Linear tests,
   trim the Linear-specific portions of the conftest rather than deleting
   the whole file.

4. `__pycache__` directories under the deleted paths should be removed too,
   but they will be ignored by git. No special handling needed.

## Out of Scope

- Do not edit any remaining `.py` file's contents for runtime behavior.
  This task is pure deletion plus the minimal conftest trims required to
  let the suite collect.
- Do not yet run the full test suite or attempt to fix breakage from this
  deletion. That is Task 03's contract.
- Do not yet touch the inbox package. That is Task 04.

## Acceptance Criteria

1. `find src/cli_agent_orchestrator -name linear -type d` returns nothing.
2. `find test -name linear -type d` returns nothing.
3. `grep -rn "cli_agent_orchestrator.linear" src/ test/` returns no matches.
4. `uv run pytest --collect-only -q 2>&1 | tail -20` succeeds at collection
   (collection may still emit errors but the explicit-import-from-linear
   class is gone). Test execution failures are fine here — they are Task 03.
5. Single focused commit, e.g. `Delete linear/ package and test/linear/`.

## Criteria to Consult

Run `uv run python scripts/catalog_criteria.py`. Pure deletion is a tame
diff but the following still apply:

- `do-not-assume-backwards-compatibility` — Always.
- `system-code-locality` — Always; verify no Linear-shaped code is hiding
  under a non-Linear path.
- `test-validity-preserved` — if any test outside `test/linear/` was
  importing Linear setup helpers, those tests must either be updated to
  not need them or escalated.

## Notes for the Implementing Agent

- This is a one-shot destructive operation. Use `git rm -r` rather than
  `rm -rf` so the deletion is staged and visible in the commit.
- If `grep` finds Linear references in `test/conftest.py` or similar shared
  fixtures, prefer surgical trimming over wholesale deletion. Document any
  shared fixture that no longer has any consumer after the trim — it can
  be deleted in Task 03 if confirmed dead.
- The `.mypy_cache/` and `__pycache__/` directories will contain stale
  Linear references. Those are not in git so they are not your concern;
  they will be regenerated on the next type-check / test run.
