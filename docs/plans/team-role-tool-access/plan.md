# Team Role Tool Access Roadmap

Status: complete

## Goal

Add team-role-owned tool access as the active grant source for teamed agents,
while preserving agent-local standalone access for unteamed agents. All effective
tool access must resolve through ToolService's centralized access resolution
layer.

This plan set replaces the earlier monolithic draft. The old draft is reference
material only; implementers should follow this roadmap and the child plans.

## Baseline

This work starts after `docs/plans/effective-tool-access-consolidation/plan.md`
has landed.

Current baseline:

- ToolService owns effective MCP registration, invocation checks, MCP
  materialization, provider-mediated tool filtering, API/CLI/dashboard effective
  access display, and inactive local diagnostics.
- Provider vocabularies remain provider-owned.
- Linear agent-local `[linear.tool_access.*]` still exists for standalone access
  and as current input material, but it must stop being active grant authoring
  for teamed agents.

## Source Of Truth

There are exactly two active grant owner models:

- `team role policy` for agents with `agent.workspace.team`;
- `agent-local standalone policy` for agents without `agent.workspace.team`.

Team role policy is persisted with the workspace team in the existing
`WorkspaceTeamStore` / `workspace-teams.json` owner. Do not create a separate
role config file unless the existing store is proven unable to preserve team
roles and assignments cleanly.

Agent TOML remains the membership pointer through `agent.workspace.team` and the
standalone local tool access owner for unteamed agents. Linear config remains
provider identity/vocabulary input; it is not the teamed role policy store.

ToolService owns the access resolution layer that chooses one source for a given
agent and produces normalized grants. Use boring boundary names:

- `ToolAccessResolver`
- `TeamRoleToolAccessSource`
- `StandaloneAgentToolAccessSource`

No production code outside that boundary may read config and then "apply" grants
through ToolService. Consumers ask ToolService for effective access.

Providers define vocabulary, schema, validation, conversion, hooks, handlers,
and descriptors. Providers do not author effective grants for teamed agents.

## Effective Rule

```text
if agent.workspace.team is set:
  active source = TeamRoleToolAccessSource(team, resolved_role)
  inactive source = StandaloneAgentToolAccessSource(agent)
else:
  active source = StandaloneAgentToolAccessSource(agent)
  inactive source = none
```

The active source returns normalized grants for:

- built-in CAO MCP tools;
- provider-mediated tools;
- direct/custom MCP servers;
- provider-backed inbox/conversation access for scoped CAO inbox items;
- source markers and diagnostics.

ToolService must never merge team-role grants with agent-local grants for the
same effective access decision.

## Scoped Provider-Backed CAO Tools

CAO-owned inbox tools such as `read_inbox_message` and
`reply_to_inbox_message` are CAO MCP tools. When they operate on a
provider-backed inbox notification, the notification itself defines the
provider/thread scope.

The required authorization is:

- the role grants the CAO inbox tool;
- the caller is the notification recipient;
- the provider identity on that notification still maps to the same agent in
  the current team/setup context.

Do not require a separate Linear provider-mediated tool grant just to reply to
the exact Linear-backed inbox item the agent received. Require separate
provider-mediated access only when a CAO tool performs broader provider work
outside the scoped inbox item.

Provider-backed notification body delivery must be authorized before delivery.
Raw terminal output, tmux attach, live terminal streaming, and monitoring logs
are operator/debug transcript surfaces. This plan does not attempt perfect
role-based redaction of already-delivered freeform transcript text.

## Runtime Staleness

Role/tool access changes produce runtime staleness through the existing
configuration freshness model. This plan must mark affected running terminals
stale when their effective MCP surface changes.

Do not redesign staleness in this plan. Do not auto-stop terminals as part of
this plan. A separate staleness plan may decide whether agent-originated tool
actions trigger reload/resume checks beyond current notification-delivery paths.

## Non-Goals

- Cross-team messaging.
- Multiple roles per team member.
- Per-agent exceptions layered on top of team roles.
- Moving provider identity into team role policy.
- Moving provider-native runtime capabilities into team role policy.
- GitHub provider implementation.
- Broad transcript/log redaction redesign.
- Linear monitor or webhook architecture redesign beyond honoring effective
  authorization where this work touches delivery.

## Plan Set

Implement in order:

1. [Access Resolution Core](01-access-resolution-core.md)
2. [Provider Role Access](02-provider-role-access.md)
3. [Dashboard Role Management](03-dashboard-role-management.md)
4. [Runtime, Cleanup, And Verification](04-runtime-cleanup-verification.md)

Each child plan must remain small enough for one implementer/reviewer loop.
If a child plan grows beyond that, split it before implementation.

## Acceptance Model

This roadmap does not define acceptance criteria. Each child plan has exactly
one authoritative `Acceptance Criteria` section, and that section is the only
source of done for that phase. If a requirement applies to more than one phase,
it must appear in each affected child plan instead of being inherited from this
roadmap.

Each child plan also has a `Review Gate` section. Review gates are required
completion process, not acceptance criteria. Meeting the acceptance criteria is
insufficient until the review gate passes.

Implementers and reviewers must not treat roadmap narrative, task descriptions,
or [review-findings-reference.md](review-findings-reference.md) as alternate
acceptance sources.

## Review Findings Reference

Historical review findings from the earlier draft are summarized in
[review-findings-reference.md](review-findings-reference.md). They are
reference material used to shape these child plans, not a second source of
requirements.
