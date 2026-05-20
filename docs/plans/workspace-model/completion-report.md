# Workspace Model Completion Report

Status: complete.

## Summary

Workspace is now the active CAO model name for the provider/resolver workflow
contract. The backend package, Python symbols, API schemas/routes, CLI output,
frontend types/helpers, dashboard copy, tests, and active docs were moved from
setup terminology to workspace terminology.

The default workspace is now `linear_delivery` with display name
`Linear Delivery`. No new workspace definition was added.

## Migration Behavior

`workspace-teams.json` remains the persisted team store. Canonical writes now
emit `workspace` and never emit `workspace_setup`.

Legacy read behavior is intentionally limited to the explicit persisted JSON
migration path:

- `workspace` only: accepted and canonicalized.
- `workspace_setup` only: accepted as migration input, then rewritten as
  `workspace`.
- both fields with the same value: accepted as migration input, then rewritten
  as `workspace`.
- both fields with different values: rejected with `WorkspaceConfigError`.
- legacy id `linear_delivery_setup`: mapped to `linear_delivery`.

Evidence:

- `uv run pytest test/workspaces -q` passed: 25 tests.
- Browser verification wrote `/tmp/cao-workspace-model-browser/home/.aws/cli-agent-orchestrator/workspace-teams.json`
  with `workspace: "linear_delivery"` and no `workspace_setup` key.

## Database Inventory

No SQLite migration was added. Inventory commands found no SQLite
`workspace_setup` schema state. SQLite references are limited to
`workspace_context_*` runtime context tables/columns, which are explicitly out
of scope for this plan.

Commands:

- `rg -n "workspace_setup|WorkspaceSetup|workspace setup|workspace-setups|derived_workspace_setup|linear_delivery_setup" src/cli_agent_orchestrator/clients src/cli_agent_orchestrator -g'*.py' -S`
  returned only the explicit JSON migration code in
  `src/cli_agent_orchestrator/workspaces/manager.py`.
- `rg -n "workspace_context_|CREATE TABLE|workspace_setup|linear_delivery_setup" src/cli_agent_orchestrator/clients -S`
  returned `workspace_context_*` storage and no `workspace_setup`.
- `find . \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print`
  returned no repo SQLite files.

## Static Old-Term Audit

Command:

```bash
rg -n "workspace_setup|WorkspaceSetup|workspace setup|workspace-setups|derived_workspace_setup|DEFAULT_WORKSPACE_SETUP|WorkspaceSetupResolver|WorkspaceSetupRegistry|WorkspaceSetupDiagnostic|setup_for_team|setup_for_agent" src test web/src web/vite.config.ts docs -S
```

Classification:

| Area | Remaining hits | Classification |
| --- | --- | --- |
| `src/cli_agent_orchestrator/workspaces/manager.py` | `workspace_setup`, `linear_delivery_setup` | explicit persisted JSON migration handling |
| `test/workspaces/test_workspace_manager.py` | legacy field/id migration assertions | explicit persisted JSON migration tests |
| `test/api/test_agent_routes.py` | `/workspace-setups`, `workspace_setup` | old-route/old-field rejection tests |
| `docs/plans/workspace-model/plan.md` | old inventory and required audit terms | source plan/reference text |
| `docs/plans/workspace-model/completion-report.md` | migration/audit/review evidence | this completion report's own classification text |
| `docs/plans/team-role-tool-access/**`, `docs/plans/*/completion-*`, completed hardening logs | old terminology in completed plans/logs/reports | historical completed docs |

Active docs and draft plans that still guide new work were updated to workspace
terminology. The built dashboard bundle was rebuilt, and `web/src` /
`web/vite.config.ts` have no active old helper/route hits.

After Reviewer 3, the active teams-tab redesign mockup was also checked with:

```bash
rg -n "workspace setup|Workspace setup|Workspace Setup|linear_delivery_setup|Linear Delivery Setup|setup-select|WorkspaceSetup|workspace_setup|workspace-setups" docs/plans/teams-tab-redesign/mockup.html docs/plans/teams-tab-redesign/plan.md -S
```

It now returns no hits.

After Reviewer 4, active tests and active planning docs were also checked with:

```bash
rg -n "\bsetup\b|\bsetups\b|Setup|workspace_setup|WorkspaceSetup|workspace-setups|linear_delivery_setup|Linear Delivery Setup" docs/agents.md docs/plans/effective-tool-access-consolidation/plan.md docs/plans/team-management-backend-crud/plan.md docs/plans/teams-tab-redesign/plan.md docs/plans/teams-tab-redesign/mockup.html docs/plans/tool-service-agent-tool-view/plan.md docs/plans/workspace-team-model/plan.md docs/plans/workspace-team-model/hardening-log.md docs/plans/workspace-tool-provider-rename/plan.md -S
```

It now returns no hits.

Additional active setup audit:

```bash
rg -n "\bsetup\b|\bsetups\b|workspaceSetup|WorkspaceSetup" src/cli_agent_orchestrator test web/src web/vite.config.ts -S
```

Remaining active hits outside explicit JSON migration and legacy API/config
rejection tests are generic setup wording (`setupFiles`, provider setup,
SQLAlchemy setup, test fixture setup comments) or intentional rejection of
unsupported `[workspace].setup` agent config.

## Verification

| Command | Outcome |
| --- | --- |
| `uv run python scripts/catalog_criteria.py --format json` | passed; criteria reviewed |
| `uv run python -m compileall -q src/cli_agent_orchestrator` | passed |
| old/new import check via `uv run python - <<'PY' ...` | old imports removed; new imports ok |
| `uv run pytest test/workspaces -q` | passed, 25 tests |
| `uv run pytest test/api/test_agent_routes.py -q` | passed, 43 tests |
| `uv run pytest test/services/test_tool_service.py test/workspace_tool_providers test/linear/test_provider_tools.py -q` | passed, 154 tests |
| `uv run pytest test/services/test_tool_service.py test/services/test_linear_agent_runtime_service.py -q` | passed, 54 tests |
| `uv run pytest test/api/test_api_endpoints.py test/api/test_agent_routes.py test/services/test_baton_service.py test/services/test_baton_watchdog_service.py test/services/test_linear_agent_runtime_service.py test/provider_conversations/test_inbox_bridge.py test/provider_conversations/test_reply_service.py test/mcp_server/test_inbox_tools.py test/mcp_server/test_workspace_collaboration.py test/linear/test_workspace_adapter.py test/linear/test_workspace_context_resolver.py test/integration/test_agent_runtime_provider_state.py test/integration/test_baton_workflow_smoke.py -q` | passed, 210 tests |
| `uv run pytest test/test_agent.py -q` | passed, 30 tests |
| `uv run pytest test/cli/commands/test_agent.py -q` | passed, 12 tests |
| `npm --prefix web test -- workspace-teams-panel.test.tsx` | passed, 1 file / 6 tests |
| `npm --prefix web test -- agent-config-tab.test.tsx` | passed, 1 file / 20 tests |
| `npm --prefix web test` | passed, 14 files / 168 tests; existing jsdom/xterm and React act warnings were emitted |
| `npm --prefix web run build` | passed; rebuilt backend-served static dashboard bundle |
| `git diff --check` | passed |

Initial attempted frontend command `npm --prefix web run test -- --runInBand`
failed because Vitest does not support `--runInBand`; it was rerun as
`npm --prefix web test`.

## Browser Verification

Backend-served dashboard verification used a temporary CAO home and agents root:

- server: `HOME=/tmp/cao-workspace-model-browser/home CAO_AGENTS_DIR=/tmp/cao-workspace-model-browser/agents CAO_BATON_ENABLED=true uv run cao-server --host 127.0.0.1 --port 8765`
- browser script: `cd /tmp/cao-workspace-model-browser && npx playwright test verify-dashboard.spec.js --browser=chromium --reporter=line`

Outcome: passed, 1 browser test.

Verified:

- Teams tab loaded from backend-served static assets.
- workspace selector is labeled `Workspace`.
- page body does not contain `Workspace setup`.
- API/network requests include `/workspaces` and do not include
  `/workspace-setups`.
- team metadata edit uses `PUT /workspace-teams/cao_delivery` and survives
  reload.
- teamed agent details render workspace metadata with `linear_delivery`.
- canonical persisted JSON contains `workspace` only.

Screenshot evidence:
`/tmp/cao-workspace-model-browser/home/dashboard-workspace-verified.png`.

## Review Findings And Fixes

### Reviewer 1: Active Workspace-Team Plan Still Used Setup Model Terms

Finding: `docs/plans/workspace-team-model/plan.md` still described the retired
setup model in active guidance, including `display_name="Linear Delivery Setup"`
and setup-owned wording around team/workspace ownership.

Why valid: the workspace-model plan requires current docs and draft plans that
actively guide new work to use the new workspace terminology, and the default
display name must be `Linear Delivery`.

Fix: updated `docs/plans/workspace-team-model/plan.md` to use workspace
terminology throughout, including `Linear Delivery`, `linear_delivery`, derived
workspace metadata, team/workspace diagnostics, and workspace/resolver context
language. The active doc now has no `setup` / `WorkspaceSetup` /
`workspace_setup` hits.

### Reviewer 2: CLI Test Still Expected Setup Output

Finding: `test/cli/commands/test_agent.py` still asserted `setup=default` in
`agent list` output even though the CLI now emits `workspace=default`, and the
CLI test was not included in the initial verification table.

Why valid: the plan requires CLI surfaces and tests to use workspace
terminology, and the stale test failed when run directly.

Fix: updated the CLI test expectations to `workspace=default`, verified
`test/cli/commands/test_agent.py`, and added the CLI test command to the
verification table.

### Reviewer 3: Active Teams-Tab Mockup Still Used Setup Terms

Finding: `docs/plans/teams-tab-redesign/plan.md` treats
`docs/plans/teams-tab-redesign/mockup.html` as the authoritative visual
reference, but the mockup still displayed `Workspace setup`,
`Linear Delivery Setup (linear_delivery_setup)`, and `linear_delivery_setup`.
Its mockup-local class name also used `setup-select`.

Why valid: the workspace-model plan requires current docs and draft plans that
actively guide new work to use workspace terminology, and the teams-tab mockup
is part of an active draft plan.

Fix: updated the mockup to use `Workspace`,
`Linear Delivery (linear_delivery)`, `linear_delivery`, and
`workspace-select`. A focused old-term audit against the teams-tab plan and
mockup now returns no hits.

### Reviewer 4: Active Tests And Docs Still Used Setup Terms

Finding: active service/frontend tests still used setup terminology in helper
names and fixture ids, including `_ProviderSetupManager`,
`test_teamed_missing_setup_diagnostic_is_actionable`, `outside_setup`,
`future_setup`, `out_of_setup`, and `docs_setup`. Active planning docs still
used setup language in the teams-tab redesign plan, team-management backend
CRUD plan, workspace-team-model hardening log, and tool-service agent-tool-view
plan.

Why valid: the workspace-model plan requires active tests and current/draft
docs to use workspace terminology except for the explicit JSON migration and
legacy API rejection tests.

Fix: renamed the active test helpers, test names, and fixture ids to workspace
terms; updated active planning docs to use workspace terminology; verified the
focused backend/frontend tests; and reran active-doc old-term scans, which now
return no hits.

### Reviewer 5: Frontend Raw TOML Silently Dropped Workspace Setup

Finding: `web/src/components/agents-tab/agentTomlSerialization.ts` silently
ignored `setup` inside the raw `[workspace]` TOML section.

Why valid: the plan removes frontend compatibility shims and aliases outside
the explicit persisted JSON migration. Silent stripping would hide the legacy
field before backend validation could reject it.

Fix: changed the parser to reject `[workspace].setup` with an explicit error,
added a frontend test proving the save is blocked and `updateAgent` is not
called, and verified `npm --prefix web test -- agent-config-tab.test.tsx`.

### Reviewer 6: API Test Variable Still Used Setup Name

Finding: `test/api/test_agent_routes.py` used the variable name
`setups_response` for a `/workspaces` response.

Why valid: this was active test code outside the explicit JSON migration and
legacy API rejection tests.

Fix: renamed the variable to `workspaces_response` and verified
`uv run pytest test/api/test_agent_routes.py -q`.

### Reviewer 7: Frontend Rejection Test Name Used Old Phrase

Finding: the frontend raw TOML rejection test name used the phrase
`workspace setup`, which made the exact old-term audit return an active
frontend test hit that was not classified.

Why valid: even though the test behavior was a rejection path, active test names
should avoid the retired model phrase unless they are explicitly testing legacy
JSON migration or legacy API field/route rejection.

Fix: renamed the test to reference `[workspace].setup` explicitly and reran the
audit. The active frontend test no longer trips the `workspace setup` phrase.

### Pre-Review Fix: Baton Smoke Fixture

Finding: `test/integration/test_baton_workflow_smoke.py` failed when run
directly because baton guidance now asks `ToolService` which baton tools the
holder can use, and the smoke fixture did not provide the test agents to the
real default tool service.

Why valid: the plan requires baton tests touched by the rename to pass, and the
offline smoke test should not depend on the user agent registry.

Fix: added an explicit fixture-local tool service in the smoke test that returns
the requested built-in baton tools, preserving the test's existing offline
scope while making the dependency explicit. The standalone smoke test and broad
touched suite then passed.

## Review Gate

Reviewer 1, Reviewer 2, Reviewer 3, Reviewer 4, Reviewer 5, and Reviewer 6
and Reviewer 7 produced valid findings, fixed above. The clean-pass count was
restarted after the Reviewer 7 fix.

Reviewer 8 returned `ZERO VALID FINDINGS`.

Evidence:

- exact old-term scans matched the report classification;
- active docs scan returned no hits;
- old imports/routes were absent and new workspace imports/routes were present;
- persisted JSON migration and canonical write behavior were spot-checked;
- `uv run pytest test/workspaces -q` passed, 25 tests;
- `uv run pytest test/api/test_agent_routes.py -q` passed, 43 tests;
- `npm --prefix web test -- agent-config-tab.test.tsx workspace-teams-panel.test.tsx api.test.ts`
  passed, 60 tests.

Reviewer 9 returned `ZERO VALID FINDINGS`.

Evidence:

- exact old-term audit still matched the report classification;
- active frontend/code scan and backend-served bundle had no old helper/type/route hits;
- default workspace remained `linear_delivery` / `Linear Delivery`;
- legacy JSON migration rewrote `workspace_setup: linear_delivery_setup` to
  `workspace: linear_delivery` with no `workspace_setup` write;
- `WorkspaceContextResolution` and `workspace_context_*` were intact;
- `uv run pytest test/workspaces -q` passed, 25 tests;
- `uv run pytest test/api/test_agent_routes.py -q` passed, 43 tests;
- `npm --prefix web test -- workspace-teams-panel.test.tsx agent-config-tab.test.tsx`
  passed, 26 tests.

Review gate complete: Reviewer 8 and Reviewer 9 were two consecutive fresh
review passes with zero valid findings.
