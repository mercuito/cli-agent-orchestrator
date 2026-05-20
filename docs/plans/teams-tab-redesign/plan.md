# Teams Tab Redesign

Status: draft

## Goal

Replace the current admin-form Teams tab with a focused team editor that
matches the approved HTML mockup. The new UI lets a user:

- create a team and switch between teams from a left rail;
- add known agents to a team from an available-agents list;
- assign a role to each member through an inline dropdown;
- create, edit, and delete per-team roles through a side drawer;
- configure a role's tool access from one searchable tool list.

The backend CRUD surface for this already shipped in
[team-management-backend-crud](../team-management-backend-crud/plan.md) and
[team-role-tool-access](../team-role-tool-access/plan.md). This plan is
frontend-only.

## Authoritative Mockup

The authoritative visual and interaction reference is the approved HTML mockup:

`docs/plans/teams-tab-redesign/mockup.html`

Any previous static image/reference screenshot is historical context only and
must not be treated as an implementation target. The HTML mockup is the only
visual reference artifact for this plan.

The approved mockup establishes this target:

- Top dashboard header and tab nav remain visually consistent with the current
  app.
- Left rail shows team cards with display name, agent count, role count, and a
  `+ New team` action.
- Main area shows selected team identity, read-only Team ID, workspace
  select, available agents, members, and a roles strip.
- Available agents are added with explicit row actions, not drag-and-drop.
- Members have inline role dropdowns and remove actions.
- Roles are edited in a right-side drawer.
- The role drawer shows the role display name, editable display-name field,
  and one `Tools` section.
- The `Tools` section is a searchable flat list of tool toggles. Tool category
  or provider appears as metadata/pills such as `CAO`, `MCP`, or `Linear`.
- The drawer does not show immutable role IDs in the primary editor.
- The drawer does not expose provider-specific issue scopes, model access,
  project scope, history, or autosave preferences.

## Current State

- `web/src/components/WorkspaceTeamsPanel.tsx` renders the current Teams tab as
  a read-only list plus a single-form editor. Role assignments are edited as raw
  JSON and membership is not directly manageable.
- The component already loads teams, workspaces, CAO tool descriptors, and
  workspace tool provider role access schemas.
- The frontend must use the granular team CRUD endpoints added by the backend
  plans instead of the old whole-team upsert flow.
- `WorkspaceTeam` in `web/src/api.ts` must include `member_details` so the UI
  can render per-member role assignment directly from the backend response.
- Tailwind + lucide-react are available. Do not add a drag-and-drop dependency
  for this plan.

## Conceptual Model

This redesign does not change the backend model.

- Team membership remains anchored in `agent.workspace.team`.
- Per-team role assignment remains the team's `role_assignments` map.
- The UI must call `PUT /workspace-teams/{team_id}/members/{agent_id}` for
  member add and role-change operations so the backend updates membership and
  role assignment atomically.
- The default `member` role remains the system fallback. It is not shown as a
  special default badge in the UI.
- Tool access is configured through team roles. A role's tools are presented as
  one searchable list, regardless of whether a tool is CAO-owned, MCP-server
  backed, or workspace-tool-provider backed.

## Non-Goals

- Do not change backend Python services, stores, routes, or schemas.
- Do not introduce drag-and-drop.
- Do not introduce provider-specific model access, project scopes, issue scope
  fields, top-level-create toggles, or provider configuration forms in this UI.
- Do not introduce a real autosave preference, History panel, or audit timeline.
- Do not introduce member ordering or persisted ordering.
- Do not introduce a per-team configurable default role.
- Do not move the Teams tab to a different route or mount point.

## Component Shape

All new components should live under `web/src/components/teams/`.
`web/src/components/WorkspaceTeamsPanel.tsx` should become a data/loading shell
that composes these pieces:

- `TeamRail` — renders team cards, selection, and `+ New team`.
- `TeamHeader` — renders selected team name, read-only Team ID, and workspace
  select.
- `AvailableAgentsPanel` — renders searchable agents not currently in the
  selected team. Each row has an explicit add action.
- `MembersPanel` — renders searchable team members. Each row has an inline role
  dropdown and remove action.
- `RolesStrip` — renders role cards, member counts, selected role state, and
  `+ New role`.
- `RoleDrawer` — edits one role's display name and searchable flat tool list.
- `useTeamMutations` — wraps granular API calls and optimistic update/rollback
  behavior against one source-of-truth team list.

## API Client Changes (`web/src/api.ts`)

Add typed wrappers for the granular backend endpoints:

- `createWorkspaceTeam({ id, display_name, workspace })`
  -> `POST /workspace-teams`
- `updateWorkspaceTeamMetadata(team_id, { display_name, workspace })`
  -> `PUT /workspace-teams/{team_id}`
- `deleteWorkspaceTeam(team_id)` -> `DELETE /workspace-teams/{team_id}`
- `putWorkspaceTeamRole(team_id, role_id, role)`
  -> `PUT /workspace-teams/{team_id}/roles/{role_id}`
- `deleteWorkspaceTeamRole(team_id, role_id)`
  -> `DELETE /workspace-teams/{team_id}/roles/{role_id}`
- `putWorkspaceTeamMember(team_id, agent_id, { role_id? })`
  -> `PUT /workspace-teams/{team_id}/members/{agent_id}`
- `deleteWorkspaceTeamMember(team_id, agent_id)`
  -> `DELETE /workspace-teams/{team_id}/members/{agent_id}`

Add `member_details` to `WorkspaceTeam`:

```ts
export interface WorkspaceTeamMemberDetail {
  agent_id: string
  display_name: string
  role_id: string
  role_explicitly_assigned: boolean
}

export interface WorkspaceTeam {
  // ...existing fields
  member_details: WorkspaceTeamMemberDetail[]
}
```

The backend does not expose `PATCH` routes for this surface. Metadata and role
edits that feel patch-like in the UI must be implemented by merging the changed
field into the current frontend object and then sending the complete backend
`PUT` payload:

- team metadata `PUT` requires both `display_name` and `workspace`;
- role `PUT` requires the complete role object, including display name, CAO
  tools, MCP server grants, and provider grants;
- member add/change is granular already and uses the member endpoint.

The new UI must consume `member_details` directly instead of re-deriving member
role state from `role_assignments`.

## Implementation Tasks

1. **Update API types and wrappers.** Add `member_details` and the granular
   team CRUD wrappers. Remove frontend reliance on the old whole-team upsert
   path for team editing.

2. **Scaffold the new component structure.** Create the components listed in
   Component Shape and wire them through `WorkspaceTeamsPanel.tsx`.

3. **Replace the data shell.** Load teams, agents, workspaces, CAO tool
   descriptors, and provider tool schemas. Hold one selected team id and one
   source-of-truth team list.

4. **Implement mutations.** Centralize optimistic updates and rollback in
   `useTeamMutations`. UI-level field edits are local patches, but API writes
   must send the full payload required by the current backend `PUT` contract.
   Surface errors through the existing snackbar path.

5. **Wire team membership.** Add-agent actions call
   `putWorkspaceTeamMember`. Member role dropdowns call the same endpoint with
   `role_id`. Remove actions call `deleteWorkspaceTeamMember`.

6. **Wire role lifecycle.** Role cards open the drawer. `+ New role` persists a
   new role and opens it. Drawer save calls `putWorkspaceTeamRole`. Delete role
   confirms the number of affected members and calls `deleteWorkspaceTeamRole`.
   The `member` fallback role is not deletable from the UI.

7. **Implement the flat tool list.** Build the role drawer tool list from Tool
   Service-backed descriptors exposed to the frontend: CAO tools, MCP server
   surfaces, and provider-backed tools. Render them in one searchable list with
   provider/category pills. Do not render provider-specific config fields.

8. **Remove legacy controls.** Remove the JSON `role_assignments` textarea, old
   single-form Save Team flow, stale provider config UI, and any dead controls
   from the old Teams panel.

9. **Update tests.** Cover add member, remove member, role change, role create,
   role delete warning/fallback behavior, drawer tool filtering, role save, and
   optimistic rollback on API error.

10. **Verify end-to-end in a real browser.** Build and serve the dashboard,
    then exercise the Teams tab against the served app in Safari when available
    or the in-app browser otherwise. Code-based tests are not sufficient for
    completion.

## Definition of Done

This is the single authoritative acceptance section for this plan.

- The implemented Teams tab matches
  `docs/plans/teams-tab-redesign/mockup.html` in layout, supported controls, and
  interaction scope.
- The static reference image is not used as an implementation target.
- The Teams tab renders the new left rail, selected-team editor, available
  agents panel, members panel, roles strip, and right-side role drawer.
- Creating a team works from the rail and opens the new team in the editor.
- Adding an available agent uses
  `PUT /workspace-teams/{team_id}/members/{agent_id}` and updates member counts.
- Member role changes use the same endpoint with `role_id` set and update
  optimistically with rollback on failure.
- Removing a member uses
  `DELETE /workspace-teams/{team_id}/members/{agent_id}` and updates
  optimistically with rollback on failure.
- Workspace and team display-name changes use the metadata endpoint with
  both `display_name` and `workspace` in the request body, matching the
  current backend contract.
- Role cards show member counts derived from `member_details`.
- Clicking a role card opens the drawer for that role.
- The drawer shows the role display name and editable display-name field, but
  does not show immutable role IDs in the primary editor.
- The drawer `Tools` section is one searchable flat list of tool toggles with
  category/provider metadata.
- The drawer does not include provider-specific issue fields, top-level-create
  toggles, reason fields, model/provider access controls, project scopes, or
  history/autosave controls.
- New role, save role, and delete role use the granular role endpoints. Role
  saves send the complete role object expected by the current backend contract,
  not a partial patch body.
- Deleting a role confirms the affected member count and does not allow deleting
  the `member` fallback role.
- The new UI consumes `member_details` directly; it does not re-derive member
  role state from `role_assignments`.
- The legacy JSON `role_assignments` textarea, old single-form Save Team button,
  and stale provider config UI are removed.
- No drag-and-drop dependency or drag-and-drop behavior is introduced.
- All production changes are scoped to `web/` and generated served dashboard
  assets as needed; backend Python files are not modified.
- Browser end-to-end verification is completed against the served dashboard, not
  only component tests or a static mockup. The implementer must interact with
  the UI through a real browser and verify create, edit, save, refresh, and
  delete behavior. The goal is not complete if browser verification is skipped.
- A durable completion report exists at
  `docs/plans/teams-tab-redesign/completion-report.md`. It must include a
  browser verification table that records every required UI element/action and
  whether it was verified end-to-end in the served app. A narrative summary
  without the table does not satisfy this requirement.
- The implementer runs `uv run python scripts/catalog_criteria.py`, browses the
  catalog it reports, applies all criteria whose `when` clauses match the final
  diff, and treats any violation as a blocking acceptance failure.
- After implementation, the pending changes satisfy all applicable
  `docs/criteria` entries.
- The completion report records evidence for every acceptance item, including
  commands run, relevant tests, the required browser verification table, review
  revisions, and criteria catalog judgments.

## Verification

Expected commands from repo root unless noted:

```bash
cd web && npm test
cd web && tsc --noEmit
cd web && npm run build
uv run python scripts/catalog_criteria.py
git diff --name-only
```

Real-browser verification required by
`ui-changes-require-real-browser-verification`:

The implementer must run this as an end-to-end workflow through the browser UI.
They may use browser automation, but the actions must target the served
dashboard, not mocked components and not `mockup.html`.

1. Open the served dashboard Teams tab in Safari when available, otherwise the
   in-app browser.
2. Create a team from the rail and confirm it appears selected in the rail and
   main editor.
3. Add two available agents through the UI and confirm the member list, rail
   count, and role-card member counts update.
4. Change one member's role through the inline dropdown and confirm the visible
   role assignment changes.
5. Remove one member and confirm the member list and counts update.
6. Change the team display name and workspace, refresh the page, and
   confirm the saved values persist.
7. Create a role and confirm the role drawer opens for it.
8. Search/filter the tool list by name and confirm unrelated tools are hidden
   while matching CAO, MCP, and provider-backed tools remain findable.
9. Toggle at least one CAO tool, one MCP tool/server surface, and one
   Linear/provider-backed tool.
10. Save the role, refresh the page, reopen the role drawer, and confirm the
    tool selections persisted.
11. Delete the created role and confirm the affected-member warning appears.
12. Confirm no stale unsupported controls appear in the browser: no JSON role
    assignments textarea, no provider issue-scope fields, no model/provider
    access controls, no project scope, no history/autosave controls, and no
    drag/drop affordance.

The completion report must include the browser used, the served URL, the exact
workflow evidence, and any screenshots or notes needed to understand failures.
If Safari verification is impossible, the completion report must say so
explicitly, use the in-app browser instead, and name the remaining risk. Code
tests alone can never satisfy this verification gate.

The completion report must include a table with these exact columns:

| UI element/action | Browser path exercised | Expected persisted/API effect | Refresh/persistence checked | Result | Evidence |
| --- | --- | --- | --- | --- | --- |

The table must include at least these rows:

- Teams tab navigation.
- Team rail selection.
- `+ New team`.
- Team display-name edit.
- Workspace select.
- Available-agent search.
- Available-agent `Add` action.
- Members search.
- Member role dropdown.
- Member remove action.
- Roles strip selection.
- `+ New role`.
- Role drawer open/close.
- Role display-name edit.
- Tool search/filter.
- CAO tool toggle.
- MCP tool/server toggle.
- Linear/provider-backed tool toggle.
- Save role.
- Delete role warning and confirmation.
- Page refresh/reload persistence.
- Absence check for unsupported legacy controls.

Every row must have a concrete `Result` of `pass`, `fail`, or `blocked`. A
`blocked` row must explain why it was blocked, what risk remains, and why the
implementer believes the goal can or cannot be considered complete. The plan is
not complete with any unexplained `blocked` row or any `fail` row.

## Criteria Catalog

The criteria catalog was reviewed during planning with:

```bash
uv run python scripts/catalog_criteria.py
```

Likely applicable entries include, but are not limited to:

Implementation:

- `do-not-assume-backwards-compatibility`
- `minimal-cohesive-changes`
- `no-test-only-production-seams`
- `no-unnecessary-duplication`
- `parallel-safe-execution`
- `prefer-public-surfaces`
- `properly-designed-shared-code`
- `readable-and-explicit`
- `simple-systems`
- `system-code-locality`
- `authoritative-sources-are-referenced-not-copied`

Tests:

- `all-system-interactions-are-verified-by-tests`
- `assertions-occur-in-the-then-clause`
- `given-when-then-test-structure`
- `seams-must-be-tested`
- `target-behavior-must-not-be-mocked`
- `test-file-organization`
- `test-validity-preserved`
- `ui-changes-require-real-browser-verification`

The implementer must rerun the catalog before completion and apply the full set
then in force, not only the entries listed here.

## Review Gate

After implementation, run a review loop. The reviewer compares the landed
implementation against each item in Definition of Done plus all applicable
`docs/criteria` catalog criteria.

Any valid finding confirmed by the implementer must be fixed, then the review
loop restarts with a fresh reviewer. For every review finding that requires an
implementation change, the implementer updates
`docs/plans/teams-tab-redesign/completion-report.md` before restarting the loop.
The report must contain a `Review Revisions` section with one subsection per
accepted finding, recording what the reviewer found, why it was accepted as
valid, how it was fixed, and what evidence verifies the fix.

This plan is complete only after two successive review loops report zero valid
findings, and the completion report includes those two clean review passes.
