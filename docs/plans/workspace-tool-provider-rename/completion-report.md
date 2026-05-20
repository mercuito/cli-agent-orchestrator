# Workspace Tool Provider Rename Completion Report

Date: 2026-05-19

## Summary

Implemented the semantic rename from "workspace provider" to "workspace tool provider" across active Python code, API routes, frontend helpers, tests, generated frontend payload types, and current documentation.

The old active Python import paths were removed rather than shimmed:

- `cli_agent_orchestrator.workspace_providers`
- `cli_agent_orchestrator.linear.workspace_provider`

The canonical dashboard/API route is now:

- `/workspace-tool-providers/{provider}/role-access-schema`

The old `/workspace-providers/...` API route is not registered and is covered by an explicit 404 test.

The canonical default config file is now:

- `$CAO_HOME/workspace-tool-providers.toml`

The only retained old filename handling is the explicit one-time default migration from `$CAO_HOME/workspace-providers.toml`.

## Changed Paths

### Backend rename

- `src/cli_agent_orchestrator/workspace_tool_providers/`
- `src/cli_agent_orchestrator/linear/workspace_tool_provider.py`
- `src/cli_agent_orchestrator/api/main.py`
- `src/cli_agent_orchestrator/linear/agent_policies.py`
- `src/cli_agent_orchestrator/linear/app_client.py`
- `src/cli_agent_orchestrator/linear/monitor.py`
- `src/cli_agent_orchestrator/linear/provider_tools.py`
- `src/cli_agent_orchestrator/linear/routes.py`
- `src/cli_agent_orchestrator/linear/runtime.py`
- `src/cli_agent_orchestrator/linear/workspace_context_tool_results.py`
- `src/cli_agent_orchestrator/linear/workspace_events.py`
- `src/cli_agent_orchestrator/linear/workspace_setup_adapter.py`
- `src/cli_agent_orchestrator/mcp_server/freshness.py`
- `src/cli_agent_orchestrator/mcp_server/provider_tools.py`
- `src/cli_agent_orchestrator/mcp_server/server.py`
- `src/cli_agent_orchestrator/provider_conversations/inbox_authorization.py`
- `src/cli_agent_orchestrator/provider_conversations/models.py`
- `src/cli_agent_orchestrator/runtime/agent.py`
- `src/cli_agent_orchestrator/services/tool_service.py`
- `src/cli_agent_orchestrator/workspace_setups/__init__.py`
- `src/cli_agent_orchestrator/workspace_setups/manager.py`

### Removed old active backend paths

- `src/cli_agent_orchestrator/workspace_providers/`
- `src/cli_agent_orchestrator/linear/workspace_provider.py`

### Tests

- `test/workspace_tool_providers/`
- `test/linear/test_workspace_tool_provider.py`
- `test/api/test_agent_routes.py`
- `test/api/test_api_endpoints.py`
- `test/api/test_linear_app_routes.py`
- `test/api/test_terminals.py`
- `test/integration/test_agent_runtime_provider_state.py`
- `test/integration/test_provider_mediated_contract.py`
- `test/linear/test_monitor.py`
- `test/linear/test_provider_tools.py`
- `test/mcp_server/test_mcp_freshness.py`
- `test/mcp_server/test_provider_tool_registration.py`
- `test/services/test_linear_agent_runtime_service.py`
- `test/services/test_linear_app_service.py`
- `test/services/test_tool_service.py`
- `test/support/fake_provider_tools.py`
- `test/workspace_setups/test_workspace_setup_manager.py`

### Removed old active test paths

- `test/workspace_providers/`
- `test/linear/test_workspace_provider.py`

### Frontend and generated surfaces

- `web/src/api.ts`
- `web/src/components/WorkspaceTeamsPanel.tsx`
- `web/src/components/teams/teamUtils.ts`
- `web/src/generated/caoEventPayloadTypes.ts`
- `web/src/test/workspace-teams-panel.test.tsx`
- `web/vite.config.ts`

### Documentation

- `CHANGELOG.md`
- `docs/tool-restrictions.md`
- `docs/plans/agent-model-cleanup/handoff.md`
- `docs/plans/agent-model-cleanup/plan.md`
- `docs/plans/agent-model-cleanup/tasks.md`
- `docs/plans/effective-tool-access-consolidation/plan.md`
- `docs/plans/teams-tab-redesign/mockup.html`
- `docs/plans/teams-tab-redesign/plan.md`
- `docs/plans/workspace-team-model/hardening-log.md`
- `docs/plans/workspace-team-model/plan.md`
- `docs/plans/workspace-tool-provider-rename/completion-report.md`
- `docs/plans/workspace-tool-provider-rename/plan.md`

## Config Migration

`src/cli_agent_orchestrator/workspace_tool_providers/registry.py` now exposes `WORKSPACE_TOOL_PROVIDERS_CONFIG_PATH` as the canonical default path.

Default path behavior:

- If only `$CAO_HOME/workspace-providers.toml` exists, it is moved to `$CAO_HOME/workspace-tool-providers.toml`.
- If both old and new default files exist, registry loading fails with a clear `WorkspaceToolProviderConfigError`.
- If an explicit config path is passed, that path is used exactly and no migration is attempted.

Coverage was added for successful default migration, ambiguous default files, explicit old path behavior, and `workspace_tool_provider_config_exists()`.

## Database Inventory

No SQLite/database migration was added.

Inventory command:

```bash
rg -n "workspace_provider|workspace-providers|workspace provider|WorkspaceProvider|workspace_providers|workspace-provider" src/cli_agent_orchestrator/clients src/cli_agent_orchestrator -g '*migration*' -g '*.py' -S
```

Outcome:

- The only active hit was `src/cli_agent_orchestrator/workspace_tool_providers/registry.py`, for the explicit one-time default config filename migration.
- Existing persisted names remain generic `provider_*` / provider-conversation concepts and were not renamed because the plan explicitly excluded them.

Conclusion: no persisted `workspace_provider_*` table, column, or migration surface was found.

## Verification

### Static old-term audit

Required command:

```bash
rg -n "workspace[_-]providers?|workspace providers?|WorkspaceProvider|workspace_provider" src test web/src web/vite.config.ts docs -S
```

Outcome: no unacceptable active legacy hits.

Additional case-insensitive current-doc/code audit command:

```bash
rg -n -i "workspace[_-]providers?|workspace providers?|WorkspaceProvider|workspace_provider|workspace-provider" CHANGELOG.md README.md docs src test web/src web/vite.config.ts -S
```

Outcome: no unacceptable active legacy hits. This companion audit caught and verified removal of capitalized current-doc variants that the required case-sensitive audit does not match.

Classified remaining hits:

- Explicit migration handling/tests:
  - `src/cli_agent_orchestrator/workspace_tool_providers/registry.py`
  - `test/workspace_tool_providers/test_registry.py`
- Explicit old-route absence test:
  - `test/api/test_api_endpoints.py`
- Historical completed plan/documents:
  - `docs/plans/team-role-tool-access/*`
  - `docs/plans/effective-tool-access-consolidation/completion-notes.md`
  - `docs/plans/teams-tab-redesign/completion-report.md`
  - `docs/plans/tool-service-agent-tool-view/completion-report.md`
- Current plan source:
  - `docs/plans/workspace-tool-provider-rename/plan.md`
- This completion report, which records audit evidence and migration terminology.

### Backend checks

```bash
uv run pytest test/workspace_tool_providers -q
```

Outcome: 39 passed.

```bash
uv run pytest test/linear/test_workspace_tool_provider.py -q
```

Outcome: 21 passed.

```bash
uv run pytest test/api/test_api_endpoints.py -q -k 'WorkspaceToolProviderRoutes or lifespan'
```

Outcome: 4 passed, 44 deselected.

```bash
uv run pytest test/linear/test_provider_tools.py test/linear/test_monitor.py test/services/test_linear_agent_runtime_service.py test/api/test_linear_app_routes.py -q
```

Outcome: 150 passed.

```bash
uv run pytest test/workspace_setups/test_workspace_setup_manager.py test/linear/test_workspace_setup_adapter.py -q
```

Outcome: 24 passed.

```bash
uv run pytest test/services/test_tool_service.py test/mcp_server/test_provider_tool_registration.py test/mcp_server/test_mcp_freshness.py test/integration/test_provider_mediated_contract.py -q
```

Outcome: 57 passed.

```bash
uv run python - <<'PY'
import importlib

for name in (
    "cli_agent_orchestrator.workspace_providers",
    "cli_agent_orchestrator.linear.workspace_provider",
):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError:
        print(f"{name}: removed")
    else:
        raise SystemExit(f"{name}: still importable")
PY
```

Outcome:

```text
cli_agent_orchestrator.workspace_providers: removed
cli_agent_orchestrator.linear.workspace_provider: removed
```

### Frontend and generated checks

```bash
cd web && npm run generate:event-types
```

Outcome: succeeded; `web/src/generated/caoEventPayloadTypes.ts` was regenerated.

```bash
cd web && npm test -- src/test/workspace-teams-panel.test.tsx
```

Outcome: event type check and TypeScript check passed; 6 tests passed.

```bash
cd web && npm run build
```

Outcome: succeeded. Vite reported its existing large chunk warning.

### Browser verification

Server command:

```bash
tmp_home=$(mktemp -d /tmp/cao-verify-home.XXXXXX)
tmp_agents=$(mktemp -d /tmp/cao-verify-agents.XXXXXX)
HOME="$tmp_home" CAO_LOAD_ENV_FILE=0 uv run cao-server --agents-dir "$tmp_agents" --host 127.0.0.1 --port 9893
```

Browser flow:

- Opened `http://127.0.0.1:9893/?tab=teams`.
- Opened the Teams tab.
- Opened a role editor.
- Confirmed Linear provider-backed tools loaded successfully.
- Used tool search/filter with `get_issue`.
- Toggled `cao_linear.get_issue` in the role editor and confirmed the checkbox state changed.

API behavior observed in server logs:

```text
GET /workspace-tool-providers/linear/role-access-schema HTTP/1.1" 200 OK
```

No `/workspace-providers/...` request appeared in the Teams role editor UI flow.

## Criteria Review

Reviewed applicable criteria via:

```bash
uv run python scripts/catalog_criteria.py --format json
```

Applied criteria:

- `docs/criteria/implementation/do-not-assume-backwards-compatibility.md`
- `docs/criteria/implementation/migration-discipline.md`
- `docs/criteria/implementation/authoritative-sources-are-referenced-not-copied.md`
- `docs/criteria/tests/ui-changes-require-real-browser-verification.md`

Compliance notes:

- No old import shims or runtime route aliases were kept.
- The only compatibility behavior is the explicit config migration required by the plan.
- Database migration was not added because no persisted old-name schema surface was found.
- UI behavior was verified in a browser against the running dashboard.

## Review Gate

### Review loop 1

Reviewer findings:

- Valid: `src/cli_agent_orchestrator/workspace_tool_providers/events.py` still used `_DEFAULT_WORKSPACE_PROVIDER_EVENT_DISPATCHER` as an active production symbol. Fixed by renaming it to `_DEFAULT_WORKSPACE_TOOL_PROVIDER_EVENT_DISPATCHER`.
- Valid: this report listed `docs/criteria/implementation/ui-changes-require-real-browser-verification.md`, but the actual criterion path is `docs/criteria/tests/ui-changes-require-real-browser-verification.md`. Fixed this report path.

Because valid findings were fixed, the review gate was restarted with a fresh reviewer.

### Review loop 2

Reviewer finding:

- Valid: several draft/current plan documents still used old workspace-provider terminology and paths, while the report incorrectly classified them as historical/current plan documents. Fixed the active draft guidance in `docs/plans/teams-tab-redesign/`, `docs/plans/workspace-team-model/`, `docs/plans/effective-tool-access-consolidation/`, and `docs/plans/agent-model-cleanup/`, then narrowed the report classification to completed historical docs plus this plan/report evidence.

Because a valid finding was fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 3

Reviewer finding:

- Valid: `docs/plans/agent-model-cleanup/` was mechanically updated to a non-existent directory-style `workspace-tool-providers/linear.toml` path. Fixed those active docs to describe the actual model: Linear provider data lives in agent-local `agent.toml` sections, and the only external workspace tool provider config is the flat `workspace-tool-providers.toml` global enablement file.

Because a valid finding was fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 4

Reviewer finding:

- Valid: `CHANGELOG.md` `[Unreleased]` still referenced the old directory-style `workspace-providers/linear.toml` config path. Fixed the current changelog entry to describe the old provider-specific Linear config without pointing readers at a removed path.

Because a valid finding was fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 5

Reviewer finding:

- Valid: frontend verification commands in this report were recorded as bare `npm ...` commands even though the scripts live under `web/package.json`. Fixed the report to record reproducible repo-root commands using `cd web && ...`.

Because a valid finding was fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 6

Reviewer findings:

- Valid: the changed documentation path list omitted current docs and the changelog changes made during review. Fixed the report to list all changed current documentation paths.
- Valid: the old-term classification incorrectly grouped `docs/plans/workspace-tool-provider-rename/plan.md` under historical completed documents even though it is the current plan source. Fixed the classification to separate the current plan source from completed historical docs.

Because valid findings were fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 7

Reviewer finding:

- Valid: `docs/plans/effective-tool-access-consolidation/plan.md` still had a capitalized current-doc old term, `Workspace-provider role-access schema API`, which the required case-sensitive audit did not catch. Fixed it to `Workspace-tool-provider role-access schema API` and added a case-insensitive old-term audit to the final local checks.

Because a valid finding was fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 8

Reviewer findings:

- Valid: the report mentioned adding a case-insensitive audit but did not record its exact command and outcome. Fixed the static audit section to record the companion command and outcome.
- Valid: the changed documentation list omitted the current plan file in the untracked plan directory. Fixed the changed-path list to include `docs/plans/workspace-tool-provider-rename/plan.md`.

Because valid findings were fixed, the review gate was restarted again with a fresh reviewer.

### Review loop 9

Fresh reviewer result: no valid findings.

### Review loop 10

Fresh reviewer result: no valid findings.

Review gate outcome: passed after two consecutive fresh review passes with zero valid findings.
