# 02 - Provider Role Access

Status: complete

## Goal

Move provider-mediated grant authoring for teamed agents into team role policy
while keeping provider vocabulary, schema, validation, conversion, and handlers
provider-owned.

## Scope

Implement role-owned provider access for Linear through ToolService's access
resolution boundary.

Preserve agent-local Linear tool access for unteamed agents.

## Rules

For teamed agents:

- role-owned provider grants are the only active provider-mediated grants;
- role-owned provider grants must reference providers in the team's workspace
  setup;
- each role-owned grant expands to concrete agent-scoped access for current team
  members assigned to that role;
- non-member assignments emit no usable provider access;
- missing Linear identity/presence emits an actionable diagnostic and no usable
  Linear tool;
- agent-local `[linear.tool_access.*]` is inactive diagnostics/raw config only.

For unteamed agents:

- existing agent-local `[linear.tool_access.*]` remains active and strictly
  validated.

## Linear Responsibilities

Linear remains owner of:

- tool vocabulary and descriptions;
- provider-specific fields such as issue/team/project/update-field scopes;
- validation of Linear access specs;
- conversion to provider-mediated tool definitions and handlers;
- provider identity/presence loading.

Linear must not decide that a teamed agent receives access. It validates and
converts the role-owned access selected by ToolService.

`has_provider_tool_access_config()` must not require agent-local
`[linear.tool_access.*]` to exist when team roles declare Linear access.

## Scoped Provider-Backed Inbox Items

CAO-owned inbox tools authorize scoped inbox operations. For a Linear-backed
inbox notification:

- `read_inbox_message` requires the CAO read tool grant plus recipient/provider
  identity validation for that exact notification;
- `reply_to_inbox_message` requires the CAO reply tool grant plus
  recipient/provider identity validation for that exact notification/thread;
- do not require a separate Linear provider-mediated tool grant for the exact
  scoped inbox item;
- require provider-mediated access only when a CAO tool performs broader Linear
  work outside the scoped inbox item.

Provider-backed notification body delivery must be authorized before the body is
delivered to the terminal.

## Affected Areas

Likely files/modules:

- `src/cli_agent_orchestrator/services/tool_service.py`
- `src/cli_agent_orchestrator/linear/workspace_provider.py`
- `src/cli_agent_orchestrator/linear/provider_tools.py`
- `src/cli_agent_orchestrator/linear/workspace_setup_adapter.py`
- `src/cli_agent_orchestrator/workspace_providers/registry.py`
- `src/cli_agent_orchestrator/workspace_providers/invocation.py`
- provider-conversation inbox authorization modules only as needed for scoped
  inbox item validation

## Acceptance Criteria

- For teamed agents, role-owned provider grants selected by ToolService are the
  only active provider-mediated grants.
- For teamed agents, agent-local `[linear.tool_access.*]` is inactive
  diagnostics/raw config only and cannot grant usable provider tools.
- For unteamed agents, existing agent-local `[linear.tool_access.*]` remains
  active, strictly validated, and usable.
- Linear initializes provider-mediated tools from team role grants even when no
  agent-local `[linear.tool_access.*]` exists.
- Linear remains owner of provider vocabulary, descriptions, provider-specific
  fields, validation, conversion to provider-mediated tool definitions and
  handlers, and provider identity/presence loading.
- Linear does not decide that a teamed agent receives access. It validates and
  converts the role-owned access selected by ToolService.
- Role-owned provider grants may reference only providers in the team's
  workspace setup. Grants outside the setup are rejected or diagnosed and never
  emitted as effective access.
- Each role-owned grant expands to concrete agent-scoped access for current team
  members assigned to that role. Two members on the same role receive separate
  agent-scoped access.
- Non-member assignments emit no usable provider access and do not create team
  membership.
- Missing Linear identity/presence emits an actionable diagnostic and no usable
  Linear tool.
- Provider-mediated invocation rechecks current ToolService access before
  executing.
- CAO-owned scoped inbox tools authorize Linear-backed inbox operations through
  CAO inbox grants plus recipient/provider identity validation for the exact
  notification or thread. A separate Linear provider-mediated grant is not
  required for that exact scoped inbox item.
- Provider-backed notification body delivery is authorized before the body is
  delivered to the terminal.
- Broader Linear work outside a scoped inbox item still requires appropriate
  provider-mediated access.
- The implementation runs and records these commands, or a justified narrower
  replacement that covers the same owner surfaces:

```bash
uv run pytest test/services/test_tool_service.py test/linear test/workspace_providers test/provider_conversations -q
uv run python -m compileall -q src/cli_agent_orchestrator
```

- The implementation runs and records this static audit:

```bash
rg "agent\\.linear\\.tool_access|LinearToolAccessConfig|_linear_tool_access_from_agent|has_provider_tool_access_config|provider_tool_access|TeamRoleToolAccessSource|StandaloneAgentToolAccessSource|ToolAccessResolver" src test
```

Every production hit must be classified as ToolService access resolution,
provider-owned vocabulary/schema/validation, standalone unteamed parsing,
inactive teamed diagnostics, raw config display/edit, or non-authority code.
- The implementer and reviewer run `uv run python scripts/catalog_criteria.py`,
  browse the `docs/criteria` catalog it reports, apply all applicable
  implementation and test criteria to this phase, and treat any violation as a
  blocking acceptance failure.
- Completion notes include concrete evidence for every acceptance criterion,
  including test commands, audit classifications, and criteria catalog
  judgments.

## Completion Notes

### Criteria Catalog

- Ran `uv run python scripts/catalog_criteria.py`.
- Applied implementation criteria for migration discipline, public owner
  surfaces, no test-only seams, no backwards-compatibility assumption, and
  localized system definitions.
- Applied test criteria for owner-surface behavior, seam verification,
  target behavior not mocked, and tests through provider/ToolService owner
  boundaries.

### Acceptance Evidence

- Teamed Linear provider access is selected by ToolService from role-owned
  provider grant specs. Agent-local `[linear.tool_access.*]` remains active
  only for unteamed agents and is inactive diagnostics/raw config for teamed
  agents.
- Linear still owns tool vocabulary, descriptions, provider fields, schema,
  validation, conversion to provider-mediated tool definitions/handlers, and
  identity/presence loading. ToolService decides which role grants are active;
  Linear only validates and converts selected grants.
- Role provider grants are limited to providers in the team's workspace setup.
  Non-member assignments and missing Linear presence emit diagnostics and do
  not yield usable provider tools.
- Two members assigned to the same role expand to separate agent-scoped Linear
  access entries.
- Provider-mediated invocation rechecks current ToolService access before
  execution.
- Provider-backed inbox preview/read/reply authorization is now ToolService
  driven and requires CAO inbox grants plus provider identity for the scoped
  notification/thread, without requiring a broader Linear provider grant.
- Broader Linear work still requires a provider-mediated grant.

### Verification Evidence

- `uv run pytest test/services/test_tool_service.py test/linear test/workspace_providers test/provider_conversations -q`
  passed as part of the final broad backend suite.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- Final broad backend evidence: 1393 passed, 16 skipped, 1 deselected.
- Static audit command ran:
  `rg "agent\\.linear\\.tool_access|LinearToolAccessConfig|_linear_tool_access_from_agent|has_provider_tool_access_config|provider_tool_access|TeamRoleToolAccessSource|StandaloneAgentToolAccessSource|ToolAccessResolver" src test`.

### Audit Classification

- `services/tool_service.py`: ToolService authority, inactive teamed local
  diagnostics, standalone unteamed parsing, and provider role policy loading.
- `linear/workspace_provider.py` and `linear/provider_tools.py`:
  provider-owned vocabulary, schema, validation, and conversion.
- `workspace_providers/*`: provider registry/invocation contracts and
  current ToolService recheck.
- `agent.py`, `api/main.py`, `web/src/api.ts`, and dashboard tests:
  raw config display/edit or persistence models, not production authority for
  effective teamed access.
- `test/*`: regression coverage for standalone local access, role grants,
  provider expansion, missing presence diagnostics, and scoped inbox behavior.

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

- Loop 1 after Revision 2: Russell reported zero valid findings against phase
  02 acceptance criteria and applicable criteria catalog items.
- Loop 2 after Revision 2: Pascal reported zero valid findings. Evidence:
  criteria catalog evaluated; static provider access audit checked;
  provider-focused verification passed; inbox-focused verification passed.
- Follow-up review finding after completion: `activity` was incorrectly
  registered from `read_inbox_message`. Revision 3 records the accepted fix.
- Follow-up runtime verification found the Linear vertical-path test was missing
  a real ToolService-backed preview authorization setup. Revision 4 records the
  accepted test correction.
- Post-Revision 4 evidence: `uv run pytest test/services/test_tool_service.py
  test/linear test/workspace_providers test/provider_conversations
  test/services/test_linear_agent_runtime_service.py -q` passed with 263 tests;
  `git diff --check` passed; `uv run python -m compileall -q
  src/cli_agent_orchestrator` passed.
- Loop 1 after Revision 4: Franklin reported zero valid findings against the
  scoped inbox versus broader Linear activity boundary and applicable criteria.
- Loop 2 after Revision 4: Kant reported zero valid findings against the same
  follow-up scope and criteria.
- Final broad backend evidence: 1393 passed, 16 skipped, 1 deselected.

## Review Revisions

### Revision 1 - Provider Grant Conversion And Coverage

- Reviewer finding: Linear role grant boolean conversion used `bool(...)`,
  so non-boolean values such as `"false"` broadened to `true`; provider
  expansion/missing-presence coverage was incomplete.
- Validity decision: accepted. Linear must strictly validate provider-specific
  fields and missing presence must produce diagnostics without usable tools.
- Fix: added strict role boolean validation, two-member expansion coverage,
  missing-presence/no-tool diagnostics coverage, and invalid provider field
  regression tests.
- Verification evidence: focused and broad backend suites passed; final broad
  result was 1393 passed, 16 skipped, 1 deselected.

### Revision 2 - Teamed Linear Local Grant Deactivation

- Reviewer finding: Linear provider initialization still loaded and validated
  agent-local `[linear.tool_access.*]` for teamed agents before ToolService
  converted role-owned grants, so stale invalid local config could block valid
  team-role Linear access.
- Validity decision: accepted. Teamed agent-local Linear tool access is raw
  standalone fallback/diagnostics only and must not affect usable provider
  tools.
- Fix: `load_linear_provider_config()` now skips local Linear tool-access
  entries for teamed agents while preserving Linear presence identity; added a
  ToolService regression proving invalid teamed local Linear access remains
  inactive while role-owned `cao_linear.list_teams` is granted.
- Verification evidence: `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_tool_filtering.py
  test/services/test_builtin_skill_guidance.py -q` passed with 48 tests;
  final broad backend suite passed with 1393 passed, 16 skipped, 1 deselected.

### Revision 3 - Provider Activity Permission Separation

- Reviewer finding: Linear declares provider-conversation `activity`, and
  ToolService mapped every non-`reply` provider-conversation operation to
  `read_inbox_message`, so a scoped inbox read grant accidentally authorized
  broader Linear AgentActivity posting.
- Validity decision: accepted. Phase 02 requires scoped inbox grants to cover
  only exact inbox-item operations; broader Linear work outside that item must
  require separate authority.
- Fix: provider-conversation operations now use an explicit mapping:
  `preview`/`read` require `read_inbox_message`, `reply` requires
  `reply_to_inbox_message`, and `activity` requires the separate internal CAO
  permission `post_provider_activity`.
- Verification evidence: added ToolService regressions proving
  `read_inbox_message` alone does not register `activity`, while
  `post_provider_activity` does; focused activity tests passed.

### Revision 4 - Runtime Preview Authorization Test Coverage

- Reviewer finding: a broader Linear runtime check failed because the vertical
  AgentSession path exercised real provider preview authorization, but the test
  fixture had only patched lifecycle activity authorization and had no
  ToolService-backed team role granting scoped inbox preview access.
- Validity decision: accepted. Provider-backed notification body delivery must
  be authorized before delivery, and the vertical path should prove that through
  the same ToolService authority rather than a missing or mocked setup.
- Fix: the vertical Linear runtime test now installs a real ToolService with a
  team role granting `read_inbox_message` and Linear provider-conversation
  `preview`/`read` requirements, while leaving the existing lifecycle activity
  posting mock scoped to that separate concern.
- Verification evidence: `uv run pytest test/linear/test_monitor.py
  test/services/test_linear_agent_runtime_service.py -q` passed with 37 tests;
  the broader phase-owner suite passed with 263 tests.
