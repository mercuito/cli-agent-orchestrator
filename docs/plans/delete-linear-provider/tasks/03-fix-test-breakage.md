# Task 03 — Run the Test Suite and Fix Breakage Outside `linear/`

## Goal

Get the Python test suite back to a clean pass on the branch after Linear has
been fully removed (Tasks 01 and 02). The branch should import cleanly and
all non-Linear behavior should still work, even though the inbox is still
carrying its source-agnostic shape from before Task 04.

## Preconditions

- Task 02 complete: `linear/` package and `test/linear/` are deleted.
- The branch imports cleanly:
  `uv run python -c "import cli_agent_orchestrator.api.main"` succeeds.

## Scope

1. Run the full suite:

   ```bash
   uv run pytest -x -q
   ```

   `-x` stops at the first failure so you can fix incrementally. Drop `-x`
   once you suspect the tail is independent.

2. Categorize failures and fix:

   - **Import errors** in non-Linear test files: a test imported
     `LinearConfig`, `linear_router`, `provider_conversation_decision`, or
     similar. Update the test to the new contract or delete the test if it
     was exercising Linear-only behavior.
   - **`AttributeError: 'Agent' has no attribute 'linear'`**: a test asserts
     against `agent.linear` directly. Remove the assertion or rewrite the
     test against the new shape.
   - **Workspace bootstrap errors** (`Unknown workspace: cao_default` or
     similar): the bootstrap team in
     `default_workspace_team_store` references a workspace id that the
     empty `default_workspace_registry()` does not register. Either:
     a) Register a placeholder `cao_default` workspace with no providers
        in `default_workspace_registry()`, or
     b) Remove the bootstrap team from `default_workspace_team_store()`
        and let tests construct teams explicitly.

     Recommend (a) for least test churn; document the placeholder in the
     function docstring.
   - **API contract tests** that assert on `agent.linear` field shape: drop
     the assertions.
   - **MCP tool registry tests** that expected `reply_to_inbox_message` to
     exist: update them. The tool is gone permanently.
   - **Inbox tests** that exercised provider source kinds or replyability:
     these tests are not yet rewritten; Task 04 will refactor the inbox.
     For Task 03, leave the inbox API as-is and update tests minimally to
     keep them passing — the `source_kind="plain"` path still works.

3. After each fix, re-run the targeted file:

   ```bash
   uv run pytest test/path/to/test_file.py -x -q
   ```

   Then continue to the next failure.

4. When the full suite passes, commit. A reasonable commit message:
   `Update tests for post-Linear contracts`.

## Out of Scope

- Do not preemptively refactor inbox tests for the agent-to-agent collapse —
  that's Task 04.
- Do not write a SQLite migration — that's Task 05.
- Do not edit the web UI tests — those are exercised in Task 06.

## Acceptance Criteria

1. `uv run pytest -q` exits 0.
2. No test file is silenced with `@pytest.mark.skip` or its assertions
   weakened to truthiness checks. Tests that no longer make sense after
   the deletion are deleted, not skipped.
3. `git status` is clean; all changes are committed.

## Criteria to Consult

- `test-validity-preserved` — Always. Read this one carefully; the
  temptation under time pressure is to weaken assertions instead of
  understanding the new shape.
- `target-behavior-must-not-be-mocked` — Always.
- `test-through-owner-surfaces` — Always.
- `all-system-interactions-are-verified-by-tests` — Always.
- Implementation criteria as applicable to any source edits made while
  unblocking tests.

## Notes for the Implementing Agent

- If a test exercises behavior that was *exclusively* about Linear (e.g., a
  test of how an agent's `agent.linear.tool_access` decision shaped allowed
  tools), delete the test. Do not contort it into a generic-shape test.
- If a test exercises a generic concept that *happened* to use Linear in
  its setup (e.g., a workspace-team test that registered a Linear member),
  rewrite the setup to use no provider. The test still earns its keep.
- Sometimes the right answer is to update the *production* code, not the
  test. For example, if a test asserts that `default_workspace_registry()`
  contains a registered workspace and that's now false, ask whether the
  bootstrap workspace should be added back (with no providers) or whether
  the test is asserting an outdated invariant. The plan.md says the default
  registry is empty; lean that direction unless many tests push back.
