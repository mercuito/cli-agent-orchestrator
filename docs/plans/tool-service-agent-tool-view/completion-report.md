# Tool Service Agent Tool View Completion Report

## Summary

Implemented the `/agents` tool metadata ownership fix in `ToolService`.
The dashboard API now asks one request-scoped `ToolService` for each agent's
tool view instead of rebuilding MCP/provider metadata from API response models.

The service now owns reusable provider/tool derivations:

- raw provider policies for standalone-agent provider access;
- provider-conversation requirements;
- role-owned provider policy resolution;
- API-facing `AgentToolView`, assembled from `AgentToolAccess` and the MCP
  surface descriptor through `ToolService`.

The reuse is keyed by deterministic input tokens. It recomputes when relevant
agent config, workspace/team assignment, role grants, registry contents, or
workspace provider config state changes. The existing lower-level
`mcp_server.freshness` source-inspection cache remains only as a private source
metadata helper; service/API behavior is exercised through `ToolService`.

## Files Changed For This Plan

- `src/cli_agent_orchestrator/services/tool_service.py`
- `src/cli_agent_orchestrator/api/main.py`
- `src/cli_agent_orchestrator/mcp_server/server.py`
- `src/cli_agent_orchestrator/mcp_server/freshness.py`
- `test/services/test_tool_service.py`
- `test/api/test_agent_routes.py`
- `test/mcp_server/test_mcp_freshness.py`

Other worktree changes existed from the teams-tab redesign/performance work and
were not part of this tool-service plan's ownership change.

## Commands And Results

| Command | Result |
| --- | --- |
| `uv run pytest test/services/test_tool_service.py::test_agent_tool_view_reuses_provider_policy_metadata_for_same_inputs test/services/test_tool_service.py::test_agent_tool_view_recomputes_provider_policy_when_provider_config_changes test/services/test_tool_service.py::test_agent_tool_view_recomputes_when_agent_tool_inputs_change test/services/test_tool_service.py::test_agent_tool_view_recomputes_when_team_role_grants_change test/api/test_agent_routes.py::test_list_agents_returns_stable_status_shape test/api/test_agent_routes.py::test_list_agents_effective_access_reserves_hidden_builtin_names test/api/test_agent_routes.py::test_list_agents_reads_tool_metadata_from_tool_service_owner test/api/test_agent_routes.py::test_list_agents_active_filter` | Passed, 8 tests. |
| `uv run pytest test/services/test_tool_service.py` | Passed, 34 tests. |
| `uv run pytest test/api/test_agent_routes.py` | Passed, 38 tests. |
| `uv run pytest test/mcp_server/test_mcp_freshness.py` | Passed, 12 tests. |
| `uv run pytest test/services/test_tool_service.py test/api/test_agent_routes.py test/mcp_server/test_mcp_freshness.py` | Passed, 84 tests. |
| `uv run pytest test/api/test_agent_routes.py::test_get_agent_reads_tool_metadata_from_tool_service_owner test/api/test_agent_routes.py::test_list_agents_reads_tool_metadata_from_tool_service_owner` | Passed, 2 tests after adding single-agent route owner-boundary coverage. |
| `uv run pytest test/services/test_tool_service.py::test_agent_tool_view_reuses_team_role_provider_policy_during_surface_build test/services/test_tool_service.py::test_agent_tool_view_reuses_provider_policy_metadata_for_same_inputs test/services/test_tool_service.py::test_agent_tool_view_recomputes_provider_policy_when_provider_config_changes` | Passed, 3 tests after fixing the review finding. |
| `uv run pytest test/services/test_tool_service.py test/api/test_agent_routes.py test/mcp_server/test_mcp_freshness.py` | Passed, 86 tests after fixing the review finding. |
| `npm test` from `web/` | Passed, 14 files / 165 tests. Existing jsdom canvas and React `act(...)` warnings appeared; no failures. |
| `npm run build` from `web/` | Passed. Built backend-served dashboard assets under `src/cli_agent_orchestrator/web_ui/`; Vite emitted the existing large chunk warning. |
| `uv run python scripts/catalog_criteria.py --format json` | Passed and used for the criteria judgments below. |

## Profiling And Endpoint Timing

Served URL: `http://127.0.0.1:9891`

Server command:

```bash
uv run cao-server --host 127.0.0.1 --port 9891
```

Endpoint timing after implementation:

| Probe | Result |
| --- | --- |
| `/agents` run 1 | `status=200 total=0.097486s size=36301` |
| `/agents` run 2 | `status=200 total=0.017442s size=36301` |
| `/agents` run 3 | `status=200 total=0.023960s size=36301` |
| `/agents` run 4 | `status=200 total=0.019400s size=36301` |
| `/agents` run 5 | `status=200 total=0.019886s size=36301` |
| `/` dashboard HTML run 1 | `status=200 total=0.064965s size=403` |
| `/` dashboard HTML run 2 | `status=200 total=0.015519s size=403` |
| `/` dashboard HTML run 3 | `status=200 total=0.024968s size=403` |
| `/agents/discovery_partner` | `status=200 total=0.019184s size=14120` |
| `/agents/implementation_partner` | `status=200 total=0.017842s size=6579` |
| `/agents/linear_smoke_tester` | `status=200 total=0.013432s size=15598` |

Post-review-fix endpoint timing after restarting the backend server:

| Probe | Result |
| --- | --- |
| `/agents` run 1 | `status=200 total=0.099530s size=36301` |
| `/agents` run 2 | `status=200 total=0.019724s size=36301` |
| `/agents` run 3 | `status=200 total=0.019723s size=36301` |

Payload spot-check:

| Agent | MCP tools | Allowed tools | Source markers |
| --- | ---: | ---: | ---: |
| `discovery_partner` | 27 | 27 | 28 |
| `implementation_partner` | 2 | 2 | 3 |
| `linear_smoke_tester` | 28 | 28 | 30 |

Historical before-fix symptom: the dashboard's `/agents` call could take more
than 10 seconds and hit the frontend abort timeout. The new served endpoint
timings above did not reproduce the abort; the browser surface loaded and
rendered agent tool metadata.

## Browser Verification

Browser used: Safari, backend-served dashboard.

Served target: `http://127.0.0.1:9891/#/agents`

| Required UI element/action | Verification target | Observed result |
| --- | --- | --- |
| Load backend-served dashboard, not `mockup.html` or component tests | Safari at `http://127.0.0.1:9891/#/agents` | Page loaded from backend static bundle. Header displayed `CLI Agent Orchestrator` and `Live`. |
| Open Agents tab | Clicked `Agents` tab in Safari | Agents tab selected and rendered `AGENTS (3)`. |
| Render roster from real `/agents` data | Agents sidebar | `Discovery Partner`, `Implementation Partner`, and `Linear Smoke Tester` rendered. |
| Render selected agent detail | Default selected agent detail | `Discovery Partner` detail rendered with id, workdir, team, setup, terminal, and context fields. |
| Render API-provided tool metadata | Expanded `Available tools 27` | Tool list rendered `read_inbox_message`, `reply_to_inbox_message`, and Linear provider tools including `cao_linear.get_issue`. |
| Preserve ToolService ownership copy in UI | Expanded tools panel | Panel displayed `Managed by ToolService.` |
| Reload served dashboard | Safari reload against backend-served URL | Reload completed without the red `Fetch is aborted` snackbar. |
| API timing behind browser path | Server logs and curl probes against same server | `/agents` returned 200; repeated runs completed in roughly 18-24ms after first request. |

## Staleness Checks

| Input that can change | Evidence |
| --- | --- |
| Same input should reuse expensive provider metadata | `test_agent_tool_view_reuses_provider_policy_metadata_for_same_inputs` asserts repeated `agent_tool_view` calls call the provider policy loader once. |
| Same team-role input should reuse provider policy within one surface build | `test_agent_tool_view_reuses_team_role_provider_policy_during_surface_build` asserts one `agent_tool_view` call invokes the role provider once even when provider-conversation requirements are present. |
| Agent tool config changes | `test_agent_tool_view_recomputes_when_agent_tool_inputs_change` mutates the agent manager's agent config and verifies the new built-in tool answer. |
| Team role grant changes | `test_agent_tool_view_recomputes_when_team_role_grants_change` mutates the role grant and verifies the new role-owned built-in tool answer. |
| Provider config/provider policy content changes | `test_agent_tool_view_recomputes_provider_policy_when_provider_config_changes` changes the workspace provider config token and verifies provider metadata is recomputed. |
| Runtime/source freshness helper cannot create stale source metadata | `test/mcp_server/test_mcp_freshness.py` includes source-token reuse and token-change refresh coverage. The cache is below ToolService and does not authorize tools. |

## Criteria Judgments

| Criterion | Judgment |
| --- | --- |
| `migration-discipline` | Satisfied. `/agents` and `/agents/{agent_id}` callers moved to the ToolService-owned shape; legacy per-agent route rebuilding is retained only as response-model fallback, not on the hot route. |
| `minimal-cohesive-changes` | Satisfied for this plan. Changes are confined to ToolService ownership, MCP adapter delegation, route adaptation, and tests. Existing unrelated worktree changes were left untouched. |
| `no-test-only-production-seams` | Satisfied. `AgentToolView`, service methods, and MCP pending-tool accessor are production surfaces used by routes/adapters. |
| `no-unnecessary-duplication` | Satisfied. Response models adapt shared service results; tests use helpers only for route isolation. |
| `parallel-safe-execution` | Satisfied. No global mutation or persistent migrations were introduced; request-scoped service caches are instance-local. |
| `prefer-public-surfaces` | Satisfied. API routes consume `ToolService.agent_tool_view`; MCP server helpers delegate to ToolService when a provider-policy override is not explicitly supplied. |
| `properly-designed-shared-code` | Satisfied. Shared tool view construction lives in the tool service, not inside API route internals. |
| `readable-and-explicit` | Satisfied. Cache tokens and invalidation inputs are explicit helper functions. |
| `deep-systems` | Satisfied. The implementation uses deterministic input fingerprints instead of lifecycle hooks. |
| `system-code-locality` | Satisfied. Tool authority and reuse stay in `services/tool_service.py`; MCP server remains a thin adapter for MCP-owned built-ins. |
| `system-definitions-are-localized` | Satisfied. `AgentToolView` and service APIs are localized in ToolService. |
| `all-system-interactions-are-verified-by-tests` | Satisfied for the touched behavior: service reuse/staleness, API route ownership, and source helper freshness are covered. |
| `assertions-occur-in-the-then-clause` | Satisfied. New tests arrange, act, then assert on returned service/API behavior. |
| `given-when-then-test-structure` | Satisfied. New tests follow setup/action/assertion structure. |
| `reusable-given-state` | Satisfied. Existing test helpers and small route tool-view helpers are reused. |
| `seams-must-be-tested` | Satisfied. The route seam into ToolService and the service cache seam are directly tested. |
| `target-behavior-must-not-be-mocked` | Satisfied. Service tests exercise real `ToolService`; API route tests fake ToolService only to prove the route uses the owner boundary. |
| `test-artifact-containment` | Satisfied. New tests do not create uncontrolled artifacts. |
| `test-file-organization` | Satisfied. Service behavior tests remain in `test/services`; route-shape tests remain in `test/api`; source helper tests remain in `test/mcp_server`. |
| `test-through-owner-surfaces` | Satisfied. The new behavior is tested through `ToolService.agent_tool_view` and HTTP route surfaces. |
| `test-validity-preserved` | Satisfied. Existing API, service, MCP freshness, and web test suites passed. |
| `ui-changes-require-real-browser-verification` | Satisfied. The backend-served built dashboard was verified in Safari. |

## Review Loop

### Loop 1

Reviewer: fresh-context subagent `019e423f-28ed-71b0-aa95-5ca3690522dd`.

Finding: valid P1. Team-role agents with provider-conversation requirements
could compute role provider policy twice inside one `agent_tool_view()` call:
`tools_for_agent()` resolved with provider-conversation requirements while the
MCP surface path called `provider_policies_for_agent()` without them, producing
a different role-policy cache key.

Fix:

- `provider_policies_for_agent()` now resolves with
  `_provider_conversation_requirements()`, matching `tools_for_agent()`.
- Added `test_agent_tool_view_reuses_team_role_provider_policy_during_surface_build`.
- Added `test_get_agent_reads_tool_metadata_from_tool_service_owner` to cover
  the single-agent route owner boundary required by the plan.

Verification after fix:

- `uv run pytest test/services/test_tool_service.py::test_agent_tool_view_reuses_team_role_provider_policy_during_surface_build test/services/test_tool_service.py::test_agent_tool_view_reuses_provider_policy_metadata_for_same_inputs test/services/test_tool_service.py::test_agent_tool_view_recomputes_provider_policy_when_provider_config_changes`
  passed with 3 tests.
- `uv run pytest test/services/test_tool_service.py test/api/test_agent_routes.py test/mcp_server/test_mcp_freshness.py`
  passed with 86 tests.
- Backend server was restarted and `/agents` was re-timed successfully.

Clean-review streak reset to 0.

### Restarted Loop Review 1

Reviewer: fresh-context subagent `019e4246-1e5e-78a0-865d-d785b75d97bb`.

Result: zero valid blocking findings.

Reviewer note: the previous role-provider double-computation issue appears
fixed because `provider_policies_for_agent()` now resolves with
provider-conversation requirements, and the focused regression/API
owner-boundary tests passed. Residual non-blocking risk noted: response model
fallback behavior still exists for non-list/detail callers that do not pass
`tool_view`, but `/agents` and `/agents/{agent_id}` are covered and consume
`ToolService.agent_tool_view()` as required.

Clean-review streak: 1.

### Restarted Loop Review 2

Reviewer: fresh-context subagent `019e4248-6b8c-7771-9368-ec6209034ede`.

Result: zero valid blocking findings.

Reviewer note: the prior valid issue remains fixed; `/agents` and
`/agents/{agent_id}` consume `ToolService.agent_tool_view()`, service-owned
reuse and invalidation are localized in ToolService, and the lower-level
freshness cache is private and justified. Residual non-blocking risk repeated:
response-model fallback behavior still exists for non-list/detail callers that
do not pass `tool_view`, but this is outside the stated `/agents` and
`/agents/{agent_id}` acceptance scope.

Verification run by reviewer:

- `uv run pytest test/services/test_tool_service.py test/api/test_agent_routes.py test/mcp_server/test_mcp_freshness.py`
  passed with 86 tests.

Clean-review streak: 2.

Status: review gate satisfied. Two successive fresh-context reviewers reported
zero valid findings after the last fix.

Required gate: continue review loops until two successive fresh-context reviews
report zero valid findings. Any valid finding must be fixed, documented here,
and the two-clean-review count restarted.
