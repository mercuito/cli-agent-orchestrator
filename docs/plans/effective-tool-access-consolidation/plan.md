# Tool Service Consolidation

Status: draft

## Problem

The team-role tool-access plan exposed a larger architectural issue: CAO does
not have one owner for tool registration, tool access, and tool allow/block
decisions.

Today, different subsystems independently interpret agent-local config,
workspace team membership, provider presence, MCP server config, runtime
capabilities, provider conversation permissions, and UI presentation state.
That creates a large blast radius for any change to tool authority.

The goal of this plan is to consolidate tool registration and access decisions
behind one `ToolService` before implementing team-role-owned access.

## Target Model

Introduce a backend-owned Tool Service that answers these questions for every
agent:

- Which tools are available from CAO and registered workspace tool providers?
- Which tools are registered for a terminal/runtime?
- Which tools is an agent allowed to use?
- Which tools is an agent blocked from using?
- Which direct/custom MCP servers should be materialized?
- Which provider-conversation operations are allowed?
- What access source caused each allow/block decision?
- What diagnostics explain missing, inactive, denied, or invalid tools?

All consumers must use this service instead of reading `Agent.cao_tools`,
`Agent.mcp_servers`, provider-local tool blocks, or team role data directly.

## Boundaries

The Tool Service owns the tool catalog boundary, MCP tool registration, MCP
tool access, and provider-mediated tool access decisions.

It does not author every tool definition. Built-in CAO tool definitions remain
owned by CAO MCP code, and workspace tool providers continue to define their own
provider-mediated tools, schemas, handlers, and vocabulary. Tool Service
collects those provider-owned definitions into one catalog and decides which
registered tools each agent may use.

It does not own:

- provider-native runtime capabilities such as shell/filesystem allowlists;
- provider identity such as Linear app key/user id;
- raw operator/debug transcript access policy;
- provider infrastructure operations, except for classifying and diagnosing
  whether they are infrastructure or agent-facing access.

Those areas may consume Tool Service decisions, but they should not define tool
authority independently.

## Core Owner Surface

Add a service near the workspace/team/provider architecture:

```text
ToolService
```

It should expose public methods equivalent to:

- `tools_for_agent(agent_id) -> AgentToolAccess`
- `registered_tools_for_terminal(terminal_id) -> ToolRegistration`
- `provider_policy(provider_name) -> ProviderToolAccessPolicy`
- `can_invoke(agent_id, tool_ref, context) -> ToolAccessDecision`
- `provider_conversation_decision(agent_id, provider, operation, source) -> AccessDecision`
- `materialized_mcp_servers_for_agent(agent_id) -> Mapping[str, McpServerConfig]`

The exact API can change during implementation, but the ownership must not:
callers ask `ToolService` instead of rebuilding allow/block/registration
decisions.

## Tool Access Result Shape

The result should include:

- agent id;
- team id when present;
- role id when present;
- registered tools;
- allowed tools;
- blocked tools;
- built-in CAO MCP tools;
- provider-mediated tool grants;
- direct/custom MCP servers to materialize;
- provider-conversation access requirements;
- source markers for each grant;
- inactive local grants for diagnostics only;
- actionable diagnostics.

Source markers matter because the UI and CLI need to say why access exists or
why local access is inactive.

## Consumers To Migrate

Migrate consumers in phases. Each phase should replace local interpretation
with calls into `ToolService`.

## Migration Inventory From Review Loop

The previous team-role review loop is valuable because it identified the real
places where tool authority is currently interpreted, materialized, displayed,
or leaked. Treat this inventory as the initial migration checklist for
`ToolService`.

### Core Access And Validation

- Team membership and role assignment resolution.
- Provider policy loading and `ProviderToolAccessRequest` generation.
- Role/provider access expansion back into concrete agent-scoped grants.
- Provider grants constrained to providers in the team's workspace.
- Agent config validation/editing for inactive teamed local grants.
- CLI inspection output that currently shows raw local grants.

### MCP Registration, Invocation, And Revocation

- Built-in CAO MCP registration and allowlists.
- Provider-mediated MCP registration.
- Provider-mediated invocation checks.
- Built-in CAO invocation checks where live revocation is enforced.
- Fail-closed/diagnostic behavior for teamed startup allowlist failures.
- Live revocation behavior for already-running terminals.
- `terminate` same-team target authorization.
- Generated `assign`/callback guidance that assumes `send_message`.

### MCP Server Materialization

- Top-level agent-local `mcp_servers`.
- Role-owned direct/custom `mcp_servers`.
- Managed `cao-mcp-server` materialization.
- Codex CODEX_HOME materialization.
- Codex `codex_config.mcp_servers` and similar nested provider config.
- Claude, Gemini, Kimi, Copilot MCP launch paths.
- Copilot's separate `--additional-mcp-config` path.
- Gemini global `~/.gemini/settings.json` registration and cleanup.
- Diagnostics/preflight expected MCP server checks.
- Runtime capability `@server` marker generation.

### Provider Identity And Linear

- Linear identity/presence loading separated from tool access validation.
- Linear OAuth/app-client helpers.
- Linear provider-owned role access schema.
- Linear provider-conversation access requirements.
- Linear incoming agent guardrail policy layering.
- Linear policy fact reads.
- Linear policy-denial comments.
- Linear external URL publication/repair.
- Linear monitor recovery, retry, and watermark behavior.
- Linear live webhook permanent-denial processing.

### Provider Conversation And Content Surfaces

- Provider-backed inbox notification creation.
- Provider-backed terminal delivery and preview redaction.
- `read_inbox_message` and `reply_to_inbox_message`.
- Stored inbox list API and CLI inbox list.
- Monitoring/session message reads.
- Persisted Linear CAO events.
- Agent timeline API responses.
- Runtime notification delivery events.
- Dashboard timeline event views.
- Raw terminal output APIs.
- Live terminal WebSocket and dashboard terminal view.
- CLI tmux attach and CLI terminal output.
- Handoff output capture.
- Rendered monitoring logs.

### Dashboard And API Surfaces

- Team role CRUD.
- Team metadata updates preserving roles/assignments.
- Built-in CAO tool descriptor API.
- Workspace-tool-provider role-access schema API.
- Namespace separation from CLI provider/model catalog `/providers`.
- Vite dev proxy coverage for new dashboard API prefixes.
- Agent detail effective tool display.
- Team detail role/tool display.
- Raw `agent.toml` editor inactive-state display.

### Prompt And Generated Guidance

- Bundled CAO supervisor/worker skills.
- Default seeded skills.
- Baton service holder/originator guidance.
- Baton watchdog nudges.
- Baton lifecycle operations and diagnostics.
- Runtime-generated assign/follow-up text.

This list is not a license to implement everything in one change. It is the
known consumer map. Each phase should pick a coherent slice and move that slice
behind `ToolService`, with tests proving consumers no longer interpret access
locally.

### Phase 1 - Read-Only Tool Service

- Add `ToolService` and result types.
- Preserve current behavior while centralizing reads.
- Make current agent-local config resolve through the service.
- Add tests for unteamed agents matching existing behavior.
- Add tests for teamed agents with inactive local access diagnostics.

### Phase 2 - Tool Registration And Invocation

- Built-in CAO MCP registration uses `ToolService`.
- Provider-mediated MCP registration uses `ToolService`.
- Provider-mediated invocation re-checks current `ToolService` decisions.
- Built-in CAO tool invocation checks current `ToolService` decisions where
  live revocation requires per-call enforcement.
- Decide live revocation semantics in the service:
  - prefer per-invocation denial for revoked access;
  - otherwise require automatic terminal stop/restart before stale tools can be
    used.

### Phase 3 - Runtime Materialization

- Provider runtime launch paths consume direct/custom MCP servers from
  `ToolService`.
- Codex, Claude, Gemini, Kimi, and Copilot stop reading agent-local
  `mcp_servers` directly.
- Provider-specific nested MCP config such as `codex_config.mcp_servers` is
  folded into Tool Service rules.
- Provider-global state such as Gemini settings is reconciled from
  `ToolService`.

### Phase 4 - Provider Conversation Policy

- Add provider-owned provider-conversation access descriptors.
- Linear preview/read/reply/activity operations map to explicit provider-owned
  requirements.
- Inbox, stored inbox reads, timelines, runtime notification events, monitor
  recovery, and webhook processing all consume the same Tool Service-backed
  provider-conversation decision.
- Provider infrastructure operations are explicitly classified and audited.

### Phase 5 - Presentation

- Dashboard agent detail, team detail, raw TOML editor, timeline views, inbox
  views, and tool panels consume `ToolService` responses.
- CLI inspection surfaces consume `ToolService` responses.
- Raw transcript surfaces are clearly labeled as operator/debug transcript
  surfaces.

### Phase 6 - Team Role Authority

Only after `ToolService` is in place:

- move teamed agents from agent-local access to team role access;
- keep unteamed local access as standalone authority;
- add role assignment, default `member`, and provider-role schema editing.

This keeps the role change small because all consumers already ask
`ToolService`.

## Design Constraints

- There must be one public owner for tool registration, allow decisions, and
  block decisions.
- Tool definitions remain owned by their defining subsystem. Tool Service is
  the catalog and access boundary, not the author of provider tool vocabulary.
- Consumers must not directly interpret both team role and agent-local access.
- Provider-native vocabulary remains provider-owned.
- Built-in CAO tool vocabulary is backend-owned.
- Provider conversation access is distinct from generic provider tool access,
  but both are resolved through `ToolService`.
- Agent-local access remains first class for unteamed agents.
- Teamed agent-local access may remain in config, but only as inactive
  standalone fallback.

## Acceptance Criteria

The implementation is not complete until every gate in this section is met.
Passing a narrow unit test is not enough.

### Gate 1 - ToolService Is The Authority Boundary

- `ToolService` is the only production owner for tool registration decisions,
  tool allow/block decisions, effective direct/custom MCP server materialization,
  and provider-conversation tool decisions.
- Tool definitions remain provider/subsystem-owned, but registration and
  access decisions flow through `ToolService`.
- Team-role implementation, when added later, is a source adapter feeding
  `ToolService`, not a cross-cutting rewrite.
- Old tool-authority logic must be removed, not preserved as a compatibility
  fallback. Production code must not keep parallel paths that merge,
  double-check, or fall back to direct `Agent.cao_tools`, `Agent.mcp_servers`,
  provider-local tool access, or provider-conversation authorization outside
  `ToolService`.

### Gate 1A - No Legacy Authority Paths

This migration intentionally breaks the old authority structure. Do not add
backward-compatible code that preserves old tool-access logic.

Disallowed:

- "fallback to old behavior if ToolService has no answer";
- merging ToolService decisions with direct agent-local grants for teamed
  agents;
- keeping old provider-local access loaders as active authority paths;
- allowing runtime materialization to read direct MCP server config outside
  ToolService;
- allowing UI/API/CLI displays to calculate effective tools independently;
- keeping provider conversation authorization that bypasses ToolService.

Allowed:

- migration adapters that read old config only to feed ToolService;
- diagnostics that show inactive old config;
- standalone unteamed local access when resolved through ToolService.

Completion requires deleting or deactivating old authority paths. If a direct
read remains, it must be documented as a definition adapter, migration input, or
non-authority display/debug read in the static bypass audit.

### Gate 2 - Migration Inventory Is Accounted For

Every item in **Migration Inventory From Review Loop** must be marked in the
implementation handoff or completion notes as one of:

- migrated to `ToolService`;
- intentionally outside `ToolService` because it is not a tool authority path;
- operator/debug transcript surface with explicit labeling/documentation;
- deferred to a named follow-up plan with a blocking reason.

The implementer may not silently skip an inventory item.

### Gate 3 - Static Bypass Audit

Before claiming completion, run a code-search audit for direct access to known
tool-authority inputs. The audit must include at least:

```bash
rg "cao_tools|mcp_servers|tool_access|ProviderToolAccess|resolve_cao_tool_allowlist|register_provider_mediated|provider_conversation|reply_to_inbox_message|read_inbox_message|codex_config|allowed_tools|runtime_capabilities" src web test
```

Every production match that participates in registration, materialization,
invocation, provider-conversation authorization, API/CLI/dashboard display, or
diagnostics must either:

- call `ToolService`;
- be inside `ToolService` or a provider-owned definition adapter consumed by
  `ToolService`;
- be documented as a non-authority read.

Completion notes must include the audit result and any justified remaining
non-authority reads.

Any production match that preserves old authority behavior as a fallback is a
blocking acceptance failure.

### Gate 4 - Behavior Verification Through Owner Surfaces

Verification must prove behavior through public owner surfaces, not private
helpers alone.

Required behavior checks:

- MCP registration uses `ToolService` for built-in CAO tools.
- MCP registration uses `ToolService` for provider-mediated tools.
- MCP invocation uses current `ToolService` decisions for provider-mediated
  tools.
- Built-in CAO invocation follows the chosen live-revocation semantics.
- Runtime materialization uses `ToolService` for direct/custom MCP servers.
- Codex and Gemini bypass cases are covered, including nested Codex MCP config
  and Gemini global MCP settings reconciliation.
- Provider conversation preview/read/reply decisions use one provider-owned
  descriptor path and one `ToolService` decision path.
- API, CLI, and dashboard tool displays read from `ToolService`.
- Inactive local access for teamed agents is visible as inactive and does not
  affect effective registration, invocation, or materialization.
- Unteamed local access remains effective standalone behavior.

### Gate 5 - Revocation Is Proven

The implementation must choose and document one live revocation model:

- per-invocation current access checks; or
- automatic stop/restart before stale tools can continue.

Verification must prove revoked access cannot continue to invoke:

- built-in CAO tools;
- provider-mediated tools;
- direct/custom MCP servers after restart/materialization.

### Gate 6 - Presentation Is Proven

If UI or dashboard behavior changes, Safari browser verification is required.
The verification must show:

- effective tools displayed from `ToolService`;
- inactive local access clearly labeled for teamed agents;
- unteamed local access still editable/effective;
- raw transcript/operator surfaces labeled according to policy;
- no dashboard route relies on old provider/model catalog APIs for
  workspace-tool-provider role access schemas.

### Gate 7 - Final Acceptance Review Loop

Before finalizing, run fresh-context reviews against:

- this plan;
- the implementation diff;
- the migration inventory;
- the static bypass audit;
- the verification evidence.

The implementation is not complete until it receives **two consecutive clean
fresh-context review passes**.

A review pass is clean only if the reviewer:

- checks the implementation diff against every Definition of Done item;
- reviews the completion notes, static bypass audit, migration inventory
  disposition, and verification evidence;
- validates behavior through public owner surfaces instead of private helper
  tests alone;
- explicitly looks for remaining legacy authority paths, widened access,
  missing access denial, stale runtime behavior, and UI/API/CLI display
  mismatches;
- reports no valid blocking findings.

The reviewer must be asked specifically to find remaining bypasses where a
subsystem still decides tool registration, access, provider-conversation
authorization, or materialization outside `ToolService`.

If a reviewer finds any valid blocking issue, the implementer must fix it,
update verification evidence, and restart the two-clean-review count from zero.
A reviewer saying "no bypass findings" is not enough if any Definition of Done
gate lacks concrete evidence.

## Verification

Verification should include automated tests, static audit output, and manual
browser evidence where UI is touched.

Required automated coverage:

- service resolution for unteamed, teamed, invalid team, invalid role, inactive
  local grants, and missing provider identity;
- MCP registration and invocation through public runtime/MCP surfaces;
- runtime materialization for Codex, Gemini, and at least one other provider;
- provider conversation read/reply/preview decisions;
- API and CLI Tool Service presentation;
- dashboard tool access display and inactive local access presentation.

Required non-test evidence:

- static bypass audit output and disposition;
- migration inventory disposition;
- live revocation model statement;
- Safari screenshots or browser-run notes for dashboard changes;
- reviewer findings and resolution notes, including the two consecutive clean
  fresh-context review passes required by Gate 7.

Completion notes must include concrete evidence for each Definition of Done
item. "Accounted for", "migrated", "reviewed", or similar checklist language is
insufficient unless paired with the exact code path, test/browser verification,
or audit disposition proving the behavior.

## Definition Of Done

This plan is complete only when one final completion note can answer **yes** to
all of the following:

- `ToolService` is the single production authority for tool registration,
  allow/block decisions, direct/custom MCP server materialization, and
  provider-conversation tool decisions.
- No legacy tool-authority fallback paths remain. Old direct reads are either
  removed, converted into ToolService input adapters, or documented as
  non-authority reads in the static bypass audit.
- Every item in **Migration Inventory From Review Loop** has a recorded
  disposition.
- The static bypass audit was run, reviewed, and included in completion notes.
- Public behavior verification proves MCP registration, MCP invocation, runtime
  materialization, provider conversation decisions, API/CLI/dashboard display,
  inactive teamed local access, and unteamed standalone access all flow through
  `ToolService`.
- The live revocation model is documented and verified.
- UI/dashboard changes, if any, were verified in Safari.
- Applicable criteria from the criteria catalog were evaluated against the
  completed diff.
- Two consecutive clean fresh-context review passes checked the implementation
  diff, inventory disposition, static bypass audit, and verification evidence
  for remaining bypasses and Definition of Done failures. If any valid blocking
  issue was found, it was fixed and the two-clean-review count restarted.
- Completion notes include concrete evidence for each yes answer above; bare
  checklist assertions are not sufficient.

If any answer is no, the implementation is not done.

## Criteria Acceptance

Likely applicable criteria include:

- `do-not-assume-backwards-compatibility`
- `migration-discipline`
- `minimal-cohesive-changes`
- `no-unnecessary-duplication`
- `prefer-public-surfaces`
- `properly-designed-shared-code`
- `system-code-locality`
- `system-definitions-are-localized`
- `all-system-interactions-are-verified-by-tests`
- `seams-must-be-tested`
- `target-behavior-must-not-be-mocked`
- `test-through-owner-surfaces`
- `ui-changes-require-real-browser-verification`

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.
