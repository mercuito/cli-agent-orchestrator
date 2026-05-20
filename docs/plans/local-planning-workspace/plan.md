# Local Planning Workspace

Status: Draft

## Goal

Add a second CAO workspace, `local_planning`, that lets agents work on plans
stored as markdown in the agent's local working directory under
`docs/plans/<slug>/`. Plans become workspace contexts; the existing
context-switch machinery is reused. The workspace owns plan-lifecycle tools
(`create_plan`, `activate_plan`, `list_plans`, `complete_plan`,
`get_active_plan`) and gates outbound CAO collaboration calls on the sender
having an active plan.

Today CAO has exactly one workspace (`linear_delivery`). The infrastructure to
support multiple workspaces is in place; this plan exercises it for the first
time with a CAO-internal (non-external-provider) workspace.

## Conceptual Model

- A **plan** is registered as a workspace context with boundary
  `(resolver_id="local_planning", provider_id="local_planning",
  object_type="plan", object_id=<workdir_scope>:<slug>)`. The user-facing
  `plan_id` remains `<slug>`; `<workdir_scope>` is a deterministic hash of
  the team's normalized shared `workdir`.
- An agent's **active plan** is the workspace_context_id of its current
  terminal (`terminal_service.py:308`). "No active plan" means the terminal is
  on the per-agent sentinel context from
  `default_workspace_context_id(agent_id)`
  (`clients/workspace_context_store.py:164`).
- Plan files live at `<agent.workdir>/docs/plans/<slug>/plan.md` plus any
  sibling task/notes documents the agent writes.
- A `local_planning` team is valid only when every member agent uses the
  same normalized `workdir`. Plan identity is slug-scoped within that shared
  workdir; without this invariant, a worker could inherit a plan context
  whose `plan.md` exists only in the sender's local directory.
  `create_plan`, `activate_plan`, `list_plans`, and `complete_plan` always
  compute the caller's workdir scope and filter by
  `boundary_object_id == f"{workdir_scope}:{slug}"`.
- The `local_planning` workspace's `WorkspaceContextResolver` is the single
  authority that maps any incoming event to the appropriate
  `WorkspaceContextResolution`. The resolver consumes:
  - Sent-side agent collaboration events (one per action: send_message,
    handoff, assign, and the five baton transitions). Resolution = sender's
    current workspace_context_id. Sentinel sender → `None` → manager rejects
    when the workspace requires an active context.
  - `LocalPlanningPlanActivatedEvent` (create_plan and activate_plan emit
    this). Resolution = the target plan's workspace_context_id.
  Received-side events are observability-only; the resolver returns `None`
  for them since routing is already settled by the time they fire.

## Scope

In scope (v1):

- New workspace, adapter, tool provider, resolver, events, plan tools.
- Sender-side guardrail enforced through the resolver returning `None` on a
  sentinel sender for workspaces flagged as requiring an active context.
- Inheritance: workers spawned via handoff/assign land in the sender's plan
  context. Reuse existing `AgentRuntimeHandle(agent,
  workspace_context_id=...)` path.
- Receiver-side context-switching on `send_message` when sender's plan
  differs from receiver's current context (uses the existing
  `_deactivate_other_context_terminal_for_switch` path).
- Promote behavior for `create_plan` / `activate_plan`: copy provider runtime
  state from the agent's current context dir into the new plan's context dir
  before the runtime context switch fires. Provider resumes its prior
  conversation in the new context. Only applies when the provider exposes
  `runtime_state_capability` (currently Claude Code, Codex). Other providers
  experience a clean restart with `plan.md` as canonical recovery — this is
  consistent with their existing context-switch behavior and is not made
  worse by this plan.
- Deferred-on-busy semantics for plan activation: `create_plan` and
  `activate_plan` return success synchronously with a clear indication that
  the actual context switch will fire when the agent next becomes idle. The
  existing watchdog drives the switch; no new wait loop in the tool handler.
- New `WORKSPACE_CONTEXT_STATUS_COMPLETED` constant + `complete_plan`
  transition.

Out of scope:

- Dashboard UI for plan listing, picking, completion. (Followup.)
- Per-agent "last active plan" persistence across stops. The triggering event
  drives the receiver's context on every start; dashboard-spawned starts with
  no triggering event default to sentinel. This is sufficient.
- Sub-plans, plan nesting, plan archival, plan deletion.
- Handoff target already running on a different plan: keep existing 409
  behavior from `api/main.py:1758`. Supervisor waits or selects another
  worker. Revisit if this becomes painful.
- Runtime state implementation for Kiro, Q, Copilot, Gemini, and Kimi
  providers. Those providers do not expose `runtime_state_capability` today
  (`providers/manager.py:119-129`), so the promote helper is a no-op for
  them. Implementing state save/load for these providers is tracked as a
  separate workstream when they re-enter the active set; not part of this
  plan.

## Current Inventory

What already exists and is reused unchanged:

- `events/__init__.py` — single `CaoEventDispatcher` per process, persistent
  by default. Linear and runtime already publish here.
- `events/serialization.py`, `clients/cao_event_store.py` — durable event
  persistence. New event types get this for free once registered.
- `workspaces/manager.py` — `Workspace`, `WorkspaceRegistry`,
  `WorkspaceContextResolver` Protocol, `WorkspaceCollaborationManager` with
  `resolve_event_context(agent, event)` already in place
  (`workspaces/manager.py:916`).
- `clients/workspace_context_store.py` — `ensure_workspace_context_for_boundary`,
  `get_workspace_context_for_object`, `default_workspace_context_id`,
  `WorkspaceContextModel` with `status` column. Plan tools layer on top.
- `runtime/agent.py` — `AgentRuntimeHandle`,
  `_deactivate_other_context_terminal_for_switch` at line 688 (saves provider
  state, kills tmux window, spawns new window in target context dir, DEFERS
  if BUSY/WAITING_USER). Per-context provider data dirs at
  `agent_data_dir/contexts/<wctx_id>/runtime/<provider>/`.
- `providers/manager.py:119-129` — `runtime_state_capability` returns the
  per-provider save/discover/load surface. Claude Code
  (`providers/claude_code.py:391`) and Codex (`providers/codex.py:436`)
  implement it.
- `workspace_tool_providers/registry.py` — registry, enabled-config loader,
  factory pattern. New `local_planning` provider plugs in here.
- `workspace_tool_providers/tool_access.py` —
  `ProviderToolAccessPolicy`, `ProviderMediatedToolDefinition`,
  `ProviderToolHandler` Protocol. Allows arbitrary in-process callables as
  handlers; plan tools fit.
- `mcp_server/provider_tools.py` — registers provider-mediated MCP tools per
  terminal based on `ToolService` decisions. Plan tools surface through this
  path.
- `api/main.py:2070` — `/terminals/{receiver_id}/inbox/messages` endpoint.
  New event emission + resolver consultation slot in here for send_message.
- `api/main.py:1752` — `/agents/{agent_id}/start` endpoint. New event +
  resolver consultation slot in here for handoff/assign-triggered starts.
- `linear/runtime.py:412` — only existing caller of
  `manager.resolve_event_context`. New call sites close the asymmetry.

What's missing (the gap list this plan fills):

1. No `local_planning` package.
2. No agent-collaboration CAO event types (per-action send/received pairs
   for send_message, handoff, assign, and the five baton transitions),
   no `LocalPlanningPlanActivatedEvent`, and no
   `AgentTerminalStatusChangeEvent` (the watchdog-emitted state change
   event).
3. No `require_active_workspace_context` flag on `Workspace`.
4. No event-emission + resolver consultation in inbox/start endpoints or
   baton service.
5. No promote helper. The runtime save/load path exists but only ever writes
   to and reads from one context's dir. There's no mechanism to seed a new
   context's dir from a different context's saved state, which is what the
   plan's discovery-flow and plan-transition UX rely on.
6. No workspace-neutral mechanism to fire deferred context switches when
   the agent becomes idle. Today only Linear's monitor
   (`linear/monitor.py:601`) drives anything similar, via a
   Linear-presence-scoped retry loop. We add (a) an
   `AgentTerminalStatusChangeEvent` emitted by the existing watchdog when
   it observes a status transition, (b) per-agent context-workspace metadata
   as the durable arming, and (c) a workspace-neutral
   helper that the watchdog calls *before* publishing the event to apply
   any armed switches for that agent. Subscribers see settled state.
7. No plan tools and no `WORKSPACE_CONTEXT_STATUS_COMPLETED` constant.

## Target Shape

### New Package: `local_planning/`

Layout:

```
src/cli_agent_orchestrator/local_planning/
├── __init__.py
├── workspace_tool_provider.py   # LocalPlanningWorkspaceToolProvider
├── workspace_adapter.py         # LocalPlanningWorkspaceAdapter
├── workspace_context_resolver.py# resolve_local_planning_event
├── workspace_events.py          # event types + register helper
└── plans.py                     # plan store + tool handlers
```

Promotion execution is not in this package. `local_planning` only arms
metadata on the caller's agent-local context-workspace row. The
runtime/service layer owns the neutral promotion helper because terminal
startup must call it without importing a workspace-specific package.

### `Workspace` Definition

In `workspaces/manager.py:default_workspace_registry`, add:

```
Workspace(
    id="local_planning",
    display_name="Local Planning",
    providers=("local_planning",),
    resolver=resolve_local_planning_event,
    require_active_workspace_context=True,
)
```

`require_active_workspace_context` is a new field on the `Workspace`
dataclass. Default `False` so existing `linear_delivery` is unchanged.

### Event Types

Two families of new events. The agent-collaboration family is
workspace-neutral runtime infrastructure (not local_planning-specific) and
lives in `runtime/events.py` alongside the existing runtime events. The
local-planning family is workspace-specific and lives in
`local_planning/workspace_events.py`.

#### Agent collaboration events (runtime-owned)

Sent / initiated collaboration events carry the standard `CaoEvent` envelope
plus `sender_agent_id: str` and `sender_workspace_context_id: str`. They may
also carry `sender_terminal_id: str | None` when the caller runtime is known.
Receiver terminal ids are not required on pre-routing events because the
receiver may only be known as an agent until start/notify resolves delivery.
Received-side observability events carry receiver/holder/originator fields
and rely on correlation/causation plus `agent_participants` for sender-side
timeline linkage when needed. Specific events add fields per action.

**Sent / initiated (resolver consumes these):**

- `AgentMessageSentEvent` — `receiver_terminal_id`, `receiver_agent_id`,
  `message_source_id`. Emitted from the inbox endpoint before the durable
  inbox row exists. `message_source_id` is a deterministic idempotency key
  for this outbound send, not the database `inbox_message_id`.
- `AgentHandoffInitiatedEvent` — `receiver_agent_id`.
  Emitted from `/agents/{id}/start` when called with sender info and the
  triggering tool was handoff. The task payload is delivered by the
  follow-up inbox path, not duplicated on this start event.
- `AgentAssignInitiatedEvent` — `receiver_agent_id`.
  Emitted from `/agents/{id}/start` for assign-triggered starts.
- `BatonCreatedEvent` — `baton_id`, `holder_agent_id`,
  `holder_terminal_id | None`, `title`, `message`.
- `BatonPassedEvent` — `baton_id`, `from_holder_agent_id`,
  `from_holder_terminal_id`, `to_holder_agent_id`,
  `to_holder_terminal_id | None`, `message`.
- `BatonReturnedEvent` — `baton_id`, `from_holder_agent_id`,
  `from_holder_terminal_id`, `to_holder_agent_id`,
  `to_holder_terminal_id | None` (the previous holder being returned to),
  `message`.
- `BatonCompletedEvent` — `baton_id`, `originator_agent_id`,
  `originator_terminal_id | None`, `message`.
- `BatonBlockedEvent` — `baton_id`, `originator_agent_id`,
  `originator_terminal_id | None`, `reason`.

**Received side (observability; resolver returns `None`):**

- `AgentMessageReceivedEvent` — `receiver_agent_id`,
  `receiver_terminal_id`, `inbox_message_id`. Emitted from
  `inbox_service.check_and_send_pending_messages` after a successful
  delivery to the receiver's terminal. Its `correlation_id` references the
  original `AgentMessageSentEvent` when the notification metadata/source
  identifies one.
- `AgentHandoffAcceptedEvent` — `receiver_agent_id`,
  `receiver_terminal_id`. Emitted from `/agents/{id}/start` after the
  worker terminal successfully starts in response to a handoff trigger.
- `AgentAssignAcceptedEvent` — same shape, fires for assign-triggered
  starts.
- `BatonCreationReceivedEvent` — `baton_id`, `holder_agent_id`. Emitted
  from `baton_service` after the first holder is recorded; includes
  `holder_terminal_id`.
- `BatonPassReceivedEvent` — `baton_id`, `to_holder_agent_id`,
  `to_holder_terminal_id`. Emitted after the holder change is persisted.
- `BatonReturnReceivedEvent` — `baton_id`, `to_holder_agent_id`,
  `to_holder_terminal_id`. Same pattern.
- `BatonCompletionReceivedEvent` — `baton_id`, `originator_agent_id`,
  `originator_terminal_id`. Fires when the originator is notified of
  completion.
- `BatonBlockReceivedEvent` — `baton_id`, `originator_agent_id`,
  `originator_terminal_id`. Same pattern for block notifications.

That's 8 sent + 8 received = 16 collaboration events. Each is a small
dataclass; the duplication is mild and the per-event clarity is worth it
(matches Linear's per-typed-event convention, e.g.
`LinearIssueContextEvent`, `LinearAgentMentionedEvent`,
`LinearIssueDelegatedToAgentEvent`, etc.).

Register all 16 in a `register_agent_collaboration_events()` helper in
`runtime/events.py` that gets called during API lifespan startup and by
runtime publish helpers, mirroring the existing
`register_runtime_cao_events()` pattern at lines 185-192.

#### Local planning events (workspace-owned)

In `local_planning/workspace_events.py`:

- `LocalPlanningPlanActivatedEvent` — `agent_id`, `plan_slug`,
  `workdir_scope`, `workspace_context_id`. Emitted by `create_plan` and
  `activate_plan` tool handlers. Consumed by the local_planning resolver to
  confirm the workspace owns this workdir-scoped plan and produce the
  resolution.

Registered through an explicit
`register_local_planning_cao_events()` helper called during API lifespan
startup and again by plan-tool handlers before publishing.
`LocalPlanningWorkspaceToolProvider.published_cao_events()` can also expose
it for provider startup registration, but correctness does not depend on
optional provider startup.

#### Terminal state change event (runtime-owned)

In `runtime/events.py`:

- `AgentTerminalStatusChangeEvent` — `agent_id`, `terminal_id`,
  `previous_status`, `new_status`. Emitted by the `LogFileHandler` after it
  applies any armed workspace context switches (see "Event-driven
  deferred-switch firing" below). Subscribers see settled state.

Total new event types this plan introduces: **18** (16 collaboration + 1
plan activation + 1 terminal state change).

### Resolver

`local_planning/workspace_context_resolver.py:resolve_local_planning_event`:

```
SENT_COLLAB_EVENTS = (
    AgentMessageSentEvent,
    AgentHandoffInitiatedEvent,
    AgentAssignInitiatedEvent,
    BatonCreatedEvent,
    BatonPassedEvent,
    BatonReturnedEvent,
    BatonCompletedEvent,
    BatonBlockedEvent,
)

def resolve_local_planning_event(event):
    if isinstance(event, SENT_COLLAB_EVENTS):
        sender_default = default_workspace_context_id(event.sender_agent_id)
        if event.sender_workspace_context_id == sender_default:
            return None  # sentinel → reject for workspaces requiring active context
        context = get_workspace_context(event.sender_workspace_context_id)
        if (
            context is None
            or context.resolver_id != "local_planning"
            or context.boundary_provider_id != "local_planning"
            or context.boundary_object_type != "plan"
        ):
            return None  # non-plan/foreign/stale context is not an active plan
        return WorkspaceContextResolution(
            workspace_context_id=context.id,
            resolver_id=context.resolver_id,
            boundary_provider_id=context.boundary_provider_id,
            boundary_object_type=context.boundary_object_type,
            boundary_object_id=context.boundary_object_id,
        )
    if isinstance(event, LocalPlanningPlanActivatedEvent):
        context = get_workspace_context(event.workspace_context_id)
        if (
            context is None
            or context.resolver_id != "local_planning"
            or context.boundary_provider_id != "local_planning"
            or context.boundary_object_type != "plan"
            or context.boundary_object_id != f"{event.workdir_scope}:{event.plan_slug}"
        ):
            return None
        return WorkspaceContextResolution(
            workspace_context_id=context.id,
            resolver_id=context.resolver_id,
            boundary_provider_id=context.boundary_provider_id,
            boundary_object_type=context.boundary_object_type,
            boundary_object_id=context.boundary_object_id,
        )
    # Received-side events and any other event types not recognized here
    # return None so the resolver doesn't claim them.
    return None
```

Linear's resolver is unchanged — it returns `None` for all the new event
types, which is the existing protocol behavior.

### Adapter

`local_planning/workspace_adapter.py:LocalPlanningWorkspaceAdapter` mirrors
`LinearWorkspaceAdapter` but with no external identity. All
`build_candidate_mappings` calls return `()`. `build_provider_view` returns a
`WorkspaceToolProviderView` with `value=None` (or a small marker object).
`resolve_event_agent_id` raises (no external events to attribute) — this is
fine because the local_planning workspace doesn't process inbound
external-provider events.

### Provider

`local_planning/workspace_tool_provider.py:LocalPlanningWorkspaceToolProvider`:

- `name = "local_planning"`
- `initialize()` — verify nothing external; idempotent.
- `published_cao_events()` — returns `LocalPlanningPlanActivatedEvent` for
  startup registration when enabled; plan-tool handlers still self-register
  before publishing.
- `provider_tool_access()` — returns a `ProviderToolAccessPolicy` declaring
  the plan tools (see below). Handlers are local Python callables; no HTTP.
- `provider_role_tool_access(grants)` is required. `ToolService` only turns
  team-role provider grants into visible provider-mediated tools for
  providers implementing `ProviderRoleToolAccessWorkspaceToolProvider`; if
  omitted, the grants are skipped as unsupported. `local_planning` therefore
  owns the role-grant translation for its plan tools from v1.

Role grant shape in `~/.cao/workspace-teams.json`:

```json
{
  "teams": [
    {
      "id": "planning_team",
      "display_name": "Planning Team",
      "workspace": "local_planning",
      "roles": {
        "planner": {
          "display_name": "Planner",
          "providers": {
            "local_planning": {
              "plan_tools": {
                "create_plan": true,
                "activate_plan": true,
                "list_plans": true,
                "get_active_plan": true,
                "complete_plan": true
              }
            }
          }
        }
      },
      "role_assignments": {
        "planner_agent": "planner"
      }
    }
  ]
}
```

Team membership is not declared in `workspace-teams.json`. Agents become
team members through their agent-side config (`workspace.team =
"planning_team"`). Documentation and tests must configure the agent's
workspace team before expecting role-granted plan tools to appear.

The provider converts true-valued entries into the matching mediated tool
definitions. Unknown tool names fail closed during role validation.

Register in `workspace_tool_providers/registry.py:default_workspace_tool_provider_registry`
alongside the existing Linear registration.

### Plan Tools

Declared in `LocalPlanningWorkspaceToolProvider.provider_tool_access()`:

1. **`create_plan(title: str, body: str) -> dict`**
   - Slug: kebab-case derived from `title`.
   - Compute `workdir_scope = sha256(normalized agent.workdir)[:16]` (or a
     similarly stable deterministic scope) and
     `plan_object_id = f"{workdir_scope}:{slug}"`. Reject only if a plan with
     that scoped object id already exists.
   - Create directory `<agent.workdir>/docs/plans/<slug>/`.
   - Write `plan.md` with `body`.
   - Call `ensure_workspace_context_for_boundary(resolver_id="local_planning",
     provider_id="local_planning", object_type="plan",
     object_id=plan_object_id, metadata={"plan_slug": slug,
     "workdir_scope": workdir_scope, "workdir": normalized_workdir})`,
     then ensure the caller's agent-local context workspace row exists and
     set `promote_from_context_id` and `pending_for_agent_id` on that
     `ContextWorkspaceModel` metadata. The two metadata fields are per-agent
     durable arming for the deferred switch + promote — see
     "Event-driven deferred-switch firing" below. Caller's current context
     applies whether it is the sentinel (discovery flow) or another plan
     (wrap-up-A, commence-B flow). Do not store these arming fields on the
     global `WorkspaceContextModel`; plan contexts are shared by multiple
     agents, while provider runtime dirs are per agent.
   - Build `LocalPlanningPlanActivatedEvent` for this agent + plan.
   - Call `manager.resolve_event_context(caller_agent, event)` → resolution
     (used to ensure the workspace owns this plan and to record the
     activation through the standard pathway).
   - Construct `AgentRuntimeHandle(caller_agent,
     workspace_context_id=resolution.workspace_context_id)` and call
     `ensure_fresh_started(causing_event=event)` once. Do not use
     `ensure_started()` for this path: it raises when a context switch is
     deferred. `ensure_fresh_started()` returns an
     `AgentRuntimeFreshnessResult`, so the tool can map
     `AgentRuntimeFreshnessAction.DEFERRED` to queued success and
     STARTED/REUSED/RESTARTED to active success. If status is
     BUSY/WAITING_USER the switch DEFERS; the watchdog will drive the
     eventual fire when the agent next becomes idle. This is intended
     behavior.
   - Return `{"plan_id": slug, "status": "queued" | "active", "message":
     "Plan created. Context switch will take effect on your next idle
     moment."}`. The agent learns the outcome from this return value
     directly; no separate inbox notification is queued.

2. **`activate_plan(plan_id: str) -> dict`**
   - Compute the caller's `workdir_scope` and look up the plan's workspace
     context by `object_id=f"{workdir_scope}:{plan_id}"` (must exist).
   - If the target plan's context dir does not yet have provider runtime
     state (first-time activation from another context), set
     `promote_from_context_id = caller_current_context_id` on the target
     caller's agent-local context workspace metadata with the new metadata
     patch helper. If the target already has prior state, clear any stale
     `promote_from_context_id` for that caller/context instead — the target
     plan resumes its own history on the switch.
   - Always set `pending_for_agent_id = caller_agent_id` on the
     caller/context metadata so the watchdog's deferred-fire path picks the
     switch up at next idle.
   - Emit `LocalPlanningPlanActivatedEvent`, resolve via manager.
   - Trigger `ensure_fresh_started(causing_event=event)` on the runtime
     handle once and map `AgentRuntimeFreshnessAction.DEFERRED` to queued
     success. Promote (if armed) and the switch both fire at watchdog
     idle-detection time, same mechanism as create_plan.

3. **`list_plans() -> list[dict]`**
   - Query workspace contexts through the new store helper for
     `resolver_id == "local_planning"` and `boundary_object_type == "plan"`,
     then filter to `boundary_object_id` values with the caller's
     `workdir_scope` prefix.
   - Return id (slug), display name, status, created_at.

4. **`get_active_plan() -> dict | None`**
   - Read caller terminal's `workspace_context_id` from metadata.
   - Compute the caller's `workdir_scope`. If the terminal context is a
     `local_planning` plan context whose `boundary_object_id` has that scope
     prefix, return its details. Otherwise `{"active_plan": null}`.

5. **`complete_plan(plan_id: str) -> dict`**
   - Compute the caller's `workdir_scope` and look up
     `object_id=f"{workdir_scope}:{plan_id}"`.
   - Set the workspace context's `status` to
     `WORKSPACE_CONTEXT_STATUS_COMPLETED` through the new status helper.
   - Does not deactivate the terminal — the agent stays on the (now
     completed) plan context until they transition.

### Workspace Context Store Surface

`clients/workspace_context_store.py` needs explicit public helpers for the
new lifecycle. Existing `ensure_workspace_context_for_boundary(...)` creates
the global logical context; arming state must live on the per-agent
`ContextWorkspaceModel`, not on the global `WorkspaceContextModel`, because
multiple agents can share one plan context.

Add helpers for:

- `get_workspace_context(context_id)` — load by id.
- `list_workspace_contexts(resolver_id=None, boundary_object_type=None,
  status=None)` — used by `list_plans` and tests.
- `get_workspace_context_for_boundary(resolver_id, provider_id, object_type,
  object_id)` (or equivalent) — used by plan tools to resolve
  workdir-scoped plan ids without scanning every context.
- Add `metadata_json` to `ContextWorkspaceModel` with a migration/backfill
  path for existing rows.
- `patch_context_workspace_metadata(agent_id, workspace_context_id,
  set_values=None, clear_keys=None)` — merge new metadata keys and remove
  consumed ones for one agent/context pair.
- `list_context_workspaces_pending_for_agent(agent_id)` — used by the
  runtime idle helper to find this agent's armed context workspaces.
- `mark_workspace_context_completed(context_id)` — set status to
  `WORKSPACE_CONTEXT_STATUS_COMPLETED`.

Each helper should update `updated_at` when it mutates a row and should have
round-trip tests in `test/clients/test_workspace_context_store.py`.

### Promote Helper

The promote operation runs **at deferred-switch time, not at tool-call
time**. This is critical: when `create_plan` returns, the agent is still
mid-turn on the source context. The conversation continues, the agent
finishes its turn, the provider returns to IDLE, and only then the watchdog
drives the deferred context switch. At that switch moment, the source
context's provider state is saved (capturing the post-create_plan
conversation tail), and only after that does the promote copy run — so the
target context's first launch sees the freshest state including everything
the agent said after the tool call.

The mechanism is data-driven: `create_plan` / `activate_plan` set
`promote_from_context_id` in the caller's `ContextWorkspaceModel.metadata_json`
for the target context. The runtime's terminal-start path reads that
agent-scoped field and acts on it.

`runtime/workspace_context_promotion.py:promote_workspace_context_state(agent,
target_context_id) -> bool` (or an equivalently neutral service module):

- Reads `promote_from_context_id` from the target context workspace metadata
  for `(agent.id, target_context_id)`. Returns `False` if not set (nothing
  to do).
- Resolves source and target `provider_data_dir` via
  `workspace_context_provider_data_dir(agent, ctx_id, agent.cli_provider)`.
- If `runtime_state_capability(agent.cli_provider)` is None
  (Kiro/Q/Copilot/Gemini/Kimi today), clear the agent-scoped
  `promote_from_context_id` field and return `False` (cold restart is
  expected for those providers; plan.md is the canonical handoff).
- If the target dir already has provider state, clear the field and return
  `False` (don't overwrite an existing plan's history).
- If source has no provider state, clear the field and return `False`
  (nothing to copy).
- Otherwise copies source dir contents to target dir, clears the
  agent-scoped `promote_from_context_id` field (so this agent's future
  re-entry into this context doesn't redo the promote), and returns `True`.
  Promotion arming is one-shot once evaluated at terminal-start time,
  regardless of whether the evaluation copied or no-oped.

**Hook point**: `terminal_service._create_terminal_core` builds the
`AgentRuntimeLaunchContext`, then currently calls
`provider_manager.prepare_terminal_runtime(...)`, and only after that loads
provider runtime state. The promote helper must run **after** the launch
context exists (so `provider_data_dir` is known) but **before**
`prepare_terminal_runtime(...)`. Provider preparation writes
terminal-specific files such as terminal ids and generated config; a broad
copy after preparation could overwrite fresh material with source-context
files. Running promote before preparation lets provider prep regenerate
terminal-specific material on top of the promoted resumable state. If an
implementation chooses a later hook instead, the promote copy must be
selective and preserve freshly generated terminal/config files.

Because the promote is data-driven via agent-scoped context-workspace
metadata, the runtime code stays workspace-agnostic — it doesn't import
`local_planning`. The `local_planning` tool handlers arm the metadata; the
runtime reads it during the standard terminal-start flow.

### Event Emission and Resolver Consultation in API Endpoints

Three new emission sites in the API server. Each emits a typed sent event
(consumed by the resolver) and, once the action's effect lands, a typed
received event (observability).

1. **`api/main.py:2070` `/terminals/{receiver_id}/inbox/messages`** (the
   send_message backing endpoint):
   - Look up sender's terminal metadata from `sender_id` query param →
     sender agent + sender workspace_context_id. If `sender_id` doesn't
     resolve to a known terminal (stale or invalid), reject with 400 and a
     clear message; do not silently fall through.
   - Look up receiver's terminal metadata → receiver agent + receiver
     workspace_context_id.
   - Allocate a deterministic `message_source_id` for this outbound send
     before persistence, for example from sender terminal, receiver terminal,
     and a request UUID. This is used as the sent event's source/idempotency
     key and later as `source_id` for the runtime notification.
   - Build `AgentMessageSentEvent(sender_agent_id, sender_workspace_context_id,
     receiver_terminal_id, receiver_agent_id, message_source_id)` with a
     non-null `correlation_id` (use `message_source_id` or the sent
     event's own `event_id`, consistently) and publish via the default
     dispatcher.
   - Call `manager.apply_outbound_resolution(receiver_agent, event)` (the
     new method described below). This consults the workspace's resolver,
     enforces the `require_active_workspace_context` flag, and returns the
     target workspace_context_id for the receiver.
   - **Delivery routing**: route the inbox write through
     `AgentRuntimeHandle(receiver_agent,
     workspace_context_id=target_ctx).notify(message, source_kind=
     "agent_collaboration_message", source_id=message_source_id,
     causing_event=sent_event, notification_metadata={
     "sent_event_id": str(sent_event.event_id),
     "sent_correlation_id": str(sent_event.correlation_id)}, ...)` rather
     than the existing terminal-id-keyed
     inbox path. Extend `AgentRuntimeHandle.notify` to accept optional
     `notification_metadata` and pass it through to
     `create_inbox_delivery`; existing callers keep the default `None`.
     The runtime handle uses
     `agent:<id>:context:<ctx>` as the inbox receiver id
     (`runtime/agent.py:175`), which:
     - Survives terminal restarts triggered by the context switch.
     - Triggers the existing `ensure_fresh_started` machinery that switches
       the receiver to `target_ctx` if their terminal is on a different
       context. DEFERRED on BUSY; message stays queued in the right
       receiver_id until the switch lands.
   - The corresponding `AgentMessageReceivedEvent` fires from
     `inbox_service.check_and_send_pending_messages` on successful delivery
     to the receiver's terminal. Because inbox delivery can batch multiple
     notifications for one effective source, emit one received event per
     delivered `InboxDelivery`. Each event carries that delivery's persisted
     `inbox_message_id` and uses that delivered notification's
     `source_kind/source_id` (or notification metadata) to set
     `correlation_id` back to the original sent event. The sent event does
     not claim a database
     `inbox_message_id` that is unavailable before `notify(...)` persists
     the delivery.
   - This unifies CAO outbound delivery with the existing Linear inbound
     pattern. Linear's webhook flow already uses this exact handle.notify
     path (`linear/runtime.py:412`); send_message just stops bypassing it.
   - Preserve the existing flat endpoint response shape for MCP
     compatibility. Map `notify_result.notification.delivery` back to
     `success`, `notification_id`, `message_id`, `sender_id`,
     `receiver_id`, `source_kind`, `source_id`, and `created_at`. Do not
     return `AgentRuntimeNotifyResult` directly; any new runtime status
     fields must be backward-compatible extras.

2. **`api/main.py:1752` `/agents/{agent_id}/start`** (the
   handoff/assign-target start, also used by dashboard direct starts):
   - Accept an optional `sender_terminal_id` query param plus a discriminator
     query param `trigger_action: "handoff" | "assign"`. When present, the
     endpoint looks up sender's metadata and builds either
     `AgentHandoffInitiatedEvent` or `AgentAssignInitiatedEvent` from the
     fields. These initiated events identify the target by
     `receiver_agent_id` and do not require `receiver_terminal_id`, because
     the terminal is only known after start succeeds. They also do not carry
     the task message because `_create_terminal` starts the worker before
     `_handoff_impl` / `_assign_impl` deliver the payload through the inbox
     path. When absent (dashboard direct start), no sent event is built.
   - When event is present, publish it, call
     `manager.apply_outbound_resolution(target_agent, event)`. Apply the
     resolution's workspace_context_id to `AgentRuntimeHandle(target_agent,
     workspace_context_id=...)`. When event is absent or resolution is
     `None`, fall through to the existing sentinel default.
   - Reject when the target agent's workspace requires active context and
     resolution is `None`.
   - After the worker terminal successfully starts (or reuses), publish the
     matching `AgentHandoffAcceptedEvent` / `AgentAssignAcceptedEvent`. The
     correlation_id on the received event references the sent event's
     event_id, so timeline views can pair them.

3. **`services/baton_service.py`** (the five transition functions):

   | Function | Sent event | Received event |
   |---|---|---|
   | `create_baton` | `BatonCreatedEvent` | `BatonCreationReceivedEvent` |
   | `pass_baton` | `BatonPassedEvent` | `BatonPassReceivedEvent` |
   | `return_baton` | `BatonReturnedEvent` | `BatonReturnReceivedEvent` |
   | `complete_baton` | `BatonCompletedEvent` | `BatonCompletionReceivedEvent` |
   | `block_baton` | `BatonBlockedEvent` | `BatonBlockReceivedEvent` |

   Batons are owned by durable CAO agents, not by the ephemeral terminals
   currently backing those agents. MCP baton tools currently use terminal ids
   for caller and receiver identity; Task 10b moves explicit holder/receiver
   arguments, list filters, and baton response ownership fields to agent ids.
   The caller's `CAO_TERMINAL_ID` remains a runtime fact used to resolve the
   acting agent. Add Task 10b before this wiring step:

   - persist `originator_agent_id`, `current_holder_agent_id`, and a
     `return_stack_agent_ids_json` return stack for durable ownership;
   - keep terminal ids only as runtime/delivery/event facts, including event
     fields ending in `_terminal_id` and last-delivery/debug metadata;
   - authorize holder actions by resolving `CAO_TERMINAL_ID` to the caller's
     agent id and comparing against `current_holder_agent_id`;
   - have baton watchdog reason from holder agent/runtime state, so a baton
     is not orphaned merely because a previous holder terminal disappeared
     during context routing.

   Each transition publishes the sent event before applying the transition,
   runs it through `manager.apply_outbound_resolution(receiver_agent,
   event)` (where receiver_agent is the holder/originator agent: first
   holder for create, next holder for pass, previous holder for return,
   originator for complete/block), applies the resolution to the
   receiver's runtime handle for context routing, lands and commits the
   transition, then notifies through `handle.notify(...)` using the receiver
   agent as owner and any returned terminal id only as delivery metadata, and
   publishes the received event with the same correlation_id only when notify
   actually delivered to a receiver terminal. If notify only durably queues the
   message, the transition does not fabricate a received event.
   Implementing this requires
   splitting the current `_queue_baton_message` helper: keep the existing
   same-team validation before routing, reuse the existing `_baton_message`
   formatting, but move inbox creation to the post-commit runtime-handle
   notify path so recipients cannot observe stale baton state. Sent baton
   events require agent ids and may include sender/current terminal ids that
   are already known; receiver terminal fields are optional until the
   post-notify received event can name the terminal that actually received
   delivery. Fields that end in `_agent_id` carry the resolved durable CAO
   agent ids.

MCP-side changes for handoff/assign are limited to propagating the sender
terminal and action discriminator to the API. `_handoff_impl` and
`_assign_impl` both use `_create_terminal` today, so either change
`_create_terminal` to accept `trigger_action: "handoff" | "assign" | None`
or split the start-call path. The API request must include both
`sender_terminal_id=os.environ["CAO_TERMINAL_ID"]` and
`trigger_action=<handoff|assign>` for those two tools. No event emission from
MCP-side — events live in the API process where the dispatcher has
subscribers.

### `Workspace.require_active_workspace_context` Flag

New field on `Workspace` (`workspaces/manager.py:Workspace`):

- Default `False`. Existing `linear_delivery` workspace gets nothing new.
- `local_planning` workspace declares `True`.
- `WorkspaceCollaborationManager` reads this flag when applying the resolver
  result: if `True` and resolver returned `None`, raise
  `WorkspaceConfigError("sender has no active plan; activate or create one
  before collaborating")`.

The flag-check belongs in a new manager method
`apply_outbound_resolution(agent, event)` that wraps
`resolve_event_context(agent, event)` and enforces the flag. API call sites
use this method, not raw `resolve_event_context`.

### `WORKSPACE_CONTEXT_STATUS_COMPLETED`

Add constant to `clients/workspace_context_store.py` alongside
`WORKSPACE_CONTEXT_STATUS_ACTIVE`. Add a small helper
`mark_workspace_context_completed(context_id)` that updates the row.
`complete_plan` calls it.

### Tool Gating

Plan tools are role-gated through the existing team-role tool grant system.
Teams using `local_planning` workspace can grant `create_plan` and
`activate_plan` to "planner" roles and not grant them to "worker" roles.
`list_plans` / `get_active_plan` are probably safe to grant broadly.
`complete_plan` is planner-only.

No new gating axis. The existing `ToolService` decision flow drives this via
the required `provider_role_tool_access` implementation once we declare the
tools as provider-mediated.

## Implementation Tasks

The task files under [tasks/](tasks/) and their dependency graph are the
canonical execution order. The notes below summarize each task's ownership
and affected code paths so implementers can cross-check the detailed task
files without inferring a different order or ownership split.

### 1. Add `require_active_workspace_context` to Workspace

File: `workspaces/manager.py`.

Add field (default `False`), validate type in `__post_init__`. No call site
changes yet.

### 2. Add `WORKSPACE_CONTEXT_STATUS_COMPLETED`

File: `clients/workspace_context_store.py`.

Add the constant and a helper to set the status. Add tests for round trip.

### 2a. Add workspace/context-workspace metadata/list helpers

File: `clients/workspace_context_store.py`.

Add public helpers for context lookup by id, resolver-filtered listing,
agent-scoped context-workspace metadata patch/clear, metadata-based pending
switch lookup, and completed status mutation as described in
"Workspace Context Store Surface". These are required before implementing
`activate_plan`, `list_plans`, promote cleanup, and the idle-triggered switch
helper.

### 3. Define runtime agent collaboration + terminal-status events

File: `runtime/events.py` (extend existing).

Define 16 agent collaboration events (8 sent + 8 received) and
`AgentTerminalStatusChangeEvent`. Add
`register_agent_collaboration_events()` and
`register_agent_terminal_status_change_event()` helpers mirroring the
existing `register_runtime_cao_events()` (lines 185-192). Both helpers get
called from API lifespan startup and from any runtime publish helper before
publishing so the dispatcher knows the types before any publisher attempts
to emit one.

A small shared dataclass mixin or base for the collaboration events is
acceptable to reduce field duplication, but not required. Each event must
declare:

- `event_name` for dispatcher registration.
- `kind: Literal["..."] = "..."` with a unique storage discriminator that
  matches `events/serialization.py:cao_event_kind`.
- the standard envelope fields required by `events/__init__.py`.
- `agent_participants` for timeline indexing. Collaboration events include
  sender and receiver participants with explicit roles; baton events include
  holder/originator participants as appropriate; terminal-status events
  include the affected agent. Without `agent_participants`, the event store
  persists no participant rows and the agent timeline cannot show the event.

### 4. Add outbound resolution + active-context flag enforcement

File: `workspaces/manager.py:WorkspaceCollaborationManager`.

`apply_outbound_resolution(agent, event)` calls
`resolve_event_context(agent, event)`. If the agent's workspace flag
requires active context and resolution is `None`, raise
`WorkspaceConfigError`. Otherwise return the resolution (which may be
`None` for workspaces that don't require — caller falls back to the receiver's
existing context). Same-team collaboration authorization remains separate
and must continue to run at each endpoint before routing.

### 5. Add neutral promote helper

Files: `services/terminal_service.py`,
`clients/workspace_context_store.py`, and `runtime/promote.py` (or an
equivalently neutral runtime module).

The promotion module owns the actual provider-state copy and is callable
from `terminal_service` without importing `local_planning`. It reads and
clears only agent-scoped context-workspace metadata.

### 6. Event-driven deferred-switch firing

Files: `services/inbox_service.py`, runtime handle/delivery code, and the
workspace context store helpers from Task 02a.

Task 6 wires the existing log-change watchdog to detect terminal status
transitions, apply any armed agent-scoped pending context switch before
publishing status events, and then deliver context-keyed pending inbox work
through `try_deliver_pending`. The detailed algorithm and edge cases are in
"Event-driven deferred-switch details" below.

### 7. Create `local_planning/` package skeleton

Files described above. Adapter and provider are minimal; the resolver and
`LocalPlanningPlanActivatedEvent` are real implementations. Plan-tool
definitions are stubs here so role grants can expose the tool names; Task 8
owns the real handlers in `local_planning/plans.py`.

In `local_planning/workspace_events.py`, define
`LocalPlanningPlanActivatedEvent` only. Add an explicit
`register_local_planning_cao_events()` helper and call it from API lifespan
startup and from the plan-tool handler path before publishing. The provider
may also return it from `published_cao_events()` for provider-startup
registration, but plan-tool correctness must not depend on
`local_planning` being listed in `workspace-tool-providers.toml`;
role-granted provider-mediated tools can be visible through
`provider_role_tool_access` without provider startup.

### 7b. Register provider in registry

File: `workspace_tool_providers/registry.py`.

Add to `default_workspace_tool_provider_registry()`. The startup loop in
`initialize_enabled_workspace_tool_providers` picks it up if the workspace
tool provider is enabled in `workspace-tool-providers.toml`. By default we
register but require explicit enabling in config to opt in.

### 7c. Register `local_planning` workspace

File: `workspaces/manager.py:default_workspace_registry`.

Add the new `Workspace(...)` alongside the existing `linear_delivery`.

Also update the default workspace service construction in
`workspaces/manager.py`:

- `default_workspace_team_service()` must include
  `LocalPlanningWorkspaceAdapter()` in its available providers/adapters so
  diagnostics do not mark `local_planning` teams as requiring an unavailable
  provider.
- `default_workspace_collaboration_manager()` must include the
  `local_planning` adapter in `provider_adapters` alongside Linear.
- `WorkspaceTeamService.diagnostics()` must report a blocking diagnostic
  when a `local_planning` team has members with different normalized
  `Agent.workdir` values, and collaboration routing must reject that team
  before sending a worker into a plan context whose files may not exist in
  the receiver's workdir.

Add tests proving a `local_planning` team has no `unavailable_provider`
diagnostic, can be resolved by the default collaboration manager, passes
when all members share a workdir, and reports/rejects mixed-workdir teams.

### 7a. Register CAO events in every publishing process/path

Files: `runtime/events.py`, `api/main.py`,
`local_planning/workspace_events.py`, `local_planning/plans.py`.

The default dispatcher rejects unknown event types. Register the
runtime-owned collaboration/status events during API lifespan startup before
the inbox/start/baton endpoints can publish them, and have runtime publish
helpers self-register as an extra guard. Register local-planning events
unconditionally during API lifespan startup and also in the plan-tool handler
path before publishing `LocalPlanningPlanActivatedEvent`. Provider startup
registration remains useful when the provider is enabled, but role-granted
plan tools must work even when no `workspace-tool-providers.toml` entry
loaded the provider during startup.

### 8. Implement plan tools

File: `local_planning/plans.py`.

Each tool's handler conforms to the `ProviderToolHandler` Protocol. Handlers
read the calling agent and terminal from
`ProviderToolInvocationContext.access` and `terminal_id`. Task 8 replaces
the Task 7 stubs with real `create_plan`, `activate_plan`, `list_plans`,
`get_active_plan`, and `complete_plan` handlers. The handlers set and clear
only agent-scoped context-workspace metadata; the neutral promote helper
from Task 5 performs the provider-state copy at terminal-start time.

### 9. Wire outbound resolver into the inbox endpoint

File: `api/main.py:2070`.

Add the lookup + event-build + manager call + receiver context switch
described above. Tests for: same-plan delivery (no switch), cross-plan
delivery (receiver switches), sentinel sender on `local_planning` (rejected),
sentinel sender on `linear_delivery` (allowed — flag False), cross-team
sender/receiver rejection via the existing same-team policy, receiver BUSY
(delivery queued in new context, switch deferred).

### 9a. Emit received-side message event from inbox delivery

File: `services/inbox_service.py`.

`AgentMessageReceivedEvent` is emitted at the actual delivery point, after
`check_and_send_pending_messages` successfully sends the batch and marks the
notification(s) delivered. Emit one event per delivered `InboxDelivery` in
the batch. Each event carries the receiver agent/terminal, that delivery's
persisted `inbox_message_id`, and correlation/causation derived from that
notification's source or metadata set by the sent-side routing
(`source_kind="agent_collaboration_message"`,
`source_id=message_source_id`). Add tests in
`test/services/test_inbox_service.py` so this received-side event cannot be
forgotten when only the API endpoint is modified.

### 10. Wire outbound resolver into the agent-start endpoint

File: `api/main.py:1752`.

Add optional `sender_terminal_id` query param. When present, build an
initiated event with `receiver_agent_id` and no required
`receiver_terminal_id`, resolve, pass context_id to `AgentRuntimeHandle`.
When absent, current sentinel default behavior. Preserve the existing
same-team handoff/assign authorization before publishing or routing.

### 10b. Move baton ownership to durable agent ids

File: `services/baton_service.py` (or persistence helper in
`clients/baton_store.py`).

Add durable baton ownership fields:
`originator_agent_id`, `current_holder_agent_id`, and
`return_stack_agent_ids_json`. Baton transitions and holder authorization use
those agent ids. Update MCP/API create, pass, reassign, list, and view
surfaces so explicit holder/receiver/filter ownership arguments and response
fields are agent-id based. The caller's `CAO_TERMINAL_ID` still identifies the
calling runtime and resolves the actor agent. Existing terminal-id fields
remain compatibility/delivery facts for event metadata and debugging, but they
are not the ownership model. Backfill existing terminal-id rows where terminal
metadata can resolve to an agent id, and treat unresolved legacy rows as
explicit legacy/orphan diagnostics.

### 11. Wire outbound resolver into baton service

File: `services/baton_service.py`.

Same pattern, one event per counterparty transition, using Task 10b's durable
agent ownership. `handle.notify(...)` may return a replacement terminal id for
delivery, but baton ownership remains mapped to the receiver agent.

### MCP server propagation for handoff/assign

File: `mcp_server/server.py:_handoff_impl`, `_assign_impl`,
`_create_terminal`.

Read `os.environ["CAO_TERMINAL_ID"]` and pass both
`sender_terminal_id=<caller terminal>` and
`trigger_action=<handoff|assign>` query params to `/agents/{id}/start`.
Because both tools currently call `_create_terminal`, thread the action
through that helper or split the start call so the API can distinguish
`AgentHandoffInitiatedEvent` from `AgentAssignInitiatedEvent`.

### Event-driven deferred-switch details

Three pieces, all workspace-agnostic and living in runtime, not in
`local_planning/`. The local_planning tool handlers only arm state; the
trigger machinery is framework-level.

**(a) Deferred-switch arming.** `create_plan` and `activate_plan` set two
fields on the caller's agent-local `ContextWorkspaceModel.metadata_json` for
the target workspace context:

- `promote_from_context_id = <caller's current ctx>` (drives promote at
  start time, as described in the Promote Helper section)
- `pending_for_agent_id = <caller's agent_id>` (signals that this context is
  waiting to be entered by this specific agent at their next idle moment)

Both fields are scoped to one `(agent_id, workspace_context_id)` row and are
cleared by the runtime once that agent's switch/delivery path actually lands.

**(b) `AgentTerminalStatusChangeEvent` (new runtime event).** Fields:
`agent_id`, `terminal_id`, `previous_status`, `new_status`. Lives in
`runtime/events.py` alongside the existing runtime event family. Registered
in the default dispatcher at runtime startup.

Emitted by `services/inbox_service.py:LogFileHandler._handle_log_change`
when `provider.get_status()` differs from the previously-observed status
for that terminal. The current handler short-circuits when there are no
pending terminal-id inbox notifications; this plan changes that. The status
check must also run when the agent has any armed workspace-context switch
(`pending_for_agent_id == agent_id` on that agent's context-workspace rows),
or when the agent has pending context-keyed notifications
(`agent:<id>:context:<ctx>`) discovered through
`list_pending_agent_inbox_receiver_ids(agent_id)`, even if there is no
pending inbox notification for the current terminal id. Otherwise
`create_plan` / `activate_plan` and cross-plan send_message / baton delivery
can defer while busy and then strand the switch. Add a small per-terminal
previous-status cache (in-memory is sufficient — the event is best-effort,
not durable) and emit on transitions.

**(c) Two-phase emission.** The watchdog applies pending workspace-level
state *before* publishing the event:

```
def _handle_log_change(self, terminal_id):
    agent_id = terminal_metadata(terminal_id)["agent_id"]
    has_terminal_inbox = bool(list_pending_inbox_notifications(terminal_id, limit=1))
    has_pending_switch = bool(list_context_workspaces_pending_for_agent(agent_id))
    has_context_inbox = bool(list_pending_agent_inbox_receiver_ids(agent_id))
    if not has_terminal_inbox and not has_pending_switch and not has_context_inbox:
        logger.debug("No pending inbox or workspace switch for terminal")
        return

    provider = provider_manager.get_provider(terminal_id)
    if provider is None:
        raise ValueError(f"Provider not found for terminal {terminal_id}")
    new_status = provider.get_status()
    previous_status = self._previous_status.get(terminal_id)

    if previous_status != new_status:
        # Phase 1: apply pending workspace state gated on this transition
        apply_pending_workspace_context_switches(
            agent_id=agent_id,
            new_status=new_status,
        )
        # ^ Looks up context workspaces for this agent where
        # pending_for_agent_id == agent_id, plus pending inbox receiver ids
        # shaped agent:<id>:context:<ctx>.
        # If new_status is IDLE/COMPLETED, calls
        # AgentRuntimeHandle(agent, workspace_context_id=ctx).try_deliver_pending()
        # for each discovered context. That path first ensures freshness, then
        # moves pending agent:<id>:context:<ctx> notifications to the live
        # terminal and delivers them if the terminal is ready. Successful
        # switches clear pending_for_agent_id and promote_from_context_id from
        # the agent/context metadata only after the delivery/freshness path has
        # had a chance to move context-addressed inbox work.
        # By the time this returns, the agent's terminal_id may be different.

        # Phase 2: emit the event with settled state
        publish(AgentTerminalStatusChangeEvent(
            agent_id=agent_id,
            terminal_id=current_terminal_id_for_agent(agent_id),
            previous_status=previous_status,
            new_status=new_status,
        ))
        self._previous_status[terminal_id] = new_status

    # Existing same-terminal inbox delivery proceeds against settled state.
    # Only attempt delivery when there is pending inbox work for the settled
    # terminal id.
    settled_terminal_id = current_terminal_id_for_agent(agent_id)
    if list_pending_inbox_notifications(settled_terminal_id, limit=1):
        check_and_send_pending_messages(settled_terminal_id)
```

Subscribers of `AgentTerminalStatusChangeEvent` see post-switch state. They
don't have to know about the switch mechanism or worry about registration
ordering — the framework guarantees switch-then-event.

`apply_pending_workspace_context_switches` is the new workspace-neutral
helper called by the watchdog (a small module function in
`runtime/agent.py` or a sibling file). It contains all the logic for:
querying agent-scoped context-workspace metadata, discovering pending
context-keyed inbox receiver ids for the agent, constructing handles, calling
`try_deliver_pending()` for each discovered context, and clearing arming
metadata only after the switch/delivery path reports ready or delivered. No
`local_planning` import — plan-tool arming is metadata-driven and cross-plan
message/baton delivery is inbox-receiver-id-driven.

Edge cases:

- **Multiple discovered contexts.** If somehow an agent has two
  context-workspace rows with `pending_for_agent_id` set, two pending
  context-keyed inbox receiver ids, or both for different contexts, only one
  switch can land per idle cycle (terminal manifestation invariant). The
  helper attempts each in order; the first successful switch consumes the
  idle window. The rest remain armed or pending until the next idle.
- **Concurrent log-change events.** The runtime's existing locking around
  `_deactivate_other_context_terminal_for_switch` handles this; the second
  call sees the in-flight state and either reuses or defers.
- **Agent has no armed contexts or context-keyed pending inbox ids.** Helper
  returns quickly. The watchdog's local-planning status event path is a
  pending-work path, so no `AgentTerminalStatusChangeEvent` is published for
  this no-work log change.
- **Linear coexistence.** Linear's monitor (`linear/monitor.py:601`) still
  drives its own retry loop for Linear-specific delivery. This new watchdog
  path is additive and faster-response; it doesn't replace Linear's monitor
  but does mean Linear-armed contexts on idle agents fire promptly too.

### 12. Tests

Test directories: `test/local_planning/`, plus additions to existing
suites for the API endpoint changes.

Coverage:

- Workspace + provider registration shows up in the registry.
- Workspace/context-workspace store helpers cover context lookup by id,
  resolver-filtered listing, agent-scoped metadata patch/clear,
  agent-scoped pending switch lookup, and completed-status mutation.
- Provider role grants for `local_planning.plan_tools` expose only the
  tools enabled for that role; unsupported/unknown grant names fail closed.
  Tests configure agent-side `workspace.team` membership rather than a
  non-existent team `members` field.
- Default workspace team/collaboration services include the
  `local_planning` adapter/provider so a configured local-planning team does
  not receive `unavailable_provider` diagnostics.
- Local-planning team diagnostics reject mixed-workdir membership and
  collaboration routing refuses to inherit a plan context across agents
  whose team violates the shared-workdir invariant.
- The 17 runtime-owned event types register with the default dispatcher
  during API/runtime startup (one parameterized test per type asserting
  publish + round-trip serialization), and
  `LocalPlanningPlanActivatedEvent` registers both during API startup and
  through the plan-tool publish path.
- Event tests assert every new event has the required `kind` Literal
  discriminator and contributes expected `agent_participants` rows so
  sender/receiver/holder/originator timelines include the events.
- API startup registers runtime-owned collaboration/status events, and
  role-granted plan-tool invocation registers/publishes
  `LocalPlanningPlanActivatedEvent` without requiring
  `local_planning` in `workspace-tool-providers.toml`.
- Resolver returns expected resolutions for each of the eight sent-side
  collaboration events and for `LocalPlanningPlanActivatedEvent`. Resolver
  returns `None` for each of the eight received-side events and for an
  arbitrary unrecognized event type. Resolver also returns `None` for
  non-sentinel sender contexts that are stale or whose stored boundary is
  not `local_planning` / `local_planning` / `plan`.
- Sent + received events fired by each call site carry matching
  `correlation_id` so the timeline can pair them. For `send_message`,
  assert the resolver-consumed sent event is built before persistence with
  `message_source_id`, and each delivered event later carries its own real
  `inbox_message_id`. For baton transitions, assert the received event is
  emitted only after delivery succeeds and carries the delivery terminal id.
- `services/inbox_service.py` emits `AgentMessageReceivedEvent` from the
  successful delivery path with correlation from each delivered
  notification's source/metadata, one received event per delivered
  `InboxDelivery` in a batch.
- `create_plan` from sentinel: writes file, registers context with
  `boundary_object_id=<workdir_scope>:<slug>` and agent-scoped
  `promote_from_context_id` set to sentinel, builds event, resolves, calls
  `ensure_fresh_started`, and returns queued success on
  `AgentRuntimeFreshnessAction.DEFERRED`.
- `create_plan` from existing plan A (wrap-up flow): writes file, registers
  context with agent-scoped `promote_from_context_id=A`, triggers deferred
  switch. After the switch fires, target dir has copied state from A.
- `activate_plan` uses the same `ensure_fresh_started` path and maps
  deferred-on-busy to queued success and ready outcomes to active success
  instead of surfacing an exception.
- Promote helper: copies provider state for Claude Code / Codex when
  agent-scoped `promote_from_context_id` is set and target dir is fresh;
  no-op for providers without `runtime_state_capability`; no-op when target
  dir has prior state; clears that agent/context metadata field after any
  evaluated copy or no-op. Terminal-specific provider prep files are not
  overwritten by stale promoted files.
- `complete_plan` flips status to `completed`; `list_plans` includes the
  completed plan for the caller's workdir scope and does not list same-slug
  plans from another workdir scope.
- Sender guardrail: sentinel sender on `local_planning` workspace rejected;
  same scenario on `linear_delivery` workspace allowed.
- Inheritance via handoff: worker terminal lands in sender's plan context
  (assert terminal metadata after start).
- send_message receiver-side switch: receiver on different plan gets
  context-switched. Inbox notification is created against
  `agent:<id>:context:<resolved>` (assert via DB inspection) and survives
  the terminal restart that the switch triggers. No message loss.
- send_message preserves existing same-team authorization before routing:
  cross-team sender/receiver pairs are rejected even if context resolution
  would otherwise succeed.
- Deferred cross-plan send_message to a BUSY receiver: after the receiver
  becomes IDLE, the pending switch helper discovers the pending
  `agent:<id>:context:<resolved>` receiver id even without
  `pending_for_agent_id`, calls `try_deliver_pending()` for the resolved
  context, moves the notification to the live terminal, and delivers it.
- send_message with `sender_id` not mapping to a live terminal: 400 with
  actionable error.
- Handoff and assign MCP paths pass both `sender_terminal_id` and
  `trigger_action`, and the API emits the matching initiated/accepted event
  type for each action.
- Baton transitions across plans behave the same as send_message.
  Tests resolve baton caller terminals to sender agent ids and use receiver
  agent ids for pre-routing event construction.
- Handoff target already running on a different plan: 409 preserved; no
  force-switch attempted.
- **Deferred-switch fires on next idle**: after `create_plan` returns
  "queued" while the agent is BUSY, advancing the agent's terminal to IDLE
  triggers the watchdog extension even when
  `list_pending_inbox_notifications(current_terminal_id)` is empty. The
  extension applies the armed context switch, promotes provider state, and
  clears that agent/context row's `pending_for_agent_id` /
  `promote_from_context_id`.
- **Context-keyed inbox fires on next idle**: after send_message or baton
  creates a pending `agent:<id>:context:<ctx>` notification for a BUSY
  receiver, advancing the current terminal to IDLE triggers
  `try_deliver_pending()` for `<ctx>` even though no plan-tool arming
  metadata exists.
- Watchdog status checks resolve `provider_manager.get_provider(terminal_id)`
  and call `provider.get_status()` without passing the terminal id.
- Existing Linear tests still pass; no regression in `linear_delivery`.

### 13. Update current docs

Add a short `docs/workspaces.md` or extend `docs/agents.md` with a section
on the `local_planning` workspace and how plan files relate to it. Reference
this plan and the criteria catalog rules.

## Definition of Done

This section is the authoritative acceptance source for the plan.

1. A `local_planning` workspace is registered in
   `default_workspace_registry` with its own resolver and one
   `local_planning` workspace tool provider. The default workspace team
   service and default collaboration manager also register the
   `LocalPlanningWorkspaceAdapter`, so `local_planning` is available in
   diagnostics and collaboration routing. `local_planning` teams with mixed
   member workdirs produce a blocking diagnostic and are rejected before
   plan-context inheritance/collaboration routing.
2. The `WorkspaceContextResolver` for `local_planning` returns context
   resolutions for the eight sent-side agent collaboration events
   (`AgentMessageSentEvent`, `AgentHandoffInitiatedEvent`,
   `AgentAssignInitiatedEvent`, `BatonCreatedEvent`, `BatonPassedEvent`,
   `BatonReturnedEvent`, `BatonCompletedEvent`, `BatonBlockedEvent`) and for
   `LocalPlanningPlanActivatedEvent`. It returns `None` for all received-side
   events, any other event type, and any sender context that is not an
   existing `local_planning` / `local_planning` / `plan` workspace-context
   boundary. Linear's resolver is unaffected.
3. `Workspace.require_active_workspace_context` defaults to `False`;
   `linear_delivery` is unchanged; `local_planning` declares `True`. When
   `True`, an outbound collaboration with a sentinel sender is rejected with
   a clear error.
4. The API inbox endpoint, agent-start endpoint, and baton service all
   preserve existing same-team collaboration authorization, then build
   outbound collaboration events from sender info, consult the
   `WorkspaceCollaborationManager`, and apply the resolved context to the
   receiver (or reject when required). The MCP server propagates both
   `sender_terminal_id` from `CAO_TERMINAL_ID` and
   `trigger_action=<handoff|assign>` to the agent-start endpoint when
   initiating handoff or assign.
5. Plan tools `create_plan`, `activate_plan`, `list_plans`,
   `get_active_plan`, `complete_plan` are registered through
   `LocalPlanningWorkspaceToolProvider.provider_tool_access()` and
   `provider_role_tool_access(grants)`, and are visible only to
   role-granted agents on a `local_planning` team.
6. `create_plan` writes the plan to `<agent.workdir>/docs/plans/<slug>/plan.md`,
   registers the workspace context with
   `boundary_object_id=<workdir_scope>:<slug>`, sets agent-scoped
   context-workspace arming metadata with `promote_from_context_id` set to
   the caller's current context, then attempts the runtime switch through
   `ensure_fresh_started()`. The tool maps
   `AgentRuntimeFreshnessAction.DEFERRED` to queued success and
   STARTED/REUSED/RESTARTED to active success, returning a clear
   acknowledgment instead of letting `ensure_started()` raise. This holds
   whether the caller's current context is the sentinel (discovery flow) or
   another plan
   (wrap-up-A-commence-B flow).
7. The promote step runs at deferred-switch time inside the terminal-start
   flow, reading `promote_from_context_id` from the target context workspace
   metadata for the specific agent. It runs after the launch context is built
   but before provider runtime preparation, or uses an equivalent selective
   copy that preserves freshly generated terminal/config files. It copies
   provider runtime state for Claude Code and Codex when the target dir is
   fresh; it is a no-op for providers without `runtime_state_capability`,
   when the target dir already has state, and when the source dir has no
   state. That agent/context `promote_from_context_id` field is cleared
   after any evaluated copy or no-op so re-entries do not repeatedly
   re-evaluate stale promotion arms.
8. `send_message` delivery is routed through
   `AgentRuntimeHandle.notify(...)` (the same path Linear's webhook flow
   already uses), so the inbox notification is addressed as
   `agent:<id>:context:<resolved>` and survives any receiver context switch
   triggered by the resolution. The resolver-consumed
   `AgentMessageSentEvent` is built before persistence with
   `message_source_id` and a non-null `correlation_id`, while each
   delivered/received event carries its own real persisted
   `inbox_message_id` and reuses that delivery's sent correlation id.
   `AgentRuntimeHandle.notify` supports optional notification metadata so
   the sent event id/correlation can be persisted with the inbox
   notification and reused by the received event.
   The existing terminal-id-keyed inbox path is no longer the primary route
   for CAO-originated messages on workspaces that require active context.
9. `AgentTerminalStatusChangeEvent` is published by the watchdog on status
   transitions. **Before** publishing, the watchdog applies any armed
   workspace context switches for the agent (agent-scoped context-workspace
   rows with `pending_for_agent_id == agent_id`) and any pending
   context-keyed inbox receiver ids (`agent:<id>:context:<ctx>`), so
   subscribers see settled state. The switch fire, promote copy, and
   metadata clearing all happen in this pre-publish phase through
   `try_deliver_pending()` on the discovered context, so pending
   notifications are moved to the live terminal and delivered when ready.
   This status path runs when terminal-id inbox work exists,
   workspace-context switch metadata is armed, or context-keyed inbox work
   exists; it must not skip merely because the current terminal has no
   pending terminal-id notification. The helper is workspace-neutral and
   does not import `local_planning`.
10. `WORKSPACE_CONTEXT_STATUS_COMPLETED` exists alongside the existing
    active status; `complete_plan` flips a plan's row to completed.
11. Workspace/context-workspace store helpers support context lookup by id,
    resolver-filtered listing, agent-scoped context-workspace metadata
    patch/clear, agent-scoped pending switch lookup, and completed-status
    mutation.
12. `list_plans` enumerates `local_planning` workspace contexts only for
    the caller's workdir scope, including completed ones; `get_active_plan`
    reads the caller terminal's context and verifies it belongs to that
    scope.
13. Existing Linear flows are unchanged. Existing tests for Linear and the
    workspace registry still pass without modification.
14. The 409 response from `/agents/{id}/start` for an already-running agent
    (`api/main.py:1758`) is preserved. Handoff to a worker already on a
    different plan still fails fast — no force-switch behavior added.
15. Sender ID lookup failures at the inbox endpoint produce a clear 400 with
    actionable error text; they do not silently fall through to the legacy
    terminal-id delivery path.
16. Baton transitions resolve terminal callers/receivers to durable CAO agent
    ids and workspace_context_ids before constructing outbound events or
    applying context routing. Baton ownership and return stacks are stored as
    agent ids, so context routing may replace a receiver terminal without
    changing the baton owner. Holder authorization and watchdog scans reason
    from agent ownership/runtime state, while event fields distinguish
    terminal ids from agent ids.
17. Applicable criteria from `docs/criteria/` are reviewed and treated as
    implicit acceptance criteria. After implementation, evaluate the
    pending changes against the criteria catalog. No criteria applicable to
    the completed diff may be violated.
18. All newly published CAO event types are registered in the process/path
    that publishes them: API startup (and runtime publish helpers) register
    runtime-owned collaboration/status events, API startup also registers
    local-planning events for discovery, and plan-tool handlers register
    local-planning events again before publishing.
19. All new CAO event dataclasses include the required `kind` Literal
    discriminator and populate `agent_participants` for timeline indexing.

## Required Verification

Required static checks:

- New code passes the project's existing static checks:
  - `uv run black --check src/ test/`
  - `uv run isort --check-only src/ test/`
  - `uv run mypy src/`
- No active imports of removed names; no shims for legacy paths (none
  expected since this is additive).

Required backend checks (run from repo root):

- `uv run pytest test/workspaces` — registry, manager, flag enforcement.
- `uv run pytest test/clients/test_workspace_context_store.py` — context
  status, metadata, listing, and pending-switch helpers.
- `uv run pytest test/local_planning` — new suite.
- `uv run pytest test/api` (or whatever path covers inbox/agents endpoints)
  — endpoint changes including resolver flow.
- `uv run pytest test/mcp_server/test_handoff.py test/mcp_server/test_assign.py`
  — sender terminal and trigger-action propagation.
- `uv run pytest test/services/test_inbox_service.py` — watchdog armed-switch
  detection without terminal-id inbox work, provider status-call shape, and
  received-side message event emission after delivery.
- `uv run pytest test/services/test_baton_service.py` — baton resolver wiring.
- `uv run pytest test/linear` — confirm no regressions.
- `uv run pytest test/runtime` — confirm context-switch path unchanged for
  Linear, plus promote helper behavior.
- Manual: define a local_planning team in `~/.cao/workspace-teams.json`,
  configure the test agents' agent-side `workspace.team` to that team id,
  run a Claude Code or Codex agent, exercise `create_plan` → confirm
  `docs/plans/<slug>/plan.md` exists, terminal restarts on next idle, agent
  resumes the conversation in the new context. Then `send_message` to a
  worker on the team and confirm the worker inherits.

Required criteria-catalog check:

- `uv run python scripts/catalog_criteria.py` and load any criterion whose
  `when` clause matches the implementation diff. Document the evaluation in
  the completion report.

## Open Questions and Future Work

- Dashboard plan picker (let a user spawn an agent directly into a plan, so
  the resolver receives an event on `/agents/{id}/start` and the agent
  starts on the plan instead of the sentinel). Followup plan.
- Handoff to an already-running worker on a different plan currently returns
  409 by inheritance from `api/main.py:1758`. If this becomes a pain point,
  add a force-switch policy guarded by a flag.
- Runtime state capability for Kiro/Q/Copilot/Gemini/Kimi when those
  providers come back into the active set. Separate workstream.
- Plan archival / deletion semantics. Out of scope.

## Completion Report

Create `docs/plans/local-planning-workspace/completion-report.md` with:

- Summary of changes, file list.
- Static and backend test evidence (commands + outcomes).
- Manual verification evidence (the two-agent flow above).
- Criteria-catalog evaluation table.
- Any open followups discovered during implementation.

## Review Gate

After implementation, run review loops before declaring the plan complete.

Reviewer must compare landed implementation against the Definition of Done
and Required Verification, and must browse `docs/criteria/` applying
relevant criteria as implicit acceptance criteria.

For each valid reviewer finding: fix the implementation, add a subsection to
the completion report, restart the review loop with a fresh reviewer.
Success requires two consecutive fresh review passes with zero valid
findings.
