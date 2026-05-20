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
   - Notes that `local_planning` requires an active plan for outbound
     collaboration (the `require_active_workspace_context` flag).
   - Provides one minimal example team config that uses it.

2. Update `CODEBASE.md` to mention the new package.

3. Don't rewrite historical / completed plan docs.

## Acceptance

- A reader landing on `docs/workspaces.md` (or the new section) can
  understand what `local_planning` is and how to use it from a team
  config without reading any code.
- `CODEBASE.md` reflects the new directory.

## Tests

- No automated test required. Confirm rendered Markdown looks right.

## Out of scope

- Long-form tutorials, migration guides, or dashboard docs (deferred to
  a future plan that ships the dashboard surface for plans).
