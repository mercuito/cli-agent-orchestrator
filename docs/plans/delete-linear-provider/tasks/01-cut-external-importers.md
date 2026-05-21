# Task 01 — Cut External Importers of `cli_agent_orchestrator.linear.*`

## Goal

Make every module outside `src/cli_agent_orchestrator/linear/` stop importing
from the `linear` package, so Task 02 can delete the package without breaking
the import graph. Also delete every method, dataclass, route, response model,
and migration step that exists *solely* to support Linear or
`provider_conversation_*` concerns.

## Preconditions

- Branch `delete-linear-provider` is checked out.
- Five files are already edited and Linear-free (see "Already Done" below).
- Tests will not pass yet; that is normal until Task 02 + Task 03.

## Status

In progress. ~55% complete. The branch has uncommitted partial work that
should be retained — do not revert.

## Already Done (do not redo)

These files are committed-or-uncommitted on the branch already and are
syntactically valid:

- `src/cli_agent_orchestrator/workspace_tool_providers/events.py` — docstring
  rewritten to remove the "Linear is the real owner" framing.
- `src/cli_agent_orchestrator/workspace_tool_providers/registry.py` —
  `default_workspace_tool_provider_registry()` now returns an empty registry;
  the `if name == "linear":` branch in
  `initialize_enabled_workspace_tool_providers` is removed.
- `src/cli_agent_orchestrator/mcp_server/server.py` — three Linear imports
  removed; `_read_inbox_message_impl` no longer source-kind dispatches;
  `_provider_read_result_to_dict`, `_reply_to_inbox_message_impl`, and the
  `reply_to_inbox_message` MCP tool are deleted; `_inbox_read_result_to_dict`
  is simplified.
- `src/cli_agent_orchestrator/agent.py` — `LinearConfig`,
  `LinearToolAccessConfig`, the `linear` field on `Agent`, `_linear_config`,
  `_linear_tool_access_errors`, `_validate_linear_uniqueness`, and
  `_linear_to_toml_mapping` are all removed; validation and TOML
  serialization paths no longer reference Linear.
- `src/cli_agent_orchestrator/api/main.py` — Linear request/response models
  (`LinearToolAccessResponse`, `LinearConfigResponse`,
  `LinearToolAccessWriteRequest`, `LinearWriteRequest`), the `linear` field
  on `AgentConfigResponse` and `AgentWriteRequest`,
  `app.include_router(linear_router)`, and the
  `/workspace-tool-providers/{provider}/role-access-schema` endpoint are
  deleted. Imports of `LinearConfig`, `LinearToolAccessConfig`, and
  `linear_router` are removed.

Verify with `grep -n "linear\|Linear" <path>` after pulling the branch — all
five should return no Python-level Linear references (the strings may appear
in unrelated tokens; eyeball for `LinearConfig`, `linear_router`,
`from cli_agent_orchestrator.linear`).

## What Remains

### 1. `src/cli_agent_orchestrator/services/tool_service.py`

Remove the `provider_conversation_*` infrastructure and the
`agent.linear` references. The file should still be ~1100 lines after; this
is surgical not wholesale.

Concrete deletions:

- Imports: drop `ProviderConversationAccessWorkspaceToolProvider` (registry
  imports block), `ProviderConversationAccessRequirement` (tool_access imports
  block), and `InboxDelivery` if it becomes unused after the decision-method
  removal.
- Module-level constants: drop `_PROVIDER_CONVERSATION_OPERATION_CAO_TOOLS`
  and the `ProviderConversationRequirementLoader` type alias.
- `AgentToolAccess`: drop the `provider_conversation_requirements` field.
- `ToolAccessSourceResult`: drop the `provider_conversation_requirements`
  field.
- Every constructor / `.replace(...)` site that populated those fields with
  `()`: remove the keyword argument.
- `StandaloneAgentToolAccessSource.resolve`: remove the
  `provider_conversation_requirements=()` line.
- `TeamRoleToolAccessSource.__init__`: remove the
  `provider_conversation_requirements` parameter and the `self._...` it
  assigns to. Remove any reference inside its `resolve()`.
- `ToolService.__init__`: remove the
  `provider_conversation_requirement_loader` parameter, the
  `self._provider_conversation_requirement_loader` assignment, and the
  `self._provider_conversation_requirements_cache` field.
- `ToolService` methods to delete in full:
  - `provider_conversation_requirements_for_agent`
  - `provider_conversation_decision`
  - `provider_conversation_decision_for_inbox`
  - `_provider_conversation_requirements`
- Module-level functions to delete in full:
  - `_load_raw_enabled_provider_conversation_requirements`
  - `_role_provider_conversation_requirements`
  - `_provider_conversation_operation_tool`
- Inside the remaining resolve / source-result construction sites, remove
  any line that builds, passes, or threads
  `provider_conversation_requirements` through.
- `enabled = ("linear",)` hardcoded fallback (around line 1212) — delete the
  fallback. If the path that used it disappears entirely, fine. If a different
  default is needed, return an empty tuple (no enabled providers).
- `agent.linear.tool_access` reference (around line 1321) and the
  `inactive["linear.tool_access"] = ...` line — delete.
- `_cache_token(agent.linear)` reference (around line 1382) — delete that
  element from the cache token tuple.
- `_cache_token(source_result.provider_conversation_requirements)` (around
  line 1395) — delete.
- Public `__all__` and any export lists referencing
  `ProviderConversationAccessRequirement` — clean up.

### 2. `src/cli_agent_orchestrator/workspaces/manager.py`

- Rename `DEFAULT_WORKSPACE_ID = "linear_delivery"` to
  `DEFAULT_WORKSPACE_ID = "cao_default"`. Update `LEGACY_WORKSPACE_IDS` to map
  `"linear_delivery"` and `"linear_delivery_setup"` to the new id, so any
  stored value in `workspace-teams.json` migrates on read.
- `default_workspace_registry()` (around line 1126): drop the Linear import
  and registration. Return `WorkspaceRegistry(())` — empty registry. The
  default workspace is gone; the user adds workspaces when `local` lands.
- `default_workspace_team_service()` (around line 1159): drop the
  `LinearWorkspaceAdapter` import and the `adapters = {"linear": ...}` line.
  Pass `available_providers=()` (empty tuple) to `WorkspaceTeamService`.
- `default_workspace_collaboration_manager()` (around line 1182): drop the
  `LinearWorkspaceAdapter` import; pass `provider_adapters={}` to
  `WorkspaceCollaborationManager`.
- Anywhere a `default_workspace_team_store` bootstraps a `WorkspaceTeam` with
  `workspace=DEFAULT_WORKSPACE_ID`: this is still valid because the constant
  is renamed but the workspace itself is no longer registered. Keep the
  bootstrap; the team simply references a workspace id that does not have a
  registered handler yet. If tests fail with "Unknown workspace" errors, the
  bootstrap needs to be conditional on the workspace being registered —
  cross that bridge in Task 03.

### 3. `src/cli_agent_orchestrator/clients/database.py`

- Drop `_migrate_ensure_linear_monitor_tables` and
  `_migrate_ensure_provider_conversation_tables` from the imports at the
  top of the file (around lines 40–41).
- Drop the `from cli_agent_orchestrator.clients.provider_conversation_store
  import ...` block (around line 74).
- Drop the `from cli_agent_orchestrator.linear.conversation_store import ...`
  block exporting `ProviderConversationMessageModel` and
  `ProviderConversationThreadModel` (around lines 78–82).
- Drop `from cli_agent_orchestrator.linear.monitor_store import
  LinearMonitorWatermarkModel` (around line 113).
- Drop the corresponding entries from `__all__`:
  `"LinearMonitorWatermarkModel"`, `"ProviderConversationMessageModel"`,
  `"ProviderConversationThreadModel"`, and the
  `"_migrate_ensure_linear_monitor_tables"`,
  `"_migrate_ensure_provider_conversation_tables"` re-exports.

### 4. `src/cli_agent_orchestrator/clients/database_migrations.py`

- Drop the `from cli_agent_orchestrator.clients.provider_conversation_store
  import ...` block (around line 21).
- Drop the `from cli_agent_orchestrator.linear.conversation_store import ...`
  block (around line 24).
- Drop `from cli_agent_orchestrator.linear.monitor_store import
  LinearMonitorWatermarkModel` (around line 35).
- Drop the two `_migrate_ensure_provider_conversation_tables()` calls (around
  lines 52 and 58) and the two
  `_migrate_ensure_linear_monitor_tables()` calls (around lines 54 and 60)
  from the migration runner.
- Delete the `_migrate_ensure_provider_conversation_tables` function (around
  line 545) and the helper it calls,
  `_migrate_legacy_provider_conversation_table_names` (around line 567).
- Delete the `_migrate_ensure_linear_monitor_tables` function (around line
  761).
- Delete the `from cli_agent_orchestrator.linear.workspace_events import
  LINEAR_CAO_EVENTS` lazy import (around line 536) and any code that
  registers Linear events on the dispatcher in this file.
- Older migrations in this file that mention
  `"provider_conversation_inbox_notifications"` (lines 107, 110, 121, 242,
  319) reference a transitional marker table that no longer needs to be
  computed. Leave those branches in place — Task 05 will write the
  authoritative migration that drops the provider_conversation_* tables and
  inbox columns; this task only removes the Linear/provider creation paths.

  **Important**: do not delete the entire migrations file logic. Other
  migrations in it manage the `inbox_notifications` and `terminals` tables
  and must keep working.

## Scope Discipline

- Stay within the file list above. Do not refactor unrelated code in any of
  these files.
- Do not yet edit `inbox/*.py`. The inbox simplification is Task 04 and has
  its own contract.
- Do not yet delete `src/cli_agent_orchestrator/linear/` or `test/linear/`.
  That is Task 02.
- Do not yet write the SQLite migration. That is Task 05.
- Do not touch the web UI. That is Task 06.

## Acceptance Criteria

1. `grep -rn "from cli_agent_orchestrator.linear\|import cli_agent_orchestrator.linear" src/ test/` returns matches only inside `src/cli_agent_orchestrator/linear/` and `test/linear/`.
2. `grep -rn "provider_conversation_decision\|provider_conversation_requirements_for_agent\|ProviderConversationAccessRequirement" src/` returns no matches.
3. `grep -rn "agent\.linear" src/` returns no matches.
4. `python -c "import ast; ast.parse(open('<each touched file>').read())"` succeeds for every file in this task.
5. `uv run python -c "from cli_agent_orchestrator import agent, api.main, services.tool_service, workspaces, mcp_server.server"` still fails at runtime (because `linear/` is still present and other modules in `linear/` import from each other), but it must not fail because of missing `agent.linear` attribute, missing `LinearConfig`, missing `provider_conversation_decision`, or missing `linear_router`. Failure must be from inside `linear/` only.
6. A commit message on the branch records the partial work, e.g.
   `Cut external importers of linear.*`. Each touched file should appear in
   `git diff --stat`.

## Criteria to Consult

Run `uv run python scripts/catalog_criteria.py` and load the markdown for
criteria whose `when` clauses match the diff. Likely binders:

- `do-not-assume-backwards-compatibility` (Always)
- `minimal-cohesive-changes` (this is in pure refactor territory)
- `no-unnecessary-duplication`
- `prefer-public-surfaces`
- `system-code-locality`
- `system-definitions-are-localized`
- `readable-and-explicit`

After making changes, re-evaluate the diff against the catalog. Any criterion
applicable to the diff must not be violated. If a criterion blocks the
intended change, report and ask before deviating from this task contract.

## Notes for the Implementing Agent

- The `tool_service.py` edits are the highest-risk part because the file is
  large and the `provider_conversation_requirements` field is threaded through
  many constructor sites. Use `grep -n provider_conversation` in the file as
  your scaffold; every match must either be deleted or have its surrounding
  code restructured.
- `_cache_token` accepts a variable number of arguments by tuple aggregation.
  Removing one element from the tuple is safe as long as it is removed from
  every call site that constructs the same cache key, otherwise old and new
  keys will mismatch silently. Search for every `_cache_token(` call and
  audit.
- Do not commit a `tool_service.py` that still has a dangling
  `ProviderConversationAccessRequirement` import or unused parameter — a
  no-unused-import lint will flag it later anyway, and the criteria forbid
  leaving dead code behind.
