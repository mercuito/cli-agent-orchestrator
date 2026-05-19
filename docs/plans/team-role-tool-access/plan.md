# Team Role Tool Access

Status: draft

## Problem

Workspace teams now define the collaboration boundary and the workspace setup
that team members share, but provider-mediated MCP tool access is still authored
primarily on individual agents.

That creates a mixed authority model:

- the team decides whether a provider grant is valid for a team member;
- the agent still owns the actual provider tool grants;
- the dashboard can show effective tools, but the source of truth is split
  between team membership and agent-local tool access blocks.

The product model should be tighter. If an agent belongs to a team, the team
should describe the workflow and the roles inside that workflow. Role assignment
should determine the agent's provider and built-in CAO MCP tool access for the
workspace providers registered to the team's setup.

At the same time, unteamed agents remain valid. They need a standalone tool
access path so CAO can still run solo agents, experiments, utilities, and
non-workspace agents without forcing every agent into a team.

## Dependency On ToolService Consolidation

This plan is a follow-on to
`docs/plans/effective-tool-access-consolidation/plan.md`.

Do not start this implementation until ToolService consolidation is accepted.
Accepted means ToolService is the single production authority for effective tool
registration, invocation, MCP materialization, provider-conversation decisions,
API/CLI/dashboard display, and inactive local diagnostics.

This plan must not reintroduce direct authority reads in consumers. Team roles
and standalone agent-local access are source adapters that feed ToolService.
Callers still ask ToolService for effective access.

The implementation goal is not "add team roles beside the existing access
logic." The implementation goal is "teach ToolService how to choose exactly one
grant source for each agent."

## Target Mental Model

- An agent belongs to zero or one workspace team.
- A team points at one workspace setup.
- A team defines one or more roles.
- Every team has a default role named `member`.
- A team member has one assigned role in that team, defaulting to `member`
  when no explicit assignment exists.
- The role defines the team-owned MCP tool policy for that member.
- Team-owned tool policy is the primary authority for teamed agents.
- Agent-local MCP tool policy remains the authority for unteamed agents.
- Provider identity remains agent-owned. Provider access moves to team roles
  when the agent is teamed.
- Agent-local direct MCP server attachments are also tool access. They are
  inactive for teamed agents and remain active for unteamed agents.
- Agent-local provider-specific nested config that can attach MCP servers, such
  as Codex `codex_config.mcp_servers`, is also direct MCP tool access. It is
  inactive for teamed agents and active only for unteamed agents according to
  the provider's standalone config rules.
- The managed CAO MCP server attachment is orchestration infrastructure, not a
  role-owned direct MCP server. Role policy controls which CAO tools it exposes;
  it does not make the server attachment optional when CAO-managed tools are
  needed.
- Provider-native runtime capabilities such as `runtime_capabilities`, `tools`,
  `tool_aliases`, and `tools_settings` remain agent-owned runtime configuration
  in this plan. Team roles own MCP tool access, not coarse provider-native
  shell/filesystem/tool-blocking policy.

The effective rule:

```text
if agent has workspace.team:
  effective MCP tools = team role policy for that agent
else:
  effective MCP tools = agent-local MCP tool policy
```

ToolService must implement this as a source-selection rule, not as a merge:

```text
if agent.workspace.team is set:
  access source = TeamRoleToolAccessSource(team, resolved_role)
  inactive source = StandaloneAgentToolAccessSource(agent)
else:
  access source = StandaloneAgentToolAccessSource(agent)
  inactive source = none
```

Both sources should produce the same normalized grant shape:

- built-in CAO MCP tool grants;
- provider-mediated tool grants;
- direct/custom MCP server grants;
- provider-conversation grants or requirements;
- source markers;
- diagnostics.

ToolService chooses one source and exposes the effective result. It may expose
the inactive source only as diagnostics/presentation data. It must never merge
team role grants with agent-local grants for a teamed agent.

This rule covers the tool surface exposed through the managed CAO MCP server
and through direct/custom MCP servers. It does not mean `cao-mcp-server` itself
is user-authored role policy. CAO owns and materializes that managed server for
CAO-managed terminals, and the effective `cao_tools` allowlist determines which
built-in CAO tools are visible through it.

## Locked Vocabulary

Use **workspace team** for the collaboration boundary.

Use **workspace setup** for the provider/resolver/context machinery shared by
a team.

Use **team role** for a named permission profile inside a workspace team.

Use **role assignment** for the team's mapping from agent id to role id.
Missing role assignment means the team member uses the default `member` role.

Use **agent-local tool access** for the standalone, unteamed access path.
Agent-local access is not legacy for unteamed agents. It is only superseded
when the agent is a team member.

Agent-local tool access includes explicit top-level `cao_tools`,
provider-native tool access blocks, top-level `mcp_servers`, and
provider-specific nested config that can attach MCP servers.

Use **managed CAO MCP server** for the CAO-owned `cao-mcp-server` runtime
attachment that exposes built-in CAO tools. It is distinct from direct/custom
`mcp_servers` configured by an agent or team role.

Use **built-in CAO tool descriptor** for backend-owned metadata about tools
served by the managed CAO MCP server: name, description, category/risk where
useful, feature gate, and whether the default `member` role grants it.

Use **provider-native runtime capabilities** for non-MCP launch controls such
as shell/filesystem access and provider tool blocking. These remain separate
from team-role MCP access in this plan.

Use **raw transcript surfaces** for historical terminal transcript reads, live
terminal WebSocket streaming, CLI tmux attach, handoff output capture, and
rendered monitoring logs. These are operator/debug surfaces with full transcript
visibility unless a future auth model narrows them.

Use **baton lifecycle tools** for `create_baton`, `pass_baton`,
`return_baton`, `complete_baton`, `block_baton`, `get_my_batons`, and
`get_baton`. These are built-in CAO tools, but baton services also send
messages and nudges that instruct agents how to act on baton state.

Avoid calling role access "workspace scope"; "scope" is too vague for this
model.

## Current Shape

Current built-in CAO MCP tools:

- configured on `Agent.cao_tools`;
- resolved by `resolve_cao_tool_allowlist(agent)`;
- registered at MCP startup from the terminal's agent;
- `None` means permissive fallback for built-in CAO tools.

Current provider-mediated tools:

- Linear tool access is configured under agent-local `[linear.tool_access.*]`;
- providers translate provider-native config into
  `ProviderToolAccessPolicy`;
- `load_enabled_provider_tool_access_policies()` loads enabled providers and
  asks `WorkspaceCollaborationManager.team_bound_provider_tool_access_policies`
  to prune access entries not authorized by team membership;
- MCP startup registers provider tools visible to the terminal's resolved
  agent;
- invocation re-checks terminal-to-agent access before running the provider
  handler.

This means team membership filters provider tool access, but the team does not
yet own the grants.

## Target Configuration Shape

Team definitions should become the home for role policies and assignments.

The exact persisted format may be JSON if the existing `WorkspaceTeamStore`
remains the dashboard-owned persistence boundary. The conceptual shape is:

```toml
[workspace_team.cao_delivery]
workspace_setup = "linear_delivery_setup"

[workspace_team.cao_delivery.roles.member]
cao_tools = ["send_message", "handoff"]
# Direct/custom MCP servers only. `cao-mcp-server` is managed by CAO.
mcp_servers = {}

[workspace_team.cao_delivery.roles.reader]
cao_tools = ["send_message", "handoff"]
mcp_servers = {}

[[workspace_team.cao_delivery.roles.reader.linear.tool_access]]
tools = ["cao_linear.get_issue"]
issues = ["CAO-1", "CAO-2"]

[workspace_team.cao_delivery.roles.planner]
cao_tools = ["send_message", "handoff", "assign"]
mcp_servers = {}

[[workspace_team.cao_delivery.roles.planner.linear.tool_access]]
tools = ["cao_linear.get_issue", "cao_linear.create_issue", "cao_linear.update_issue"]
issues = ["CAO-1", "CAO-2"]
create_team_ids = ["team-1"]
update_fields = ["title", "description", "state"]

[workspace_team.cao_delivery.members.discovery_partner]
role = "reader"

[workspace_team.cao_delivery.members.implementation_partner]
role = "planner"
```

The `member` role is always present. It may be stored explicitly or
synthesized by the team service, but consumers should treat it as a normal role.
By default, `member` grants exactly `send_message` and `handoff`, and no
provider-mediated workspace tools or direct MCP servers. Higher-risk built-in
tools such as `assign`, `terminate`, inbox tools, and baton tools must be
granted explicitly by a role. Baton tools also remain subject to the existing
baton feature gate even when explicitly granted.

Provider-backed inbox tools are special because they are built-in CAO tools
that can perform provider writes. A role grant for `reply_to_inbox_message`
only makes the CAO reply tool visible; it does not by itself authorize a
provider-backed write. The reply path must also satisfy effective role-owned
provider access for the backing provider action, or it must reject with a
diagnostic that names the missing provider access.

Destructive built-in CAO tools are not cross-team powers by default.
`terminate` must require the caller and target terminal to be in the same
workspace team unless a future plan introduces an explicit cross-team
administrative capability.

Linear external URL publication/repair is a provider infrastructure write. It
is allowed only for CAO-owned Agent Session routing metadata, must be
provider-owned and audited, and must not grant agent-facing provider write
access.

Role assignment does not create team membership. Team membership remains
agent-owned through `agent.workspace.team`. Team role assignments are meaningful
only for agents whose `workspace.team` points at that team. If a team stores a
role assignment for an agent that is not currently a member, that assignment has
no effective tool-access impact and should be reported as a cleanup diagnostic
or pruned by the team service. This prevents team role state from becoming a
second membership authority.

Agent config keeps identity and runtime/persona fields:

```toml
[workspace]
team = "cao_delivery"

[linear]
app_key = "implementation-partner"
app_user_id = "..."
app_user_name = "Implementation Partner"
```

For unteamed agents, agent-local access remains valid:

```toml
cao_tools = ["send_message"]

[linear.tool_access.solo_linear]
tools = ["cao_linear.get_issue"]
issues = ["CAO-123"]
```

## Authority Rules

### Teamed Agents

When `agent.workspace.team` is set:

- the team must exist;
- the team member must resolve to exactly one role;
- if no explicit role assignment exists, the agent resolves to the team's
  `member` role;
- the resolved role must exist on that team;
- built-in CAO MCP tools come from the role's `cao_tools`;
- direct MCP server attachments come from the role's `mcp_servers`;
- the managed CAO MCP server is materialized by CAO and filtered by the role's
  `cao_tools`;
- provider-specific nested config that can attach MCP servers, including Codex
  `codex_config.mcp_servers`, must be sanitized, ignored, or validated under
  team authority and cannot widen the direct MCP server surface;
- provider-mediated tool access for providers in the team's workspace setup
  comes from the role's provider access policy;
- role-owned provider grants for providers not included in the team's workspace
  setup are invalid for that team and must be rejected or diagnosed. They must
  never be silently emitted as effective access;
- agent-local provider tool access for providers owned by the team setup must
  not affect the effective MCP surface;
- agent-local built-in `cao_tools` must not affect the effective MCP surface
  while the agent is in a team.
- agent-local direct `mcp_servers` must not affect provider runtime config,
  runtime capabilities, freshness, or the effective MCP surface while the agent
  is in a team.

Agent-local tool grants and MCP server attachments are allowed to remain in the
agent config, but they are inactive while the agent belongs to a team. They
become active again if the agent is removed from the team. This makes team roles
the authoritative source without destroying standalone configuration.

Do not silently merge role grants with agent-local grants for teamed agents. The
dashboard should make the inactive state visible by graying out agent-local tool
controls and explaining that team role access is currently authoritative.

### Unteamed Agents

When `agent.workspace.team` is unset:

- workspace setup and resolver behavior remain disabled for team collaboration;
- built-in CAO MCP tools come from agent-local `cao_tools`;
- direct MCP server attachments come from agent-local `mcp_servers`;
- the managed CAO MCP server is materialized by CAO and filtered by
  agent-local `cao_tools`;
- provider-specific nested config that can attach MCP servers remains active
  only in standalone mode according to the provider's unteamed config rules;
- provider-mediated tool access comes from agent-local provider config, as it
  does today;
- provider identities can still exist on the agent;
- the agent is outside team-aware collaboration and provider addressability.

This is the supported standalone mode, not a deprecated compatibility shim.

### Provider Identity Versus Access

Provider identity remains agent-owned because it describes who the external
provider sees:

- Linear `app_key`;
- Linear `app_user_id`;
- Linear `app_user_name`;
- future GitHub identity or installation/account mapping.

Provider access becomes team-role-owned for teamed agents because it describes
what the team member is allowed to do in the team's workflow.

Role-owned provider access cannot create provider identity. When expanded role
access targets a member that lacks the required agent-owned provider presence
or identity, CAO must not emit usable provider access for that member. It must
produce an actionable diagnostic naming the team, role, provider, member agent,
and missing identity requirement.

## Managed CAO MCP Server Versus Direct MCP Servers

There are two MCP server categories and the implementation must keep them
separate:

- **Managed CAO MCP server**: the CAO-owned `cao-mcp-server` attachment used to
  expose built-in CAO tools such as same-team messaging. CAO materializes this
  for CAO-managed terminals and filters visible tools through effective
  `cao_tools`.
- **Direct/custom MCP servers**: user-configured external MCP server
  attachments. These are `mcp_servers` in agent-local config for unteamed
  agents and role-owned `mcp_servers` for teamed agents.

Role-owned `mcp_servers` must not include or override the managed
`cao-mcp-server`. If an agent-local `mcp_servers` block contains
`cao-mcp-server`, CAO should de-duplicate or override it with the managed
definition rather than treating it as user-controlled team access.

The important invariant is:

```text
effective cao_tools controls CAO built-in tool visibility
effective direct/custom mcp_servers controls extra server attachments
managed cao-mcp-server attachment is owned by CAO runtime materialization
```

## Role Access Expansion

Provider-mediated access remains agent-scoped at the MCP authorization layer.
A team role is reusable, so role-owned provider access must be expanded before
provider policy normalization:

```text
for each team member whose effective role is R:
  for each provider access entry on R:
    emit ProviderToolAccessRequest(agent_id=member_agent_id, ...)
```

The expanded request must include a member-specific `agent_id` and a stable
source location that names the team, role, provider, access entry, and target
member. A role assignment for a non-member must not emit access requests.

Do not push "role id" into provider handlers as a replacement for `agent_id`.
Providers and MCP invocation still authorize concrete agents; the team role
layer only decides which concrete agent-scoped requests are emitted.

## Role Assignment And Membership Authority

Team membership and role assignment are related but not interchangeable:

- `agent.workspace.team` is the only source of team membership.
- Team role assignments do not make an agent a member.
- A role assignment for a non-member is inactive and should be surfaced as an
  actionable team diagnostic or removed by the owner service.
- A member without an explicit assignment resolves to `member`.
- A member with an explicit assignment resolves to that assigned role.
- Team metadata updates are not role-policy updates. Updating a team's display
  name or workspace setup must preserve existing roles, role assignments,
  role-owned `cao_tools`, provider access, and role-owned `mcp_servers` unless
  the request explicitly uses a role-policy update endpoint.

This preserves the existing "agent belongs to zero or one team" invariant and
prevents the team store from accidentally becoming a second membership source.

## Provider-Owned Role Access Schema

The dashboard must not hard-code Linear's tool names, access fields, or
provider-native validation rules when editing team role access.

Each provider that supports role-owned access should expose an authoritative
schema/descriptor through a backend-owned public surface. The schema should
describe:

- provider name;
- available provider-mediated tool names and descriptions;
- role-access fields needed to grant those tools;
- field types and validation constraints;
- provider-owned defaults where applicable.

For Linear, this schema is derived from the existing Linear provider tool
definitions and Linear access config vocabulary. React components consume the
backend schema; they do not copy Linear constants from Python into TypeScript.

The same provider-owned conversion path should translate persisted team role
access into provider-mediated access requests. That keeps the role model
provider-agnostic while preserving provider ownership of domain vocabulary.

## Provider Conversation Access Requirements

Provider-backed inbox notification, preview, read, and reply behavior must use
a provider-owned access requirement descriptor. The descriptor maps each
provider-conversation operation to the explicit provider access entry or tool
that authorizes it.

For Linear, the implementer must make this contract concrete rather than
inferring it from team membership or app presence. If the existing Linear
mediated tool vocabulary does not have the right operation for an existing
Agent Session reply/activity write, add provider-owned vocabulary such as a
dedicated reply/create-activity mediated tool or a non-MCP provider access
capability that is exposed through the same role access schema and validation
surface.

The descriptor must cover at least:

- provider notification preview delivery;
- provider-backed `read_inbox_message`;
- provider-backed `reply_to_inbox_message`;
- any provider write performed by `create_agent_activity` or equivalent direct
  app-client calls.

The provider must also classify CAO infrastructure operations separately from
agent-facing access. Infrastructure operations are operations CAO performs to
route, evaluate, recover, or diagnose provider events before any content is
exposed to an agent. For Linear this includes monitor polling/recovery,
policy fact reads, and policy-denial comments. These operations are not agent
MCP tool grants, but they must be explicit provider-owned requirements with
tests, diagnostics, and minimal data exposure guarantees.

Existing provider-specific guardrail policy layers, such as Linear incoming
agent policies, remain provider-owned guardrails unless a future plan replaces
them. They are evaluated after team-role provider-conversation access has made
the operation eligible. A role grant is necessary for access but does not
override provider-owned guardrail denial; guardrail denial must produce clear
diagnostics so users can distinguish "role lacks access" from "provider policy
rejected this event."

This keeps provider-conversation policy explicit and prevents implementers from
guessing whether a reply maps to `cao_linear.open_agent_session_on_issue`, a
read tool, or a separate provider capability.

## Design Constraints

- Keep role definitions in one localized team/workspace authority. Do not
  scatter role schema across API models, frontend-only types, and provider
  internals.
- Providers continue to own provider-native vocabulary and conversion to
  provider-mediated tool definitions.
- Built-in CAO MCP tool vocabulary must also have a backend-owned public
  descriptor surface. The dashboard must not hard-code CAO tool names or
  descriptions in React.
- The team role layer should own authorization and selection of access entries,
  not Linear-specific parsing.
- Role assignments must not create membership. They apply only to agents whose
  agent config already points at the team.
- Provider tool editing UI must consume backend/provider-owned schema rather
  than hard-coding Linear access fields.
- Provider-conversation access requirements must be provider-owned and exposed
  through the same schema/validation model as role-owned provider access.
- Direct MCP server materialization must consume effective role-owned
  `mcp_servers` for teamed agents and agent-local `mcp_servers` for unteamed
  agents.
- Provider-specific nested config that can attach MCP servers, especially Codex
  `codex_config.mcp_servers`, must be folded into the same effective direct MCP
  server policy and cannot bypass role authority for teamed agents.
- Managed `cao-mcp-server` materialization is separate from direct/custom
  `mcp_servers` and must remain available for CAO-managed terminals even when
  effective direct/custom `mcp_servers` is empty.
- The default `member` CAO tool set must be a concrete backend-owned constant:
  exactly `send_message` and `handoff`.
- MCP tool freshness descriptors must use the same effective access source as
  MCP registration and invocation.
- Provider-native runtime capability fields remain agent-owned and must not be
  accidentally folded into team role access. The only role-derived entries in
  provider `allowed_tools` are MCP server markers produced from effective
  direct/custom MCP server policy.
- The dashboard must show inherited role access for teamed agents as read-only
  effective access.
- The dashboard must let unteamed agents continue to edit agent-local access.
- Running terminals may need restart to pick up changed MCP registration; the
  UI should say this where tool access changes are user-visible.
- Same-team collaboration policy remains unchanged by this plan.

## Non-Goals

- Cross-team messaging or bridges.
- Multiple roles per team member.
- Multiple workspace setups per agent.
- Provider identity management UI beyond preserving the current agent-owned
  identity fields.
- A GitHub provider implementation.
- Fine-grained per-agent exceptions on top of a team role. Add that later only
  with a clear product reason.

## Migration Position

This plan intentionally changes the effective authority model for teamed
agents.

The implementer must not preserve old teamed-agent behavior by merging
agent-local provider tool access into role access. That would keep the footgun.

Agent-local tool access remains first class only for unteamed agents.

If the current sample/bootstrap agents are teamed and still carry local Linear
tool access, migrate the intended active access into team roles as part of the
implementation. The local config may remain as inactive standalone fallback, but
it must not affect the teamed agent's effective MCP surface.

## Expected Code Areas

Likely affected areas include:

- `workspace_setups/manager.py` or a new adjacent team role access service for
  effective team role resolution;
- `workspace_setups` public exports for role data structures;
- `WorkspaceTeamStore` persisted shape and tests;
- `workspace_providers/registry.py` for loading effective provider policies;
- `workspace_providers/tool_access.py` if the current access request shape
  needs a role-owned equivalent or a role-to-agent expansion boundary before
  `ProviderToolAccessRequest` normalization;
- `linear/workspace_provider.py` because current Linear config loading and
  `has_provider_tool_access_config()` are driven by agent-local tool access,
  and because Linear identity/OAuth helpers currently load through a config
  path coupled to agent-local tool-access validation;
- `linear/workspace_setup_adapter.py` because current Linear candidate mappings
  emit agent-local `tool_access` mappings into team provider views;
- `linear/provider_tools.py` because Linear owns mediated tool definitions,
  input schemas, hooks, and conversion to access requests;
- `mcp_server/server.py`, `mcp_server/freshness.py`, and
  `mcp_server/provider_tools.py` so visible tools, freshness fingerprints, and
  runtime registration all agree;
- `workspace_providers/invocation.py` because provider-mediated invocations
  must not rely only on startup-time policy snapshots after role access is
  revoked;
- `mcp_server/server.py` built-in CAO tool implementations and descriptions,
  because `assign`, `send_message`, `handoff`, and `terminate` generate
  runtime guidance or perform target-sensitive actions that must respect
  effective roles and same-team policy;
- a built-in CAO MCP tool descriptor module/API derived from the managed CAO
  tool registry, so role editing and validation have one backend-owned source
  for CAO tool names and feature gates;
- `services/terminal_service.py` and `runtime/agent.py` because terminal
  runtime material/fingerprints currently include agent-local `cao_tools` and
  must not restart or stale a teamed runtime because inactive local grants
  changed;
- `utils/tool_mapping.py` because runtime capability resolution currently mixes
  provider-native runtime capabilities with MCP server markers in
  `allowed_tools`, and the implementation must keep their authorities separate;
- `utils/codex_home.py`, `providers/codex.py`, `providers/claude_code.py`,
  `providers/gemini_cli.py`, and `providers/kimi_cli.py` because provider
  runtime materialization currently reads agent-local `mcp_servers` directly;
- `providers/gemini_cli.py` because Gemini writes direct MCP servers into
  global `~/.gemini/settings.json` and must reconcile/remove stale servers when
  effective access changes or inactive local servers are no longer allowed;
- `utils/codex_home.py` and `providers/codex.py` because Codex materialization
  can also inherit `codex_config.mcp_servers` through the deep-merged
  provider-specific config path;
- `providers/copilot_cli.py` because it has a separate
  `--additional-mcp-config` path for the managed CAO MCP server and must remain
  aligned with the effective tool access model;
- all provider runtime launch paths that attach MCP config, because managed
  `cao-mcp-server` materialization must be separated from direct/custom
  `mcp_servers`;
- `diagnostics/providers/codex.py` because Codex diagnostics currently compute
  expected MCP servers from agent-local `mcp_servers` and must instead use the
  effective source;
- `agent.py` and `cli/commands/agent.py` because agent validation/edit flows
  currently validate local Linear tool access without considering whether that
  access is inactive under team authority;
- `cli/commands/agent.py` because CLI inspection commands must not present
  inactive teamed local `cao_tools`, `mcp_servers`, or provider access as if
  they are effective;
- `skills/cao-supervisor-protocols/SKILL.md`,
  `skills/cao-worker-protocols/SKILL.md`, and `cli/commands/init.py` because
  bundled prompt/skill material must not promise tools that a role may hide;
- `services/baton_service.py` and `services/baton_watchdog_service.py` because
  baton creation, transfer, holder guidance, originator guidance, and watchdog
  nudges can instruct agents to call baton tools that their effective role may
  not expose;
- `provider_conversations/inbox_authorization.py` and
  `provider_conversations/reply_service.py` because provider-backed inbox read
  and reply tools currently authorize through receiver/team/presence checks
  rather than effective role-owned provider access;
- `provider_conversations/inbox_bridge.py`, `services/inbox_service.py`, and
  `linear/runtime.py` because provider-backed notification creation and
  terminal delivery can include message previews before an agent invokes a
  gated read/reply tool;
- `api/main.py`, `services/monitoring_service.py`, and `cli/commands/inbox.py`
  because stored inbox list, monitoring/session message, and CLI output paths
  can expose persisted provider-backed notification bodies after delivery;
- `services/terminal_service.py`, terminal output APIs/CLI/dashboard output
  viewer, monitoring log artifacts, and handoff output capture because raw
  transcripts can contain provider-backed notification content after terminal
  delivery;
- live terminal WebSocket streaming, dashboard terminal view, and CLI tmux
  attach paths because they expose the same raw transcript/operator surface as
  terminal output reads;
- `linear/provider_tools.py` because Linear must own the provider-conversation
  access requirement vocabulary and schema for preview/read/reply/activity
  operations;
- `linear/monitor.py` because monitor reconciliation polls Agent Sessions,
  synthesizes/retries notifications, and advances watermarks independently of
  interactive MCP tool calls;
- `linear/agent_policies.py` and `linear/runtime.py` because policy fact reads
  and policy-denial comments are provider operations that need an explicit
  infrastructure-versus-agent-access authority decision;
- `linear/runtime.py` Linear external URL publication/repair paths because they
  are provider infrastructure writes distinct from role-owned agent-facing
  provider writes;
- `linear/workspace_events.py`, `services/agent_timeline.py`, `api/main.py`,
  and dashboard timeline event views because persisted CAO events and agent
  timeline responses can expose provider message bodies, prompt context, or raw
  provider payloads outside inbox tool authorization;
- `runtime/agent.py`, `runtime/events.py`, and runtime timeline dashboard views
  because runtime notification delivery events can persist and render
  provider-backed inbox message bodies independently of Linear event payloads;
- `linear/routes.py` because live webhook processing must treat permanent
  role/provider denials as processed without conflating them with transient
  delivery failures;
- `api/main.py` for team role CRUD and effective tool surface responses;
- `web/vite.config.ts` because the dev server proxy must forward every API
  prefix used by provider catalogs, workspace setups, workspace teams, role
  management, and built-in CAO tool descriptors;
- existing CLI provider catalog/model API routes and dashboard hooks because
  workspace-provider role-access schema endpoints must use a distinct namespace
  and not overload `/providers`;
- dashboard team and agent panels for role configuration and inherited access
  display;
- agent TOML serialization/parsing only where agent-local access remains valid
  for unteamed agents or where teamed access needs diagnostics.

## Tasks

### T00 - Add ToolService Access Source Adapters

- Add or refactor ToolService internals around two explicit source adapters:
  - `TeamRoleToolAccessSource` for agents with `workspace.team`;
  - `StandaloneAgentToolAccessSource` for agents without `workspace.team`.
- Keep provider/subsystem tool definitions provider-owned; these adapters
  produce grants, not tool vocabulary.
- Make the source-selection rule local to ToolService. No API, CLI, dashboard,
  provider runtime, MCP registration, provider invocation, or freshness code may
  independently decide "team versus standalone."
- For teamed agents, expose agent-local grants only through inactive diagnostics
  and source markers.
- For unteamed agents, keep agent-local access first class and effective. Do
  not label it legacy or compatibility behavior.
- Ensure the normalized adapter result carries enough data for:
  - MCP registration and invocation;
  - direct/custom MCP server materialization;
  - provider-mediated policy expansion;
  - provider-conversation decisions;
  - API/CLI/dashboard effective access display;
  - inactive local diagnostics.
- Add tests through ToolService public owner surfaces proving:
  - teamed agents resolve only the team role source;
  - unteamed agents resolve only the standalone source;
  - switching an agent into a team makes local access inactive;
  - removing an agent from a team reactivates standalone local access;
  - no effective result contains grants from both sources.

### T01 - Define the Team Role Domain Model

- Add role and role-assignment concepts to the workspace team subsystem.
- Ensure every team has a default `member` role, either persisted or
  synthesized by the team service.
- Preserve role policy when existing team metadata update paths edit only
  display name or workspace setup. Do not let `WorkspaceTeamStore.upsert`,
  `WorkspaceTeamService.create_or_update_team`, or the existing
  `PUT /workspace-teams/{team_id}` path replace a team with a metadata-only
  shape that drops roles or assignments.
- Split metadata writes from role-policy CRUD if that is cleaner than merging,
  but make the preservation behavior explicit in the owner service.
- Seed the default `member` role with exactly `send_message` and `handoff`, and
  no provider-mediated workspace tools or direct/custom MCP servers.
- Define the canonical core same-team CAO collaboration tool set in one
  backend-owned place, then have the `member` role reference that value.
- Require elevated roles to explicitly grant `assign`, `terminate`, inbox
  tools, or baton tools. Preserve the existing baton feature gate so granted
  baton tools still do not register while the feature is disabled.
- Keep the schema localized under the team/workspace setup architectural home.
- Validate:
  - role id is non-empty and stable;
  - every assignment references an existing role;
  - role-owned provider grants reference only providers included in the team's
    workspace setup;
  - assignments do not create membership;
  - assignments for non-members are inactive and diagnosed or owner-pruned;
  - a member resolves to exactly one role;
  - a teamed agent without an explicit assignment resolves to `member`;
  - duplicate roles/assignments fail clearly.
- Add tests proving the synthesized/default `member` role exposes exactly
  `send_message` and `handoff` and does not expose `assign`, `terminate`, inbox
  tools, provider tools, direct/custom MCP servers, or baton tools by default.
- Preserve existing team fields: id, display name, workspace setup, members.
- Update store read/write tests.
- Add tests proving display/setup edits preserve role-owned `cao_tools`,
  provider access, `mcp_servers`, and assignments.

### T02 - Model Effective Tool Access Resolution

- Add one owner service/function for effective MCP access resolution.
- For teamed agents, resolve built-in tools and provider access from the team
  role.
- For teamed agents, resolve direct MCP server attachments from the team role.
- For unteamed agents, resolve built-in tools and provider access from
  agent-local config.
- For unteamed agents, resolve direct MCP server attachments from agent-local
  config.
- Do not let callers independently reimplement the `if teamed else unteamed`
  decision.
- Ensure all effective access diagnostics name:
  - agent id;
  - team id when present;
  - role id when present;
  - missing/invalid config reason.

### T03 - Move Provider-Mediated Policy Loading To Effective Access

- Update provider policy loading so provider-mediated access requests are
  generated from team roles for teamed agents.
- Expand role-owned provider access across current team members before
  provider policy normalization so each emitted `ProviderToolAccessRequest`
  remains agent-scoped and carries the concrete member agent id.
- Ensure the expansion uses effective role resolution, including default
  `member` role fallback, and emits no requests for role assignments whose
  agents are not members of the team.
- Validate expanded provider access against required agent-owned provider
  identity/presence before treating it as usable. For Linear, a role grant to a
  member without Linear presence must produce an actionable diagnostic and must
  not become an invocable Linear tool for that member.
- Replace the current provider-loading assumption that configurable provider
  access only exists when agent-local provider config declares tool access.
  In particular, Linear must still initialize when enabled and when team roles
  declare Linear access, even if no agent-local `[linear.tool_access.*]`
  exists.
- Ensure role-owned access entries carry stable source locations that replace
  current agent-local locations such as
  `agents.<agent>.linear.tool_access.<id>`.
  Source locations must identify the team, role, provider access entry, and
  member agent receiving the expanded request.
- Keep provider-native tool definitions, handlers, hooks, and argument schemas
  provider-owned.
- Preserve agent-local provider access for unteamed agents.
- Treat teamed agent-local provider access as inactive/no-op rather than
  invalid or active compatibility behavior.
- Update Linear config/materialization so provider-mediated policies can be
  built from role-owned access while Linear presences and credentials remain
  agent-owned.
- Add tests proving teamed agent-local access does not grant tools.
- Add tests proving unteamed agent-local access still grants tools.
- Add tests proving role-only Linear access registers provider-mediated tools
  even when no agent-local Linear tool access exists.
- Add tests proving two members assigned to the same role both receive the
  role-owned provider access as separate agent-scoped requests.
- Add tests proving assignments for non-members do not emit provider access.
- Add tests proving role-owned Linear access does not become usable for a team
  member without agent-owned Linear presence and emits a clear diagnostic.
- Add tests proving provider grants for providers outside the team workspace
  setup are rejected or diagnosed and never emitted as effective access.

### T03A - Update Provider Views And Diagnostics

- Update Linear workspace setup candidate mapping so `tool_access` candidates
  for teamed agents come from effective role access, not inactive agent-local
  access.
- Keep provider presence candidates agent-owned.
- Ensure provider-view diagnostics and pruning messages do not report inactive
  agent-local grants as if they were team-authorized or team-pruned grants.
- Add tests for provider views and diagnostics with:
  - role-owned Linear access;
  - inactive teamed local Linear access;
  - unteamed local Linear access.

### T03B - Decouple Linear Identity Loading From Inactive Access

- Split or make context-aware Linear provider config loading so agent-owned
  presence, app key discovery, OAuth state lookup, token refresh, and app
  client identity helpers can load Linear identity without requiring inactive
  teamed agent-local `linear.tool_access` to provider-validate.
- Preserve strict provider-specific validation for unteamed local Linear access,
  because that access remains effective in standalone mode.
- Preserve safe parse/schema validation needed to load agent config, but do not
  let invalid inactive local Linear access block identity/OAuth helpers for a
  teamed agent.
- Add tests proving:
  - Linear app key discovery and OAuth state lookup still work for teamed
    agents whose inactive local Linear access would be invalid if active;
  - Linear token/app-client identity helpers still resolve agent-owned presence
    for teamed agents with inactive invalid local access;
  - unteamed invalid local Linear access still fails strict validation.

### T04 - Move Built-In CAO Tool Allowlist To Effective Access

- Add a backend-owned built-in CAO MCP tool descriptor surface derived from the
  managed CAO tool registry. It must expose grantable tool names, descriptions,
  default-member inclusion, and feature-gate metadata such as baton enablement.
- Use that descriptor surface for team role API validation and dashboard role
  editing. Do not copy built-in CAO tool names into frontend-only constants.
- Validate role `cao_tools` entries as known, non-duplicated tool names.
- Update built-in CAO MCP allowlist resolution so teamed agents use role
  `cao_tools`.
- Preserve unteamed agent-local `cao_tools`.
- Do not use the current permissive fallback for teamed roles.
- Do not allow MCP startup failures to widen teamed built-in CAO tools. If
  terminal-to-agent, team, or role allowlist resolution fails for a teamed
  terminal, fail closed or return an explicit diagnostic surface that does not
  register all built-in tools.
- Preserve permissive fallback only for explicitly unconfigured unteamed agents
  or direct developer invocation outside a CAO terminal.
- Enforce same-team target authorization for destructive built-in tools such as
  `terminate`. A role grant for `terminate` allows the tool to be visible; it
  does not authorize terminating terminals outside the caller's workspace team.
- Make generated built-in tool descriptions and auto-injected guidance
  role-aware. Async `assign` flows that rely on receiver-side callbacks must
  either verify the receiver can use `send_message` or emit alternate guidance
  that uses only tools visible to the receiver. Do not tell a receiver to call
  hidden `send_message`.
- Every role has explicit effective CAO tools; the built-in `member` role is
  pre-seeded with the core same-team CAO collaboration tools.
- Add tests for:
  - teamed role allowlist;
  - unassigned teamed agent resolves to `member`;
  - `member` grants core same-team CAO collaboration tools and no provider
    tools by default;
  - teamed local `cao_tools` ignored as inactive;
  - unteamed local `cao_tools`;
  - unconfigured unteamed fallback.
  - teamed allowlist resolution failures caused by API timeout, missing
    terminal metadata, unknown agent, missing team, or malformed role do not
    register all built-in CAO tools.
  - `terminate` rejects out-of-team targets even when the caller role grants
    the tool.
  - `assign` rejects or adapts callback guidance when the receiver role lacks
    `send_message`.
  - explicitly granted baton tools remain hidden when the baton feature gate is
    disabled.
  - API/UI role editing consumes backend-owned CAO tool descriptors rather than
    frontend-copied tool vocabulary.
  - unknown or duplicated role `cao_tools` fail with actionable diagnostics.

### T04B - Align Provider-Backed Inbox Tools With Role Policy

- Treat provider-backed inbox read/reply tools as elevated built-in CAO tools
  whose visibility is controlled by role `cao_tools`.
- Add a provider-owned inbox access requirement descriptor that maps
  provider-conversation preview delivery, read, reply, and provider activity
  writes to explicit provider access entries or provider-owned capability
  names.
- For Linear, define the concrete provider access vocabulary for existing
  Agent Session preview/read/reply/activity operations. If no existing
  `cao_linear.*` mediated tool cleanly represents an existing-session reply,
  add a dedicated Linear-owned access entry/tool/capability rather than
  overloading an unrelated tool.
- Expose this provider-conversation access requirement through backend schema,
  validation, diagnostics, and dashboard role editing so both role-owned and
  unteamed local access can grant it deliberately.
- Apply role-aware authorization or redaction before provider-backed
  notifications are created and delivered to terminals. Agents without the
  required inbox/provider read access must not receive provider message bodies,
  previews, or reply guidance through automatic inbox delivery.
- Apply the same authorization/redaction to stored inbox read surfaces,
  including terminal inbox list APIs, CLI inbox list output, and
  monitoring/session message APIs. These surfaces must suppress, redact, or
  authorize provider-backed rows using the provider-conversation access
  descriptor at read time so previously persisted bodies do not become a legacy
  bypass if access changes later.
- Define raw transcript/log artifact policy explicitly. Terminal output APIs,
  live terminal WebSocket streaming, dashboard terminal view, CLI terminal
  output, CLI tmux attach, handoff output capture, and rendered monitoring log
  artifacts are operator/debug transcript surfaces that may contain whatever
  text was delivered to the terminal before policy changes. They must be
  labeled/documented as transcript surfaces, must not be used as the primary
  provider-content read API, and any user-facing dashboard entry point must make
  that distinction clear. If the implementation can
  reliably tag provider-backed snippets in transcripts, it may redact them
  using the same provider-conversation access descriptor; otherwise it must
  preserve raw transcript semantics and document the operator/debug access
  assumption.
- Update Linear monitor reconciliation to use the same provider-conversation
  access requirements when polling/recovering Agent Session events, retrying
  notification delivery, and synthesizing notifications.
- Define monitor semantics for denied access: policy-denied or role-denied
  recovered events should be recorded with actionable diagnostics and should
  advance processed-event/watermark state so CAO does not retry a permanently
  unauthorized event forever. Transient provider/API failures may retain retry
  behavior.
- Define equivalent live webhook semantics: permanent role/provider access
  denials should record actionable diagnostics, avoid provider content leakage,
  mark the delivery/event processed, and not be retried as if delivery were
  transiently failed. Transient provider/API failures should keep existing
  retry behavior.
- Apply role-aware redaction/filtering to persisted provider-backed CAO events
  before they are returned through agent timeline APIs or rendered in the
  dashboard. Timeline event data must not expose provider message bodies,
  prompt context, or raw provider payload snippets to agents lacking the
  effective provider-conversation read/preview access.
- Apply the same redaction/filtering to runtime notification delivery events.
  Provider-backed `AgentRuntimeNotificationDeliveryEvent` payloads must omit,
  redact, or timeline-filter `message_body` using the same
  provider-conversation access descriptor and explicit read subject.
- Classify Linear policy fact reads and policy-denial comments as provider
  infrastructure operations, not agent tool grants, when they are required to
  enforce routing/policy before agent delivery. They must be provider-owned,
  auditable, minimally scoped, and must not expose fetched provider content to
  the agent unless the agent also has effective read/preview access.
- Classify Linear external URL publication and repair as provider
  infrastructure writes for CAO-owned Agent Session routing metadata. They are
  allowed for routing/recovery, must be audited and minimally scoped, and must
  not be exposed as agent-facing provider write grants.
- Reconcile Linear incoming agent policy with role access: first require
  effective provider-conversation access for the agent/team/role, then evaluate
  provider-owned Linear guardrail policies. A guardrail denial cannot be
  bypassed by role grants, and a role denial cannot be hidden as a guardrail
  denial.
- Do not let CAO tool visibility alone authorize provider-backed writes.
  `reply_to_inbox_message` for a Linear-backed thread must also satisfy
  effective role-owned provider access for the corresponding Linear reply or
  agent-activity action.
- Replace legacy provider inbox authorization that relies only on receiver
  ownership, workspace team membership, and provider presence when the action
  performs provider-mediated work.
- Rejections must name the caller agent, team, role, provider, inbox
  notification/thread, and missing provider access requirement.
- Add tests proving:
  - Linear provider-conversation preview/read/reply/activity operations map to
    explicit provider-owned access requirements;
  - missing provider-conversation access fails with diagnostics that name the
    required provider access entry/capability;
  - roles lacking effective inbox/provider read access do not receive provider
    message bodies, previews, or reply guidance through automatic notification
    delivery;
  - terminal inbox list API, CLI inbox list output, and monitoring/session
    message reads redact or suppress provider-backed persisted bodies for
    agents lacking effective provider-conversation read/preview access;
  - terminal output APIs, dashboard output viewer, CLI terminal output,
    live terminal streaming, CLI tmux attach, handoff output capture, and
    rendered monitoring logs follow the explicit raw-transcript policy and are
    not mistaken for provider-content access surfaces;
  - a role with `reply_to_inbox_message` but no required Linear provider access
    can see the CAO tool but cannot send the provider-backed reply;
  - a role with both the inbox CAO tool and required Linear provider access can
    send the provider-backed reply;
  - unteamed local provider access continues to govern standalone
    provider-backed replies;
  - unteamed local provider-conversation access uses the same provider-owned
    requirement descriptor as role-owned access;
  - provider inbox read paths do not leak provider-backed content beyond the
    effective role policy.
  - legacy Linear direct notification paths do not bypass role-aware
    provider-conversation notification policy.
  - Linear monitor recovery suppresses or redacts unauthorized notifications,
    records diagnostics, and advances permanent-denial watermarks without
    leaking provider previews;
  - live Linear webhook permanent denials are recorded as processed and are not
    retried indefinitely, while transient delivery failures still retry;
  - agent timeline API responses and dashboard timeline views redact/filter
    provider-backed event data based on the explicit read subject. For current
    agent timeline endpoints, the read subject is the requested timeline agent;
  - runtime notification delivery events do not expose provider-backed
    `message_body` through timeline APIs or dashboard runtime event views
    without effective provider-conversation read/preview access;
  - transient monitor/provider failures still retry according to existing retry
    semantics;
  - Linear policy fact reads and policy-denial comments are covered by explicit
    provider-owned infrastructure requirements and do not become implicit agent
    provider access;
  - Linear external URL publication/repair is covered by explicit
    provider-owned infrastructure requirements and does not become implicit
    agent-facing provider write access;
  - Linear incoming agent policy diagnostics distinguish role/provider-access
    rejection from provider guardrail rejection.

### T04A - Move Direct MCP Servers To Effective Access

- Treat direct/custom `mcp_servers` as MCP tool access, not unrelated runtime
  decoration.
- Keep direct/custom `mcp_servers` separate from the managed CAO MCP server.
  Role-owned `mcp_servers` must not be the mechanism that attaches
  `cao-mcp-server`.
- Add role-owned `mcp_servers` using the same validated shape as agent-local
  `mcp_servers`, but persisted under team role policy.
- Preserve unteamed agent-local `mcp_servers`.
- For teamed agents, provider runtime materialization must use role-owned
  `mcp_servers` and ignore inactive agent-local `mcp_servers`.
- Update Codex CODEX_HOME materialization and provider-specific launch paths
  that currently read `agent.mcp_servers` directly.
- Update provider-specific launch paths, including Copilot's
  `--additional-mcp-config` flow, so the managed `cao-mcp-server` remains
  attached through CAO-owned runtime materialization while direct/custom MCP
  servers come from effective access.
- Ensure agent-local `cao-mcp-server` entries cannot disable, shadow, or widen
  the managed CAO server definition for teamed agents.
- Sanitize Codex `codex_config.mcp_servers` and any similar provider-specific
  nested MCP server config so teamed agents cannot bypass role-owned direct MCP
  policy through provider-local config merges.
- Reconcile provider-global MCP server state on startup, role changes, restart,
  and cleanup. For providers such as Gemini that write MCP servers into global
  settings, removed or inactive direct MCP servers must be de-materialized so
  stale entries do not preserve legacy access after team role changes.
- Update runtime capability resolution so MCP server names are appended from
  effective `mcp_servers`, not inactive agent-local `mcp_servers`.
- Update Codex diagnostics/preflight expectations so diagnostics compare the
  CLI-visible MCP servers against effective `mcp_servers`, not inactive
  agent-local `mcp_servers`, while also accounting for the managed
  `cao-mcp-server` separately.
- Update API responses and dashboard forms so teamed agent-local `mcp_servers`
  are grayed out/inactive in agent context and role-owned `mcp_servers` are
  edited in team role context.
- Add tests proving:
  - teamed role-owned `mcp_servers` are materialized for provider runtimes;
  - a teamed role with `cao_tools` but empty direct/custom `mcp_servers` still
    launches with the managed `cao-mcp-server`;
  - teamed agent-local `mcp_servers` are inactive and do not affect runtime
    capabilities or fingerprints;
  - agent-local `cao-mcp-server` cannot disable or override the managed CAO
    server for teamed agents;
  - teamed Codex materialization ignores or sanitizes
    `codex_config.mcp_servers` so it cannot add custom servers or override the
    managed `cao-mcp-server` outside role policy;
  - unteamed Codex materialization preserves valid standalone
    `codex_config.mcp_servers` behavior where that is intentionally supported;
  - unteamed agent-local `mcp_servers` remain active;
  - Codex diagnostics expect role-owned `mcp_servers` for teamed agents and
    local `mcp_servers` for unteamed agents, with the managed `cao-mcp-server`
    handled as CAO runtime infrastructure;
  - Copilot's MCP launch path attaches the managed CAO server and handles
    direct/custom effective MCP servers according to provider capabilities;
  - Codex runtime fingerprints are based on effective MCP server material and
    do not stale/restart teamed agents because inactive
    `codex_config.mcp_servers` changed;
  - Gemini global MCP settings remove stale direct MCP server entries after
    role changes, inactive local server changes, restart, and cleanup paths;
  - changing role-owned `mcp_servers` stales/restarts affected running
    terminals when appropriate.

### T05 - Keep MCP Registration, Invocation, And Freshness In Sync

- Ensure MCP startup registration uses effective access.
- Ensure provider-mediated invocation checks the same effective access.
- Define and implement live revocation semantics. Prefer per-invocation current
  effective-access checks for both built-in CAO tools and provider-mediated
  tools; alternatively, automatically stop/restart affected terminals when role
  policy changes so stale tools cannot continue being invoked.
- If per-invocation checks are used, diagnostics must clearly distinguish
  "tool not registered in this runtime" from "tool was registered earlier but
  current role access has since been revoked."
- Ensure dashboard `mcp_tool_surface` and freshness fingerprints use the same
  effective access source.
- Ensure terminal runtime material and runtime fingerprints use effective access
  semantics. Inactive teamed agent-local `cao_tools`, local provider grants, or
  local `mcp_servers` must not by themselves mark a runtime stale or cause a
  restart.
- Keep provider-native runtime capability authority agent-owned. Existing
  `runtime_capabilities`, `tools`, `tool_aliases`, and `tools_settings` remain
  effective for teamed and unteamed agents unless a future plan moves them into
  roles.
- When building provider `allowed_tools`, combine agent-owned provider-native
  runtime capabilities with MCP server markers from effective direct/custom MCP
  server access. Do not use inactive teamed local MCP servers to append
  `@server` markers.
- Add regression tests proving the surface descriptor and runtime registration
  agree for teamed and unteamed agents.
- Add regression tests proving inactive local tool-access changes do not stale a
  teamed runtime, while team role access changes do.
- Add regression tests proving revoked role access cannot still invoke built-in
  CAO tools or provider-mediated tools from an already-running terminal.
- Add regression tests proving teamed agent-owned provider-native runtime
  capability changes still affect runtime descriptors, while inactive local MCP
  server changes do not.
- Add a stale-terminal diagnostic or UI note when role access changes while an
  agent is running.

### T06 - Agent Validation And Editing

- Update validation so inactive local tool access on teamed agents is not
  treated as active provider-access configuration.
- Preserve parse/schema validation required to load the agent config safely, but
  do not reject a teamed agent solely because an inactive local grant would be
  invalid if it were active.
- Preserve basic schema validation for inactive local `mcp_servers`, but do not
  treat them as effective or materialize them while teamed.
- Ensure unteamed agents still validate agent-local grants strictly because
  those grants are effective in standalone mode.
- Update CLI edit validation and tests so editing unrelated fields on a teamed
  agent is not blocked by inactive local Linear access.
- When an agent is removed from its team, local grants become active again and
  strict provider-specific validation applies.

### T06A - CLI Inspection Surface

- Update `cao agent show` and any agent list/detail CLI output that displays
  tool access so teamed agents do not appear to use inactive local `cao_tools`,
  local `mcp_servers`, or local provider access.
- Prefer showing the same effective team/role access summary used by the API.
  If raw agent TOML is still shown, label local tool access blocks as inactive
  when `agent.workspace.team` is set.
- Preserve the ability to inspect raw config for debugging, but do not make raw
  inactive grants the primary status signal.
- Add CLI tests for teamed and unteamed agent inspection output.

### T06B - Prompt And Skill Tool Visibility

- Update bundled CAO supervisor/worker protocol skills and any seeded prompt
  material so they do not imply `assign`, baton tools, inbox tools, or other
  built-in CAO tools are always available.
- Prompt/skill guidance should either:
  - describe optional tools conditionally, keyed off the visible tool surface;
  - or instruct agents to use a tool only when it is present in their runtime
    MCP tool list.
- Preserve clear guidance for default `member` agents: they can use
  `send_message` and `handoff`, while `assign`, baton, and elevated tools
  require a role that grants them and any relevant feature gate.
- Update default skill seeding/materialization tests so shipped skills do not
  preserve legacy assumptions that all CAO MCP tools are available.

### T06C - Baton Lifecycle Tool Visibility

- Update baton service and watchdog behavior so baton lifecycle messages do not
  instruct an agent to call baton tools that are not visible through that
  agent's effective role.
- Before creating, passing, returning, completing, blocking, nudging, or
  orphaning a baton, evaluate the relevant current holder, receiver, and
  originator effective baton tool grants.
- If a baton operation would leave an agent responsible for an impossible next
  action, either:
  - reject the operation with an actionable diagnostic that names the missing
    baton tool grant and affected agent/team/role; or
  - render alternate guidance using only tools visible to that agent.
- Preserve baton feature-gate behavior: baton tools remain unavailable when the
  baton feature is disabled, regardless of role grants.
- Add tests proving:
  - baton create/pass/return/complete/block paths reject or adjust guidance when
    holder/originator roles lack required baton tools;
  - watchdog nudges do not tell agents to call hidden baton tools;
  - roles with explicit baton grants receive the intended baton guidance;
  - default `member` roles do not receive impossible baton-tool instructions.

### T07 - API And Dashboard Role Management

- Add API surfaces to read and update team roles and role assignments through
  the localized team service.
- Preserve role policy when the existing workspace team metadata API updates
  display name or workspace setup. If a new endpoint replaces this behavior,
  retire or adapt the old endpoint so it cannot silently wipe role policy.
- Add or extend API surfaces so the dashboard can read backend-owned built-in
  CAO MCP tool descriptors for role `cao_tools` editing.
- Add or extend provider schema API surfaces so the dashboard can render
  provider-owned role access forms without hard-coding Linear constants.
- Put workspace-provider role-access schema APIs under a distinct namespace,
  such as `/workspace-providers/{provider}/role-access-schema`. Do not overload
  existing `/providers` CLI provider/model catalog endpoints used by the Agents
  tab.
- The API must validate role-owned provider access through provider-owned
  conversion/validation, not frontend-only checks.
- The API must validate role-owned built-in CAO tool grants through the
  backend-owned CAO tool descriptor surface, not frontend-only checks.
- Add API/read-write support for role-owned `mcp_servers` and effective
  `mcp_servers` so provider runtime materialization and dashboard display use
  the same source.
- Update the Vite dev server proxy to forward every backend API prefix used by
  the role-management UI, including providers/provider catalogs, workspace
  setups, workspace teams, role CRUD, and built-in CAO tool descriptor routes.
- In the Teams tab:
  - list roles for each team;
  - show members and their assigned roles;
  - allow creating/editing/deleting roles where safe;
  - allow assigning a role to a team member;
  - ensure ordinary team metadata edits preserve existing roles and
    assignments;
  - configure role-owned built-in CAO tools using backend-owned tool
    descriptors;
  - configure role-owned provider access using backend/provider-owned schema;
  - configure role-owned direct MCP servers.
- In the Agents tab:
  - if teamed, show role and inherited effective tools read-only;
  - gray out agent-local tool access fields and explain they are inactive while
    the agent belongs to a team;
  - gray out agent-local `mcp_servers` and explain they are inactive while the
    agent belongs to a team;
  - treat the raw `agent.toml` editor as an agent-local tool access surface.
    For teamed agents, it must either make inactive local access sections
    read-only/disabled or clearly label them inactive and prevent the UI from
    presenting those sections as effective access;
  - if raw `agent.toml` editing remains allowed for inactive local sections,
    save/preview copy must state that those changes affect only standalone
    fallback behavior after the agent leaves the team;
  - if unteamed, keep agent-local tool access editable.
- Hide noisy internal pruning diagnostics from user-facing panels unless they
  are promoted into an actionable diagnostic.
- Add frontend tests for raw `agent.toml` rendering/parsing so teamed local
  `cao_tools`, `mcp_servers`, `codex_config.mcp_servers`, and
  `linear.tool_access` cannot be mistaken for effective access.

### T08 - Migration And Cleanup

- Migrate bootstrap/sample team members so current working agents keep their
  intended effective tools through team roles.
- Disable teamed-agent local access code paths from effective access
  calculation without deleting the local config.
- Keep unteamed local access code paths because they are still the standalone
  authority.
- Update docs/comments that describe provider access as agent-specific for team
  members.
- Ensure diagnostics and UI copy make inactive agent-local grants obvious for
  teamed agents.

### T09 - Verification And Review Loop

- Run the criteria catalog after implementation and evaluate the completed diff.
- Run backend tests for workspace teams, provider tool access, MCP registration,
  and API routes.
- Run frontend tests for team role management and agent inherited-access UI.
- Build the frontend if dashboard bundle output is affected.
- Verify in Safari against the served dashboard URL:
  - create or edit a team role;
  - assign an agent to that role;
  - confirm the agent detail panel shows inherited effective tools;
  - confirm teamed agent-local tool controls are read-only/disabled;
  - confirm an unteamed agent can still use local tool access controls;
  - confirm a running agent clearly indicates restart/staleness when role
    access changes.
- Use the final review gate before finalizing. The implementation is not done
  until it receives two consecutive clean fresh-context review passes. A clean
  pass must check the implementation diff, this plan, completion notes, static
  bypass audit, verification evidence, legacy path removal, and browser
  verification evidence. If any valid blocking issue is found, fix it and
  restart the two-clean-review count from zero.

## Acceptance Criteria

- ToolService is the single public owner that selects the effective access
  source for an agent.
- Team roles and standalone agent-local config feed ToolService as grant source
  adapters; consumers do not read either source directly for effective access.
- ToolService never merges team-role and agent-local grants for the same
  effective access decision.
- Team roles are the sole effective MCP tool authority for teamed agents.
- Every team has a default `member` role.
- Unassigned team members resolve to `member`.
- Role assignments do not create membership; `agent.workspace.team` remains the
  only team membership source.
- Role assignments for non-members are inactive and diagnosed or owner-pruned.
- Existing team metadata update paths preserve role policy and assignments, or
  are replaced by endpoints that cannot accidentally drop role policy.
- The default `member` role grants exactly `send_message` and `handoff`, and no
  `assign`, `terminate`, inbox tools, baton tools, provider-mediated workspace
  tools, or direct/custom MCP servers.
- Baton tools remain feature-gated even when a role explicitly grants them.
- Role-owned provider access requires the targeted member to have the required
  agent-owned provider identity/presence; missing identity produces an
  actionable diagnostic and no usable provider tool for that member.
- Role-owned provider grants outside the team's workspace setup providers are
  rejected or diagnosed and never emitted as effective access.
- Agent-local MCP tool access remains effective for unteamed agents.
- Teamed agent-local provider access is an inactive no-op and cannot widen the
  effective tool surface.
- Teamed agent-local `mcp_servers` are inactive/no-op and cannot widen the
  effective tool surface or provider runtime materialization.
- Teamed provider-specific nested MCP config such as Codex
  `codex_config.mcp_servers` is inactive/no-op or sanitized and cannot widen
  the effective MCP surface, provider runtime materialization, or managed CAO
  server definition.
- Managed `cao-mcp-server` materialization is not controlled by role-owned
  direct/custom `mcp_servers`; CAO keeps it attached for CAO-managed terminal
  access and filters its built-in tools through effective `cao_tools`.
- Teamed MCP startup resolution failures do not fail open to every built-in CAO
  tool.
- `terminate` is same-team authorized and cannot target out-of-team terminals
  by default.
- Generated built-in CAO tool guidance does not instruct agents to use hidden
  tools such as `send_message` for callbacks.
- Agent-local `cao-mcp-server` definitions cannot disable, shadow, or widen
  the CAO-managed server for teamed agents.
- If an agent is removed from its team, its agent-local tool access becomes
  effective again.
- Provider identity remains agent-owned and is not moved into role policy.
- Provider-native logic remains provider-owned.
- Built-in CAO MCP tool vocabulary and validation are backend-owned and exposed
  through API descriptors for role editing.
- Provider role-access editing is driven by backend/provider-owned schema, not
  copied frontend constants.
- Workspace-provider role-access schema endpoints are distinct from CLI provider
  catalog/model endpoints. Keep existing `/providers` semantics for CLI
  providers and use an explicit workspace-provider namespace such as
  `/workspace-providers/{provider}/role-access-schema`.
- Provider-backed inbox replies require both CAO inbox tool visibility and the
  required effective provider-mediated access; legacy team/presence checks
  alone are not enough for provider writes.
- Provider-backed inbox preview/read/reply/activity requirements are concrete
  provider-owned access requirements exposed through schema and validation.
- Provider infrastructure operations such as Linear monitor recovery, policy
  fact reads, policy-denial comments, and external URL publication/repair are
  explicitly classified, audited, and tested; they do not silently grant
  agent-facing provider access.
- Provider-owned guardrail policies such as Linear incoming agent policies are
  evaluated alongside, not replaced by, team-role provider access with clear
  diagnostics for each denial source.
- Provider-backed notification delivery must redact or suppress provider
  message bodies/previews unless the receiving agent has effective inbox and
  provider read access.
- Stored inbox and monitoring/session message read surfaces apply the same
  provider-conversation authorization/redaction at read time.
- Raw terminal transcript and monitoring log artifact surfaces have an explicit
  operator/debug policy and are labeled/documented as transcripts, not primary
  provider-content access APIs. This includes live terminal streaming and CLI
  attach surfaces.
- Provider-backed CAO event timeline APIs and dashboard views redact/filter
  provider message bodies, prompt context, and raw payload snippets unless the
  read subject has effective provider-conversation read/preview access.
  Current timeline endpoints have no authenticated viewer identity, so the read
  subject for agent timeline responses is the requested timeline agent. Any
  future operator-authenticated dashboard route may use an explicit operator
  read policy, but it must not silently inherit agent access.
- Runtime notification delivery events follow the same provider-conversation
  timeline redaction/filtering rules for provider-backed `message_body`.
- Provider-global MCP settings are reconciled so removed or inactive direct MCP
  servers do not remain registered after role changes, restarts, or cleanup.
- Live webhook permanent role/provider denials are processed with diagnostics
  and are not retried indefinitely; transient failures still retry.
- Provider-native runtime capability fields remain agent-owned for teamed and
  unteamed agents; team roles control MCP tool access only.
- Effective access is resolved through one public owner surface used by MCP
  registration, invocation, freshness descriptors, API responses, and dashboard
  display.
- Live MCP revocation semantics are explicit. Revoked role access must either
  be denied on the next invocation through current effective-access checks or
  trigger automatic stop/restart before the terminal can continue using stale
  tools. This applies to built-in CAO tools and provider-mediated tools.
- Workspace-provider role-access schema APIs are namespaced separately from CLI
  provider/model catalog APIs.
- Terminal runtime freshness/fingerprints are based on effective access, not
  inactive teamed agent-local grants.
- Agent validation/editing treats teamed local grants as inactive while still
  validating unteamed local grants as active standalone configuration.
- Provider-mediated role access expands to concrete agent-scoped provider
  access requests for every current member assigned to the role, and never for
  non-member assignments.
- Linear identity/OAuth/app-client helpers remain functional for teamed agents
  even when inactive local Linear access would be invalid if active.
- Dashboard makes the authority model visible:
  - team role access is editable in team context;
  - inherited teamed access is read-only in agent context;
  - unteamed local access remains editable in agent context.
- Dashboard raw `agent.toml` editing/rendering labels or disables inactive
  local tool access for teamed agents and makes clear it affects only
  standalone fallback behavior.
- Diagnostics for invalid team/role/access configuration are actionable and
  include agent/team/role identifiers.
- CLI agent inspection shows effective teamed role access or clearly labels
  local tool access as inactive for teamed agents.
- Bundled CAO prompt/skill material describes elevated or feature-gated tools
  conditionally and does not promise tools hidden by the effective role.
- Baton lifecycle messages, nudges, and operation results do not instruct
  agents to use baton tools hidden by their effective role.
- Tests cover both teamed and unteamed paths.
- Safari browser verification covers the real served dashboard workflow.
- Dashboard role-management APIs work through the Vite dev server proxy as well
  as the production-served dashboard.
- Old teamed-agent local access behavior is disabled from effective access; it
  may remain in config only as inactive standalone fallback.
- Completion notes include concrete evidence for every acceptance criterion.
  Checklist-only statements such as "accounted for" or "migrated" are not
  sufficient without code paths, tests, browser verification, or audit
  disposition proving the behavior.
- Two consecutive clean fresh-context review passes were completed after the
  final fix. If either reviewer found a valid blocker, the issue was fixed and
  the two-clean-review count restarted.

## Criteria Catalog

The implementer must run:

```bash
uv run python scripts/catalog_criteria.py
```

Likely applicable implementation criteria:

- `do-not-assume-backwards-compatibility`
- `migration-discipline`
- `minimal-cohesive-changes`
- `no-test-only-production-seams`
- `no-unnecessary-duplication`
- `parallel-safe-execution`
- `prefer-public-surfaces`
- `properly-designed-shared-code`
- `readable-and-explicit`
- `simple-systems`
- `system-code-locality`
- `system-definitions-are-localized`

Likely applicable test criteria:

- `all-system-interactions-are-verified-by-tests`
- `given-when-then-test-structure`
- `seams-must-be-tested`
- `target-behavior-must-not-be-mocked`
- `test-through-owner-surfaces`
- `test-validity-preserved`
- `ui-changes-require-real-browser-verification`

After implementation, evaluate the pending changes against the criteria
catalog. No criteria applicable to the completed diff may be violated.

## Role Deletion

- The built-in `member` role cannot be deleted.
- If any other role is deleted, members assigned to it fall back to `member`.
- Deleting a role must recompute effective tool access for affected agents and
  mark running terminals stale where applicable.

## Review Hardening Log

### R01

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Clarified that role assignments do not create team membership; membership
  remains `agent.workspace.team`.
- Added explicit Linear/provider loading steering for role-only access so
  configurable providers do not depend on agent-local tool access existing.
- Added Linear workspace setup adapter/provider-view work so inactive
  agent-local tool access is not still treated as team-authorized mappings.
- Added provider-owned role access schema/API requirements so the dashboard does
  not hard-code Linear tool-access vocabulary.

### R02

Reviewer: fresh no-context codebase plan review.

Result: no findings.

### R03

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added `services/terminal_service.py` and `runtime/agent.py` runtime
  fingerprint/material steering so inactive local grants do not stale teamed
  runtimes.
- Added `agent.py` and `cli/commands/agent.py` validation/edit steering so
  inactive local Linear grants do not block teamed agent edits while unteamed
  local grants remain strictly validated.

### R04

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added direct/custom `mcp_servers` to effective access. Teamed agent-local
  `mcp_servers` are inactive, role-owned `mcp_servers` become the active source
  for teamed agents, and provider runtime materialization/fingerprints/API/UI
  must use the effective source.

### R05

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added Codex diagnostics/preflight steering so expected MCP server checks use
  effective `mcp_servers`, not inactive teamed agent-local `mcp_servers`.

### R06

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Distinguished the managed CAO MCP server from role-owned direct/custom
  `mcp_servers` so teamed agents with role `cao_tools` still launch with
  `cao-mcp-server` even when direct/custom `mcp_servers` is empty.
- Added Copilot's separate MCP launch path to the expected implementation and
  verification surface.

### R07

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added role access expansion rules so reusable team-role provider access emits
  concrete agent-scoped `ProviderToolAccessRequest`s for current members before
  provider policy normalization.
- Added Linear identity/OAuth/app-client steering so agent-owned Linear
  identity loading is decoupled from inactive teamed local tool-access
  validation.

### R08

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Made the default `member` CAO tool set explicit: exactly `send_message` and
  `handoff`, with `assign`, `terminate`, inbox tools, baton tools, provider
  tools, and direct/custom MCP servers requiring explicit role grants.
- Added CLI inspection requirements so `cao agent show` and related output do
  not present inactive teamed local tool access as effective access.

### R09

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added a backend-owned built-in CAO MCP tool descriptor/API requirement so
  team role `cao_tools` editing and validation do not hard-code CAO tool
  vocabulary in the dashboard.

### R10

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added provider identity/presence validation for expanded role-owned provider
  access so Linear grants to members without Linear presence produce actionable
  diagnostics and no usable provider tool.
- Added bundled CAO prompt/skill updates so shipped supervisor/worker guidance
  does not promise elevated or feature-gated tools that the effective role may
  hide.

### R11

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added fail-closed/diagnostic requirements for teamed MCP startup allowlist
  resolution failures so unavailable team-role resolution cannot register every
  built-in CAO tool.
- Added Codex `codex_config.mcp_servers` and similar nested provider config to
  the direct MCP access model so teamed provider-local config merges cannot
  bypass role-owned MCP server policy.

### R12

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added provider-backed inbox read/reply authorization requirements so
  `reply_to_inbox_message` visibility does not by itself authorize Linear or
  other provider-backed writes without effective role-owned provider access.
- Added raw `agent.toml` dashboard editor requirements so teamed local
  `cao_tools`, `mcp_servers`, `codex_config.mcp_servers`, and provider access
  sections are not presented as effective access.

### R13

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Clarified that provider-native runtime capabilities remain agent-owned and
  separate from team-role MCP access; only effective MCP servers contribute
  role-derived `@server` markers to provider `allowed_tools`.
- Added Vite dev proxy requirements so the role-management UI works against
  every new backend API prefix during frontend development.

### R14

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added role-aware authorization/redaction requirements for provider-backed
  notification creation and terminal delivery so provider message previews or
  bodies cannot leak before gated inbox read/reply tools are invoked.

### R15

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added a provider-owned provider-conversation access requirement descriptor so
  preview/read/reply/activity operations map to concrete Linear provider access
  vocabulary rather than an implementer guessing which existing tool implies
  provider-backed inbox authority.

### R16

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added Linear monitor reconciliation requirements for role-aware recovery,
  notification redaction/suppression, diagnostics, retry behavior, and
  permanent-denial watermark advancement.
- Added explicit infrastructure-operation authority for Linear policy fact
  reads and policy-denial comments so they are provider-owned and audited but do
  not become implicit agent-facing provider access.

### R17

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added persistence/API requirements so existing team metadata update paths
  preserve roles, role assignments, role-owned `cao_tools`, provider access,
  and role-owned `mcp_servers` instead of silently replacing teams with a
  metadata-only shape.

### R18

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added role-aware redaction/filtering requirements for persisted Linear CAO
  events, agent timeline API responses, and dashboard timeline views so
  provider message bodies, prompt context, or raw payload snippets do not bypass
  provider-conversation access policy.
- Added live webhook permanent-denial semantics so role/provider denials are
  recorded as processed with diagnostics and are not retried indefinitely, while
  transient failures keep retry behavior.

### R19

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added stored inbox and monitoring/session message read surfaces to
  provider-conversation authorization/redaction so persisted provider-backed
  notification bodies cannot bypass role policy through inbox list APIs, CLI
  output, or monitoring logs.

### R20

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added baton lifecycle role semantics so baton operations, holder/originator
  guidance, and watchdog nudges reject or adapt when affected agents lack the
  effective baton tools needed for the requested workflow.

### R21

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added validation/diagnostics that role-owned provider grants must reference
  providers included in the team's workspace setup and must never be emitted as
  effective access otherwise.
- Reconciled Linear incoming agent guardrail policies with role access:
  effective provider-conversation access is required first, provider-owned
  guardrails still apply after that, and diagnostics must distinguish the denial
  source.

### R22

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added same-team authorization requirements for `terminate` so a role grant
  does not become an unrestricted cross-team destructive capability.
- Added role-aware generated guidance requirements for built-in CAO async flows
  so `assign` and follow-up messages do not tell receivers to call hidden
  `send_message`.

### R23

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added an explicit raw transcript/log artifact policy for terminal output,
  dashboard output viewer, CLI output, handoff capture, and monitoring log
  surfaces so they are not mistaken for provider-content access APIs and are
  either redacted when reliably taggable or treated as operator/debug
  transcripts with clear labeling.

### R24

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added an explicit read-subject rule for timeline redaction. Current agent
  timeline endpoints use the requested timeline agent as the subject because
  they do not carry authenticated viewer identity.
- Added provider-global MCP reconciliation requirements, especially for Gemini
  `~/.gemini/settings.json`, so removed or inactive MCP server entries are
  de-materialized after role changes, restarts, and cleanup.

### R25

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added live terminal WebSocket streaming, dashboard terminal view, and CLI tmux
  attach to the raw transcript/operator surface policy.
- Classified Linear external URL publication/repair as provider infrastructure
  writes for CAO-owned routing metadata, with audit/minimal-scope requirements.

### R26

Reviewer: fresh no-context codebase plan review.

Valid finding addressed:

- Added runtime notification delivery event redaction/filtering requirements so
  provider-backed inbox `message_body` cannot bypass provider-conversation
  access policy through `AgentRuntimeNotificationDeliveryEvent` timeline
  payloads or dashboard runtime event views.

### R27

Reviewer: fresh no-context codebase plan review.

Valid findings addressed:

- Added live MCP revocation semantics so revoked role access cannot remain
  invocable from already-running terminals through stale built-in CAO or
  provider-mediated tool registrations.
- Added workspace-provider role-access schema API namespace requirements so new
  Linear/workspace role descriptors do not overload existing CLI provider/model
  catalog endpoints.
