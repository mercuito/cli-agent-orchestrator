# 03 - Dashboard Role Management

Status: complete

## Goal

Expose team role tool access in the dashboard and API without making the
frontend a source of tool vocabulary or access authority.

## Scope

Implement:

- API surfaces to read/update team roles and role assignments;
- backend descriptor surfaces for grantable built-in CAO tools;
- backend/provider-owned descriptor surfaces for role-owned provider access;
- dashboard team UI for role management;
- agent UI inherited access display;
- read-only/inactive treatment of teamed agent-local access.

## API Rules

Team role APIs must preserve existing team metadata and must not accidentally
drop roles, assignments, `cao_tools`, provider access, or role-owned
`mcp_servers`.

The API reads and writes role policy through the existing workspace team
persistence owner, `WorkspaceTeamStore` / `workspace-teams.json`. It must not
introduce an independent role file or persist effective access into agent TOML.

Provider role-access schema APIs must be namespaced separately from CLI
provider/model catalog APIs. Use an explicit workspace-provider namespace such
as:

```text
/workspace-providers/{provider}/role-access-schema
```

Do not overload existing `/providers` semantics.

## Dashboard Rules

The dashboard must show the authority model plainly:

- Teams tab edits team role access.
- Agent detail shows inherited effective access for teamed agents.
- Agent-local access controls are read-only/disabled or clearly labeled
  inactive for teamed agents.
- Agent-local access remains editable for unteamed agents.
- Raw `agent.toml` edit/preview must not present inactive teamed sections as
  effective access. If editing remains allowed, copy must state the changes
  affect only standalone fallback behavior after leaving the team.
- Running agents show restart/stale messaging when effective MCP surface changes
  require terminal reload/resume.

The dashboard must not hard-code Linear tool names, Linear access fields, or
built-in CAO tool descriptors. It consumes backend descriptors.

## Affected Areas

Likely files/modules:

- `src/cli_agent_orchestrator/api/main.py`
- team/workspace setup persistence code
- built-in CAO tool descriptor module/API
- workspace-provider role schema API
- `web/src/api.ts`
- `web/src/components/agents-tab/*`
- dashboard team tab/components
- `web/vite.config.ts`

## Acceptance Criteria

- API surfaces can read and update team roles and role assignments through
  `WorkspaceTeamStore` / `workspace-teams.json`.
- Team role create/update preserves existing team metadata, roles,
  assignments, `cao_tools`, provider access, and role-owned `mcp_servers`.
- No API path introduces an independent role file or persists effective team
  role access into agent TOML.
- Provider role-access schema APIs are namespaced separately from CLI
  provider/model catalog APIs, using an explicit workspace-provider namespace.
- Built-in CAO tool descriptors and provider role-access descriptors are served
  by the backend. The dashboard does not hard-code Linear tool names, Linear
  access fields, or built-in CAO tool descriptors.
- The Teams tab can create/edit roles, configure role-owned tool access, and
  assign roles to team members.
- Assigning a role to a member updates effective access. Assigning a role to a
  non-member does not create membership.
- The default `member` role appears in the API/dashboard as a normal role while
  still respecting the core rule that it cannot be deleted.
- Agent detail shows inherited effective access for teamed agents.
- Agent-local access controls are read-only, disabled, or clearly labeled
  inactive for teamed agents.
- Agent-local access remains editable for unteamed agents.
- Raw `agent.toml` edit/preview cannot confuse inactive teamed sections with
  effective access. If editing remains allowed, copy states that changes affect
  only standalone fallback behavior after leaving the team.
- Running agents show restart/stale messaging when effective MCP surface changes
  require terminal reload/resume.
- The Vite dev proxy forwards new role/schema API prefixes.
- The implementation runs and records these commands, or a justified narrower
  replacement that covers the same API and frontend surfaces:

```bash
uv run pytest test/api -q
cd web && npm test -- src/test/agent-detail-panel.test.tsx src/test/agent-config-tab.test.tsx
cd web && npm run build
```

- Safari verification against the served dashboard proves create/edit role,
  assign an agent to a role, effective access display changes in the agent
  detail panel, teamed local controls are inactive, unteamed local controls
  remain editable, and stale/restart messaging appears when applicable.
- The implementer and reviewer run `uv run python scripts/catalog_criteria.py`,
  browse the `docs/criteria` catalog it reports, apply all applicable
  implementation and test criteria to this phase, and treat any violation as a
  blocking acceptance failure.
- Completion notes include concrete evidence for every acceptance criterion,
  including test commands, Safari verification, and criteria catalog judgments.

## Completion Notes

### Criteria Catalog

- Ran `uv run python scripts/catalog_criteria.py`.
- Applied implementation criteria for authoritative source references,
  minimal cohesive changes, public surfaces, readable explicit code, and
  localized definitions.
- Applied test criteria for owner-surface API tests, dashboard behavior tests,
  and `ui-changes-require-real-browser-verification`.

### Acceptance Evidence

- API read/update surfaces expose roles and role assignments through
  `WorkspaceTeamStore` / `workspace-teams.json`, preserving team metadata,
  role fields, assignments, CAO tools, provider access, and role MCP servers.
- No role file was introduced and no effective team role access is persisted
  into agent TOML.
- Provider role schema APIs live under
  `/workspace-providers/{provider}/role-access-schema`, separate from CLI
  provider/model catalog APIs.
- Backend descriptor endpoints serve CAO tool descriptors and Linear
  role-access descriptors; dashboard role editing consumes those descriptors
  rather than hard-coding Linear tool names, Linear fields, or CAO tool
  descriptions.
- Teams tab creates/edits roles, configures role-owned CAO/provider access, and
  assigns roles. Assigning a role to a non-member remains a non-member
  diagnostic and does not create membership.
- Agent detail shows inherited effective ToolService/MCP access for teamed
  agents and restart messaging for running terminals.
- Agent config shows inactive-local copy for teamed local grants and keeps
  standalone raw local config editable for unteamed agents.
- Vite proxies include `/cao-tools`, `/workspace-setups`, `/workspace-teams`,
  `/workspace-providers`, and `/providers`.

### Verification Evidence

- `uv run pytest test/api -q` passed as part of the final broad backend suite.
- `cd web && npm test -- src/test/workspace-teams-panel.test.tsx src/test/agent-config-tab.test.tsx src/test/agent-detail-panel.test.tsx`
  passed: 33 tests.
- `cd web && npm run build` passed.
- Real Safari WebDriver verification against `http://localhost:5173` passed:
  role `role_2` was created/edited with Linear `cao_linear.get_issue`, the
  role was assigned to `implementation_partner`, `outsider_agent` remained a
  non-member, agent detail showed `cao_linear.get_issue` with source marker
  `linear:workspace_team.cao_delivery.roles.role_2.providers.linear.default`,
  running-agent restart messaging appeared, standalone local controls were
  editable for `discovery_partner`, and teamed local grants were labeled
  inactive after temporarily assigning `discovery_partner` to the team.
- Safari screenshot evidence: `/tmp/cao-role-dashboard-safari.png`.
- Temporary verification edits were restored to the prior `cao_delivery` team
  and `discovery_partner` workspace membership.

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

- Loop 1 after Revision 2: Kuhn reported zero valid findings against phase 03
  acceptance criteria and applicable criteria catalog items.
- Loop 2 after Revision 2: Pauli reported zero valid findings. Evidence:
  API/store/dashboard surfaces inspected; focused API and frontend tests
  checked; real Safari dashboard workflow evidence reviewed.
- Final frontend verification: `npm test --
  src/test/workspace-teams-panel.test.tsx src/test/agent-config-tab.test.tsx
  src/test/agent-detail-panel.test.tsx` passed with 33 tests, and
  `npm run build` passed.
- Final broad backend evidence: 1393 passed, 16 skipped, 1 deselected.

## Review Revisions

### Revision 1 - Dashboard Provider Fields And Real Store Coverage

- Reviewer finding: provider role field controls were incomplete; Vite did not
  proxy every needed prefix; API tests mocked the team service and did not
  verify role round-tripping through the real `WorkspaceTeamStore`.
- Validity decision: accepted. The phase requires provider-owned descriptors,
  real persistence owner coverage, Vite proxy support, and browser evidence.
- Fix: added descriptor-driven provider field rendering, `/providers` dev
  proxy coverage, a real-store API round-trip test, and real Safari dashboard
  verification evidence.
- Verification evidence: API/web tests and build passed; Safari WebDriver
  workflow passed with the evidence listed above.

### Revision 2 - Teamed Raw Local Fallback Copy

- Reviewer finding: teamed agents with no existing local grants could still
  edit raw `agent.toml` without fallback-only copy, which could imply those
  edits affect current effective access.
- Validity decision: accepted. The phase requires raw config edit/preview to
  avoid presenting inactive teamed sections as effective access.
- Fix: Agent config now shows standalone-fallback copy for every teamed agent
  in raw local access editing, regardless of whether inactive local grants are
  already present; added a frontend regression for teamed agents without local
  grants.
- Verification evidence: `cd web && npm test --
  src/test/workspace-teams-panel.test.tsx src/test/agent-config-tab.test.tsx
  src/test/agent-detail-panel.test.tsx` passed with 33 tests, and
  `cd web && npm run build` passed.
