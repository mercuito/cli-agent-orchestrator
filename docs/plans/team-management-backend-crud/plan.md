# Team Management Backend CRUD

Status: draft

## Goal

Provide backend-owned CRUD surfaces for workspace teams, team roles, and team
membership so the dashboard can manage teams without editing whole
`workspace-teams.json` payloads or coordinating agent config writes itself.

This plan prepares the backend for a later Teams tab redesign. The backend must
make the normal UI actions first-class:

- create, edit, read, and delete teams;
- create, edit, read, and delete roles on a team;
- assign an agent to a team;
- remove an agent from a team;
- change a team member's role;
- expose enough team/member/role detail for the UI to render the current state.

## Current State

- `GET /workspace-teams` lists persisted teams.
- `PUT /workspace-teams/{team_id}` creates or updates a whole team payload.
- `GET /workspaces` lists code-owned workspaces.
- Team definitions and role policy live in `WorkspaceTeamStore` /
  `workspace-teams.json`.
- Agent membership lives in agent config at `agent.workspace.team`.
- `role_assignments` are role policy only. They do not make an agent a team
  member.
- `WorkspaceTeamService` already has role assignment helpers, but they do not
  atomically update agent membership.

That means the dashboard currently has to coordinate multiple concepts itself:
team persistence, role assignment, and agent membership. The backend should own
that coordination.

## Non-Goals

- Do not implement the Teams tab redesign in this plan.
- Do not add workspace CRUD or a workspace editor. Workspaces
  remain code-owned and selectable through the existing workspace registry/list
  API.
- Do not change `ToolService` authority, effective access resolution, MCP
  materialization, provider conversation rules, or cross-team messaging policy.
- Do not introduce a second team, role, or membership persistence owner.
- Do not persist effective access into agent TOML.

## Conceptual Model

An agent belongs to zero or one workspace team.

The source of team membership remains `agent.workspace.team`. A workspace team
owns role policy and role assignments, but a role assignment is meaningful only
for an agent whose `agent.workspace.team` points at that team.

The backend team management API must preserve this model. UI code should not
need to know that membership is in agent config while role assignments are in
`workspace-teams.json`; it should call one backend operation for the user action.

## Proposed API

Add explicit team detail and CRUD endpoints:

```text
GET    /workspace-teams/{team_id}
POST   /workspace-teams
PUT    /workspace-teams/{team_id}
DELETE /workspace-teams/{team_id}
```

`POST /workspace-teams` creates a team with a valid workspace and the
default `member` role. `PUT /workspace-teams/{team_id}` updates team metadata and
workspace selection without requiring the caller to resubmit unrelated
role policy or role assignments. Deleting a team rejects while any agent is a
member of that team.

Add explicit role endpoints:

```text
PUT    /workspace-teams/{team_id}/roles/{role_id}
DELETE /workspace-teams/{team_id}/roles/{role_id}
```

`PUT` creates or updates one role. `DELETE` removes one role and falls assigned
agents back to `member`. The default `member` role cannot be deleted.

Add explicit member endpoints:

```text
PUT    /workspace-teams/{team_id}/members/{agent_id}
DELETE /workspace-teams/{team_id}/members/{agent_id}
```

`PUT` assigns the agent to the team and optionally sets its role. If the agent
already belongs to a different team, the operation moves it by clearing stale
role assignment state from the old team and setting `agent.workspace.team` to
the new team. `DELETE` removes the agent from the team and clears that team's
role assignment for the agent.

The member endpoint is the only dashboard-facing operation that changes team
membership. It must be idempotent and must validate the target team, agent, role,
and workspace before writing.

## Response Shape

Team responses must expose enough detail for the future Teams UI to render
without deriving authority itself:

- team id, display name, and workspace id;
- roles and role configuration;
- role assignments;
- member ids;
- member details with at least agent id, display name, current role id, and
  whether the role is explicitly assigned or defaulting to `member`;
- diagnostics relevant to the team.

Existing fields may remain, but new UI code should consume the richer member
detail shape rather than inferring member role state from separate lists.

## Implementation Tasks

1. Extend the team store/service owner.
   - Add store delete support.
   - Add service methods for team create, metadata/workspace update, delete,
     single-role create/update, single-role delete, member assign/move, and
     member removal.
   - Keep validation and normalization inside the service/store owner.

2. Add atomic membership coordination.
   - Use the existing public agent config read/write path instead of direct file
     mutation from API route code.
   - Validate all inputs before writes.
   - Avoid partial writes. If a multi-file operation cannot be made truly
     transactional, write in the safest order and include rollback or explicit
     cleanup for stale old-team role assignment state.

3. Add API models and routes.
   - Add request/response models for team create/update, role create/update,
     and member assignment.
   - Route handlers should delegate to service methods and avoid duplicating
     storage rules.
   - Convert service validation failures to clear `400` or `404` responses with
     actionable messages.

4. Preserve and narrow legacy surfaces.
   - Existing whole-team `PUT /workspace-teams/{team_id}` must not remain the
     primary dashboard mutation path for roles or membership.
   - If retained, it must share the same service validation and must not allow
     omitted fields to accidentally erase roles, assignments, or members.
   - Dashboard/API client code should move to the explicit CRUD endpoints when
     this plan includes client updates.

5. Test through owner surfaces.
   - Add service/store tests for each new behavior.
   - Add API tests for successful CRUD flows and rejection paths.
   - Test moving an agent between teams, removing a member, deleting a role with
     fallback to `member`, rejecting deletion of `member`, and rejecting team
     deletion while members exist.
   - Test that role assignment alone does not create membership.

## Definition of Done

This is the single authoritative acceptance section for this plan.

- Team CRUD endpoints exist and are backed by `WorkspaceTeamService` /
  `WorkspaceTeamStore`; route handlers do not mutate team files directly.
- Role CRUD endpoints exist and mutate one role at a time without requiring the
  caller to resubmit unrelated roles or assignments.
- The default `member` role is always present and cannot be deleted.
- Deleting a non-default role falls all assignments for that role back to
  `member`.
- Member assignment/removal endpoints exist and are the dashboard-facing way to
  change team membership.
- Assigning a member updates `agent.workspace.team` and the team's role
  assignment state through one service-owned operation.
- Removing a member clears `agent.workspace.team` when it points at that team
  and clears that team's role assignment for the agent.
- Moving an agent between teams leaves the agent in exactly one team and removes
  stale role assignment state from the previous team.
- Role assignments for non-members remain diagnostics-only and never create
  membership.
- Team deletion rejects while any agent is a member of the team.
- Team workspace updates validate that the workspace exists, but this plan
  does not introduce workspace CRUD.
- Team responses include member detail with effective/default role information
  sufficient for the future Teams UI.
- Existing whole-team upsert behavior is either replaced for dashboard usage or
  made safe through the same service validation; it must not remain an
  accidental bypass around the new CRUD rules.
- No new team, role, membership, or effective-access persistence owner is
  introduced.
- `ToolService` effective access behavior remains unchanged except for consuming
  cleaner team membership/role state produced by these APIs.
- Tests verify the behavior through service/store and HTTP API owner surfaces;
  target behavior must not be mocked.
- The implementer runs `uv run python scripts/catalog_criteria.py`, browses the
  `docs/criteria` catalog it reports, applies all applicable implementation and
  test criteria to this plan, and treats any violation as a blocking acceptance
  failure.
- Completion notes record concrete evidence for every acceptance criterion,
  including commands run, relevant test names, and criteria catalog judgments.

Expected verification commands:

```bash
uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q
uv run pytest test/services/test_tool_service.py test/mcp_server/test_workspace_collaboration.py -q
uv run python -m compileall -q src/cli_agent_orchestrator
uv run python scripts/catalog_criteria.py
```

If implementation scope touches the web API client or dashboard code, frontend
tests and real browser verification become required by the applicable
`docs/criteria` catalog entries. If this remains backend-only, no Safari
verification is required for this plan.

## Review Gate

After implementation, the implementer must run a review loop. The reviewer must
compare the landed implementation strictly against each item in `Definition of
Done`, plus all applicable `docs/criteria` catalog criteria.

Any valid finding confirmed by the implementer must be fixed, then the review
loop must restart with a fresh reviewer.

For every review finding that requires an implementation change, the implementer
must update `Review Revisions` before restarting the loop. Add a new subsection
for each such revision, recording what the reviewer found, why the implementer
accepted it as valid, how it was fixed, and what evidence verifies the fix.

This plan is complete only after two successive review loops report zero valid
findings.

## Completion Notes

Implementation verification recorded 2026-05-19.

### Definition of Done Evidence

- Team CRUD endpoints are implemented in `src/cli_agent_orchestrator/api/main.py`:
  `GET /workspace-teams/{team_id}`, `POST /workspace-teams`,
  metadata-only `PUT /workspace-teams/{team_id}`, and
  `DELETE /workspace-teams/{team_id}`. Route handlers delegate to
  `WorkspaceTeamService`; no route mutates `workspace-teams.json` directly.
- Role CRUD endpoints are implemented as
  `PUT /workspace-teams/{team_id}/roles/{role_id}` and
  `DELETE /workspace-teams/{team_id}/roles/{role_id}`. `put_role` mutates one
  role while preserving unrelated roles and assignments, verified by
  `test_team_service_put_role_mutates_one_role_without_resubmitting_policy` and
  `test_workspace_team_role_api_round_trips_single_role_policy_through_store`.
- The default `member` role remains injected by `WorkspaceTeam.__post_init__`
  and is returned with `deletable: false`; deleting it is rejected by
  `WorkspaceTeam.without_role`, verified by
  `test_team_role_assignment_and_deletion_semantics` and
  `test_workspace_team_api_rejects_member_role_and_member_team_deletion`.
- Deleting a non-default role falls assignments back to `member` through
  `WorkspaceTeam.without_role`, verified by
  `test_team_role_assignment_and_deletion_semantics` and
  `test_workspace_team_role_delete_api_falls_assignments_back_to_member`.
- Member assignment/removal endpoints are implemented as
  `PUT /workspace-teams/{team_id}/members/{agent_id}` and
  `DELETE /workspace-teams/{team_id}/members/{agent_id}`. They are the new
  dashboard-facing membership write surface.
- Assigning a member writes `agent.workspace.team` through `patch_agent_config`
  and updates the target team's role assignment in one service-owned operation,
  verified by
  `test_team_service_assigns_member_through_agent_config_and_role_assignment`.
- Removing a member clears `agent.workspace.team` when it points at the team
  and clears that team's role assignment, verified by
  `test_team_service_removes_member_and_clears_team_role_assignment` and
  `test_workspace_team_member_remove_api_clears_membership_and_assignment`.
- Moving an agent between teams leaves exactly one team membership and clears
  stale old-team role assignments, verified by
  `test_team_service_moves_member_and_clears_old_role_assignment` and
  `test_workspace_team_member_api_moves_agent_and_returns_member_detail`.
- Role assignments for non-members remain diagnostics-only and do not create
  membership; `assign_role` remains role-policy-only and member CRUD owns
  membership writes. Verified by
  `test_role_assignment_alone_does_not_create_team_membership` and existing
  `ToolService` tests in `test/services/test_tool_service.py`.
- Team deletion rejects while any agent is a member of the team, verified by
  `test_team_service_deletes_empty_team_and_rejects_member_team_deletion` and
  `test_workspace_team_api_rejects_member_role_and_member_team_deletion`.
- Team workspace create/update paths validate workspace existence through
  `WorkspaceRegistry.get`; no workspace CRUD was added.
- Team responses now include `member_details` with `agent_id`, `display_name`,
  effective `role_id`, and `role_explicitly_assigned`, verified by
  `test_workspace_team_member_api_moves_agent_and_returns_member_detail`.
- Existing whole-team upsert was narrowed to metadata-only PUT with extra
  fields rejected, so it cannot bypass role or membership CRUD. Verified by
  `test_workspace_team_metadata_put_rejects_legacy_role_policy_payload`.
- Agent HTTP create/update routes reject direct `workspace.team` writes, so
  `/agents` cannot bypass service-owned member assignment/removal/move. Verified
  by `test_update_agent_rejects_direct_workspace_team_mutation` and
  `test_create_agent_rejects_direct_workspace_team_membership`.
- No new team, role, membership, or effective-access persistence owner was
  introduced. Team/role policy stays in `WorkspaceTeamStore`; membership stays
  in `agent.workspace.team`; effective access remains computed by existing
  services.
- `ToolService` effective access code was not changed. Existing behavior was
  reverified by `uv run pytest test/services/test_tool_service.py
  test/mcp_server/test_workspace_collaboration.py -q`.
- Tests verify service/store and HTTP API owner surfaces without mocking target
  behavior. Agent membership tests write real temporary agent config files via
  `write_agent` and inspect them via `load_agent`.
- Criteria catalog was run and applicable criteria were applied. Applicable
  implementation criteria: minimal cohesive changes, migration discipline,
  prefer public surfaces, system definitions localized, no test-only production
  seams, no unnecessary duplication, readable/simple/system-local code,
  parallel-safe execution, and backwards-compatibility discipline. Applicable
  test criteria: behavior verified through owner surfaces, target behavior not
  mocked, test artifacts contained in `tmp_path`, and given/when/then structure.
  Frontend/browser criteria were judged not applicable because no dashboard or
  web client code was changed.

### Verification Commands

- `uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q`
  passed: 58 tests.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_workspace_collaboration.py -q`
  passed: 35 tests.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- `uv run python scripts/catalog_criteria.py` passed and reported the criteria
  catalog reviewed above.

## Review Revisions

### Revision 1: Refresh Reused File-Backed Service Agent Registry

Reviewer 1 found that a reused default-style `WorkspaceTeamService` could assign
an agent to a team and then delete that team because the in-memory
`AgentRegistry` was stale after `patch_agent_config`. I accepted this as valid
because it violated the DoD requirement that team deletion rejects while any
agent is a member and could leave `agent.workspace.team` pointing at a deleted
team.

The fix marks the service registry as file-backed after any agent config load
for a member write, then refreshes the registry from the same agent config root
before membership-sensitive deletion checks. Regression coverage was added in
`test_reused_default_root_team_service_rejects_delete_after_member_assignment`.

Evidence after the fix:

- `uv run pytest test/workspaces/test_workspace_manager.py -q`
  passed.

### Revision 2: Forbid Agent Route Membership Bypass

Reviewer 2 found that `PUT /agents/{agent_id}` still accepted
`workspace.team`, which could move or remove an agent from a team without
delegating through `WorkspaceTeamService` and without clearing stale role
assignments. I accepted this as valid because it violated the DoD requirement
that member assignment/removal endpoints are the dashboard-facing way to change
team membership and that moves are service-owned.

The fix rejects direct `workspace.team` writes in HTTP agent create/update
requests and tells callers to use
`/workspace-teams/{team_id}/members/{agent_id}` instead. Regression coverage was
added in `test_update_agent_rejects_direct_workspace_team_mutation` and
`test_create_agent_rejects_direct_workspace_team_membership`.

Evidence after the fix:

- `uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q`
  passed: 58 tests.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_workspace_collaboration.py -q`
  passed: 35 tests.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- `uv run python scripts/catalog_criteria.py` passed.

### Revision 3: Inject Agent Root into Default Team Service

Reviewer 3 found that `WorkspaceTeamService` could still fall back to the
process-global agent root during member writes because the default team service
factory did not accept or pass an explicit `agents_root`. I accepted this as
valid because it violated the `no-global-state-reads` criterion and could
mismatch an injected `AgentRegistry` from one root with member writes against a
different process-default root.

The fix adds an explicit `agents_root` parameter to
`default_workspace_team_service`, resolves the default root at that boundary,
passes the root to both `load_agent_registry` and `WorkspaceTeamService`, and
prevents `WorkspaceTeamService` member writes from calling agent persistence
without an injected root. Regression coverage was added in
`test_default_team_service_uses_injected_agents_root_for_member_writes`.

Evidence after the fix:

- `uv run pytest test/workspaces/test_workspace_manager.py::test_default_team_service_uses_injected_agents_root_for_member_writes test/workspaces/test_workspace_manager.py::test_reused_default_root_team_service_rejects_delete_after_member_assignment -q`
  passed: 2 tests.
- `uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q`
  passed: 58 tests.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_workspace_collaboration.py -q`
  passed: 35 tests.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- `uv run python scripts/catalog_criteria.py` passed.

## Review Gate Results

### Fresh Review 1

Reviewer 1 reported zero valid findings. Non-blocking residual notes were that
the reviewer did not rerun the full pytest suites during review, and that extra
failure-injection coverage around rollback during multi-file member moves plus
explicit unknown-role deletion coverage could be useful. The reviewer judged
these notes non-blocking for the Definition of Done.

### Fresh Review 2

Reviewer 2 reported zero valid findings. The reviewer independently reran the
full verification set and `git diff --check` for touched paths:

- `uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q`
  passed: 57 tests.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_workspace_collaboration.py -q`
  passed: 35 tests.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- `uv run python scripts/catalog_criteria.py` passed.
- `git diff --check` for touched paths passed.

The same optional coverage notes were judged non-blocking. This review gate was
superseded by Revision 3 and restarted.

### Fresh Review 3

Reviewer 3 reported zero valid findings after Revision 3. The reviewer reran:

- `uv run pytest test/workspaces/test_workspace_manager.py::test_default_team_service_uses_injected_agents_root_for_member_writes test/workspaces/test_workspace_manager.py::test_reused_default_root_team_service_rejects_delete_after_member_assignment -q`
  passed.
- `uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q`
  passed: 58 tests.
- `uv run python scripts/catalog_criteria.py` passed.
- `git diff --check` for touched paths passed.

Non-blocking residual notes were the same optional failure-injection and
unknown-role delete coverage ideas, plus that this reviewer did not rerun the
ToolService/collaboration suite or compileall during review.

### Fresh Review 4

Reviewer 4 reported zero valid findings after Revision 3. The reviewer reran:

- `uv run pytest test/workspaces/test_workspace_manager.py::test_default_team_service_uses_injected_agents_root_for_member_writes test/workspaces/test_workspace_manager.py::test_reused_default_root_team_service_rejects_delete_after_member_assignment -q`
  passed.
- `uv run pytest test/workspaces/test_workspace_manager.py test/api/test_agent_routes.py -q`
  passed: 58 tests.
- `uv run pytest test/services/test_tool_service.py test/mcp_server/test_workspace_collaboration.py -q`
  passed: 35 tests.
- `uv run python -m compileall -q src/cli_agent_orchestrator` passed.
- `uv run python scripts/catalog_criteria.py` passed.
- `git diff --check` for touched paths passed.

The same optional failure-injection and unknown-role delete coverage notes were
judged non-blocking. With two successive fresh reviews after Revision 3
reporting zero valid findings, the Review Gate passed.
