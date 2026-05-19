# 04 - Runtime, Cleanup, And Verification

Status: complete

## Goal

Wire role-owned effective access through runtime materialization, freshness,
inspection, cleanup, and final verification.

## Scope

Implement:

- runtime materialization from effective access only;
- stale configuration marking when role access changes effective MCP surface;
- CLI inspection updates;
- prompt/skill/tool guidance alignment;
- cleanup of old active teamed local access paths;
- final static audits and review loops.

## Runtime Rules

Effective access drives:

- MCP registration;
- provider-mediated registration;
- provider-mediated invocation rechecks;
- direct/custom MCP materialization;
- runtime freshness/fingerprints;
- API/CLI/dashboard effective display.

Agent-local `mcp_servers`, `codex_config.mcp_servers`, `cao_tools`, and
`linear.tool_access` must not stale or widen teamed runtimes while inactive.

Managed `cao-mcp-server` remains CAO infrastructure. Role-owned `mcp_servers`
must not disable, override, or shadow it.

Provider-global MCP settings, especially Gemini settings, must be reconciled so
removed or inactive direct MCP servers do not remain registered after role
changes, restarts, or cleanup.

## Staleness

Treat role/tool access changes as stale runtime configuration. This plan marks
affected terminals stale and preserves existing reload/resume behavior.

Do not redesign staleness triggers. Agent-originated staleness checks are a
separate future plan.

## CLI, Prompt, And Guidance

CLI inspection must show effective role access for teamed agents or clearly
label local access as inactive.

Generated prompt/skill/baton guidance must not promise tools hidden by the
effective role. Baton lifecycle messages and watchdog nudges should adapt or
reject when the affected agent lacks required baton tools.

`terminate` must remain same-team constrained by default; a role grant must not
become unrestricted cross-team termination.

## Migration And Cleanup

If current teamed bootstrap/sample agents rely on local Linear access, migrate
the intended active access into team roles.

Persist migrated team role policy in `workspace-teams.json` through
`WorkspaceTeamStore`. Do not move teamed role policy into agent TOML, Linear
config, or a separate role file.

Local config may remain as inactive standalone fallback. It must not affect
teamed effective access.

Remove or deactivate legacy code paths that:

- merge team role grants with local grants;
- use local grants as active teamed access;
- materialize provider runtime config from inactive local grants;
- present inactive local grants as effective access.

## Acceptance Criteria

- Effective access from ToolService drives MCP registration, provider-mediated
  registration, provider-mediated invocation rechecks, direct/custom MCP
  materialization, runtime freshness/fingerprints, and API/CLI/dashboard
  effective display.
- Agent-local `mcp_servers`, `codex_config.mcp_servers`, `cao_tools`, and
  `linear.tool_access` do not stale or widen teamed runtimes while inactive.
- Managed `cao-mcp-server` remains CAO infrastructure. Role-owned
  `mcp_servers` cannot disable, override, or shadow it.
- Provider-global MCP settings, especially Gemini settings, are reconciled so
  removed or inactive direct MCP servers do not remain registered after role
  changes, restarts, or cleanup.
- Role/tool access changes mark affected terminals stale and preserve existing
  reload/resume behavior. This phase does not redesign staleness triggers or
  add agent-originated staleness checks.
- CLI inspection shows effective role access for teamed agents or clearly
  labels local access as inactive.
- Generated prompt, skill, and baton guidance do not promise tools hidden by
  the effective role.
- Baton lifecycle messages and watchdog nudges adapt or reject when the
  affected agent lacks required baton tools.
- `terminate` remains same-team constrained by default. A role grant does not
  become unrestricted cross-team termination.
- Current teamed bootstrap/sample agents that rely on local Linear access are
  migrated so intended active access lives in team roles.
- Migrated team role policy persists through `WorkspaceTeamStore` /
  `workspace-teams.json`, not agent TOML, Linear config, or a separate role
  file.
- Local config may remain as inactive standalone fallback but cannot affect
  teamed effective access.
- Legacy production paths are removed or deactivated when they merge team role
  grants with local grants, use local grants as active teamed access,
  materialize provider runtime config from inactive local grants, or present
  inactive local grants as effective access.
- A broad backend owner-surface suite covers ToolService access resolution, MCP
  registration and invocation, provider-mediated registration and invocation,
  runtime materialization for Codex, Gemini, Copilot, Claude, and Kimi paths
  touched by the change, CLI inspection, provider-backed scoped inbox
  validation, and team role persistence/API behavior.
- Frontend tests and build run if dashboard output changed.
- The implementation runs and records these static audits:

```bash
rg "agent\\.linear\\.tool_access|LinearToolAccessConfig|_linear_tool_access_from_agent|has_provider_tool_access_config|provider_tool_access|TeamRoleToolAccessSource|StandaloneAgentToolAccessSource|ToolAccessResolver|cao_tools|mcp_servers|codex_config\\.mcp_servers" src web test
rg "resolve_cao_tool_allowlist|Registering all tools|allowlist=permissive|read_reply" src test
```

Every production match must be classified in completion notes. Any production
path that defines, activates, merges, or applies grants outside ToolService's
access resolution layer is a blocking failure.
- The implementer and reviewer run `uv run python scripts/catalog_criteria.py`,
  browse the `docs/criteria` catalog it reports, apply all applicable
  implementation and test criteria to this phase, and treat any violation as a
  blocking acceptance failure.
- Completion notes include concrete evidence for every acceptance criterion,
  including test commands, audit classifications, migration notes, and criteria
  catalog judgments.

## Completion Notes

### Criteria Catalog

- Ran `uv run python scripts/catalog_criteria.py`.
- Applied implementation criteria for migration discipline, no backwards
  compatibility assumption, system locality, no global grant authority outside
  ToolService, and simple/readable shared code.
- Applied test criteria for all system interactions, seam coverage, owner
  surface tests, and browser verification for dashboard output.

### Acceptance Evidence

- Effective ToolService access now drives MCP registration, provider-mediated
  registration, provider-mediated invocation rechecks, direct/custom MCP
  materialization, runtime freshness/fingerprints, CLI/API/dashboard effective
  display, and provider CLI MCP injection.
- Agent-local `mcp_servers`, `codex_config.mcp_servers`, `cao_tools`, and
  `linear.tool_access` are inactive for teamed agents and do not widen or
  stale teamed runtimes.
- Managed `cao-mcp-server` remains CAO infrastructure and role-owned MCP
  servers cannot shadow it.
- Gemini global MCP settings remove stale CAO-managed entries before writing
  current effective servers and cleanup removes CAO-managed entries.
- Role/tool access changes mark affected terminals stale using the existing
  reload/resume path; this phase did not add agent-originated staleness checks.
- CLI/API/dashboard inspection shows effective ToolService role access and
  inactive local grant diagnostics.
- Baton service and watchdog guidance now adapt to the holder terminal's
  allowed baton tools instead of promising unavailable lifecycle tools.
- `terminate` remains same-team constrained by ToolService terminal-target
  authorization; role grants do not make it unrestricted.
- The current default team policy is persisted in `workspace-teams.json`
  through `WorkspaceTeamStore`; local config may remain only as inactive
  standalone fallback.
- Legacy active paths were removed/deactivated: Linear workspace setup adapter
  no longer emits active `tool_access`, `authorized_tool_access_locations()`
  returns no active locations, and provider conversation/body delivery routes
  through ToolService.

### Verification Evidence

- Final broad backend suite:
  `uv run pytest test/services/test_tool_service.py test/workspace_setups test/api test/linear test/workspace_providers test/provider_conversations test/mcp_server test/providers test/runtime test/integration/test_agent_runtime_provider_state.py test/integration/test_provider_mediated_contract.py test/cli -q -k 'not test_real_api_returns_non_empty_catalog'`
  passed with 1393 passed, 16 skipped, 1 deselected.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- Frontend verification ran because dashboard output changed:
  `npm test -- src/test/workspace-teams-panel.test.tsx src/test/agent-config-tab.test.tsx src/test/agent-detail-panel.test.tsx`
  passed with 33 tests, and `npm run build` passed.
- Real Safari verification passed with screenshot
  `/tmp/cao-role-dashboard-safari.png`.

### Static Audit Classification

- Ran:
  `rg "agent\\.linear\\.tool_access|LinearToolAccessConfig|_linear_tool_access_from_agent|has_provider_tool_access_config|provider_tool_access|TeamRoleToolAccessSource|StandaloneAgentToolAccessSource|ToolAccessResolver|cao_tools|mcp_servers|codex_config\\.mcp_servers" src web test`
  and
  `rg "resolve_cao_tool_allowlist|Registering all tools|allowlist=permissive|read_reply" src test`.
- Production authority matches are in `services/tool_service.py` and are
  ToolService access resolution, inactive diagnostics, or materialization from
  effective access.
- Provider matches in `linear/*` and `workspace_providers/*` are provider-owned
  vocabulary/schema/validation/conversion, registry contracts, or current
  ToolService rechecks.
- Runtime/provider CLI matches in Codex, Claude, Gemini, Copilot, Kimi, API,
  diagnostics, and terminal service materialize or display
  `ToolService.materialized_mcp_servers_for_agent()` /
  `ToolService.tools_for_agent()` output.
- Agent/API/web matches are raw config read/write/display or schema models, not
  effective teamed authority.
- `read_reply` remains only in test coverage for unsupported-operation denial.
  The audit also matches production `thread_reply` helper names in
  `provider_conversations/reply_service.py`; those are scoped provider-thread
  reply delivery helpers behind ToolService inbox authorization, not permissive
  allowlists or active grant paths. No production permissive allowlist or
  "registering all tools" path remains.

## Review Gate

After implementation, the implementer must run a review loop. The reviewer must
compare the landed implementation strictly against each acceptance criterion in
this file, including the applicable `docs/criteria` catalog criteria. Any valid
finding confirmed by the implementer must be fixed, then the loop must restart
with a fresh reviewer.

For every review finding that requires an implementation change, the implementer
must update `Review Revisions` before restarting the loop. Add a new subsection
for each such revision, recording what the reviewer found, why the implementer
accepted it as valid, how it was fixed, and what evidence verifies the fix.

This phase is complete only after two successive review loops report zero valid
findings.

### Review Gate Evidence

- Loop 1 after Revision 7: Leibniz reported zero valid findings. Evidence:
  criteria catalog evaluated; `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_send_message.py test/mcp_server/test_workspace_setup_collaboration.py
  test/mcp_server/test_tool_filtering.py test/services/test_builtin_skill_guidance.py
  test/provider_conversations/test_inbox_bridge.py test/mcp_server/test_inbox_tools.py
  test/provider_conversations/test_reply_service.py -q` passed with 107
  tests; `uv run python -m compileall -q src/cli_agent_orchestrator` passed;
  static audits matched only classified production/test locations; frontend
  tests passed with 33 tests and `npm run build` passed.
- Loop 2 after Revision 7: Maxwell reported zero valid findings. Evidence:
  criteria catalog evaluated; the same 107-test phase 04 focused sweep passed;
  compileall passed; required static audits matched classified locations;
  additional baton, Gemini, and provider unit suites passed.
- Final broad backend evidence: 1393 passed, 16 skipped, 1 deselected.

## Review Revisions

### Revision 1 - Legacy Cleanup And Runtime Guidance

- Reviewer finding: Gemini global MCP settings could leave stale CAO-managed
  entries; baton lifecycle/watchdog guidance could promise unavailable tools;
  legacy Linear workspace setup paths still treated local tool access as active
  team access.
- Validity decision: accepted. The phase requires cleanup of old active paths,
  provider-global MCP reconciliation, and guidance aligned with effective
  tools.
- Fix: Gemini registration now removes stale CAO-managed entries and marks
  current entries with CAO metadata; baton guidance inspects holder terminal
  allowed tools; Linear workspace setup adapter no longer emits active
  `tool_access`, and `authorized_tool_access_locations()` returns no active
  legacy locations.
- Verification evidence: targeted baton/watchdog/provider tests passed and the
  final broad backend suite passed with 1393 passed, 16 skipped, 1 deselected.

### Revision 2 - ToolService Runtime Guidance And Full-Registry Display

- Reviewer finding: baton service/watchdog guidance used terminal
  `allowed_tools`, which is runtime capability data rather than the CAO MCP
  allowlist, and loaded-agent API/CLI inspection built ToolService with a
  truncated one-agent registry that could mark other real team members as
  non-members.
- Validity decision: accepted. Runtime guidance and API/CLI/dashboard
  effective displays must be driven by ToolService effective access, and
  diagnostics must use the full agent registry.
- Fix: baton holder guidance now resolves baton lifecycle tools through
  ToolService for the holder terminal's agent; the watchdog reuses that helper;
  `tool_service_for_loaded_agent()` now overlays the loaded agent onto the full
  registry instead of replacing the registry with a singleton.
- Verification evidence: `uv run pytest test/services/test_tool_service.py -q`
  passed with 23 tests, and `uv run pytest test/services/test_baton_service.py
  test/services/test_baton_watchdog_service.py -q` passed with 31 tests.

### Revision 3 - Terminate Target Authorization And Role-Aware Skill Guidance

- Reviewer finding: the MCP `terminate` wrapper checked only whether the caller
  could invoke `terminate`, so a role grant could terminate a terminal outside
  the caller's team; bundled supervisor/worker skill guidance also promised
  tools such as `assign`, `handoff`, `send_message`, and baton tools without
  respecting the effective visible tool list.
- Validity decision: accepted. This phase explicitly requires `terminate` to
  remain same-team constrained and generated prompt/skill guidance to avoid
  promising hidden tools.
- Fix: added ToolService terminal-target authorization for `terminate`, wired
  MCP wrapper registration to pass the requested target terminal through that
  check, added same-team/cross-team target regression coverage, and revised the
  bundled skills to say agents should use only currently visible/granted tools.
- Verification evidence: `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py -q` passed with 48 tests;
  `uv run pytest
  test/integration/test_agent_runtime_provider_state.py::test_linear_agent_session_terminal_uses_provider_mediated_linear_mcp_tools
  -q` passed; final broad backend suite passed with 1393 passed, 16 skipped,
  1 deselected.

### Revision 4 - Static Audit Classification Correction

- Reviewer finding: the completion notes said `read_reply` matched only tests,
  but the required static audit also matched production `thread_reply` helper
  names in `provider_conversations/reply_service.py`.
- Validity decision: accepted. The phase requires every production audit match
  to be classified accurately, even incidental substring matches.
- Fix: updated the static audit classification to identify the production
  `thread_reply` substring matches as scoped provider-thread reply delivery
  helpers behind ToolService inbox authorization, not permissive allowlists or
  active grant authority.
- Verification evidence: reran
  `rg "resolve_cao_tool_allowlist|Registering all tools|allowlist=permissive|read_reply" src test`
  and confirmed the only production matches are the classified
  `reply_service.py` `thread_reply` helper names.

### Revision 5 - Assignment And Message Guidance Respects Visible Tools

- Reviewer finding: assignment delivery and sender-ID injection still told
  receiving agents to use `send_message` without checking whether the receiver
  terminal's effective role exposed that tool.
- Validity decision: accepted. Generated prompt/guidance must not promise
  tools hidden by the effective role.
- Fix: assignment and message delivery now append `send_message` callback
  instructions only when ToolService says the receiving terminal can invoke
  `send_message`; otherwise they append sender identity without naming a hidden
  tool. Public `assign`, `terminate`, supervisor, and worker guidance now
  describe callback delivery as conditional on visible/current tools. Added
  regression tests for hidden-tool guidance.
- Verification evidence: `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_send_message.py test/mcp_server/test_workspace_setup_collaboration.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py -q` passed with 60 tests;
  `uv run pytest test/mcp_server/test_assign.py
  test/mcp_server/test_send_message.py
  test/mcp_server/test_workspace_setup_collaboration.py
  test/services/test_builtin_skill_guidance.py -q` passed with 40 tests;
  `uv run python -m compileall -q src/cli_agent_orchestrator` passed; final
  broad backend suite passed with 1393 passed, 16 skipped, 1 deselected.

### Revision 6 - Provider Inbox Reply Guidance Respects Reply Authority

- Reviewer finding: provider conversation inbox notifications were created
  after preview/read authorization but unconditionally included
  `reply_to_inbox_message` guidance, and `read_inbox_message` marked provider
  messages replyable based only on backing thread presence.
- Validity decision: accepted. Phase 04 requires generated prompt/guidance and
  runtime surfaces not to promise tools hidden by the effective role; preview
  and read access do not imply reply access.
- Fix: provider conversation inbox bridging now checks ToolService reply
  authority separately before adding reply guidance, and the inbox read
  surface now reports `replyable=false` with an authorization reason when the
  receiver lacks `reply_to_inbox_message`.
- Verification evidence: new regressions first failed, then passed:
  `test_notification_body_omits_reply_guidance_when_reply_tool_is_hidden` and
  `test_provider_backed_read_is_not_replyable_when_reply_tool_is_hidden`.
  `uv run pytest test/provider_conversations/test_inbox_bridge.py
  test/mcp_server/test_inbox_tools.py -q` passed with 38 tests;
  `uv run pytest test/provider_conversations -q` passed with 33 tests;
  `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_send_message.py
  test/mcp_server/test_workspace_setup_collaboration.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py
  test/provider_conversations/test_inbox_bridge.py
  test/mcp_server/test_inbox_tools.py -q` passed with 98 tests;
  `uv run python -m compileall -q src/cli_agent_orchestrator` passed. The
  static audit still matched only the classified unsupported-operation test
  and `thread_reply` helper-name occurrences behind ToolService authorization.

### Revision 7 - Provider Inbox Reply Uses The Same Selected Message Context

- Reviewer finding: provider inbox reply guidance and `read_inbox_message`
  could authorize using provider identity from the selected provider message,
  while the actual reply path authorized and sent using only thread metadata.
  This let a notification promise `reply_to_inbox_message` and report
  `replyable=true` even though `reply_to_inbox_message` would reject the same
  notification for missing Linear app identity.
- Validity decision: accepted. Provider-backed scoped inbox validation,
  generated guidance, read surfaces, and provider-mediated invocation rechecks
  must use the same authority context for the same provider notification.
- Fix: `reply_to_inbox_message` now loads the selected provider message for
  the inbox notification marker, passes its metadata/raw snapshot into
  ToolService provider inbox authorization, and includes that selected-message
  context in provider reply metadata so Linear app-key selection matches the
  bridge/read authority decision.
- Verification evidence: the new regression
  `test_reply_to_inbox_message_uses_selected_message_identity_context` first
  failed, then passed. `uv run pytest
  test/provider_conversations/test_reply_service.py
  test/provider_conversations/test_inbox_bridge.py
  test/mcp_server/test_inbox_tools.py -q` passed with 47 tests;
  `uv run pytest test/provider_conversations -q` passed with 33 tests;
  `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_send_message.py
  test/mcp_server/test_workspace_setup_collaboration.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py
  test/provider_conversations/test_inbox_bridge.py
  test/mcp_server/test_inbox_tools.py
  test/provider_conversations/test_reply_service.py -q` passed with
  107 tests; `uv run python -m compileall -q src/cli_agent_orchestrator`
  passed. The static audit still matched only the classified
  unsupported-operation test and `thread_reply` helper-name occurrences behind
  ToolService authorization.
