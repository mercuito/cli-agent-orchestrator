# Workspace Team Model

Status: draft

## Problem

Workspace context is currently configured at too low a level for how agents are
supposed to collaborate.

Today an agent can opt into workspace context resolution through its own
`[workspace_context]` block:

```toml
[workspace_context]
enabled = true
resolver_id = "linear_planning"
```

That exposes implementation details directly on each agent. It also makes
collaboration fragile: two agents may both be "workspace aware" while using
different resolver definitions, provider assumptions, or context IDs. When that
happens, a message can look valid while the receiver is not actually in the same
planning/work context.

The desired model is higher level:

- an agent belongs to one named workspace team,
- a team points at one workspace,
- a workspace defines the workspace tool providers and resolver available to that team,
- a workspace owns exactly one resolver,
- the resolver may consult multiple providers, but it is the only authority for
  deriving workspace context IDs,
- agents in the same team can naturally collaborate,
- agents outside the same team receive an explicit rejection instead of
  silently degrading.

## Current Shape

The implementation pieces already exist, but they are not grouped into a single
concept:

- Global provider enablement lives in `workspace-tool-providers.toml`.
- `AgentWorkspaceContextConfig` lives on each agent and stores
  `enabled/resolver_id`.
- `resolve_workspace_context_for_agent(agent, event)` skips resolution when the
  agent-level flag is disabled and otherwise dispatches by resolver id.
- The Linear provider registers `linear_planning` as a resolver.
- `AgentRuntimeHandle` always binds terminals to a concrete workspace context;
  when no context is supplied it uses the default context.
- Agent inbox receiver IDs include the active workspace context id, so runtime
  messaging already has a context dimension.

The missing piece is a manager above providers and resolvers that turns these
parts into a team membership model.

## Locked Vocabulary

Use **workspace** for provider/resolver/context machinery.

Use **workspace team** for the logical group of agents that can collaborate
naturally. This is the collaboration boundary.

Avoid **workspace scope** in the implementation and UI unless a later plan
defines a different concept. "Scope" is too vague for the product model here.

Treat "membership" carefully. An agent can have an external provider presence,
such as a Linear app user or GitHub identity, without being addressable inside a
CAO workspace team. In this plan, membership means participation in the
CAO-managed team, not membership in the provider's own workspace.

## Mental Model

- An agent belongs to zero or one team.
- An agent with no team is standalone: it can run, own a terminal, use default
  workspace context, and be inspected, but it cannot use team-aware agent
  collaboration.
- Agent-to-agent messaging requires both agents to be on the same team.
- A team has one workspace, which supplies the provider address book,
  resolver, and workspace context model for that team's collaboration.
- Cross-team messaging is blocked in v1. If needed later, it should be added as
  an explicit bridge, front desk, gateway, or delegation policy.

## Target Configuration

Each agent references at most one workspace team:

```toml
[workspace]
team = "cao_delivery"
```

The team definition points at one workspace. Agent configs do not directly select a
workspace for collaboration. That keeps collaboration policy from collapsing into a
raw workspace-name equality check.

No team means the agent has no workspace team membership. In that state:

- provider event resolution is disabled for that agent,
- collaboration checks treat the agent as outside any team,
- runtime terminals still get a default workspace context, preserving the
  existing terminal invariant.

Workspace definitions are code-owned in v1. A workspace is still the
provider/resolver contract, so keeping it in code prevents users from creating
invalid provider/resolver combinations before the model is proven.

Workspace team definitions are persisted through one localized team-definition
owner surface in v1 because the dashboard can create and edit teams. Code-owned
bootstrap teams may seed the persisted store, but dashboard-managed teams must
not live in process-global mutable registries, API-local state, or ad hoc UI
state. A later plan can introduce a user-authored TOML format if operators need
file-based team management.

Example v1 definitions:

```python
Workspace(
    id="linear_delivery",
    display_name="Linear Delivery",
    providers=("linear", "github"),
    resolver=LinearPlanningWorkspaceResolver(...),
)

WorkspaceTeam(
    id="cao_delivery",
    display_name="CAO Delivery",
    workspace="linear_delivery",
)
```

Use `cao_delivery` as the first team id. Use `linear_delivery` as the
first workspace id. Keeping these ids distinct prevents the code from accidentally
treating team identity and workspace identity as interchangeable.

The workspace has one resolver. That resolver can ask Linear, GitHub, or future
providers for data, but it must return one authoritative
`WorkspaceContextResolution`.

Two teams may point at the same workspace, but they remain separate collaboration
domains unless a future plan introduces an explicit bridge. Same workspace does not
mean same team.

Workspace context identity is workspace/resolver scoped, not team scoped. If two
teams share the same workspace and resolve the same provider object, they may use
the same workspace context id while message policy still prevents cross-team
collaboration. If two different workspaces or resolver namespaces resolve the same
provider object, they must not silently collide into one context.

## Team Boundary

Workspace and workspace team are intentionally separate:

- a workspace answers "how do we resolve workspace context and provider views?";
- a team answers "which agents are allowed to collaborate naturally?";
- provider addressability is materialized for a team using that team's workspace;
- collaboration checks compare team membership, not workspace ids.

This prevents a subtle class of bugs where two unrelated teams happen to use
the same provider/resolver machinery and accidentally become mutually
addressable.

## Shared Workflow, Individual Permissions

A workspace team shares one workflow model, not one identical permission set.

The team's workspace defines the workflow concepts available to the team:
which providers exist, which resolver determines context, and which provider
address books can participate in collaboration. Every agent on the team operates
inside that same workflow model.

Provider permissions remain agent-specific. Team membership does not grant
provider power by itself. An agent can belong to a team whose workspace includes
Linear and GitHub while only having Linear read access, GitHub read access,
Linear write access, or no provider tool access at all.

The conceptual rule is:

```text
effective capability =
  team workflow includes the provider/tool concept
  AND the agent has the provider-specific permission or grant
```

Provider addressability is team-scoped; provider capability is agent-scoped.

Provider-specific identity uniqueness is separate from team authorization. A
provider may reject duplicate external identities globally when that is required
for credentials, OAuth, webhook verification, or unambiguous account mapping.
Team authorization still decides which valid provider identities are
CAO-addressable inside a team.

## Message Policy

Team membership makes agent-to-agent messaging policy first class.

For v1, CAO-managed agent collaboration is same-team only:

- agents on the same team may message, hand off to, delegate to, or otherwise
  address each other through CAO collaboration surfaces;
- agents on different teams may not collaborate through those surfaces, even
  when both teams use the same workspace;
- agents without a team may still have terminals and default runtime context,
  but they are outside team-aware collaboration;
- lower-level terminal diagnostics can remain available through terminal-owned
  surfaces, but they must not silently become agent collaboration.

This deliberately trades broader cross-team communication for a stronger
invariant: every normal collaboration path has one team, one derived workspace, and
one resolver-backed context model. If cross-team communication becomes a product
requirement later, it should be introduced as an explicit bridge or gateway
policy rather than by weakening same-team enforcement.

For v1, `send_message` between agent terminals is agent collaboration and must
use the same message policy as handoff, delegation, and provider-originated
teammate lookup. Operator/admin terminal control is separate and may remain
available through explicit owner surfaces.

Apply this policy at owner boundaries, not only at MCP wrappers. Direct REST
routes, CLI commands, and services that create inbox deliveries must not be able
to bypass team policy for agent-to-agent messages.

## Provider Addressability

Workspace team membership should gate provider addressability as early as
possible.

The boundary should be:

- a workspace tool provider owns provider-native vocabulary, credentials, API calls,
  webhook parsing, tool implementations, and candidate provider-to-agent
  mappings;
- a workspace team owns which candidate mappings are authorized for that team;
- provider-native presence does not automatically imply CAO team membership.

In other words, Linear can remain a provider adapter, but the `cao_delivery`
team authorizes the Linear address book that CAO uses for that team. The team
uses its configured workspace to know which providers and resolver apply.

External providers can still know about a presence that CAO should not use. For
example, a Linear app user may exist for Agent B because OAuth/workspace happened at
some point. If Agent A belongs to team `cao_delivery` and Agent B does not,
then a Linear mention, delegation, teammate lookup, or app-user ping inside
`cao_delivery` must not resolve Agent B as a CAO-managed recipient.

The natural prevention point is provider config materialization:

- Let each provider build candidate mappings using its own domain rules.
- Pass those candidates through workspace team authorization before they become
  CAO-addressable.
- Include only authorized provider presences and provider tool access for agents
  that belong to that team.
- Keep provider-native extraction functions available so the workspace can ask the
  provider for candidates without duplicating Linear/GitHub parsing details.
- Let external provider identities remain untouched.
- Do not expose a CAO recipient mapping for out-of-team agents.

For Linear, the provider still creates candidate `LinearPresence` mappings from
agent `[linear]` config. The team manager then authorizes only candidates whose
agent belongs to the current team. The resulting team-bound
`LinearProviderConfig` for `cao_delivery` includes only authorized presences and
tool access. If a webhook or provider tool tries to resolve an app user for
Agent B outside the team, `presence_by_app_user_id` and `resolve_presence`
should behave as "unknown in this team" rather than returning Agent B and
relying on a later runtime guard.

This gives three layers of protection:

1. Team authorization prevents provider candidate mappings from becoming
   addressable in the wrong team.
2. Event resolution rejects unknown/out-of-team provider identities before a
   runtime handle is created.
3. Collaboration routing still rejects cross-team messages as a final
   invariant check.

The third layer is still required, but it should not be the first line of
defense.

## Provider Event Team Selection

Inbound provider events must resolve through a team lens, not a global provider
address book.

For v1:

- if a provider event resolves to exactly one team-authorized agent, use that
  agent's team and that team's workspace for runtime context resolution;
- if a provider event resolves to no team-authorized agent, reject it as not
  CAO-addressable;
- if a provider event resolves to multiple team-authorized agents across
  different teams, reject it as ambiguous and do not create a runtime handle,
  terminal, or inbox notification;
- provider adapters own provider-native extraction and matching details, while
  the team/collaboration manager owns the final team selection and ambiguity
  decision.

This keeps external provider identity from becoming a hidden cross-team routing
channel.

Some providers may reject duplicate identities before ambiguity can arise. The
team/collaboration manager must still fail closed for provider-agnostic
adapters, or future providers, that can produce multiple team-authorized
matches.

Legacy or alternate provider conversation bridges that route to explicit
receiver terminals must either be retired, constrained behind an explicit
operator/admin surface, or made to use the same team-authorized event selection
before creating inbox notifications.

## Proposed Architecture

Create a localized workspace/team subsystem, likely under:

```text
src/cli_agent_orchestrator/workspaces/
```

The subsystem owns these public concepts:

- `Workspace`: immutable definition of a named workspace.
- `WorkspaceResolver`: protocol for resolving provider/runtime events into
  a `WorkspaceContextResolution`.
- `WorkspaceRegistry`: code-owned registration and lookup of known workspace
  definitions.
- `WorkspaceTeam`: immutable definition of a named team and its selected workspace.
- `WorkspaceTeamStore`: the persisted owner for dashboard-managed team
  definitions.
- `WorkspaceTeamRegistry`: read-through lookup over persisted teams plus
  code-owned bootstrap seeds, without process-global mutable team state.
- `WorkspaceTeamService`: public create, update, list, validate, and diagnostic
  API for team definitions. Dashboard/API/CLI consumers use this service
  instead of mutating registries directly.
- `WorkspaceTeamMembership`: the parsed agent team reference.
- `WorkspaceCollaborationManager`: the runtime service that validates team
  membership, resolves events through the team's workspace, and enforces
  collaboration boundaries.
- `WorkspaceTeamProviderView`: a team-filtered projection of provider
  presences, provider tool access, and provider-native address mappings.
- `WorkspaceTeamProviderCapability`: the effective provider/tool capability for
  one agent inside a team, computed from team workflow availability and
  agent-specific provider grants.
- `WorkspaceToolProviderAdapter`: provider-owned code that can build a provider view
  from authorized provider mappings while keeping provider-specific parsing and
  API behavior inside the provider package.
- `WorkspaceToolProviderCandidateMapping`: provider-owned candidate mapping from a
  provider-native identity or access grant to a CAO agent before team
  authorization.
- `WorkspaceTeamAuthorizedMapping`: team-owned decision that a candidate
  mapping is addressable inside one team.

Consumers should use this package's public API. They should not reach directly
into registry internals or provider-specific resolver modules except from workspace
definition code.

## Manager Responsibilities

`WorkspaceCollaborationManager` should own the behavior that is currently
spread across agent config, provider runtime code, and message routing
decisions:

1. Validate an agent's configured team name when agents are loaded or used.
2. Report unknown team names as diagnostics instead of silently disabling
   context.
3. Resolve the team to its workspace.
4. Report teams that reference unknown workspace names as diagnostics.
5. Validate that the workspace's providers are available when the team is used.
6. Request candidate provider mappings from provider adapters.
7. Authorize or prune those mappings against team membership.
8. Build team-filtered provider views so out-of-team agents are not
   addressable through provider-native identities.
9. Preserve agent-specific provider permissions when building provider views;
   team membership must not grant provider tool access by itself.
10. Resolve provider/runtime events by delegating to the team's workspace resolver.
11. Return no resolution for agents without a team.
12. Bind resolved workspace context IDs into `AgentRuntimeHandle` creation.
13. Decide whether two agents can collaborate naturally:
   - same non-empty team: allowed,
   - different team: rejected even when both teams use the same workspace,
   - one or both without a team: rejected for team-aware collaboration.
14. Keep the collaboration decision on an explicit message-policy path so
   provider context resolution does not accidentally become the messaging
   authorization model.
15. Produce user-visible rejection messages that name the sender, receiver, and
   team mismatch.
16. Ensure workspace context identity is scoped by workspace/resolver namespace so
   different resolver models do not silently share one provider-object context.

The manager should not replace the lower-level workspace context store. It sits
above it and chooses which context ID the runtime should use.

The manager should also avoid becoming a provider parser. It should ask each
provider adapter for candidate mappings, authorize or prune those mappings
against team membership, and pass authorized mappings back to provider adapters
to construct provider views. That keeps Linear-specific fields like
`app_user_id`, `app_key`, OAuth state, and Linear tool-access validation inside
the Linear package, while moving the final addressability decision one level
higher.

## Migration Strategy

This plan intentionally makes a hard cutover away from agent-owned workspace
context configuration. Existing local agent files may still contain
`[workspace_context]`, but that block is not a supported runtime, migration, or
compatibility input under the team model.

Final behavior:

- `[workspace] team = "..."` is the new authoritative shape.
- `[workspace_context]` must not be translated into a workspace team.
- Legacy `resolver_id` values must not be mapped to teams during normal agent
  loading, runtime routing, API updates, CLI writes, dashboard saves, provider
  event resolution, or tests.
- If an agent file contains `[workspace_context]`, production loading may only
  detect it to produce an actionable diagnostic or error instructing the
  operator to migrate to `[workspace] team`.
- If both `[workspace] team` and `[workspace_context]` are present,
  `[workspace] team` remains the only usable membership field and the legacy
  block still produces a legacy-config diagnostic.
- Repository examples/tests use `[workspace] team`.
- No production call site has direct behavioral dependence on
  `[workspace_context]`.
- No new feature is built on the legacy shape.

An explicit migration command or offline diagnostic may be introduced later, but
normal CAO runtime/config loading must not provide backwards-compatible
resolver-id-to-team behavior.

## Implementation Phases

### Phase 1 - Define the Workspace/Team Subsystem

- Add the `workspaces` package with public types and manager API.
- Register the first workspace that models the current Linear planning behavior.
- Add a persisted team-definition owner surface under the workspace/team subsystem,
  including store/config format, service API, validation, diagnostics, and
  isolated test-owned storage.
- Seed the first team that uses the Linear workspace through the team owner
  surface. Bootstrap seeds may be code-owned, but runtime team definitions are
  read from the localized persisted store.
- Keep runtime behavior unchanged while unit tests prove lookup, validation,
  team lookup, workspace lookup, and one-resolver-per-workspace invariants.
- Add diagnostics for unknown team names, unknown workspace names, and unavailable
  providers.
- Add the provider candidate mapping and team authorization contracts, even if
  Linear is the only provider implementation at first.

### Phase 2 - Add Agent Team Config

- Add `[workspace] team` parsing/writing to the agent config model.
- Detect legacy `[workspace_context]` only to emit an unsupported-legacy
  diagnostic/error; do not translate it into team membership.
- Update config serialization so newly written agent files use `[workspace]`.
- Update API responses and dashboard config views to show the team name, derived
  workspace name, and workspace context state clearly.

### Phase 3 - Route Resolution Through the Manager

- Replace direct calls to `resolve_workspace_context_for_agent` in provider
  runtimes with manager calls.
- Move Linear planning resolution behind a workspace resolver adapter.
- Build Linear presence resolution from team-authorized candidate mappings, not
  the global set of agents with Linear config.
- Treat a Linear app user/app key that belongs to an out-of-team agent as not
  CAO-addressable in the current team.
- Preserve default runtime context behavior for agents without team
  membership.
- Add integration coverage that a Linear event resolves through the team/workspace
  and starts or addresses the agent in the resolved context.

### Phase 4 - Enforce Collaboration Boundaries

- Identify agent-to-agent messaging entry points, including MCP/server surfaces.
- Add a team-aware guard before sending workspace-dependent messages.
- Treat the guard as message policy, not just workspace compatibility.
- Allow same-team collaboration.
- Reject cross-team collaboration with a clear message.
- Reject collaboration across different teams even if both teams share the same
  workspace.
- Reject team-aware collaboration when either agent has no team.
- Keep purely terminal-addressed diagnostic operations separate if they are not
  semantically agent collaboration.

### Phase 5 - Diagnostics and UI

- Surface team/workspace validation problems in API responses and the dashboard.
- Show the selected agent's team, derived workspace, and workspace context metadata.
- Keep terminals visible only in agent context, but include enough team/workspace/context
  information to explain why collaboration or provider event routing worked.
- If UI changes are made, verify in a real browser against the backend-served
  bundle, including any remote/Tailscale route used during review.

### Phase 6 - Legacy Cleanup

- Remove old `[workspace_context]` behavioral entry points. Normal production
  loading must not accept legacy blocks as migration input.
- Delete unused resolver-id plumbing that lets agents bypass team membership.
- Delete old tests, fixtures, examples, and docs that encode the legacy
  `[workspace_context]` model except for explicit historical migration notes.
- Update docs/examples so "workspace team" is the documented agent membership
  path and "workspace" is documented only as team-owned context machinery.

## Task Breakdown

Use these tasks as the implementation checklist. Each task should leave the
codebase closer to the team model without preserving workspace-as-membership as a
parallel behavior path.

### Task 1 - Agent Config Becomes Team Membership

Owned areas:

- `src/cli_agent_orchestrator/agent.py`
- `src/cli_agent_orchestrator/cli/commands/agent.py`
- agent config update/serialization surfaces in `src/cli_agent_orchestrator/api/main.py`
- `web/src/components/agents-tab/agentTomlSerialization.ts`
- agent config tests in `test/test_agent.py`, `test/api/test_agent_routes.py`,
  CLI agent command tests, and web config tests.

Required changes:

- Replace agent membership field `workspace.workspace` with `workspace.team`.
- Parse and write `[workspace] team = "cao_delivery"`.
- Update `cao agent create/show/list/edit/start` surfaces. `create` must either
  support explicit `--team` or intentionally create standalone no-team agents
  with documented behavior.
- Treat legacy `[workspace_context]` as unsupported current configuration:
  detect it for diagnostics/errors only, and never map it to a team id, workspace
  id, resolver, recipient, or runtime context.
- Ensure newly serialized configs do not emit `[workspace] workspace`.

### Task 2 - Add Team Registry And Team-Aware Manager

Owned areas:

- `src/cli_agent_orchestrator/workspaces/`
- persisted team-definition storage under the workspace/team subsystem or a
  localized client owned by that subsystem.
- `test/workspaces/`

Required changes:

- Add `WorkspaceTeam`, `WorkspaceTeamStore`, `WorkspaceTeamRegistry`,
  `WorkspaceTeamService`, and team diagnostics.
- Keep `Workspace` as provider/resolver machinery.
- Add manager APIs for `agent -> team -> workspace`.
- Register `linear_delivery` as the first code-owned workspace.
- Seed `cao_delivery` as the first bootstrap team through the same team owner
  surface used by dashboard/API management.
- Define team create, update, list, validation, diagnostics, and persistence in
  the workspace/team subsystem. Dashboard-managed teams must not be represented by
  process-global mutable registries or ad hoc API-local state.
- Tests must use isolated test-owned team storage and must not share mutable
  team registry state across test cases or concurrent runs.
- Fail closed for unknown teams and for teams that reference unknown workspaces.

### Task 3 - Move Provider Addressability To Team Authorization

Owned areas:

- `src/cli_agent_orchestrator/workspaces/`
- `src/cli_agent_orchestrator/linear/workspace_adapter.py`
- `src/cli_agent_orchestrator/workspace_tool_providers/registry.py`
- `src/cli_agent_orchestrator/workspace_tool_providers/events.py`
- `src/cli_agent_orchestrator/mcp_server/freshness.py`
- `src/cli_agent_orchestrator/mcp_server/provider_tools.py`
- `src/cli_agent_orchestrator/services/terminal_service.py`
- provider and workspace tests under `test/linear/`, `test/workspaces/`, and
  `test/workspace_tool_providers/`.

Required changes:

- Replace workspace-authorized mappings with team-authorized mappings.
- Build team-bound provider views using the team's workspace.
- Preserve provider-owned candidate extraction and provider-native domain logic.
- Preserve agent-specific provider tool permissions; team membership must not
  expand tool access.
- Classify legacy workspace tool provider protocols and dispatchers. Retire them,
  constrain them to telemetry-only behavior with no CAO recipient semantics, or
  require provider-published events and provider-backed agent listings that can
  address agents to flow through team-authorized provider views.
- Include team-bound provider policy material in MCP surface descriptors,
  runtime fingerprints, and terminal reuse/restart decisions so stale terminals
  do not retain tools after team or provider-view changes.
- Add coverage for two agents on the same team with different provider grants.

### Task 4 - Resolve Provider Events Through Teams

Owned areas:

- `src/cli_agent_orchestrator/linear/runtime.py`
- `src/cli_agent_orchestrator/linear/app_client.py`
- `src/cli_agent_orchestrator/linear/routes.py`
- `src/cli_agent_orchestrator/linear/workspace_events.py`
- `src/cli_agent_orchestrator/linear/workspace_context_resolver.py`
- `src/cli_agent_orchestrator/linear/workspace_context_tool_results.py`
- `src/cli_agent_orchestrator/linear/monitor.py`
- `src/cli_agent_orchestrator/linear/monitor_store.py`
- `src/cli_agent_orchestrator/linear/inbox_bridge.py`
- `src/cli_agent_orchestrator/provider_conversations/inbox_bridge.py`
- `src/cli_agent_orchestrator/provider_conversations/reply_service.py`
- manager/provider event tests under `test/linear/` and `test/workspaces/`.
  Include provider-conversation tests under `test/provider_conversations/` and
  Linear app route tests. Include Linear app service tests and Linear monitor
  tests.

Required changes:

- Resolve inbound provider events through team-authorized provider views.
- If exactly one team-authorized agent matches, use that agent's team and workspace.
- If no team-authorized agent matches, reject before runtime handle creation.
- If multiple teams match, reject as ambiguous before runtime handle creation.
- Make provider-originated rejection diagnostics visible through the owning
  provider/runtime surface. Rejections should explain that the provider event
  was authenticated but not CAO-addressable in the resolved team context, and
  should include enough provider identity and team/workspace context for an operator
  to understand why no agent response occurred.
- Retire, constrain, or reroute explicit provider-conversation receiver paths so
  provider-originated notifications cannot bypass team-authorized event
  selection.
- Keep Linear OAuth/webhook verification as provider-security verification only.
  Verified webhook metadata, including stamped `_cao_linear_agent_id`, must not
  become the first CAO recipient decision or bypass team-authorized selection.
- Route Linear monitor presence iteration, synthetic event creation, pending
  delivery retry, and watermark advancement through team-authorized provider
  views.
- Do not advance monitor watermarks for no-team, out-of-team, or ambiguous
  identities that were not safely processed.
- Remove runtime checks that use `agent.workspace.workspace` as the membership
  signal.

### Task 4A - Scope Workspace Context Identity By Workspace/Resolver

Owned areas:

- `src/cli_agent_orchestrator/clients/workspace_context_store.py`
- `src/cli_agent_orchestrator/clients/database_migrations.py`
- workspace context tests under `test/clients/`
- Linear workspace context resolver tests under `test/linear/`

Required changes:

- Make workspace/resolver namespace part of workspace context identity or enforce an
  equivalent conflict check that prevents different workspaces/resolvers from
  silently sharing one provider-object context.
- Preserve the default agent context behavior for no-team runtime work.
- Allow two teams sharing the same workspace to resolve the same provider object to
  the same workspace context id; collaboration remains blocked by team policy.
- Add migration/backfill coverage for existing workspace contexts.

### Task 4B - Classify Linear Identity Uniqueness

Owned areas:

- `src/cli_agent_orchestrator/agent.py`
- `src/cli_agent_orchestrator/linear/app_client.py`
- `src/cli_agent_orchestrator/linear/routes.py`
- `src/cli_agent_orchestrator/linear/workspace_tool_provider.py`
- `src/cli_agent_orchestrator/linear/workspace_events.py`
- Linear provider tests under `test/linear/`
- Linear app service and route tests.

Required changes:

- Explicitly classify Linear fields that must remain globally unique for v1:
  `app_key`, `oauth_state`, and `webhook_secret`.
- Decide and test whether `app_user_id` and `app_user_name` remain globally
  unique in v1 or become team-view scoped.
- Ensure the chosen Linear uniqueness policy is documented in tests and does
  not accidentally stand in for generic cross-team ambiguity handling.
- Keep provider-agnostic ambiguity coverage in the team/collaboration manager
  even if Linear rejects duplicate identities earlier.
- Ensure OAuth state validation, token lookup, webhook secret verification, and
  webhook metadata stamping follow the same identity classification. These
  surfaces may verify source authenticity, but they must not globally select a
  CAO recipient outside the team manager.

### Task 5 - Enforce First-Class Message Policy

Owned areas:

- `src/cli_agent_orchestrator/mcp_server/server.py`
- `src/cli_agent_orchestrator/api/main.py`
- `src/cli_agent_orchestrator/cli/commands/inbox.py`
- `src/cli_agent_orchestrator/clients/inbox_store.py`
- `src/cli_agent_orchestrator/provider_conversations/inbox_access.py`
- `src/cli_agent_orchestrator/provider_conversations/reply_service.py`
- services that route handoff, assign/delegation, baton, or inbox messages
- `test/mcp_server/`, inbox API tests, terminal inbox tests, and provider
  conversation read/reply tests.

Required changes:

- Replace same-workspace collaboration guards with same-team message policy.
- Apply the policy to direct `send_message`, handoff, assign/delegation, baton
  collaboration paths, and provider-originated teammate lookup.
- Apply the policy before `create_inbox_delivery` at the inbox message owner
  boundary so direct REST and CLI inbox writes cannot bypass MCP guards.
- Authorize `read_inbox_message` and `reply_to_inbox_message` by current
  caller/terminal ownership and current team/provider-view policy; notification
  id possession and stored provider metadata such as Linear `app_key` must not
  bypass current authorization.
- Allow same non-empty team.
- Reject missing-team, different-team, and different-teams-sharing-one-workspace
  cases with clear user-visible text.
- Keep operator/admin terminal control separate from agent collaboration.

### Task 6 - Rename API/UI From Membership Workspace To Team

Owned areas:

- `src/cli_agent_orchestrator/services/agent_manager.py`
- `src/cli_agent_orchestrator/cli/commands/agent.py`
- `src/cli_agent_orchestrator/api/main.py`
- `web/src/api.ts`
- `web/src/components/AgentPanel.tsx`
- team dashboard views/components under `web/src/components/`
- `web/src/components/agents-tab/AgentDetailPanel.tsx`
- runtime and provider event schemas in `src/cli_agent_orchestrator/runtime/`
  and `src/cli_agent_orchestrator/linear/`
- timeline services and views under `src/cli_agent_orchestrator/services/` and
  `web/src/components/timelineEventViews/`
- affected web tests.

Required changes:

- Expose team id as the agent membership field.
- Expose derived workspace id as metadata, not membership.
- Add a first-class dashboard Teams tab for viewing, creating, and managing
  workspace teams. The tab should show each team, its selected workspace,
  workspace diagnostics, and current member agents so operators can understand who
  can collaborate with whom.
- Make the Teams tab the dashboard owner for changing a team's workspace.
  An agent that belongs to a team inherits its workspace from that team.
- Route Teams tab create/update/list actions through the localized
  `WorkspaceTeamService` owner surface and persisted team store. The UI and API
  must not mutate workspace/team registries directly or keep team definitions only
  in frontend state.
- In the agent configuration UI, allow changing the agent's team membership but
  render the workspace as derived read-only metadata whenever the agent is
  in a team. The workspace control must be disabled or replaced with read-only
  text, with copy that makes clear the workspace is owned by the selected team.
- Do not allow the dashboard to persist an agent-level workspace override
  for a teamed agent. No-team agents may show default/no workspace context, but
  they must not imply independent team workflow membership.
- Update CLI list/show/create/start output and tests to reflect team membership,
  derived workspace metadata, and team/workspace diagnostics where relevant.
- Rename diagnostics and UI labels that still present workspace as direct agent membership.
- Continue showing derived workspace and workspace context metadata so operators can
  understand routing.
- Add team id and derived workspace id to relevant runtime/provider event payloads,
  or explicitly document why a payload remains context-only.
- Update generated web types and timeline views/tests for events that explain
  routing, collaboration, or provider event selection.

### Task 7 - Classify Existing Runtime State And Admin Recovery Surfaces

Owned areas:

- `src/cli_agent_orchestrator/runtime/agent.py`
- `src/cli_agent_orchestrator/services/inbox_service.py`
- `src/cli_agent_orchestrator/services/monitoring_service.py`
- `src/cli_agent_orchestrator/services/flow_service.py`
- `src/cli_agent_orchestrator/diagnostics/providers/codex.py`
- `src/cli_agent_orchestrator/cli/commands/diagnostics.py`
- flow routes in `src/cli_agent_orchestrator/api/main.py`
- `src/cli_agent_orchestrator/cli/commands/flow.py`
- `src/cli_agent_orchestrator/clients/inbox_store.py`
- provider conversation persistence/idempotency files under
  `src/cli_agent_orchestrator/clients/` and
  `src/cli_agent_orchestrator/provider_conversations/`
- `src/cli_agent_orchestrator/clients/baton_store.py`
- `src/cli_agent_orchestrator/models/baton.py`
- `src/cli_agent_orchestrator/services/baton_service.py`
- `src/cli_agent_orchestrator/services/baton_watchdog_service.py`
- baton API/CLI/service files under `src/cli_agent_orchestrator/api/`,
  `src/cli_agent_orchestrator/cli/commands/`, and
  `src/cli_agent_orchestrator/services/`.
- monitoring API/CLI/service/docs under `src/cli_agent_orchestrator/api/`,
  `src/cli_agent_orchestrator/cli/commands/`,
  `src/cli_agent_orchestrator/services/`, and `docs/monitoring.md`.

Required changes:

- Define behavior for active terminals and pre-existing pending inbox
  notifications when an agent's team changes or is removed.
- State whether pending notifications are grandfathered, blocked on delivery,
  moved, or surfaced as diagnostics.
- Add tests around pending inbox movement during runtime context switches.
- Classify baton HTTP/CLI recovery endpoints as operator/admin surfaces when
  exempt from same-team policy.
- Add tests and wording that distinguish baton recovery from normal agent
  collaboration.
- Classify existing active baton records when an agent's team changes or is
  removed. Durable baton fields such as `originator_id`, `current_holder_id`,
  and `return_stack` must be grandfathered, blocked, orphaned, revalidated on
  each transition, or surfaced as diagnostics by explicit policy.
- Add tests for active baton pass, return, complete, block, reassign, watchdog
  nudge, and watchdog orphan behavior after holder, originator, or return-stack
  participant team changes, including missing-team and different-team cases.
- Classify scheduled/manual flow execution as an operator runtime-start surface.
  Flows should use default workspace context unless a provider event supplies a
  resolved context, and must surface diagnostics for unknown teams.
- Add flow tests for team agents, no-team agents, unknown-team diagnostics, and
  active terminal reuse after team changes.
- Classify diagnostics provider runs as operator runtime-start surfaces.
  Diagnostics should use default workspace context unless explicitly testing a
  provider-resolved context, surface team diagnostics for unknown teams, and
  handle existing active terminals intentionally.
- Classify provider-conversation persistence/idempotency keys and metadata.
  Rejected no-team, out-of-team, or ambiguous provider events must not be marked
  as successfully processed before team authorization.
- Classify monitoring sessions as terminal/operator diagnostics over historical
  inbox records. Monitoring must not authorize collaboration, and monitoring
  docs/tests should cover team changes, context switches, peer filters, and
  rejected cross-team messages.

### Task 8 - Update Agent-Facing Instructions And Protocol Docs

Owned areas:

- MCP tool descriptions and injected callback text in
  `src/cli_agent_orchestrator/mcp_server/server.py`
- repo-root skills under `skills/`
- `src/cli_agent_orchestrator/skills/cao-supervisor-protocols/SKILL.md`
- `src/cli_agent_orchestrator/skills/cao-worker-protocols/SKILL.md`
- docs/examples/e2e prompts that teach `send_message`, `assign`, handoff, or
  terminal-id callbacks.

Required changes:

- Update agent-facing text to say terminal-id messaging is subject to team
  message policy and may be rejected.
- Avoid teaching terminal id possession as sufficient authority to collaborate.
- Update `skills/cao-provider/SKILL.md` and its references so assign, handoff,
  send_message, and provider validation flows align with same-team policy.
- Update tests that assert exact callback text or protocol prompts.

### Task 9 - Legacy Cleanup And Documentation

Owned areas:

- old `[workspace_context]` parser/migration code
- docs/examples/tests that still present workspace membership or legacy context as
  valid configuration.

Required changes:

- Remove direct resolver-id dispatch and legacy behavior paths.
- Remove any production parser that successfully maps `[workspace_context]` or
  `resolver_id` to workspace team membership.
- Retain, at most, unsupported-legacy detection that emits an actionable
  diagnostic/error and cannot authorize runtime behavior.
- Replace legacy compatibility tests with tests proving legacy config is
  rejected or diagnosed and cannot select a team, workspace, resolver, recipient, or
  runtime context.
- Ensure examples and docs present `[workspace] team` as the only current
  membership path.
- Static search must not find production behavior that treats
  `[workspace_context]` or `[workspace] workspace` as current configuration.

## Test Plan

Use owner surfaces and real seams wherever practical.

Required coverage:

- Config parse/write:
  - agent with `[workspace] team` round-trips,
  - agent with no team remains valid,
  - CLI agent create/show/list/edit/start behavior reflects team membership or
    intentionally documented standalone no-team behavior,
  - legacy `[workspace_context]` is rejected or diagnosed as unsupported and
    does not map through any resolver-to-team compatibility table,
  - both shapes present keeps `[workspace] team` as the only usable membership
    field and still emits a legacy-config diagnostic.
- Workspace/team registry and manager:
  - unknown team is rejected or surfaced as a diagnostic,
  - unknown workspace is rejected or surfaced as a diagnostic,
  - a team that references an unknown workspace is rejected or surfaced as a
    diagnostic,
  - dashboard-created or edited teams persist through the localized team owner
    surface and are visible after service/browser reload,
  - code-owned bootstrap teams seed the same owner surface used by
    dashboard/API management,
  - tests use isolated team storage and do not rely on process-global mutable
    registries,
  - unavailable provider is detected,
  - workspace definitions cannot have multiple resolvers,
  - agents without a team do not run provider event resolution.
- Workspace context identity:
  - workspace/resolver namespace participates in context identity or conflict
    detection,
  - two teams sharing one workspace can resolve the same provider object to one
    context,
  - two different workspaces/resolver namespaces cannot silently collide on the same
    provider object,
  - default no-team runtime contexts remain agent-scoped.
- Provider addressability:
  - Linear creates candidate mappings from agent `[linear]` config,
  - team authorization prunes candidates whose agents are not in that team,
  - Linear provider view for a team includes only authorized candidates,
  - an out-of-team agent with valid Linear credentials is not returned by
    team-bound app user/app key lookup,
  - provider tool access for out-of-team agents is not exposed in that team,
  - in-team provider tool access still respects each agent's own provider
    grants and does not expand to all team members,
  - the rejection/error text makes clear that the provider identity is not
    CAO-addressable in the current team.
- Linear identity validation:
  - security-sensitive identifiers remain globally unique,
  - any addressability identifiers allowed to repeat are resolved through
    team-bound views,
  - provider-agnostic ambiguity behavior is tested independently of Linear's
    duplicate-identity policy.
- Legacy workspace-tool-provider surfaces:
  - provider registry protocols and event dispatchers cannot publish
    agent-addressing events or listings outside team-authorized provider views,
  - any retained legacy dispatcher behavior is telemetry-only and covered by
    tests/static review.
- Runtime resolution:
  - Linear event plus team membership resolves to the expected workspace
    context,
  - Linear event targeting an out-of-team app user is rejected before an
    `AgentRuntimeHandle` is created,
  - Linear event targeting a provider identity authorized in multiple teams is
    rejected as ambiguous before an `AgentRuntimeHandle` is created,
  - Linear monitor reconciliation uses team-authorized provider views and does
    not advance watermarks for unprocessed no-team, out-of-team, or ambiguous
    identities,
  - Linear OAuth/webhook verification authenticates provider source without
    bypassing team-authorized recipient selection,
  - `AgentRuntimeHandle` receives the resolved context ID,
  - no team still binds to the default context.
- Operator/runtime starts:
  - scheduled/manual flows and diagnostics runs use default context unless a
    provider event supplies context,
  - team, no-team, unknown-team, and active-terminal reuse cases are covered,
  - provider-conversation idempotency is written only after team authorization
    succeeds.
- Durable baton state:
  - active baton records have explicit behavior after team changes or removal,
  - pass, return, complete, block, reassign, watchdog nudge, and watchdog orphan
    paths revalidate or classify stored terminal participants according to the
    chosen policy,
  - stored terminal ids in `originator_id`, `current_holder_id`, and
    `return_stack` do not silently authorize stale cross-team collaboration.
- Collaboration:
  - same team can collaborate,
  - different teams with different workspaces are rejected with a clear message,
  - different teams with the same workspace are still rejected with a clear message,
  - missing team is rejected for team-aware collaboration,
  - direct messaging, handoff, delegation, and provider-originated teammate
    lookup all use the same message-policy owner surface,
  - direct REST and CLI inbox writes cannot bypass the inbox delivery policy,
  - inbox read/reply by notification id verifies current caller/receiver
    ownership and current team/provider authorization,
  - direct diagnostic terminal access remains possible only through its existing
    owner surface.
- Dashboard/API, if touched:
  - a Teams tab can create/manage teams, choose team workspace, and show members,
  - team name, derived workspace name, and active workspace context render for
    selected agents,
  - agent configuration shows team membership as editable while team-derived
    workspace is read-only/disabled for teamed agents,
  - saving agent configuration cannot persist an agent-level workspace override for
    a teamed agent,
  - timeline or runtime events that explain routing/collaboration include team
    context where relevant,
  - diagnostics render without blocking unrelated agent inspection,
  - Safari end-to-end verification exercises the backend-served dashboard, not
    only component tests or a Vite-only dev server.

## Verification Matrix

Implementation is not complete until each acceptance claim has observable
evidence. Do not rely on illustrative providers that do not exist in production
unless the test is explicitly exercising the provider-agnostic team/workspace
contract.

| Claim | Required evidence |
| --- | --- |
| Agent config supports one team | Parse/write tests load real temporary agent directories with `[workspace] team`, no team, legacy `[workspace_context]`, and both shapes present. Legacy `[workspace_context]` must be rejected or diagnosed as unsupported and must not produce team membership. |
| CLI agent management reflects team membership | CLI tests cover create/show/list/edit/start behavior for team membership, derived workspace metadata, diagnostics, and intentionally standalone no-team creation where applicable. |
| Team/workspace definitions are localized | Code review verifies workspace/team public types, registries, manager, and provider-view contracts live under the workspace subsystem; consumers import the public surface. |
| Dashboard-managed teams have one owner | Service/API/component tests prove team create/update/list/validation flows use the localized `WorkspaceTeamService` and persisted team store, bootstrap teams seed through the same owner surface, reloads preserve team definitions, and tests use isolated team storage rather than process-global mutable registries. |
| Team owns final addressability | Manager tests use a real in-process test provider adapter that returns candidate mappings for Agent A and Agent B, then verify only team-member candidates become authorized. The manager itself must not be mocked. |
| Team workflow does not grant provider power | Tests configure two agents on the same team with different provider grants and verify each agent's effective provider tool access remains agent-specific. |
| Workspace context identity is workspace/resolver-scoped | Workspace context store and migration tests prove different workspace/resolver namespaces cannot silently share one provider-object context, while two teams sharing a workspace can intentionally share the same resolved context. |
| Linear candidate mapping still owns Linear domain details | Linear tests build candidate mappings from real temporary agent configs containing `[linear]` fields and assert `app_key`, `app_user_id`, tool access, and validation behavior come from Linear-owned code. |
| Linear identity uniqueness is explicit | Linear tests classify `app_key`, `oauth_state`, `webhook_secret`, `app_user_id`, and `app_user_name` uniqueness behavior and prove manager-level ambiguity coverage does not depend on Linear duplicate identities being allowed. |
| Legacy workspace-tool-provider surfaces are classified | Static search and `test/workspace_tool_providers/` coverage prove retained registry protocols/event dispatchers cannot address agents outside team-authorized provider views, or are documented/tested as telemetry-only. |
| Linear pruning works | With Agent A and Agent B both having valid Linear config but only Agent A in team `cao_delivery`, team-bound Linear lookup resolves A and does not resolve B by app key, app user id, or app user name. |
| Provider tool access is pruned | With out-of-team Linear tool access configured for Agent B, the team-bound provider tool surface does not expose B's tools in `cao_delivery`. |
| Runtime resolution uses authorized mappings | A Linear issue event for Agent A resolves through the collaboration manager and creates/uses an `AgentRuntimeHandle` with the resolved workspace context id. |
| Runtime rejection is early | A Linear issue event for Agent B, outside the team, is rejected before an `AgentRuntimeHandle` is constructed, before a terminal is started, and before an inbox notification is queued. |
| Ambiguous provider events fail closed | A provider event identity authorized in two teams is rejected with an ambiguity diagnostic before an `AgentRuntimeHandle` is constructed, before a terminal is started, and before an inbox notification is queued. |
| Provider-originated rejection diagnostics are useful | Linear/provider event tests prove rejected authenticated events produce visible diagnostics that distinguish no-team, out-of-team, and ambiguous identity cases and include enough provider identity plus team/workspace context for an operator to understand why CAO did not deliver an agent message. |
| Linear monitor is team-bound | Monitor presence iteration, synthetic event creation, pending-delivery retry, and watermark advancement all use team-authorized provider views; unprocessed no-team, out-of-team, and ambiguous identities do not advance watermarks. |
| Linear OAuth/webhook source verification is not recipient routing | Linear app service and route tests prove OAuth state, token lookup, webhook secret verification, and stamped webhook metadata authenticate source only and cannot bypass team-authorized event selection. |
| Default runtime context survives | Starting an agent with no team still creates a terminal in the default workspace context and does not attempt provider-event resolution. |
| Flow runtime starts are classified | Flow service/API/CLI tests prove scheduled/manual flow execution uses default runtime context unless a provider event supplies context, handles team/no-team/unknown-team cases, and does not reuse stale active terminals across team changes without diagnostics. |
| Diagnostics runtime starts are classified | Diagnostics provider tests prove diagnostic runtime starts use default context unless explicitly testing provider context, surface team diagnostics, and handle existing active terminals intentionally. |
| Provider conversation idempotency is team-safe | Persistence tests prove processed-event markers, provider-conversation records, and agent runtime notifications are not recorded as successful before team authorization succeeds for no-team, out-of-team, or ambiguous provider events. |
| Monitoring remains diagnostic-only | Monitoring service/API/CLI/docs tests prove monitoring reads historical terminal inbox records without authorizing collaboration and handles team changes, context switches, peer filters, and rejected cross-team messages as documented. |
| Collaboration boundaries hold | Public messaging/handoff surfaces allow same-team collaboration and reject different-team or missing-team collaboration with clear text naming both agents and team mismatch. Tests must include two different teams that share one workspace and prove they are still rejected. |
| Messaging policy is first class | Direct messaging, handoff, delegation, provider-originated teammate lookup, REST inbox writes, and CLI inbox writes go through one public policy owner or equivalent shared guard; tests cover at least two distinct owner surfaces so a bypass cannot survive in a sibling route. |
| Inbox read/reply cannot bypass policy | `read_inbox_message` and `reply_to_inbox_message` require current caller/receiver ownership plus current team/provider-view authorization; tests prove notification id possession and stored Linear app metadata do not bypass policy. |
| Collaboration does not compare raw workspace ids | Static search/code review verifies collaboration guards call the manager/public team API and do not authorize communication by directly comparing `workspace` ids. |
| Existing runtime state is classified | Tests cover active terminals and pending inbox notifications when team membership changes or is removed, including runtime context switch notification movement. |
| Active baton state is classified | Baton service/store/watchdog tests prove active baton records have explicit behavior after team changes or removal, including pass, return, complete, block, reassign, watchdog nudge, watchdog orphan, and stored originator/current-holder/return-stack participants. |
| Admin recovery surfaces are explicit | Baton HTTP/CLI recovery endpoints are either guarded by message policy or tested/documented as operator/admin recovery actions rather than agent collaboration. |
| Provider MCP surfaces refresh on team policy changes | Tests prove team membership or team provider-view changes invalidate stale provider-mediated tool exposure through MCP freshness/fingerprint logic. |
| Agent-facing protocol text matches policy | MCP descriptions, injected callback text, bundled skills, repo-root skills, docs, diagrams/assets, and e2e prompts no longer present terminal id possession as sufficient authority for collaboration. |
| Diagnostics are visible | Unknown team, team referencing unknown workspace, unavailable provider, legacy config conflict, and pruned provider identity diagnostics are visible through the owning API/service surface. |
| Legacy code paths are removed | Static search and focused tests verify production code no longer uses `[workspace_context]` for behavior, direct resolver-id dispatch is gone from agent-owned routing, no resolver-to-team compatibility table participates in normal loading/runtime behavior, and examples/docs no longer present the legacy model as valid configuration. |
| Dashboard team management prevents foot guns | API/component/browser tests prove the dashboard exposes a Teams tab for team creation/management, shows team workspace and members, changes workspace through the team owner surface, renders team-derived workspace as read-only/disabled in agent configuration, and never saves an agent-level workspace override for a teamed agent. |
| Dashboard Teams tab works end to end in Safari | Safari verification against the backend-served dashboard creates or edits a team, selects a workspace through the Teams tab, confirms member agents render under that team, opens a teamed agent configuration, verifies the workspace control is read-only/disabled, changes team membership where applicable, saves, reloads the page, and confirms the persisted team/workspace state still renders correctly. |
| UI behavior works if touched | Component tests cover rendered fields/actions, `npm run build` passes, and Safari verifies the backend-served dashboard path that changed. |

The provider-agnostic pruning test is required even before a GitHub provider
exists. It should implement the real candidate-mapping adapter protocol in test
code and exercise the collaboration manager's team authorization logic.
GitHub-specific behavior is not required until a GitHub provider exists.

## Required Verification Commands

The final implementation report must list the exact commands run and their
results. At minimum, run the narrow tests added for this plan plus the relevant
existing suites they touch.

Expected verification shape:

- `uv run pytest ...` for agent config, team/workspace manager, Linear provider
  mapping, Linear runtime event handling, and collaboration boundary tests.
- `npm test -- ...` for dashboard component changes, if the web UI is touched.
- `npm run build`, if frontend code or generated API types are touched.
- Safari end-to-end verification of the backend-served dashboard, if dashboard
  UI or runtime links/actions are touched. The report must name the served URL
  class used, the Teams tab actions clicked, the agent configuration controls
  inspected, the save/reload persistence check, and the observed result.
- `git diff --check`.

If any command cannot be run, the implementation is not complete until the
blocker is documented in the completion report and either resolved or accepted
by the operator.

Implementation evidence captured on May 17, 2026:

- Backend-served Safari target: `http://127.0.0.1:9889/?tab=agents`, served by
  `uv run cao-server --host 127.0.0.1 --port 9889`.
- Safari rendered the Agents tab with three configured agents after the server
  was restarted, confirming the earlier "No agents configured" view was a stale
  offline tab state rather than persisted agent loss.
- Safari Teams tab created `safari_review_team`, selected
  `linear_delivery`, saved it, rendered the created team, edited its
  display name to `Safari Review Team Updated`, and rendered persisted workspace
  and member state.
- Safari rendered `cao_delivery` members as `implementation_partner`.
- Safari opened the teamed `implementation_partner` agent config, entered edit
  mode, showed team `cao_delivery`, showed derived workspace
  `linear_delivery` in a disabled/read-only field, saved successfully,
  reloaded, and confirmed the team/workspace state still rendered correctly.

## Definition of Done

The work is done only when all of the following are true:

- Agents reference workspace team membership through exactly one new
  authoritative config field, `[workspace] team`.
- Agent config parse/write behavior is verified through real temporary config
  files, including no-team and legacy-conflict cases.
- CLI agent management surfaces create, show, list, edit, and start agents with
  clear team membership, derived workspace metadata, diagnostics, and documented
  standalone no-team behavior where applicable.
- The dashboard has a first-class Teams tab where operators can create/manage
  teams, inspect team members, inspect diagnostics, and change the team's
  workspace through the team owner surface.
- Dashboard-managed teams are persisted through one localized
  `WorkspaceTeamService`/store owner surface. Code-owned bootstrap teams seed
  that owner surface, workspace definitions remain code-owned, and no team
  definition is stored only in process-global mutable registries, API-local
  state, or frontend-only state.
- Agent configuration in the dashboard treats team membership as the editable
  agent field and workspace as derived metadata. For teamed agents, the
  workspace control is read-only/disabled and cannot save an agent-level workspace
  override.
- Safari end-to-end verification against the backend-served dashboard proves
  the Teams tab and agent configuration workflow works: create or edit a team,
  select a team workspace, verify team members render, open a teamed
  agent configuration, confirm workspace is read-only/disabled, save, reload, and
  confirm persisted team/workspace state still renders correctly.
- Workspace team definitions, workspace definitions, candidate
  authorization, provider-view creation, diagnostics, and collaboration checks
  are localized behind one public workspace/team subsystem surface.
- Each workspace owns exactly one resolver, and tests fail if a workspace
  attempts to define more than one.
- Each workspace team points at exactly one workspace, and tests fail when a team
  references an unknown workspace.
- Workspace context identity is workspace/resolver scoped, with migration/backfill
  coverage and explicit tests for shared-workspace sharing versus different-workspace
  collision prevention.
- Providers create candidate mappings using provider-owned domain logic; team
  authorization decides which candidates become CAO-addressable.
- Legacy workspace-tool-provider registry protocols and event dispatchers are
  retired, telemetry-only, or routed through team-authorized provider views
  before they can address agents.
- Linear provider identity uniqueness is explicitly classified and tested; the
  generic ambiguous-provider-event behavior is not dependent on Linear allowing
  duplicate identities.
- Team workflow availability and agent-specific provider grants are both
  required for effective provider tool access.
- Same-team agents may have different provider permissions; team membership
  never grants provider tool access by itself.
- Provider-agnostic pruning is verified with a real test adapter implementing
  the public provider adapter contract.
- Linear pruning is verified concretely: an out-of-team agent with valid
  Linear credentials cannot be resolved by app key, app user id, app user name,
  provider event, or provider tool-access lookup inside another team.
- Linear provider behavior that should still work is verified through the new
  manager path, including a successful issue event for an in-team agent.
- Out-of-team provider events are rejected before terminal creation, runtime
  handle construction, or inbox notification creation.
- Provider events that match multiple teams are rejected as ambiguous before
  terminal creation, runtime handle construction, or inbox notification
  creation.
- Provider-originated rejection diagnostics are visible and useful: an operator
  can distinguish authenticated-but-not-addressable events from auth failures,
  no-team agents, out-of-team agents, and ambiguous cross-team matches, with
  enough provider identity and team/workspace context to understand why CAO did not
  deliver an agent message.
- Linear monitor reconciliation is team-bound, and watermarks do not advance
  for no-team, out-of-team, or ambiguous identities that were not safely
  processed.
- Linear OAuth/webhook verification authenticates provider source but does not
  select CAO recipients outside team-authorized event selection.
- Agents without team membership still start in the default workspace context
  and do not receive provider-event context switching.
- Scheduled/manual flow execution is classified as operator runtime start,
  default-context behavior and diagnostics are covered, and stale active
  terminal reuse after team changes is tested.
- Diagnostics provider runs are classified as operator runtime starts, with
  default-context behavior, team diagnostics, and active-terminal behavior
  tested.
- Provider-conversation persistence/idempotency writes happen only after team
  authorization succeeds and carry enough team/workspace metadata to avoid stale or
  wrong-team recipient state.
- Monitoring sessions are terminal/operator diagnostics only; they preserve or
  annotate historical inbox records across team changes according to documented
  behavior and never authorize collaboration.
- Same-team collaboration succeeds through the public messaging/handoff owner
  surface; different-team and missing-team collaboration fail with clear,
  user-visible rejection text.
- Messaging policy is implemented as a first-class shared owner surface or
  equivalent public guard that is reused by direct messaging, handoff,
  delegation, provider-originated teammate lookup, REST inbox writes, and CLI
  inbox writes.
- Inbox read/reply tools require current caller/receiver ownership and current
  team/provider-view authorization; notification id possession and stored
  provider metadata do not authorize access by themselves.
- Different teams that share the same workspace are still rejected by
  collaboration checks.
- Collaboration guards go through the public team/collaboration manager API and
  do not authorize communication by directly comparing workspace ids.
- Existing active terminals, pending inbox notifications, and runtime context
  switch inbox moves have explicit team-change behavior covered by tests.
- Active baton records have explicit team-change behavior covered by tests for
  pass, return, complete, block, reassign, watchdog nudge, watchdog orphan, and
  stored originator/current-holder/return-stack participants.
- Baton HTTP/CLI recovery endpoints are explicitly classified as guarded
  collaboration or operator/admin recovery, with tests for the chosen behavior.
- Provider-mediated MCP tool freshness/fingerprints account for team-bound
  provider policy so stale terminals cannot retain tools after team/provider
  view changes.
- Agent-facing protocol text, MCP descriptions, bundled skills, repo-root
  skills, docs, diagrams/assets, and e2e prompts align with same-team message
  policy.
- Unknown team names, teams that reference unknown workspace names, unavailable
  providers, legacy config conflicts, and pruned provider identities produce
  diagnostics visible through the owning service/API surface.
- Shared names and values introduced by this work, including `[workspace] team`,
  team ids, workspace ids, provider ids, CLI flags, API field names, and dashboard
  option values, have authoritative definitions that consumers import or
  reference instead of copying literals across boundaries.
- New registries, managers, stores, dashboard APIs, and tests are parallel-safe:
  no fixed ports, shared test paths, process-global mutable registries, or leaf
  global-state reads are introduced. Environment or host state is read only at
  composition/configuration boundaries and passed inward explicitly.
- Production constructors, adapters, exports, and helper APIs exist for the
  contracted architecture or runtime behavior, not only to make tests easier.
  Tests exercise production owner surfaces and real seams rather than widening
  production code with test-only hooks.
- Legacy `[workspace_context]` behavior paths, direct resolver-id dispatch,
  resolver-to-team compatibility mappings, and old examples/docs are removed.
  Production loading may only detect `[workspace_context]` to emit an
  unsupported-legacy diagnostic/error; it must not accept it as migration input,
  translate it into `[workspace] team`, or use it to authorize runtime behavior.
- Every changed behavior in the verification matrix has passing automated
  coverage through owner surfaces and relevant seams.
- Tests added or updated for this plan use Given/When/Then structure, keep
  assertions in Then clauses, preserve the target behavior being tested, mirror
  production file organization, and keep generated files, databases, repos, and
  other artifacts inside isolated test-owned locations.
- If dashboard or API-visible UI behavior changes, component tests, production
  build, and Safari end-to-end verification of the served dashboard all pass.
- A review loop has inspected the completed diff against this plan and the
  criteria catalog.
- After implementation, evaluate the pending changes against the criteria
  catalog. No criteria applicable to the completed diff may be violated.

## Criteria Catalog

The criteria catalog was reviewed with:

```bash
uv run python scripts/catalog_criteria.py --format json
```

Likely implementation criteria for this work:

- `authoritative-sources-are-referenced-not-copied`
- `do-not-assume-backwards-compatibility`
- `migration-discipline`
- `minimal-cohesive-changes`
- `no-global-state-reads`
- `no-test-only-production-seams`
- `no-unnecessary-duplication`
- `parallel-safe-execution`
- `prefer-public-surfaces`
- `properly-designed-shared-code`
- `readable-and-explicit`
- `simple-systems`
- `system-code-locality`
- `system-definitions-are-localized`

Likely test criteria for this work:

- `all-system-interactions-are-verified-by-tests`
- `assertions-occur-in-the-then-clause`
- `given-when-then-test-structure`
- `reusable-given-state`
- `seams-must-be-tested`
- `target-behavior-must-not-be-mocked`
- `test-artifact-containment`
- `test-file-organization`
- `test-through-owner-surfaces`
- `test-validity-preserved`
- `ui-changes-require-real-browser-verification` if dashboard behavior changes.

Implementation must reload any criteria whose `when` clauses match the actual
diff before final review.

## Open Questions

- Do we need an explicit future bridge concept for agents that belong to
  different teams but are allowed to communicate through a user-approved
  gateway?
