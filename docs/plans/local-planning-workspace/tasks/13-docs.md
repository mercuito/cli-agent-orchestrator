# Task 13: Update current docs

Part of: [../plan.md](../plan.md) — Implementation Tasks → Update current
docs.

## Goal

Surface the new `local_planning` workspace in the parts of `docs/` that
guide active work. Existing plans and completed-plan completion reports
stay as archival history; they don't need rewriting.

## Dependencies

Tasks 01–12 ideally complete (so the doc reflects shipped behavior, not
projected behavior).

## Files Touched

- `docs/workspaces.md` (new) OR section added to `docs/agents.md` — pick
  the path that fits the existing docs layout best.
- `CODEBASE.md` — extend the directory tree to include `local_planning/`
  under `src/cli_agent_orchestrator/`.
- (Optionally) `CHANGELOG.md` entry under the next release.

## What to do

1. Write a short workspaces section that:
   - Defines the workspace concept (`Workspace` model + workspace tool
     provider) at a glance.
   - Lists the two workspaces CAO ships: `linear_delivery` and
     `local_planning`.
   - For `local_planning`, explains the plan lifecycle (create →
     activate → complete), where plan files live
     (`<agent.workdir>/docs/plans/<slug>/plan.md`), and the
     deferred-on-idle context-switch semantic.
   - States that all members of a `local_planning` team must share the same
     normalized `workdir`; plan identity is scoped to that shared local
     file tree with an internal `boundary_object_id=<workdir_scope>:<slug>`
     while the user-facing plan id remains `<slug>`.
   - Notes that `local_planning` requires an active plan for outbound
     collaboration (the `require_active_workspace_context` flag).
   - Provides one minimal example team config plus the matching agent-side
     `workspace.team` membership configuration that uses it.

2. Update `CODEBASE.md` to mention the new package.

3. Don't rewrite historical / completed plan docs.

## Out of scope

- Long-form tutorials, migration guides, or dashboard docs (deferred to
  a future plan that ships the dashboard surface for plans).

## Definition of Done

1. A reader landing on `docs/workspaces.md` (or the chosen alternative
   section) can understand what `local_planning` is and how to use it
   from a team config without reading any code.
2. The doc lists the two shipped workspaces (`linear_delivery`,
   `local_planning`), explains the plan lifecycle
   (create → activate → complete), states where plan files live
   (`<agent.workdir>/docs/plans/<slug>/plan.md`), and describes the
   deferred-on-idle context-switch semantic.
3. The doc notes the `require_active_workspace_context` flag on
   `local_planning` and gives one minimal example team config that uses
   the workspace, including the shared-workdir invariant and agent-side
   team membership configuration. It also explains that the internal
   workspace-context boundary includes the workdir scope, while users refer
   to plans by slug inside that shared workdir.
4. `CODEBASE.md` directory tree includes
   `src/cli_agent_orchestrator/local_planning/`.
5. Rendered Markdown reviewed — links resolve, headings sensible, no
   broken references.

## Review Gate

After implementing this task, run a review loop. The reviewer compares
the landed implementation against each item in Definition of Done above
plus all applicable entries in the `docs/criteria` catalog (run
`uv run python scripts/catalog_criteria.py` and load any criterion whose
`when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the
review loop restarts with a fresh reviewer. For every review finding
that requires an implementation change, the implementer updates
[../completion-report.md](../completion-report.md) under this task's
heading, recording what the reviewer found, why it was accepted as
valid, how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero
valid findings for this task, and those two clean review passes are
recorded in the completion report.
