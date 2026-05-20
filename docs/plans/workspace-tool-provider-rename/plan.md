# Workspace Tool Provider Rename

Status: Draft

## Goal

Rename the active “workspace provider” concept to “workspace tool provider” so the code matches the current model: these integrations do not provide a workspace; they provide tools, identity/addressability metadata, and provider-backed behavior for a workspace/team.

This is a semantic cleanup with API/config consequences. The old runtime concept should not remain as a parallel compatibility layer.

## Target Terminology

- `workspace tool provider`: canonical name for integrations such as Linear that register provider-backed tools and metadata.
- `WorkspaceToolProvider*`: canonical Python type prefix.
- `workspace_tool_providers`: canonical Python package/module path.
- `/workspace-tool-providers/...`: canonical dashboard/API route prefix.
- `workspace-tool-providers.toml`: canonical global enablement/config file.

The generic word `provider` remains valid where it already means “provider-backed conversation”, “provider-mediated invocation”, or generic tool provider plumbing. Do not rename generic `provider_*` database tables or conversation storage solely because they contain the word `provider`.

## Current Inventory

Production code currently uses the old name in these active areas:

- Python package: `src/cli_agent_orchestrator/workspace_providers/`
- Linear implementation: `src/cli_agent_orchestrator/linear/workspace_provider.py`
- Registry/config helpers:
  - `WORKSPACE_PROVIDERS_CONFIG_PATH`
  - `default_workspace_provider_registry`
  - `load_enabled_workspace_providers`
  - `initialize_enabled_workspace_providers`
  - `workspace_provider_config_exists`
  - `is_workspace_provider_enabled`
- Linear global accessors:
  - `get_linear_workspace_provider`
  - `set_default_linear_workspace_provider`
- Workspace manager names:
  - `WorkspaceProviderCandidateMapping`
  - `WorkspaceProviderView`
  - `WorkspaceProviderEventResolution`
- Event types in `workspace_providers/events.py`, including `WorkspaceProviderEvent*`.
- Dashboard API route:
  - `GET /workspace-providers/{provider}/role-access-schema`
- Web helper/proxy names:
  - `getWorkspaceProviderRoleAccessSchema`
  - Vite proxy for `/workspace-providers`
- Tests under `test/workspace_providers/` and `test/linear/test_workspace_provider.py`.
- Non-historical docs such as `docs/tool-restrictions.md`.

Database inventory did not find any `workspace_provider_*` SQLite table or column. Existing persisted tables are generic `provider_*` / provider-conversation tables, so no SQLite migration is expected unless implementation research discovers a hidden persisted old-name surface.

## Non-Goals

- Do not change the team/workspace model.
- Do not change ToolService authority or tool access behavior.
- Do not add provider-specific UI features.
- Do not preserve old Python import paths, aliases, or old API routes as normal runtime compatibility.
- Do not rewrite historical completed plan documents just to remove old terminology. Historical docs may remain unless they are used as current acceptance/implementation guidance.

## Migration Decision

The canonical global config file becomes `$CAO_HOME/workspace-tool-providers.toml`.

Implement one explicit transition for the old default file name:

- If the default old file `$CAO_HOME/workspace-providers.toml` exists and the new default file does not exist, migrate it to `$CAO_HOME/workspace-tool-providers.toml` and use the new path thereafter.
- If both old and new default files exist, fail with a clear configuration error explaining the ambiguity and asking the user to keep only `workspace-tool-providers.toml`.
- If a caller passes an explicit config path, use that path exactly and do not auto-migrate it.

This transition is allowed because it moves user configuration to the new canonical name. It must not become long-term dual-read behavior.

## Implementation Tasks

### 1. Rename Python Modules And Types

Rename active modules, imports, classes, helper functions, and tests from workspace provider to workspace tool provider.

Expected changes include:

- `src/cli_agent_orchestrator/workspace_providers/` -> `src/cli_agent_orchestrator/workspace_tool_providers/`
- `src/cli_agent_orchestrator/linear/workspace_provider.py` -> `src/cli_agent_orchestrator/linear/workspace_tool_provider.py`
- `test/workspace_providers/` -> `test/workspace_tool_providers/`
- `test/linear/test_workspace_provider.py` -> `test/linear/test_workspace_tool_provider.py`
- Rename `WorkspaceProvider*` and `LinearWorkspaceProvider*` active code symbols to `WorkspaceToolProvider*` and `LinearWorkspaceToolProvider*`.
- Rename workspace manager view/mapping/event-resolution types that describe provider-supplied tool/addressability information.

Do not add import shims for the old module names.

### 2. Rename Config Surface

Replace the canonical config file constant with `WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH`.

Implement and test the one-time default-file migration behavior described in “Migration Decision”.

Update docs and tests that mention the global config file so current guidance points to `workspace-tool-providers.toml`.

### 3. Rename API And Web Surfaces

Replace the dashboard/API route:

- Old: `/workspace-providers/{provider}/role-access-schema`
- New: `/workspace-tool-providers/{provider}/role-access-schema`

Update API function names, frontend API helpers, Vite proxy config, component usage, mocks, and tests.

The old route must not remain registered. A request to `/workspace-providers/...` should behave like an unknown route.

### 4. Regenerate Or Update Generated Surfaces

If event payload schemas/docstrings are renamed, regenerate affected generated frontend types rather than hand-editing generated files when a generator exists.

At minimum, check `web/src/generated/caoEventPayloadTypes.ts` for stale active comments after the rename.

### 5. Update Current Documentation

Update current, non-historical docs and plan references that developers or agents would use as live guidance.

Historical completed plans may keep the old term, but the completion report must list any intentionally remaining old-term matches and why they are historical or migration-only.

## Definition Of Done

This section is the single authoritative acceptance source for this plan.

1. Active production terminology uses “workspace tool provider” consistently for the Linear provider and the provider registry/API concept.
2. Old active Python module paths and class/function names using `workspace_provider` / `WorkspaceProvider` are removed, not kept as shims.
3. The canonical config file is `workspace-tool-providers.toml`, with the explicit one-time default-file migration behavior implemented and tested.
4. The canonical API route is `/workspace-tool-providers/{provider}/role-access-schema`; the old `/workspace-providers/...` route is not registered.
5. Dashboard Teams role editing still loads provider-backed role access schema through the renamed route and does not depend on old frontend helper/proxy names.
6. No SQLite/database migration is added unless implementation research finds a persisted old-name schema surface. The completion report must document the database inventory and conclusion.
7. Generated frontend types or event payload artifacts are regenerated or updated through the project’s established process if source docstrings/schemas changed.
8. Current documentation points agents/developers to the new terminology and config file name. Any remaining old-term search hits are either migration tests/messages or historical docs and are listed in the completion report.
9. Applicable criteria from `docs/criteria` are reviewed and treated as implicit acceptance criteria, especially:
   - `docs/criteria/implementation/do-not-assume-backwards-compatibility.md`
   - `docs/criteria/implementation/migration-discipline.md`
   - `docs/criteria/implementation/authoritative-sources-are-referenced-not-copied.md`

## Required Verification

The implementer must record exact commands and outcomes in a completion report.

Required static checks:

- Search active surfaces for old names:
  - `rg -n "workspace[_-]providers?|workspace providers?|WorkspaceProvider|workspace_provider" src test web/src web/vite.config.ts docs -S`
- Classify every remaining hit as one of:
  - historical completed plan/doc
  - explicit migration handling for `workspace-providers.toml`
  - unacceptable active legacy hit that must be fixed

Required backend checks:

- Run the renamed workspace tool provider tests.
- Run Linear provider tests.
- Run API route tests covering the renamed route and absence of the old route.
- Run workspace manager tests.
- Run ToolService/provider-mediated registration and invocation tests touched by the rename.

Required frontend checks:

- Run frontend API/component tests touched by the helper rename.
- Run TypeScript/build verification.
- Verify the Teams role editor in a browser against the running dashboard:
  - Open Teams tab.
  - Open a role editor.
  - Confirm provider-backed tools load successfully.
  - Use tool search/filter and toggle at least one tool in the role editor.
  - Confirm the browser path/API behavior uses `/workspace-tool-providers/...` and no UI flow depends on `/workspace-providers/...`.

## Review Gate

After implementation, run review loops before declaring the plan complete.

Each reviewer must compare the landed implementation strictly against the Definition Of Done and Required Verification. They must also browse `docs/criteria` and apply relevant criteria as implicit acceptance criteria.

For each valid reviewer finding:

- Fix the implementation.
- Add a subsection to the completion report containing the finding, why it was valid, and how it was fixed.
- Restart the review loop with a fresh reviewer.

Success requires two consecutive fresh review passes with zero valid findings.

