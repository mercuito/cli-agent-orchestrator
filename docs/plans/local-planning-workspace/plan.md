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
  object_type="plan", object_id=<slug>)`.
- An agent's **active plan** is the workspace_context_id of its current
  terminal (`terminal_service.py:308`). "No active plan" means the terminal is
  on the per-agent sentinel context from
  `default_workspace_context_id(agent_id)`
  (`clients/workspace_context_store.py:164`).
- Plan files live at `<agent.workdir>/docs/plans/<slug>/plan.md` plus any
  sibling task/notes documents the agent writes.
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
   it observes a status transition, (b) `pending_for_agent_id` metadata on
   workspace contexts as the durable arming, and (c) a workspace-neutral
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
├── plans.py                     # plan store + tool handlers
└── promote.py                   # promote-path helper
```

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

All carry the standard `CaoEvent` envelope plus `sender_agent_id: str` and
`sender_workspace_context_id: str`. Specific events add fields per action.

**Sent / initiated (resolver consumes these):**

- `AgentMessageSentEvent` — `receiver_terminal_id`, `receiver_agent_id`,
  `inbox_message_id`. Emitted from the inbox endpoint.
- `AgentHandoffInitiatedEvent` — `receiver_agent_id`, `message`.
  Emitted from `/agents/{id}/start` when called with sender info and the
  triggering tool was handoff.
- `AgentAssignInitiatedEvent` — `receiver_agent_id`, `message`.
  Emitted from `/agents/{id}/start` for assign-triggered starts.
- `BatonCreatedEvent` — `baton_id`, `holder_agent_id`, `title`, `message`.
- `BatonPassedEvent` — `baton_id`, `from_holder_agent_id`,
  `to_holder_agent_id`, `message`.
- `BatonReturnedEvent` — `baton_id`, `from_holder_agent_id`,
  `to_holder_agent_id` (the previous holder being returned to), `message`.
- `BatonCompletedEvent` — `baton_id`, `originator_agent_id`, `message`.
- `BatonBlockedEvent` — `baton_id`, `originator_agent_id`, `reason`.

**Received side (observability; resolver returns `None`):**

- `AgentMessageReceivedEvent` — `receiver_agent_id`,
  `receiver_terminal_id`, `inbox_message_id`. Emitted from
  `inbox_service.check_and_send_pending_messages` after a successful
  delivery to the receiver's terminal.
- `AgentHandoffAcceptedEvent` — `receiver_agent_id`,
  `receiver_terminal_id`. Emitted from `/agents/{id}/start` after the
  worker terminal successfully starts in response to a handoff trigger.
- `AgentAssignAcceptedEvent` — same shape, fires for assign-triggered
  starts.
- `BatonCreationReceivedEvent` — `baton_id`, `holder_agent_id`. Emitted
  from `baton_service` after the first holder is recorded.
- `BatonPassReceivedEvent` — `baton_id`, `to_holder_agent_id`. Emitted
  after the holder change is persisted.
- `BatonReturnReceivedEvent` — `baton_id`, `to_holder_agent_id`. Same
  pattern.
- `BatonCompletionReceivedEvent` — `baton_id`, `originator_agent_id`.
  Fires when the originator is notified of completion.
- `BatonBlockReceivedEvent` — `baton_id`, `originator_agent_id`. Same
  pattern for block notifications.

That's 8 sent + 8 received = 16 collaboration events. Each is a small
dataclass; the duplication is mild and the per-event clarity is worth it
(matches Linear's per-typed-event convention, e.g.
`LinearIssueContextEvent`, `LinearAgentMentionedEvent`,
`LinearIssueDelegatedToAgentEvent`, etc.).

Register all 16 in a `register_agent_collaboration_events()` helper in
`runtime/events.py` that gets called during runtime startup, mirroring the
existing `register_runtime_cao_events()` pattern at lines 185-192.

#### Local planning events (workspace-owned)

In `local_planning/workspace_events.py`:

- `LocalPlanningPlanActivatedEvent` — `agent_id`, `plan_slug`,
  `workspace_context_id`. Emitted by `create_plan` and `activate_plan` tool
  handlers. Consumed by the local_planning resolver to confirm the
  workspace owns this plan and produce the resolution.

Registered through
`LocalPlanningWorkspaceToolProvider.published_cao_events()` which
`workspace_tool_providers/registry.py:_register_provider_events` calls at
provider startup (lines 303-307).

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
        return WorkspaceContextResolution(
            workspace_context_id=event.sender_workspace_context_id,
            resolver_id="local_planning",
            boundary_provider_id="local_planning",
            boundary_object_type="plan",
            boundary_object_id=_slug_for_context(event.sender_workspace_context_id),
        )
    if isinstance(event, LocalPlanningPlanActivatedEvent):
        return WorkspaceContextResolution(
            workspace_context_id=event.workspace_context_id,
            resolver_id="local_planning",
            boundary_provider_id="local_planning",
            boundary_object_type="plan",
            boundary_object_id=event.plan_slug,
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
- `published_cao_events()` — returns the new event types.
- `provider_tool_access()` — returns a `ProviderToolAccessPolicy` declaring
  the plan tools (see below). Handlers are local Python callables; no HTTP.
- Optional `provider_role_tool_access(grants)` if we want role-grant-driven
  access spec. v1 can omit and use a default access policy for any team on
  the workspace.

Register in `workspace_tool_providers/registry.py:default_workspace_tool_provider_registry`
alongside the existing Linear registration.

### Plan Tools

Declared in `LocalPlanningWorkspaceToolProvider.provider_tool_access()`:

1. **`create_plan(title: str, body: str) -> dict`**
   - Slug: kebab-case derived from `title`; reject if a plan with that slug
     already exists.
   - Create directory `<agent.workdir>/docs/plans/<slug>/`.
   - Write `plan.md` with `body`.
   - Call `ensure_workspace_context_for_boundary(resolver_id="local_planning",
     provider_id="local_planning", object_type="plan", object_id=slug,
     metadata={"promote_from_context_id": caller_current_context_id,
     "pending_for_agent_id": caller_agent_id})`. The two metadata fields are
     the durable arming for the deferred switch + promote — see "Event-driven
     deferred-switch firing" below. Caller's current context applies whether
     it is the sentinel (discovery flow) or another plan (wrap-up-A,
     commence-B flow).
   - Build `LocalPlanningPlanActivatedEvent` for this agent + plan.
   - Call `manager.resolve_event_context(caller_agent, event)` → resolution
     (used to ensure the workspace owns this plan and to record the
     activation through the standard pathway).
   - Construct `AgentRuntimeHandle(caller_agent,
     workspace_context_id=resolution.workspace_context_id)` and call
     `ensure_started()` once. If status is BUSY/WAITING_USER the switch
     DEFERS; the watchdog will drive the eventual fire when the agent next
     becomes idle. This is intended behavior.
   - Return `{"plan_id": slug, "status": "queued" | "active", "message":
     "Plan created. Context switch will take effect on your next idle
     moment."}`. The agent learns the outcome from this return value
     directly; no separate inbox notification is queued.

2. **`activate_plan(plan_id: str) -> dict`**
   - Look up the plan's workspace context (must exist).
   - If the target plan's context dir does not yet have provider runtime
     state (first-time activation from another context), set
     `promote_from_context_id = caller_current_context_id` on the target
     workspace context's metadata. If the target already has prior state, do
     not set this — the target plan resumes its own history on the switch.
   - Always set `pending_for_agent_id = caller_agent_id` so the watchdog's
     deferred-fire path picks the switch up at next idle.
   - Emit `LocalPlanningPlanActivatedEvent`, resolve via manager.
   - Trigger `ensure_started` on the runtime handle once. Promote (if
     armed) and the switch both fire at watchdog idle-detection time, same
     mechanism as create_plan.

3. **`list_plans() -> list[dict]`**
   - Query workspace contexts where `resolver_id == "local_planning"`.
   - Return id (slug), display name, status, created_at.

4. **`get_active_plan() -> dict | None`**
   - Read caller terminal's `workspace_context_id` from metadata.
   - If it's a `local_planning` plan context, return its details. Otherwise
     `{"active_plan": null}`.

5. **`complete_plan(plan_id: str) -> dict`**
   - Set the workspace context's `status` to
     `WORKSPACE_CONTEXT_STATUS_COMPLETED`.
   - Does not deactivate the terminal — the agent stays on the (now
     completed) plan context until they transition.

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
`promote_from_context_id` in the new workspace context's `metadata_json`
when they register the context. The runtime's terminal-start path reads
that field and acts on it.

`local_planning/promote.py:promote_workspace_context_state(agent,
target_context_id) -> bool`:

- Reads `promote_from_context_id` from the target workspace context's
  metadata. Returns `False` if not set (nothing to do).
- Resolves source and target `provider_data_dir` via
  `workspace_context_provider_data_dir(agent, ctx_id, agent.cli_provider)`.
- Returns `False` if `runtime_state_capability(agent.cli_provider)` is None
  (Kiro/Q/Copilot/Gemini/Kimi today — no state to copy; cold restart for
  those providers, plan.md is the canonical handoff).
- Returns `False` if the target dir already has provider state (don't
  overwrite an existing plan's history).
- Returns `False` if source has no provider state (nothing to copy).
- Otherwise copies source dir contents to target dir, clears the
  `promote_from_context_id` field (so a future re-entry into this context
  doesn't redo the promote), and returns `True`.

**Hook point**: `terminal_service._create_terminal_core` already loads
runtime state via `runtime_state_capability.load_runtime_state(...)` at
lines 268-277 *before* spawning the tmux window. The promote helper runs
**immediately before** that load — it ensures the dir contents are in place
so the existing load picks them up. Cleanest insertion is a new call
`runtime_paths_with_promote_applied(...)` (or similar) in
`terminal_service` that wraps the existing path resolution + invokes
promote when the metadata is set.

Because the promote is data-driven via workspace-context metadata, the
runtime code stays workspace-agnostic — it doesn't import `local_planning`.
The `local_planning` tool handlers arm the metadata; the runtime reads it
during the standard terminal-start flow.

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
   - Build `AgentMessageSentEvent(sender_agent_id, sender_workspace_context_id,
     receiver_terminal_id, receiver_agent_id, inbox_message_id)` and publish
     via the default dispatcher.
   - Call `manager.apply_outbound_resolution(receiver_agent, event)` (the
     new method described below). This consults the workspace's resolver,
     enforces the `require_active_workspace_context` flag, and returns the
     target workspace_context_id for the receiver.
   - **Delivery routing**: route the inbox write through
     `AgentRuntimeHandle(receiver_agent,
     workspace_context_id=target_ctx).notify(message, ...)` rather than the
     existing terminal-id-keyed inbox path. The runtime handle uses
     `agent:<id>:context:<ctx>` as the inbox receiver id
     (`runtime/agent.py:175`), which:
     - Survives terminal restarts triggered by the context switch.
     - Triggers the existing `ensure_fresh_started` machinery that switches
       the receiver to `target_ctx` if their terminal is on a different
       context. DEFERRED on BUSY; message stays queued in the right
       receiver_id until the switch lands.
   - The corresponding `AgentMessageReceivedEvent` fires from
     `inbox_service.check_and_send_pending_messages` on successful delivery
     to the receiver's terminal (a different code path, but the same
     `inbox_message_id` ties the pair together via correlation).
   - This unifies CAO outbound delivery with the existing Linear inbound
     pattern. Linear's webhook flow already uses this exact handle.notify
     path (`linear/runtime.py:412`); send_message just stops bypassing it.

2. **`api/main.py:1752` `/agents/{agent_id}/start`** (the
   handoff/assign-target start, also used by dashboard direct starts):
   - Accept an optional `sender_terminal_id` query param plus a discriminator
     query param `trigger_action: "handoff" | "assign"`. When present, the
     endpoint looks up sender's metadata and builds either
     `AgentHandoffInitiatedEvent` or `AgentAssignInitiatedEvent` from the
     fields. When absent (dashboard direct start), no sent event is built.
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

   Each transition publishes the sent event before applying the transition,
   runs it through `manager.apply_outbound_resolution(receiver_agent,
   event)` (where receiver_agent is the agent on the receiving side of that
   specific transition — first holder for create, next holder for pass,
   previous holder for return, originator for complete/block), applies the
   resolution to the receiver's runtime handle for context routing, lands
   the transition, then publishes the received event with the same
   correlation_id.

MCP-side changes are limited to one new query param:
`sender_terminal_id`/`sender_id` propagated to the API when starting a
worker from `_handoff_impl` / `_assign_impl`. The MCP server reads
`os.environ["CAO_TERMINAL_ID"]` and includes it. No event emission from
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
`apply_outbound_resolution(workspace, agent, event)` that wraps
`resolve_event_context` and enforces the flag. API call sites use this
method, not raw `resolve_event_context`.

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
`provider_role_tool_access` once we declare the tools as
provider-mediated.

## Implementation Tasks

### 1. Add `require_active_workspace_context` to Workspace

File: `workspaces/manager.py`.

Add field (default `False`), validate type in `__post_init__`. No call site
changes yet.

### 2. Add `WORKSPACE_CONTEXT_STATUS_COMPLETED`

File: `clients/workspace_context_store.py`.

Add the constant and a helper to set the status. Add tests for round trip.

### 3. Create `local_planning/` package skeleton

Files described above. Adapter and provider are minimal; resolver and tools
are real implementations.

### 4. Define new event types

Two files:

- `runtime/events.py` (extend existing): 16 agent collaboration events
  (8 sent + 8 received) and `AgentTerminalStatusChangeEvent`. Add
  `register_agent_collaboration_events()` and
  `register_agent_terminal_status_change_event()` helpers mirroring the
  existing `register_runtime_cao_events()` (lines 185-192). Both helpers
  get called during runtime startup so the dispatcher knows the types
  before any publisher attempts to emit one.
- `local_planning/workspace_events.py`: `LocalPlanningPlanActivatedEvent`
  only. Provider's `published_cao_events()` returns it; the registry's
  `_register_provider_events` calls
  `default_cao_event_dispatcher().register_events(...)` during provider
  startup (`workspace_tool_providers/registry.py:303-307`).

A small shared dataclass mixin or base for the collaboration events is
acceptable to reduce field duplication, but not required. Each event must
declare its own `event_name` and otherwise satisfy the
`_EVENT_TYPE_REQUIRED_FIELDS` shape from `events/__init__.py:120-126`.

### 5. Implement plan tools and promote helper

Files: `local_planning/plans.py`, `local_planning/promote.py`.

Each tool's handler conforms to `ProviderToolHandler` Protocol. Handlers
read the calling agent + terminal from the
`ProviderToolInvocationContext.access` and `terminal_id`.

### 6. Register provider in registry

File: `workspace_tool_providers/registry.py`.

Add to `default_workspace_tool_provider_registry()`. The startup loop in
`initialize_enabled_workspace_tool_providers` picks it up if the workspace
tool provider is enabled in `workspace-tool-providers.toml`. By default we
register but require explicit enabling in config to opt in.

### 7. Register `local_planning` workspace

File: `workspaces/manager.py:default_workspace_registry`.

Add the new `Workspace(...)` alongside the existing `linear_delivery`.

### 8. Add manager method for outbound resolution + flag enforcement

File: `workspaces/manager.py:WorkspaceCollaborationManager`.

`apply_outbound_resolution(agent, event)` calls
`resolve_event_context(agent, event)`. If the agent's workspace flag
requires active context and resolution is `None`, raise
`WorkspaceConfigError`. Otherwise return the resolution (which may be
`None` for workspaces that don't require — caller falls back to the receiver's
existing context).

### 9. Wire outbound resolver into the inbox endpoint

File: `api/main.py:2070`.

Add the lookup + event-build + manager call + receiver context switch
described above. Tests for: same-plan delivery (no switch), cross-plan
delivery (receiver switches), sentinel sender on `local_planning` (rejected),
sentinel sender on `linear_delivery` (allowed — flag False), receiver BUSY
(delivery queued in new context, switch deferred).

### 10. Wire outbound resolver into the agent-start endpoint

File: `api/main.py:1752`.

Add optional `sender_terminal_id` query param. When present, build event,
resolve, pass context_id to `AgentRuntimeHandle`. When absent, current
sentinel default behavior.

### 11. Wire outbound resolver into baton service

File: `services/baton_service.py`.

Same pattern, one event per counterparty transition.

### 12. MCP server: propagate sender terminal id on handoff/assign

File: `mcp_server/server.py:_handoff_impl`, `_assign_impl`,
`_create_terminal`.

Read `os.environ["CAO_TERMINAL_ID"]`, pass as `sender_terminal_id` query
param to `/agents/{id}/start`.

### 13. Event-driven deferred-switch firing

Three pieces, all workspace-agnostic and living in runtime, not in
`local_planning/`. The local_planning tool handlers only arm state; the
trigger machinery is framework-level.

**(a) Deferred-switch arming.** `create_plan` and `activate_plan` set two
fields on the new workspace context's `metadata_json`:

- `promote_from_context_id = <caller's current ctx>` (drives promote at
  start time, as described in the Promote Helper section)
- `pending_for_agent_id = <caller's agent_id>` (signals that this context is
  waiting to be entered by this specific agent at their next idle moment)

Both fields are cleared by the runtime once the switch actually lands.

**(b) `AgentTerminalStatusChangeEvent` (new runtime event).** Fields:
`agent_id`, `terminal_id`, `previous_status`, `new_status`. Lives in
`runtime/events.py` alongside the existing runtime event family. Registered
in the default dispatcher at runtime startup.

Emitted by `services/inbox_service.py:LogFileHandler._handle_log_change`
when `provider.get_status()` differs from the previously-observed status
for that terminal. The watchdog already calls `get_status()`; we add a
small per-terminal previous-status cache (in-memory is sufficient — the
event is best-effort, not durable) and emit on transitions.

**(c) Two-phase emission.** The watchdog applies pending workspace-level
state *before* publishing the event:

```
def _handle_log_change(self, terminal_id):
    if not list_pending_inbox_notifications(terminal_id, limit=1):
        # existing fast-path skip
        ...
    new_status = provider.get_status(terminal_id)
    previous_status = self._previous_status.get(terminal_id)

    if previous_status != new_status:
        # Phase 1: apply pending workspace state gated on this transition
        agent_id = terminal_metadata(terminal_id)["agent_id"]
        apply_pending_workspace_context_switches(
            agent_id=agent_id,
            new_status=new_status,
        )
        # ^ Looks up workspace contexts where pending_for_agent_id == agent_id.
        # If new_status is IDLE/COMPLETED, calls
        # AgentRuntimeHandle(agent, workspace_context_id=ctx).ensure_fresh_started()
        # for each. Successful switches clear pending_for_agent_id and
        # promote_from_context_id from the context's metadata.
        # By the time this returns, the agent's terminal_id may be different.

        # Phase 2: emit the event with settled state
        publish(AgentTerminalStatusChangeEvent(
            agent_id=agent_id,
            terminal_id=current_terminal_id_for_agent(agent_id),
            previous_status=previous_status,
            new_status=new_status,
        ))
        self._previous_status[terminal_id] = new_status

    # Existing same-terminal inbox delivery proceeds against settled state
    check_and_send_pending_messages(current_terminal_id_for_agent(agent_id))
```

Subscribers of `AgentTerminalStatusChangeEvent` see post-switch state. They
don't have to know about the switch mechanism or worry about registration
ordering — the framework guarantees switch-then-event.

`apply_pending_workspace_context_switches` is the new workspace-neutral
helper called by the watchdog (a small module function in
`runtime/agent.py` or a sibling file). It contains all the logic for:
querying contexts by metadata, constructing handles, firing switches,
clearing metadata on success. No `local_planning` import — it's driven
entirely by the metadata fields.

Edge cases:

- **Multiple armed contexts.** If somehow an agent has two contexts with
  `pending_for_agent_id` set, only one switch can land per idle cycle
  (terminal manifestation invariant). The helper attempts each in order;
  the first successful switch consumes the idle window. The rest remain
  armed until the next idle.
- **Concurrent log-change events.** The runtime's existing locking around
  `_deactivate_other_context_terminal_for_switch` handles this; the second
  call sees the in-flight state and either reuses or defers.
- **Agent has no armed contexts.** Helper returns quickly; the event still
  publishes for any other subscribers that care about state changes.
- **Linear coexistence.** Linear's monitor (`linear/monitor.py:601`) still
  drives its own retry loop for Linear-specific delivery. This new watchdog
  path is additive and faster-response; it doesn't replace Linear's monitor
  but does mean Linear-armed contexts on idle agents fire promptly too.

### 14. Tests

Test directories: `test/local_planning/`, plus additions to existing
suites for the API endpoint changes.

Coverage:

- Workspace + provider registration shows up in the registry.
- All 18 new event types register with the default dispatcher (one
  parameterized test per type asserting publish + round-trip serialization).
- Resolver returns expected resolutions for each of the eight sent-side
  collaboration events and for `LocalPlanningPlanActivatedEvent`. Resolver
  returns `None` for each of the eight received-side events and for an
  arbitrary unrecognized event type.
- Sent + received events fired by each call site carry matching
  `correlation_id` so the timeline can pair them.
- `create_plan` from sentinel: writes file, registers context with
  `promote_from_context_id` set to sentinel, builds event, resolves,
  triggers deferred switch.
- `create_plan` from existing plan A (wrap-up flow): writes file, registers
  context with `promote_from_context_id=A`, triggers deferred switch. After
  the switch fires, target dir has copied state from A.
- Promote helper: copies provider state for Claude Code / Codex when
  `promote_from_context_id` is set and target dir is fresh; no-op for
  providers without `runtime_state_capability`; no-op when target dir has
  prior state; metadata field cleared after copy.
- `complete_plan` flips status to `completed`; `list_plans` includes the
  completed plan.
- Sender guardrail: sentinel sender on `local_planning` workspace rejected;
  same scenario on `linear_delivery` workspace allowed.
- Inheritance via handoff: worker terminal lands in sender's plan context
  (assert terminal metadata after start).
- send_message receiver-side switch: receiver on different plan gets
  context-switched. Inbox notification is created against
  `agent:<id>:context:<resolved>` (assert via DB inspection) and survives
  the terminal restart that the switch triggers. No message loss.
- send_message with `sender_id` not mapping to a live terminal: 400 with
  actionable error.
- Baton transitions across plans behave the same as send_message.
- Handoff target already running on a different plan: 409 preserved; no
  force-switch attempted.
- **Deferred-switch fires on next idle**: after `create_plan` returns
  "queued" while the agent is BUSY, advancing the agent's terminal to IDLE
  triggers the watchdog extension, which calls
  `try_deliver_pending` for the agent's `agent:<id>:context:P` receiver id,
  which lands the switch + delivers the queued seed notification + applies
  the promote.
- Existing Linear tests still pass; no regression in `linear_delivery`.

### 15. Update current docs

Add a short `docs/workspaces.md` or extend `docs/agents.md` with a section
on the `local_planning` workspace and how plan files relate to it. Reference
this plan and the criteria catalog rules.

## Definition of Done

This section is the authoritative acceptance source for the plan.

1. A `local_planning` workspace is registered in
   `default_workspace_registry` with its own resolver and one
   `local_planning` workspace tool provider.
2. The `WorkspaceContextResolver` for `local_planning` returns context
   resolutions for the eight sent-side agent collaboration events
   (`AgentMessageSentEvent`, `AgentHandoffInitiatedEvent`,
   `AgentAssignInitiatedEvent`, `BatonCreatedEvent`, `BatonPassedEvent`,
   `BatonReturnedEvent`, `BatonCompletedEvent`, `BatonBlockedEvent`) and for
   `LocalPlanningPlanActivatedEvent`. It returns `None` for all received-side
   events and for any other event type. Linear's resolver is unaffected.
3. `Workspace.require_active_workspace_context` defaults to `False`;
   `linear_delivery` is unchanged; `local_planning` declares `True`. When
   `True`, an outbound collaboration with a sentinel sender is rejected with
   a clear error.
4. The API inbox endpoint, agent-start endpoint, and baton service all
   build outbound collaboration events from sender info, consult the
   `WorkspaceCollaborationManager`, and apply the resolved context to the
   receiver (or reject when required). The MCP server propagates
   `CAO_TERMINAL_ID` to the agent-start endpoint when initiating handoff or
   assign.
5. Plan tools `create_plan`, `activate_plan`, `list_plans`,
   `get_active_plan`, `complete_plan` are registered through
   `LocalPlanningWorkspaceToolProvider.provider_tool_access()` and visible
   to role-granted agents on a `local_planning` team.
6. `create_plan` writes the plan to `<agent.workdir>/docs/plans/<slug>/plan.md`,
   registers the workspace context with `promote_from_context_id` set to
   the caller's current context, and triggers a deferred runtime context
   switch. The tool returns a clear acknowledgment of the deferred behavior.
   This holds whether the caller's current context is the sentinel
   (discovery flow) or another plan (wrap-up-A-commence-B flow).
7. The promote step runs at deferred-switch time inside the terminal-start
   flow, reading `promote_from_context_id` from the target workspace
   context's metadata. It copies provider runtime state for Claude Code and
   Codex when the target dir is fresh; it is a no-op for providers without
   `runtime_state_capability` and when the target dir already has state.
   The metadata field is cleared after a successful copy so re-entries do
   not re-promote.
8. `send_message` delivery is routed through
   `AgentRuntimeHandle.notify(...)` (the same path Linear's webhook flow
   already uses), so the inbox notification is addressed as
   `agent:<id>:context:<resolved>` and survives any receiver context switch
   triggered by the resolution. The existing terminal-id-keyed inbox path
   is no longer the primary route for CAO-originated messages on workspaces
   that require active context.
9. `AgentTerminalStatusChangeEvent` is published by the watchdog on status
   transitions. **Before** publishing, the watchdog applies any armed
   workspace context switches for the agent (contexts with
   `pending_for_agent_id == agent_id`), so subscribers see settled state.
   The switch fire, promote copy, and metadata clearing all happen in this
   pre-publish phase. The helper is workspace-neutral and does not import
   `local_planning`. Subscribers don't need to know about subscription
   ordering relative to the switch.
10. `WORKSPACE_CONTEXT_STATUS_COMPLETED` exists alongside the existing
    active status; `complete_plan` flips a plan's row to completed.
11. `list_plans` enumerates all `local_planning` workspace contexts
    including completed ones; `get_active_plan` reads the caller terminal's
    context.
12. Existing Linear flows are unchanged. Existing tests for Linear and the
    workspace registry still pass without modification.
13. The 409 response from `/agents/{id}/start` for an already-running agent
    (`api/main.py:1758`) is preserved. Handoff to a worker already on a
    different plan still fails fast — no force-switch behavior added.
14. Sender ID lookup failures at the inbox endpoint produce a clear 400 with
    actionable error text; they do not silently fall through to the legacy
    terminal-id delivery path.
15. Applicable criteria from `docs/criteria/` are reviewed and treated as
    implicit acceptance criteria. After implementation, evaluate the
    pending changes against the criteria catalog. No criteria applicable to
    the completed diff may be violated.

## Required Verification

Required static checks:

- New code passes `mypy` and `ruff` per the project's existing config.
- No active imports of removed names; no shims for legacy paths (none
  expected since this is additive).

Required backend checks (run from repo root):

- `uv run pytest test/workspaces` — registry, manager, flag enforcement.
- `uv run pytest test/local_planning` — new suite.
- `uv run pytest test/api` (or whatever path covers inbox/agents endpoints)
  — endpoint changes including resolver flow.
- `uv run pytest test/services/test_baton_service.py` — baton resolver wiring.
- `uv run pytest test/linear` — confirm no regressions.
- `uv run pytest test/runtime` — confirm context-switch path unchanged for
  Linear, plus promote helper behavior.
- Manual: start a local_planning team in `~/.cao/workspace-teams.json`, run
  a Claude Code or Codex agent, exercise `create_plan` → confirm
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
