# Tool Service Consolidation Completion Notes

Status: Definition of Done satisfied after two consecutive clean fresh-context review passes.

## Implemented Architecture

`src/cli_agent_orchestrator/services/tool_service.py` is the production owner
for effective tool access. Production consumers now ask `ToolService` for:

- built-in CAO MCP registration and per-invocation allow/deny decisions;
- provider-mediated MCP registration and per-invocation allow/deny decisions;
- direct/custom MCP server materialization, including nested Codex MCP config;
- runtime MCP server marker generation from ToolService materialization;
- provider-conversation preview/read/reply/activity decisions from
  provider-owned descriptors.

Tool definitions remain where they belong: built-in CAO MCP definitions stay in
`mcp_server/server.py`, provider-mediated definitions stay under provider-owned
workspace-provider modules, and provider-native runtime capability vocabulary
stays provider-native. Those definitions are input adapters to ToolService, not
parallel access authorities.

Teamed agents no longer merge direct agent-local grants into effective access.
Their local `cao_tools`, direct `mcp_servers`, nested
`codex_config.mcp_servers`, and provider-local tool grants are retained only in
`inactive_local_grants` diagnostics until team-role-owned sources exist.
Unteamed agents still keep standalone local access, but only through
ToolService resolution.

## Live Revocation Model

The chosen model is per-invocation current access checks for built-in CAO MCP
tools and provider-mediated MCP tools. Direct/custom MCP server revocation is
enforced on restart/materialization by recomputing provider launch config from
ToolService.

Evidence:

- `mcp_server/server.py` wraps registered built-in CAO callables in
  `_toolservice_authorized_callable`, which calls
  `ToolService.can_invoke_for_terminal(...)` on every invocation.
- `workspace_providers/invocation.py` rechecks provider-mediated invocations
  through ToolService before dispatching provider handlers.
- Runtime providers call ToolService-backed terminal materialization paths
  before launch, so revoked direct/custom MCP servers disappear on restart.

## Migration Inventory Disposition

### Core Access And Validation

- Team membership and role assignment resolution: team membership migrated to
  ToolService inputs; role assignment is deferred to
  `docs/plans/team-role-tool-access/plan.md` because role authority is not
  modeled yet.
- Provider policy loading and `ProviderToolAccessRequest` generation: migrated
  as provider-owned definition input consumed by ToolService.
- Role/provider access expansion back into concrete agent-scoped grants:
  provider expansion migrated; role expansion deferred to the team-role plan.
- Provider grants constrained to providers in the team's workspace setup:
  migrated into `ToolService._policy_for_agent(...)`.
- Agent config validation/editing for inactive teamed local grants: migrated to
  ToolService diagnostics; raw config editing remains a non-authority input.
- CLI inspection output that currently shows raw local grants: migrated;
  `cao agent show` prints ToolService effective access before raw TOML.

### MCP Registration, Invocation, And Revocation

- Built-in CAO MCP registration and allowlists: migrated to
  `ToolService.registered_tools_for_terminal(...)`.
- Provider-mediated MCP registration: migrated through ToolService-scoped
  provider policies.
- Provider-mediated invocation checks: migrated to per-call ToolService checks.
- Built-in CAO invocation checks where live revocation is enforced: migrated to
  per-call ToolService checks.
- Fail-closed/diagnostic behavior for teamed startup allowlist failures:
  migrated; startup registers no built-in CAO MCP tools when ToolService
  resolution fails.
- Live revocation behavior for already-running terminals: migrated to
  per-invocation checks for MCP tools.
- `terminate` same-team target authorization: intentionally outside
  ToolService; it is collaboration target authorization, not tool availability.
- Generated `assign`/callback guidance that assumes `send_message`:
  intentionally outside ToolService; ToolService controls whether the tool is
  visible/invokable.

### MCP Server Materialization

- Top-level agent-local `mcp_servers`: migrated to ToolService.
- Role-owned direct/custom `mcp_servers`: deferred to the team-role plan because
  role-owned direct MCP config is not modeled yet.
- Managed `cao-mcp-server` materialization: migrated to ToolService.
- Codex CODEX_HOME materialization: migrated to ToolService-backed config.
- Codex `codex_config.mcp_servers` and similar nested provider config:
  migrated to ToolService.
- Claude, Gemini, Kimi, and Copilot MCP launch paths: migrated to ToolService.
- Copilot's separate `--additional-mcp-config` path: migrated to ToolService.
- Gemini global `~/.gemini/settings.json` registration and cleanup: migrated to
  ToolService materialization input.
- Diagnostics/preflight expected MCP server checks: migrated to ToolService.
- Runtime capability `@server` marker generation: migrated to ToolService.

### Provider Identity And Linear

- Linear identity/presence loading separated from tool access validation:
  intentionally outside ToolService as provider identity input.
- Linear OAuth/app-client helpers: intentionally outside ToolService provider
  infrastructure.
- Linear provider-owned role access schema: provider-owned definition input.
- Linear provider-conversation access requirements: migrated to provider-owned
  descriptors consumed by ToolService.
- Linear incoming agent guardrail policy layering: intentionally outside
  ToolService content guardrail policy.
- Linear policy fact reads: intentionally outside ToolService provider fact
  reads.
- Linear policy-denial comments: intentionally outside ToolService provider UX.
- Linear external URL publication/repair: intentionally outside ToolService
  infrastructure.
- Linear monitor recovery, retry, and watermark behavior: intentionally outside
  ToolService infrastructure.
- Linear live webhook permanent-denial processing: intentionally outside
  ToolService provider event policy.

### Provider Conversation And Content Surfaces

- Provider-backed inbox notification creation: intentionally outside
  ToolService creation/persistence; read/reply access is ToolService-backed.
- Provider-backed terminal delivery and preview redaction: content presentation;
  preview/read/reply access decisions are ToolService-backed.
- `read_inbox_message` and `reply_to_inbox_message`: migrated through shared
  ToolService-backed inbox authorization.
- Stored inbox list API and CLI inbox list: operator/content surfaces; no
  effective tool authority is calculated there.
- Monitoring/session message reads: operator/content surface.
- Persisted Linear CAO events: event storage surface.
- Agent timeline API responses: operator/event surface.
- Runtime notification delivery events: event delivery surface.
- Dashboard timeline event views: operator/event surface.
- Raw terminal output APIs: operator/debug transcript surface.
- Live terminal WebSocket and dashboard terminal view: operator/debug
  transcript surface.
- CLI tmux attach and CLI terminal output: operator/debug transcript surface.
- Handoff output capture: operator/debug transcript surface.
- Rendered monitoring logs: operator/debug transcript surface.

### Dashboard And API Surfaces

- Team role CRUD: deferred to the team-role plan because role CRUD is not part
  of the current model.
- Team metadata updates preserving roles/assignments: deferred to the team-role
  plan because roles are not modeled yet.
- Built-in CAO tool descriptor API: migrated; descriptors are built from
  subsystem definitions and ToolService effective access.
- Workspace-provider role-access schema API: provider-owned definition surface;
  role editing remains deferred to the team-role plan.
- Namespace separation from CLI provider/model catalog `/providers`:
  intentionally outside ToolService; no new dashboard workspace-provider schema
  route relies on the CLI provider/model catalog.
- Vite dev proxy coverage for new dashboard API prefixes: not applicable; no
  new dashboard API prefix was introduced.
- Agent detail effective tool display: migrated to ToolService response data.
- Team detail role/tool display: deferred to the team-role plan because role
  tools are not modeled yet.
- Raw `agent.toml` editor inactive-state display: migrated to ToolService
  diagnostics in the agent detail panel.

### Prompt And Generated Guidance

- Bundled CAO supervisor/worker skills: intentionally outside ToolService
  static guidance.
- Default seeded skills: intentionally outside ToolService static guidance.
- Baton service holder/originator guidance: intentionally outside ToolService
  feature guidance.
- Baton watchdog nudges: intentionally outside ToolService feature guidance.
- Baton lifecycle operations and diagnostics: intentionally outside ToolService
  feature operations.
- Runtime-generated assign/follow-up text: intentionally outside ToolService
  generated guidance; visibility and invocation are ToolService controlled.

## Static Bypass Audit

Audit command:

```bash
rg "cao_tools|mcp_servers|tool_access|ProviderToolAccess|resolve_cao_tool_allowlist|register_provider_mediated|provider_conversation|reply_to_inbox_message|read_inbox_message|codex_config|allowed_tools|runtime_capabilities|load_provider_tool_access_policies" src web test > /tmp/toolservice-static-bypass-audit.txt
```

Result summary from the latest run:

- `total_matches=1427`
- `production_non_test_matches=673`
- `test_matches=754`
- `legacy_helper_prod=0`
- `read_reply_prod=0`
- `old_team_loader_prod=0`
- `register_provider_mediated_prod=7`
- `permissive_prod=1`
- `raw_provider_policy_loader_prod=0`

Reviewed production match classes:

- `services/tool_service.py`: authoritative input adapters, owner decisions,
  diagnostics, and copied output shapes.
- `agent.py`, `api/main.py`, `cli/commands/agent.py`,
  `web/src/components/agents-tab/*`: raw config editing/display or
  ToolService response presentation; no effective access calculation outside
  ToolService.
- `mcp_server/server.py` and `mcp_server/provider_tools.py`: tool definition
  candidate registries and ToolService registration/invocation adapters. The
  seven `register_provider_mediated` production matches are these adapter names,
  their imports/exports, and the MCP startup call site; registration is scoped by
  `ToolService.registered_tools_for_terminal(...)` and invocation by
  `ProviderMediatedToolInvocationService` with a ToolService instance.
- provider modules and `utils/codex_home.py`: provider launch/materialization
  consumers that now receive ToolService-derived MCP server config.
- `workspace_providers/*` and Linear provider modules: provider-owned tool
  vocabulary/schema/descriptor adapters consumed by ToolService.
- provider conversation, inbox, timeline, database, and terminal output
  matches: content/operator/debug/persistence surfaces or shared
  ToolService-backed authorization helpers.
- generated `web_ui/assets/*`: built dashboard bundle generated from the
  current `web/src` sources. The one `permissive_prod` hit is in this generated
  bundle text, not in an authority path or source module.

No production match remains as an active fallback to legacy tool authority.

## Verification Evidence

Automated verification completed after the review-fix loop:

```bash
npm test -- src/test/agent-detail-panel.test.tsx src/test/agent-config-tab.test.tsx src/test/api.test.ts src/test/output-viewer.test.tsx
# 4 files passed, 62 tests passed
```

```bash
npm run build
# passed; Vite emitted only the existing large-chunk warning
```

```bash
uv run python -m compileall -q src/cli_agent_orchestrator
# passed
```

```bash
uv run ruff check ...
# not run: ruff is not installed in this uv environment
```

```bash
uv run pytest test/services/test_tool_service.py test/mcp_server/test_tool_filtering.py test/mcp_server/test_provider_tool_registration.py test/mcp_server/test_mcp_freshness.py test/workspace_providers/test_tool_access.py test/workspace_providers/test_registry.py test/linear/test_provider_tools.py test/services/test_linear_agent_runtime_service.py test/api/test_linear_app_routes.py test/integration/test_provider_mediated_contract.py test/provider_conversations test/providers/test_codex_provider_unit.py test/providers/test_gemini_cli_unit.py test/providers/test_claude_code_unit.py test/providers/test_kimi_cli_unit.py test/providers/test_copilot_cli_unit.py test/services/test_terminal_service_codex_env.py test/utils/test_codex_home.py test/api/test_agent_routes.py test/diagnostics/test_codex_mcp_parsing_unit.py test/cli/commands/test_agent.py -q
# 624 passed in 124.06s
```

This suite covers service resolution, MCP registration/invocation, runtime
materialization across providers, provider conversation decisions, API/CLI
presentation, live revocation checks, inactive teamed local access, and
unteamed standalone access.

Focused post-fix coverage included:

- `test_teamed_provider_local_access_is_inactive_not_effective`, proving
  teamed `agents.<id>.linear.tool_access.*` grants are inactive diagnostics and
  no longer effective provider-mediated access.
- `test_provider_conversation_notification_denies_preview_before_inbox_write`,
  proving preview delivery uses `ToolService.provider_conversation_decision(...)`
  before provider-backed inbox creation.
- `test_teamed_provider_access_requires_workspace_setup_authorized_location`,
  proving teamed provider-mediated access must have both a team-owned source and
  an authorized workspace-setup tool-access location.
- `test_handle_agent_session_event_updates_linear_and_sends_terminal_input`,
  proving Linear lifecycle activity posting consults
  `ToolService.provider_conversation_decision(..., operation="activity")`.
- `test_handle_agent_session_event_denies_activity_before_linear_write`,
  proving Linear activity writes are denied before
  `create_agent_activity(...)` when ToolService denies the activity operation.
- `uv run pytest test/api/test_linear_app_routes.py test/services/test_linear_agent_runtime_service.py -q`
  passed with `52 passed`, covering route-level provider conversation delivery
  and Linear runtime activity authorization.
- `test_baton_tools_are_hidden_when_feature_disabled` proves disabled baton
  built-in definitions are removed from the candidate list passed into
  ToolService instead of filtered after ToolService registration.
- `test_agent_show_uses_available_builtin_tool_candidates` proves CLI
  presentation uses the same ToolService candidate set and does not display
  disabled baton tools as effective access.
- `test_build_runtime_mcp_config_does_not_add_managed_server_without_tool_service`
  proves Copilot no longer materializes the managed `cao-mcp-server` from a
  local fallback when ToolService returns no materialized servers.
- `test_provider_mediated_registration_skips_builtin_name_conflicts` and
  `test_provider_mediated_registration_deduplicates_names_in_tool_service`
  prove provider-mediated reserved-name and duplicate-name decisions are owned
  by ToolService.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_provider_tool_registration.py test/mcp_server/test_tool_filtering.py test/mcp_server/test_mcp_freshness.py test/providers/test_copilot_cli_unit.py test/integration/test_provider_mediated_contract.py -q`
  passed with `82 passed` after adding the API/dashboard hidden-reserved-name
  regression coverage, covering the post-review owner surfaces for ToolService
  provider-mediated filtering, MCP registration, freshness descriptors,
  Copilot materialization, and API presentation.
- `test_list_agents_effective_access_reserves_hidden_builtin_names` proves
  `/agents` effective access uses the same full current built-in candidate
  namespace as MCP and CLI, so a provider-mediated tool cannot appear in the
  dashboard/API payload by occupying a hidden built-in name.

## Safari Dashboard Evidence

Served target:

```bash
HOME=/tmp/cao-toolservice-safari.DqtWT1/home \
CAO_AGENTS_DIR=/tmp/cao-toolservice-safari.DqtWT1/agents \
uv run cao-server --host 127.0.0.1 --port 9891 \
  --agents-dir /tmp/cao-toolservice-safari.DqtWT1/agents
```

Safari URL: `http://127.0.0.1:9891/?tab=agents`.

Fixture API evidence from `GET /agents`:

- unteamed `toolservice-standalone`: allowed tools `assign`, `send_message`;
  materialized MCP servers `cao-mcp-server`, `custom`, `nested`; runtime
  `fs_read`, `@cao-mcp-server`, `@custom`, `@nested`; sources
  `agent_config:cao_tools` and `agent_config:mcp_servers`.
- teamed `toolservice-teamed`: allowed tools `[]`; materialized MCP servers
  only `cao-mcp-server`; runtime `fs_read`, `@cao-mcp-server`; inactive grants
  `cao_tools`, `mcp_servers`, `codex_config.mcp_servers`; provider
  conversation descriptors for Linear `activity`, `preview`, `read`, `reply`.

Safari screenshots:

- `/tmp/cao-toolservice-safari.DqtWT1/evidence/safari-standalone-toolservice-access-final-bundle.png`
  shows ToolService access expanded for the unteamed agent with actual allowed
  tools, sources, runtime capabilities, and MCP server names.
- `/tmp/cao-toolservice-safari.DqtWT1/evidence/safari-teamed-toolservice-access-final-bundle.png`
  shows ToolService access expanded for the teamed agent with `allowed: none`,
  only managed MCP materialization, and inactive local grants labeled.

Additional UI labeling evidence:

- `web/src/components/OutputViewer.tsx` now labels raw terminal transcript
  access as `Operator Terminal Output`.
- `web/src/components/agents-tab/AgentConfigTab.tsx` continues to label the raw
  config editor as `RAW AGENT.TOML (UNSTRUCTURED FIELDS)`.

## Criteria Catalog Evaluation

- `do-not-assume-backwards-compatibility`: satisfied. The old allowlist helper
  was deleted and old authority fallbacks were not preserved.
- `migration-discipline`: satisfied. Callers migrated to ToolService; deferred
  role-owned access is named in the team-role follow-up because the source model
  does not yet exist.
- `minimal-cohesive-changes`: satisfied. Changes are limited to ToolService
  consolidation, necessary provider descriptors, presentation, and tests.
- `no-unnecessary-duplication`: satisfied. Shared decisions live in
  ToolService; consumers call it instead of copying access logic.
- `prefer-public-surfaces`: satisfied. Cross-boundary consumers use
  ToolService, provider contracts, API responses, or existing public managers.
- `properly-designed-shared-code`: satisfied. ToolService has a dedicated
  service module and explicit result types instead of being nested under one
  consumer.
- `system-code-locality`: satisfied. Authority code is localized under
  `services/tool_service.py`; host-required MCP/provider adapters stay thin.
- `system-definitions-are-localized`: satisfied. ToolService result shapes and
  decision APIs are localized in the service module; provider vocabulary stays
  localized in provider contracts.
- `all-system-interactions-are-verified-by-tests`: satisfied by the focused and
  broad owner-surface suites listed above, plus Safari verification for UI.
- `seams-must-be-tested`: satisfied for service/API/MCP/runtime/provider
  seams through the targeted integration tests.
- `target-behavior-must-not-be-mocked`: satisfied for the key owner surfaces;
  tests assert production ToolService behavior, with fakes only for external
  provider/setup boundaries.
- `test-through-owner-surfaces`: satisfied. Verification goes through
  ToolService, MCP registration/invocation surfaces, API/CLI, runtime provider
  launch config, and dashboard UI.
- `ui-changes-require-real-browser-verification`: satisfied by Safari against
  the backend-served built dashboard.

## Intentionally Remaining Non-Authority Reads

- `Agent.cao_tools`, `Agent.mcp_servers`, `Agent.codex_config.mcp_servers`,
  `Agent.runtime_capabilities`, and `Agent.linear.tool_access` are read by
  ToolService as migration/provider-native input adapters and inactive-grant
  diagnostics.
- API/CLI/dashboard raw config surfaces read local config for editing and
  display only; effective access is displayed from ToolService responses.
- Provider modules read provider-owned tool definitions, schemas, handlers, and
  descriptors; ToolService consumes those definitions and owns access decisions.
- Provider identity/presence reads remain provider/team inputs for
  provider-conversation identity checks; ToolService owns the allow/deny
  decision.
- Transcript, inbox list, event/timeline, monitoring, and terminal output
  reads are operator/content/debug/persistence surfaces, not tool authority.
- `_PENDING_TOOLS` in `mcp_server/server.py` is a built-in CAO tool definition
  candidate registry. Registration and invocation decisions are made by
  ToolService.

## Fresh-Context Review Status

The first fresh-context review found two valid blockers:

- teamed agents could still receive agent-local provider-mediated grants through
  ToolService policy filtering;
- provider-conversation preview notification delivery bypassed ToolService.

Both findings were fixed and verified:

- teamed provider-local source locations such as
  `agents.<id>.linear.tool_access.*` are now inactive for teamed agents unless a
  future team-owned source adapter feeds ToolService;
- provider-backed inbox preview delivery now calls
  `ToolService.provider_conversation_decision(..., operation="preview")` and
  denies before writing inbox rows.

Because that review found blockers, the clean-review count was reset to zero.

Clean pass 1:

- reviewer `019e3d8d-dc0f-7420-be94-f944e1818de6`;
- verdict `CLEAN`;
- checked the implementation diff, migration inventory disposition, static
  bypass audit, verification evidence, and remaining non-authority reads;
- found no active legacy authority fallbacks, teamed-agent access widening, or
  missing ToolService owner-surface routing;
- non-blocking observation: provider-native `runtime_capabilities` plumbing
  remains, but not as MCP/tool authority outside ToolService server markers.

The next fresh-context review found one valid blocker:

- `mcp_server/server.py` still registered every built-in CAO MCP tool when
  `CAO_TERMINAL_ID` was missing, preserving a permissive no-terminal fallback.

That finding was fixed and verified:

- no-terminal MCP startup now fails closed by registering no built-in CAO tools;
- wrapped built-in callables deny invocation when terminal context is absent;
- `test_main_without_cao_terminal_id_fails_closed` and
  `test_without_terminal_registers_no_tools` cover the public startup/registry
  behavior;
- `uv run pytest test/mcp_server/test_tool_filtering.py -q` passed with
  `18 passed`;
- the broad backend suite passed with `561 passed`;
- the then-current static audit reported `permissive_prod=0`.

Because a valid blocker was found after clean pass 1, the clean-review count was
reset to zero.

The next clean-attempt review found two additional valid blockers:

- `workspace_providers.registry.load_provider_tool_access_policies()` remained
  exported as a raw provider-policy loader outside ToolService;
- teamed provider-mediated access filtering did not consult workspace setup
  `authorized_tool_access_locations(...)`.

Both findings were fixed and verified:

- the public raw provider-policy loader was removed from
  `workspace_providers.registry` and from `workspace_providers.__all__`;
- ToolService now requires teamed provider-mediated grants to have both a
  team-owned source marker and an authorized workspace-setup tool-access
  location;
- `test_teamed_provider_access_requires_workspace_setup_authorized_location`
  covers the ToolService decision;
- `test_provider_tool_policy_loading_makes_teamed_local_access_inactive` covers
  the registry public surface through ToolService;
- the final static audit reports `raw_provider_policy_loader_prod=0`;
- the broad backend suite passed with `568 passed`.

Because valid blockers were found again, the clean-review count was reset to
zero.

The next clean-attempt review found one additional valid blocker:

- Linear `activity` provider-conversation access was declared in provider-owned
  descriptors, but runtime lifecycle activity posting still called Linear
  `create_agent_activity(...)` without a ToolService authorization decision.

That finding was fixed and verified:

- `linear/runtime.py` now calls
  `ToolService.provider_conversation_decision(..., operation="activity")`
  before posting lifecycle activity and denies before any Linear write if
  ToolService rejects the operation;
- `test_handle_agent_session_event_updates_linear_and_sends_terminal_input`
  covers the allowed activity path through the runtime owner surface;
- `test_handle_agent_session_event_denies_activity_before_linear_write` covers
  denial before `create_agent_activity(...)`;
- `uv run pytest test/api/test_linear_app_routes.py test/services/test_linear_agent_runtime_service.py -q`
  passed with `52 passed`;
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed;
- the final static audit reports `raw_provider_policy_loader_prod=0`,
  `read_reply_prod=0`, and `legacy_helper_prod=0`;
- the then-current broad backend suite passed with `620 passed`.

Because a valid blocker was found again, the clean-review count was reset to
zero.

The next clean-attempt review found one additional valid blocker:

- disabled baton built-in MCP tools were filtered after
  `ToolService.registered_tools_for_terminal(...)`, and `cao agent show` passed
  the unfiltered built-in definition list to ToolService. That left MCP
  registration and CLI display able to disagree about effective built-in tools.

That finding was fixed and verified:

- `mcp_server/server.py` now exposes the currently available built-in CAO tool
  definition names through `built_in_cao_tool_names(...)`; disabled baton tools
  are removed from the definition candidate list before ToolService resolves
  registration, display, descriptors, or invocation checks;
- `_register_tools(...)` no longer applies a separate baton post-filter after
  ToolService returns the allowed built-in tools;
- `cao agent show` continues to call ToolService, now with the same currently
  available built-in candidate list that MCP startup uses;
- the duplicate private startup allowlist resolver was removed, so MCP startup
  has one ToolService registration call path and fails closed inside that owner
  path if resolution fails;
- `test_baton_tools_are_hidden_when_feature_disabled` covers the MCP
  registration candidate list;
- `test_agent_show_uses_available_builtin_tool_candidates` covers CLI
  presentation for disabled baton built-ins;
- `test_tool_service_registration_failure_registers_nothing` covers fail-closed
  startup registration when ToolService resolution raises;
- `uv run pytest test/integration/test_provider_mediated_contract.py test/mcp_server/test_tool_filtering.py test/cli/commands/test_agent.py -q`
  passed with `31 passed`;
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed;
- the then-current static audit reported `total_matches=1404`,
  `production_non_test_matches=672`,
  `test_matches=732`, `raw_provider_policy_loader_prod=0`,
  `read_reply_prod=0`, and `legacy_helper_prod=0`;
- the then-current broad backend suite passed with `620 passed`.

Because a valid blocker was found again, the clean-review count was reset to
zero. Two consecutive clean fresh-context review passes are required from this
post-startup-cleanup state before the next clean-attempt review.

The next clean-attempt review found two additional valid blockers:

- Copilot still materialized the managed `cao-mcp-server` through a local
  fallback when ToolService returned no materialized MCP servers.
- Provider-mediated MCP registration and MCP freshness descriptors still
  performed reserved-name and duplicate-name filtering outside ToolService,
  allowing registration, invocation, and presentation descriptors to diverge
  from the ToolService decision.

Both findings were fixed and verified:

- `providers/copilot_cli.py` now serializes only the MCP servers returned by
  `ToolService.materialized_mcp_servers_for_agent(...)`; if ToolService returns
  no managed server, Copilot receives no managed-server fallback.
- ToolService now owns provider-mediated reserved-name and duplicate-name
  filtering through
  `provider_mediated_tools_for_agent(..., built_in_tool_names=...)`.
- MCP provider registration, provider-mediated invocation checks, and MCP
  freshness descriptors consume ToolService's filtered provider-mediated tool
  map instead of applying their own reserved-name or duplicate-name filters.
- `test_build_runtime_mcp_config_does_not_add_managed_server_without_tool_service`
  covers the Copilot materialization owner surface.
- `test_provider_mediated_registration_skips_builtin_name_conflicts`,
  `test_provider_mediated_registration_deduplicates_names_in_tool_service`, and
  `test_provider_tool_cannot_occupy_reserved_hidden_builtin_name` cover
  ToolService-owned provider-mediated filtering and the descriptor adapter.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_provider_tool_registration.py test/mcp_server/test_tool_filtering.py test/mcp_server/test_mcp_freshness.py test/providers/test_copilot_cli_unit.py test/integration/test_provider_mediated_contract.py -q`
  passed with `81 passed`;
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed;
- the final static audit reports `total_matches=1417`,
  `production_non_test_matches=673`, `test_matches=744`,
  `raw_provider_policy_loader_prod=0`, `read_reply_prod=0`,
  `legacy_helper_prod=0`, and one generated-bundle `permissive_prod` false
  positive that is not an authority path;
- the final broad backend suite passed with `623 passed`;
- dashboard verification still applies because the post-Planck fixes were
  backend authority changes and did not alter the already-verified UI behavior.

Because valid blockers were found again, the clean-review count was reset to
zero. Two consecutive clean fresh-context review passes are required from this
post-Planck-fix state before this plan can be marked complete.

Clean pass 1 after the post-Planck fixes:

- reviewer `019e3dd0-4b2a-7e42-bd23-5777dfb2e4cb`;
- verdict `CLEAN`;
- checked the DoD, completion notes, migration inventory disposition, static
  bypass audit file, pending diff, Safari screenshots, compile verification,
  focused owner-surface suite, broad backend owner-surface suite, dashboard
  tests, and frontend build;
- explicitly checked for remaining legacy authority paths across built-in MCP
  registration/invocation, provider-mediated registration/invocation,
  direct/custom MCP materialization, provider-conversation decisions,
  API/CLI/dashboard presentation, and diagnostics;
- explicitly confirmed prior blockers stayed fixed, including missing-terminal
  fail-closed behavior, teamed local grants remaining inactive, Copilot having
  no managed-server fallback, and provider-mediated duplicate/reserved filtering
  moving into ToolService;
- residual non-blocking risk: the static audit remains large and future changes
  should keep treating direct config reads with suspicion.

Clean-review count is now one. One more consecutive clean fresh-context review
pass is required before this plan can be marked complete.

The next clean-attempt review found one additional valid blocker:

- `EffectiveToolAccessResponse.from_agent(...)` built its
  `built_in_tool_names` input from the already-visible MCP surface descriptor,
  so hidden but reserved built-in CAO tool names were omitted. A provider tool
  with that hidden built-in name could appear as allowed in API/dashboard
  effective access while MCP registration/invocation still denied it.

That finding was fixed and verified:

- `api/main.py` now passes `_available_builtin_cao_tool_names_for_access()`,
  which uses `mcp_server.server.built_in_cao_tool_names()`, into
  `ToolService.tools_for_agent(...)` for API/dashboard effective access.
  This aligns API/dashboard presentation with MCP registration and CLI
  presentation.
- `test_list_agents_effective_access_reserves_hidden_builtin_names` covers the
  `/agents` public API response for a provider-mediated tool that conflicts
  with a hidden built-in name.
- Focused verification passed:
  `uv run pytest test/services/test_tool_service.py test/mcp_server/test_provider_tool_registration.py test/mcp_server/test_tool_filtering.py test/mcp_server/test_mcp_freshness.py test/providers/test_copilot_cli_unit.py test/integration/test_provider_mediated_contract.py test/api/test_agent_routes.py::test_list_agents_effective_access_reserves_hidden_builtin_names -q`
  with `82 passed`.
- Regression cross-check passed:
  `uv run pytest test/api/test_agent_routes.py::test_list_agents_effective_access_reserves_hidden_builtin_names test/cli/commands/test_agent.py::test_agent_show_uses_available_builtin_tool_candidates test/mcp_server/test_mcp_freshness.py::test_provider_tool_cannot_occupy_reserved_hidden_builtin_name -q`
  with `3 passed`.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- The final static audit reports `total_matches=1427`,
  `production_non_test_matches=673`, `test_matches=754`,
  `raw_provider_policy_loader_prod=0`, `read_reply_prod=0`,
  `legacy_helper_prod=0`, and one generated-bundle `permissive_prod` false
  positive that is not an authority path.
- Dashboard tests passed with `62 passed`; `npm run build` passed with only the
  existing Vite large-chunk warning.
- The final broad backend suite passed with `624 passed`.

Because a valid blocker was found after clean pass 1, the clean-review count was
reset to zero. Two consecutive clean fresh-context review passes are required
from this post-API-presentation-fix state before this plan can be marked
complete.

Clean pass 1 after the post-API-presentation fix:

- reviewer `019e3dde-cfca-7141-8019-7d87d0a20e1d`;
- verdict `CLEAN`;
- checked the plan/DoD, completion notes, static bypass audit, pending diff,
  ToolService, MCP registration/invocation, provider-mediated invocation,
  runtime materialization, provider-conversation preview/read/reply/activity,
  API/CLI/dashboard presentation, and diagnostics;
- verified compile, the focused `82 passed` owner-surface suite, the `3 passed`
  hidden-reserved-name cross-check, the broad `624 passed` backend suite, the
  `62 passed` dashboard tests, frontend build, refreshed audit count, and
  Safari screenshot file existence;
- explicitly confirmed the latest API/dashboard hidden-reserved-name blocker
  stayed fixed, along with prior blockers around missing-terminal fail-closed
  startup, teamed inactive local grants, ToolService-owned provider-mediated
  duplicate/reserved filtering, Copilot managed-server fallback removal, and
  Linear provider-conversation decisions.

Clean-review count is now one. One more consecutive clean fresh-context review
pass is required before this plan can be marked complete.

Clean pass 2 after the post-API-presentation fix:

- reviewer `019e3de4-56ac-70d0-a75e-d7192b5b22c9`;
- verdict `CLEAN`;
- checked the DoD, completion notes, static bypass audit, pending diff, and
  owner-surface paths for ToolService, MCP registration/invocation,
  provider-mediated filtering, runtime MCP materialization, provider
  conversation preview/read/reply/activity, API/CLI/dashboard presentation, and
  diagnostics;
- independently ran `uv run python -m compileall -q src/cli_agent_orchestrator`
  successfully;
- independently ran the hidden-reserved-name cross-check:
  `uv run pytest test/api/test_agent_routes.py::test_list_agents_effective_access_reserves_hidden_builtin_names test/cli/commands/test_agent.py::test_agent_show_uses_available_builtin_tool_candidates test/mcp_server/test_mcp_freshness.py::test_provider_tool_cannot_occupy_reserved_hidden_builtin_name -q`
  with `3 passed`;
- independently confirmed the focused owner-surface suite passed with
  `82 passed`;
- checked `/tmp/toolservice-static-bypass-audit.txt` and found no legacy
  allowlist helper, read/reply combined bypass, or raw provider-policy loader
  hits in reviewed production paths;
- residual non-blocking risk: the static audit surface remains large, so future
  changes should continue treating direct reads of `cao_tools`, `mcp_servers`,
  provider tool access, and runtime capability fields as suspicious unless they
  are clearly ToolService inputs, raw config display/editing, provider-owned
  definitions, or debug/operator transcript reads.

This is the second consecutive clean fresh-context review pass after the last
valid blocker was fixed. The Gate 7 review requirement is satisfied.
