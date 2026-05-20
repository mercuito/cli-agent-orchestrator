# Workspace Model

Status: Draft

## Goal

Establish **Workspace** as a first-class CAO model and retire the old
“workspace setup” terminology from active code, API, persistence, frontend, and
current docs.

The current `WorkspaceSetup` type already represents the concept we want: a
named workflow environment composed of workspace tool providers plus exactly one
workspace context resolver. It should be called `Workspace`.

This plan is intentionally a model/terminology refactor. It prepares the codebase
for adding new workspaces later without agents or implementers confusing
workspace tool providers with workspaces.

## Conceptual Model

- **Workspace Tool Provider**: an integration such as Linear that registers
  provider-backed tools, provider identity/addressability, and provider-specific
  behavior.
- **Workspace**: a CAO-owned workflow contract. It declares which workspace tool
  providers participate and owns exactly one context resolver.
- **Workspace Context**: the active resolved runtime focus inside a workspace,
  represented by `WorkspaceContextResolution`.
- **Team**: a group of agents that uses one workspace.
- **Role**: a team-local tool access policy for agents in that team.

A CAO workspace is not the external provider’s workspace. For example, a CAO
workspace can use Linear, but it is not “the Linear workspace”; it is CAO’s
workflow model over Linear-backed tools and context resolution.

## Target Terminology

Canonical active names:

- `Workspace`
- `WorkspaceRegistry`
- `WorkspaceConfigError`
- `WorkspaceDiagnostic`
- `WorkspaceContextResolver`
- `WorkspaceToolProviderAdapter`
- `default_workspace_registry`
- `workspace_for_team`
- `workspace_for_agent`
- `/workspaces`
- `/workspaces/diagnostics`
- `WorkspaceTeam.workspace`

Names that should remain:

- `WorkspaceContextResolution`: this already names the resolved runtime context,
  not the workspace definition.
- `workspace_context_*` database and code surfaces: these are about resolved
  context state and should not be renamed by this plan.
- `WorkspaceToolProvider*`: this was just clarified and remains the provider
  integration/tool side.

## Current Inventory

Active code still uses `WorkspaceSetup` and `workspace_setup` in these areas:

- Package: `src/cli_agent_orchestrator/workspace_setups/`
- Linear adapter: `src/cli_agent_orchestrator/linear/workspace_setup_adapter.py`
- Main model types:
  - `WorkspaceSetup`
  - `WorkspaceSetupResolver`
  - `WorkspaceSetupRegistry`
  - `WorkspaceSetupConfigError`
  - `WorkspaceSetupDiagnostic`
  - `WorkspaceSetupProviderAdapter`
- Default constants/functions:
  - `DEFAULT_WORKSPACE_SETUP_ID`
  - `default_workspace_setup_registry`
  - `setup_for_team`
  - `setup_for_agent`
- Team persistence and API field:
  - `WorkspaceTeam.workspace_setup`
  - `workspace_setup` in `workspace-teams.json`
  - `WorkspaceTeamResponse.workspace_setup`
  - create/update request field `workspace_setup`
- Agent/API status field:
  - `derived_workspace_setup_id`
- Routes:
  - `GET /workspace-setups`
  - `GET /workspace-setups/diagnostics`
- Frontend:
  - `WorkspaceSetup` TypeScript types
  - `listWorkspaceSetups`
  - UI labels reading “Workspace setup”
  - Vite proxy for `/workspace-setups`
- Tests under `test/workspace_setups/` and many callers in service/API/frontend
  tests.

The default setup id is currently `linear_delivery_setup`. This should become a
workspace id, not a setup id.

## Target Shape

### Package And Type Names

Rename the active subsystem:

- `src/cli_agent_orchestrator/workspace_setups/` -> `src/cli_agent_orchestrator/workspaces/`
- `test/workspace_setups/` -> `test/workspaces/`
- `src/cli_agent_orchestrator/linear/workspace_setup_adapter.py` ->
  `src/cli_agent_orchestrator/linear/workspace_adapter.py`

Rename active types/functions:

- `WorkspaceSetup` -> `Workspace`
- `WorkspaceSetupResolver` -> `WorkspaceContextResolver`
- `WorkspaceSetupRegistry` -> `WorkspaceRegistry`
- `WorkspaceSetupConfigError` -> `WorkspaceConfigError`
- `WorkspaceSetupDiagnostic` -> `WorkspaceDiagnostic`
- `WorkspaceSetupProviderAdapter` -> `WorkspaceToolProviderAdapter`
- `LinearWorkspaceSetupAdapter` -> `LinearWorkspaceAdapter`
- `DEFAULT_WORKSPACE_SETUP_ID` -> `DEFAULT_WORKSPACE_ID`
- `default_workspace_setup_registry` -> `default_workspace_registry`
- `setup_for_team` -> `workspace_for_team`
- `setup_for_agent` -> `workspace_for_agent`

Do not keep old Python import shims or aliases for the old names.

### Default Workspace

Rename the default code-owned workspace:

- old id: `linear_delivery_setup`
- new id: `linear_delivery`
- old display name: `Linear Delivery Setup`
- new display name: `Linear Delivery`

The old id should be accepted only by the persisted team-store migration path,
then rewritten to the new id.

### Team Model

Rename the team field:

- `WorkspaceTeam.workspace_setup` -> `WorkspaceTeam.workspace`

The meaning stays the same: every team references exactly one workspace.

### API And Frontend

Replace active API routes and schemas:

- old: `GET /workspace-setups`
- new: `GET /workspaces`
- old: `GET /workspace-setups/diagnostics`
- new: `GET /workspaces/diagnostics`
- old response/request fields: `workspace_setup`
- new response/request fields: `workspace`
- old status field: `derived_workspace_setup_id`
- new status field: `derived_workspace_id`

Update frontend helpers, component props, labels, tests, Vite proxy config, and
browser flows to use “Workspace” consistently.

The old API routes and fields should not remain registered as normal runtime
compatibility. Tests should assert the old routes are gone.

## Persistence Migration

The existing `workspace-teams.json` file remains the persisted team store. Its
canonical team field changes from `workspace_setup` to `workspace`.

Implement explicit migration behavior:

- If a team entry has `workspace` only, use it.
- If a team entry has legacy `workspace_setup` only, read it as legacy input,
  map known legacy workspace ids, and rewrite the store using canonical
  `workspace` on the next write/migration pass.
- If a team entry has both fields with different values, fail with a clear
  `WorkspaceConfigError`.
- If both fields are present with the same value, treat it as migration input and
  rewrite only `workspace`.

Legacy id mapping:

- `linear_delivery_setup` -> `linear_delivery`

This migration is a data migration, not long-term dual-write support. New writes
must contain only `workspace`.

No SQLite migration is expected because current persisted workspace setup state
lives in `workspace-teams.json`; `workspace_context_*` SQLite tables model
runtime context and are out of scope.

## Non-Goals

- Do not add a new workspace definition yet. This plan only makes the model ready
  for that follow-up.
- Do not change ToolService authority or role permission semantics.
- Do not change team membership rules.
- Do not rename `WorkspaceContextResolution` or `workspace_context_*` runtime
  context storage.
- Do not preserve old runtime import paths, API routes, or TypeScript helper
  names as compatibility aliases.
- Do not rewrite historical completed plans only to remove old terminology.

## Implementation Tasks

### 1. Rename Backend Workspace Model

Move the package and rename Python symbols to the target names.

Update all production imports and public owner surfaces. Keep definitions
localized in the new `workspaces` package, and make other subsystems consume the
new public package API instead of reaching into renamed internals.

### 2. Migrate Team Persistence

Update `WorkspaceTeamStore` to read legacy `workspace_setup`, migrate it to
`workspace`, map the default legacy id to the new workspace id, and write only
canonical payloads.

Add tests for:

- canonical `workspace` round trip;
- legacy `workspace_setup` migration;
- old default id migration to `linear_delivery`;
- conflict when both fields disagree;
- no `workspace_setup` key in newly written JSON.

### 3. Rename API, CLI, And Service Surfaces

Update API models, endpoints, agent status fields, service methods, CLI output,
diagnostics, and error codes/messages.

Old routes must return 404. Old request fields must not be accepted by new
write endpoints.

### 4. Rename Frontend Surfaces

Update TypeScript API types/helpers, Vite proxy, Teams tab, Agents tab metadata,
tests, and UI copy.

The Teams tab should present “Workspace”, not “Workspace setup”. Agent details
should show the derived workspace id/name using the new field.

### 5. Update Tests And Current Docs

Rename test files/directories and update assertions.

Update current docs and draft plans that actively guide new work. Historical
completion reports and completed plans may keep old terminology if they are
clearly archival.

## Definition Of Done

This section is the single authoritative acceptance source for this plan.

1. `Workspace` is the active code-level model for the provider/resolver workflow
   contract formerly called `WorkspaceSetup`.
2. Active Python package paths, class names, function names, constants, and error
   types no longer expose `workspace_setup` / `WorkspaceSetup` terminology.
3. Teams reference one `workspace`, not one `workspace_setup`, across Python
   models, API schemas, frontend types, and persisted JSON.
4. The default workspace is canonically `linear_delivery` with display name
   `Linear Delivery`.
5. `workspace-teams.json` migration handles legacy `workspace_setup` data and
   rewrites canonical JSON with only `workspace`.
6. The canonical API routes are `/workspaces` and `/workspaces/diagnostics`; old
   `/workspace-setups` routes are not registered.
7. Dashboard Teams and Agents UI use “Workspace” terminology and operate against
   the renamed API fields/routes.
8. No SQLite migration is added unless implementation research finds persisted
   `workspace_setup` schema state. The completion report documents the database
   inventory and conclusion.
9. No old import shims, API aliases, frontend helper aliases, or dual-write
   compatibility paths remain, except the explicit persisted JSON migration.
10. Applicable criteria from `docs/criteria` are reviewed and treated as
    implicit acceptance criteria. After implementation, evaluate the pending
    changes against the criteria catalog. No criteria applicable to the completed
    diff may be violated.

## Required Verification

The implementer must record exact commands and outcomes in a completion report.

Required static checks:

- Search active surfaces for old setup terminology:
  - `rg -n "workspace_setup|WorkspaceSetup|workspace setup|workspace-setups|derived_workspace_setup|DEFAULT_WORKSPACE_SETUP|WorkspaceSetupResolver|WorkspaceSetupRegistry|WorkspaceSetupDiagnostic|setup_for_team|setup_for_agent" src test web/src web/vite.config.ts docs -S`
- Classify every remaining hit as:
  - explicit persisted JSON migration handling;
  - old-route/old-field rejection tests;
  - historical completed docs;
  - unacceptable active legacy hit that must be fixed.

Required backend checks:

- Workspace model/store tests under the renamed `test/workspaces/`.
- API route and schema tests for `/workspaces`, `/workspaces/diagnostics`, old
  route 404 behavior, and old request-field rejection.
- Team CRUD tests covering `workspace`.
- ToolService, collaboration policy, baton, inbox, Linear monitor/runtime, and
  provider-mediated tests touched by the rename.
- Import checks proving old Python paths are removed.

Required frontend checks:

- API/component tests for Teams and Agents tab metadata.
- TypeScript/build verification.
- Backend-served browser verification:
  - open Teams tab;
  - verify the workspace selector is labeled “Workspace”;
  - create or edit a team using the new `workspace` field;
  - reload and confirm persistence;
  - open a teamed agent and confirm derived workspace metadata renders;
  - confirm server logs/network requests use `/workspaces`, not
    `/workspace-setups`.

## Completion Report

Create `docs/plans/workspace-model/completion-report.md` with:

- summary of implementation;
- migration behavior and test evidence;
- database inventory and whether SQLite migration was required;
- static old-term audit table;
- backend/frontend/browser verification table;
- review findings and fixes.

## Review Gate

After implementation, run review loops before declaring the plan complete.

Each reviewer must compare the landed implementation strictly against the
Definition Of Done and Required Verification. They must also browse
`docs/criteria` and apply relevant criteria as implicit acceptance criteria.

For each valid reviewer finding:

- fix the implementation;
- add a subsection to the completion report containing the finding, why it was
  valid, and how it was fixed;
- restart the review loop with a fresh reviewer.

Success requires two consecutive fresh review passes with zero valid findings.

