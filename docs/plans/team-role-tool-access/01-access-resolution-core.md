# 01 - Access Resolution Core

Status: complete

## Goal

Create the centralized ToolService access resolution boundary and the minimal
team role domain model needed for ToolService to choose exactly one active grant
source per agent.

## Scope

Implement:

- `ToolAccessResolver`
- `TeamRoleToolAccessSource`
- `StandaloneAgentToolAccessSource`
- team role data model and persistence support
- default `member` role
- role assignment semantics
- normalized access result shape consumed by ToolService

Do not implement full dashboard editing or provider-specific role schemas in
this plan except where tests need simple fixtures.

## Model

An agent belongs to zero or one workspace team. A workspace team points to one
workspace setup and contains role policy plus optional role assignments.

## Persistence

Use the existing `WorkspaceTeamStore` persisted at `workspace-teams.json` as the
owner for team role policy and role assignments. Extend the persisted team shape
instead of creating a separate roles file.

`WorkspaceTeam` should grow from the current metadata-only shape:

```json
{
  "id": "cao_delivery",
  "display_name": "CAO Delivery",
  "workspace_setup": "linear_delivery_setup"
}
```

to a team-owned access shape:

```json
{
  "id": "cao_delivery",
  "display_name": "CAO Delivery",
  "workspace_setup": "linear_delivery_setup",
  "roles": {
    "member": {
      "display_name": "Member",
      "cao_tools": ["send_message", "handoff"],
      "mcp_servers": {},
      "providers": {}
    }
  },
  "role_assignments": {
    "implementation_partner": "member"
  }
}
```

The exact JSON field names may change during implementation, but the ownership
must not: role policy and role assignments live with the workspace team store.
Team update paths must preserve these fields.

Do not put role policy in `agent.toml`. Agent TOML keeps only team membership
and standalone local grants. Do not put role policy in Linear config; Linear
owns provider identity/vocabulary/validation, not teamed grant storage.

Role assignment rules:

- a team member has one effective role;
- missing assignment means `member`;
- assignments for non-members are inactive diagnostics, not membership;
- deleting a non-member role assignment must not alter membership;
- deleting a role moves assigned members back to `member`;
- `member` cannot be deleted.

Default role:

```toml
[workspace_team.<team>.roles.member]
display_name = "Member"
cao_tools = ["send_message", "handoff"]
```

The default `member` role grants no provider-mediated tools, no direct/custom
MCP servers, no inbox tools, no baton tools, no `assign`, and no `terminate`.

## Access Resolution

ToolService must ask the resolver for one agent's normalized access. The resolver
must choose exactly one active source:

```text
teamed   -> TeamRoleToolAccessSource
unteamed -> StandaloneAgentToolAccessSource
```

For teamed agents, standalone local grants are returned only as inactive
diagnostics/source markers. For unteamed agents, local grants remain active.

No consumer may implement its own team-versus-standalone check for effective
tool access.

## Normalized Result

The resolver result must include:

- built-in CAO MCP tools;
- direct/custom MCP servers;
- provider-mediated grant requests or provider grant specs;
- provider-backed inbox/conversation requirements for scoped inbox items;
- provider-native runtime capabilities as separate agent-owned runtime data;
- source markers;
- inactive local diagnostics;
- actionable invalid team/role diagnostics.

Provider-native runtime capabilities remain agent-owned. Team roles control MCP
tool access only.

## Affected Areas

Likely files/modules:

- `src/cli_agent_orchestrator/services/tool_service.py`
- `src/cli_agent_orchestrator/workspace_setups/manager.py`
- workspace team persistence/store code
- `src/cli_agent_orchestrator/agent.py` only for inactive local diagnostics and
  validation boundaries
- tests under `test/services/` and `test/workspace_setups/`

`workspace_setups/manager.py` may own persisted team and membership metadata.
It must not become a second effective access resolver.

## Acceptance Criteria

- ToolService has a centralized access resolution boundary, using
  `ToolAccessResolver`, `TeamRoleToolAccessSource`, and
  `StandaloneAgentToolAccessSource` or clearly documented equivalent names.
- ToolService chooses exactly one active source per agent: team role source for
  teamed agents and standalone local source for unteamed agents.
- Team role policy and role assignments persist through `WorkspaceTeamStore` /
  `workspace-teams.json`. They are not stored in agent TOML, Linear config, or a
  separate role file.
- Agent TOML keeps only team membership and standalone local grants. For teamed
  agents, local `cao_tools`, `mcp_servers`, `codex_config.mcp_servers`, and
  `[linear.tool_access.*]` appear only as inactive diagnostics/source markers.
- Unteamed agents keep first-class standalone local tool access.
- No production consumer implements its own effective team-versus-standalone
  access decision outside ToolService's access resolution boundary.
- Every team has a default `member` role that grants exactly `send_message` and
  `handoff` by default, grants no provider-mediated tools, no direct/custom MCP
  servers, no inbox tools, no baton tools, no `assign`, and no `terminate`.
- Role assignment semantics are implemented: missing assignment means `member`;
  assignments for non-members do not create membership; deleting a non-member
  assignment does not alter membership; deleting a role moves assigned members
  back to `member`; `member` cannot be deleted.
- Resolver output includes built-in CAO MCP tools, direct/custom MCP servers,
  provider-mediated grant requests/specs, provider-backed inbox requirements,
  provider-native runtime data as separate agent-owned runtime data, source
  markers, inactive local diagnostics, and actionable invalid team/role
  diagnostics.
- Tests prove teamed and unteamed access cannot be merged, including switching
  into a team, removing from a team, missing team/setup/role diagnostics,
  non-member assignment diagnostics, role deletion fallback, `member`
  immutability, and provider-native runtime capability separation.
- The implementation runs and records these commands, or a justified narrower
  replacement that covers the same owner surfaces:

```bash
uv run pytest test/services/test_tool_service.py test/workspace_setups -q
uv run python -m compileall -q src/cli_agent_orchestrator
```

- The implementer and reviewer run `uv run python scripts/catalog_criteria.py`,
  browse the `docs/criteria` catalog it reports, apply all applicable
  implementation and test criteria to this phase, and treat any violation as a
  blocking acceptance failure.
- Completion notes include concrete evidence for every acceptance criterion,
  including test commands, static checks if added, and any criteria catalog
  judgments.

## Completion Notes

### Criteria Catalog

- Ran `uv run python scripts/catalog_criteria.py`.
- Applied implementation criteria: `do-not-assume-backwards-compatibility`,
  `migration-discipline`, `minimal-cohesive-changes`,
  `no-test-only-production-seams`, `prefer-public-surfaces`,
  `system-definitions-are-localized`, and the always-on readability/simple
  system criteria.
- Applied test criteria: owner-surface verification, seam coverage,
  test-through-owner-surfaces, valid Given/When/Then structure, and artifact
  containment where persistence tests write a temporary team store.

### Acceptance Evidence

- ToolService now owns access resolution through `ToolAccessResolver`,
  `TeamRoleToolAccessSource`, and `StandaloneAgentToolAccessSource`.
- Teamed agents resolve through a role source only; unteamed agents resolve
  through standalone local grants. Teamed local `cao_tools`, `mcp_servers`,
  `codex_config.mcp_servers`, and `linear.tool_access` are inactive
  diagnostics/source markers only.
- `WorkspaceTeamStore` persists `roles` and `role_assignments` in
  `workspace-teams.json`; no role policy is written to agent TOML, Linear
  config, or a separate role file.
- Every team gets the default `member` role with exactly `send_message` and
  `handoff`, and no provider, direct MCP, inbox, baton, `assign`, or
  `terminate` grants.
- Role assignment semantics are implemented: missing assignments fall back to
  `member`, non-member assignments are diagnostic-only, deleting a role moves
  members back to `member`, and `member` is immutable.
- Resolver output includes built-in CAO tools, direct MCP servers, provider
  grant specs, provider-backed inbox requirements, provider-native runtime
  capabilities, source markers, inactive local diagnostics, and invalid
  team/role diagnostics.
- Owner tests cover teamed/unteamed switching, missing team/setup/role
  diagnostics, non-member assignment diagnostics, role deletion fallback,
  `member` immutability, provider-native runtime separation, and persistence.

### Verification Evidence

- `uv run pytest test/services/test_tool_service.py test/workspace_setups -q`
  passed as part of the broader final run.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- Broader final backend evidence: 1393 passed, 16 skipped, 1 deselected for the
  owner-surface command recorded in phase 04.

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

- Loop 1 after Revision 6: Bacon reported zero valid findings. Evidence:
  criteria catalog evaluated; `uv run pytest test/services/test_tool_service.py
  test/workspace_setups -q` passed with 38 tests; `uv run python -m
  compileall -q src/cli_agent_orchestrator` passed; provider-focused
  `test/linear/test_workspace_provider.py test/linear/test_workspace_setup_adapter.py
  test/workspace_providers -q` passed with 59 tests.
- Loop 2 after Revision 6: Bohr reported zero valid findings. Evidence:
  criteria catalog evaluated; `uv run pytest test/services/test_tool_service.py
  test/workspace_setups -q` passed with 38 tests; `uv run python -m
  compileall -q src/cli_agent_orchestrator` passed.
- Final broad backend evidence: 1393 passed, 16 skipped, 1 deselected.

## Review Revisions

### Revision 1 - Resolver Completeness And Role Semantics

- Reviewer finding: provider-backed inbox requirements, provider-native runtime
  data, and source markers were not normalized in the resolver result, and
  default members received provider conversation requirements without an
  explicit inbox grant.
- Validity decision: accepted. The phase requires complete normalized output,
  a default member role with no inbox tools, and ToolService as the single
  effective access authority.
- Fix: added resolver result fields for provider conversation requirements,
  runtime capabilities, and source markers; gated provider conversation
  requirements on the role's `read_inbox_message` /
  `reply_to_inbox_message` grants; added workspace team role persistence and
  assignment semantics tests.
- Verification evidence: focused tool service/workspace setup tests passed,
  followed by the final broad backend suite: 1393 passed, 16 skipped,
  1 deselected.

### Revision 2 - Resolver Diagnostic Assertions

- Reviewer finding: tests proved fail-closed behavior for missing
  team/setup/role and non-member assignments but did not directly assert the
  actionable resolver diagnostics required by the phase.
- Validity decision: accepted. Diagnostics are part of the normalized
  ToolService result shape and are explicit acceptance criteria.
- Fix: added direct owner-surface tests for missing team, missing setup,
  missing role assignment fallback, and inactive non-member assignment
  diagnostics.
- Verification evidence: `uv run pytest test/services/test_tool_service.py -q`
  passed with 23 tests; `uv run pytest test/services/test_tool_service.py
  test/workspace_setups -q` passed earlier with 31 tests.

### Revision 3 - Team Membership Transition Tests

- Reviewer finding: the suite did not directly prove the same agent switches
  active source when moved into a team and then removed from that team.
- Validity decision: accepted. The phase requires tests proving teamed and
  unteamed access cannot be merged, including switching into a team and
  removing from a team.
- Fix: added ToolService regression tests that resolve one agent as standalone,
  then teamed, then standalone again, asserting the active source and granted
  tools change exactly at the team membership boundary.
- Verification evidence: `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py -q` passed with 48 tests;
  final broad backend suite passed with 1393 passed, 16 skipped, 1 deselected.

### Revision 4 - Preserve Default Runtime Capabilities

- Reviewer finding: omitted `runtime_capabilities` were collapsed from `None`
  to `()`, causing `resolve_runtime_capabilities()` to treat omission as an
  explicit empty allowlist and drop default provider-native capabilities.
- Validity decision: accepted. Provider-native runtime data must remain
  separate agent-owned runtime data, and tests must prove that team role access
  does not erase omitted/default runtime capability semantics.
- Fix: the resolver now preserves `None` for omitted agent
  `runtime_capabilities` and only passes a tuple when the agent explicitly
  configured runtime capabilities; added standalone and teamed regressions that
  assert default runtime capabilities are retained while teamed local MCP
  grants stay inactive.
- Verification evidence: `uv run pytest test/services/test_tool_service.py -q`
  passed with 28 tests; `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py -q` passed with 48 tests;
  `uv run python -m compileall -q src/cli_agent_orchestrator` passed; final
  broad backend suite passed with 1393 passed, 16 skipped, 1 deselected.

### Revision 5 - Explicit Resolver Runtime Capability Contract

- Reviewer finding: `ToolAccessSourceResult.runtime_capabilities` still had a
  non-null tuple annotation even though Revision 4 intentionally preserves
  `None` to mean omitted runtime capabilities.
- Validity decision: accepted. The normalized resolver result must make the
  provider-native runtime capability omission/default distinction explicit and
  readable.
- Fix: updated the resolver result type annotation to
  `tuple[str, ...] | None`, matching the runtime capability input passed to
  `resolve_runtime_capabilities()`.
- Verification evidence: `uv run pytest test/services/test_tool_service.py
  test/workspace_setups -q` passed with 38 tests; `uv run python -m
  compileall -q src/cli_agent_orchestrator` passed.

### Revision 6 - Provider Source Selection Through Resolver Output

- Reviewer finding: provider-mediated access still used team/standalone
  checks outside the resolver: standalone provider grants were selected after
  resolution, and Linear skipped teamed local `tool_access` in provider config
  loading.
- Validity decision: accepted. The phase requires one active source decision
  inside ToolService's access resolution boundary, and no production consumer
  should perform its own effective team-versus-standalone access decision.
- Fix: added an explicit `provider_access_source` to
  `ToolAccessSourceResult`; ToolService now selects standalone local provider
  policies or team-role provider grants from that resolver output. Raw
  provider policy loading receives only agents whose resolver source is
  standalone, while Linear provider loading no longer performs a team-membership
  skip. Team-role Linear conversion initializes presence data without validating
  inactive local `linear.tool_access`.
- Verification evidence: `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_send_message.py test/mcp_server/test_workspace_setup_collaboration.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py -q` passed with 60 tests;
  `uv run pytest test/linear/test_workspace_provider.py
  test/linear/test_workspace_setup_adapter.py test/workspace_providers
  test/provider_conversations -q` passed with 91 tests; `uv run python -m
  compileall -q src/cli_agent_orchestrator` passed; final broad backend suite
  passed with 1393 passed, 16 skipped, 1 deselected.
