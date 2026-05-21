# Delete Linear Provider and Collapse the Inbox

Status: In Progress (Task 1 partially landed on branch `delete-linear-provider`)

## Goal

Remove the Linear workspace tool provider from CAO and aggressively collapse the
inbox subsystem to a pure agent-to-agent message queue. The Linear integration
has been through too many iterations and is no longer wanted; the
"source-agnostic" inbox shape that grew up around it (`source_kind`, `source_id`,
reply dispatch, provider conversation cache, breadcrumb resolution, dual
authorization) was driven by Linear's needs and becomes dead weight once Linear
is gone.

The terminal state is:

1. The `cli_agent_orchestrator.linear` package no longer exists. Neither does
   `test/linear/`. No other module imports from it.
2. `agent.linear` is removed from the Agent config model. Agent TOML files
   carrying `[linear]` blocks are no longer valid.
3. The inbox stores agent-to-agent messages only: one `sender_agent_id`, one
   `receiver_agent_id`, one body, one status. No source kind, no source id, no
   notification metadata, no reply registry, no replyability flag.
4. `read_inbox_message` returns the body of a notification. `reply_to_inbox_message`
   no longer exists — agents reply by calling `send_message` directly, and
   future provider-mediated replies (GitHub PR comments, etc.) will go through
   provider-specific tools (`github.comment_on_pr`), not through the inbox.
5. `ToolService` keeps its role as the central tool registry but loses its
   `provider_conversation_decision*` family of methods and the associated
   `ProviderConversationAccessRequirement` infrastructure.
6. The `provider_conversation_threads`, `provider_conversation_messages`,
   `provider_work_items`, and `linear_monitor_watermarks` SQLite tables are
   dropped. The inbox notification table loses `source_kind`, `source_id`, and
   `metadata_json` columns.
7. The `workspace_tool_providers/` framework stays in place but no longer
   knows any provider by name — `default_workspace_tool_provider_registry()`
   is empty and callers register providers explicitly. The framework is
   waiting for the `local` workspace tool provider to land next.
8. ADRs 0001 ("Inbox: one agnostic concept") and 0004 ("Provider-conversation
   cache owned by Linear") are superseded by a new ADR that records the
   collapse.
9. The web UI no longer ships Linear-specific code paths.

## Why Now

Two observations made the deletion the right call:

- The "convenience" of turning a Linear ping into a fully-formed agent-to-agent
  message is what made the inbox complicated. Roughly 1500 lines of bridge,
  read-context, authorization, and presentation code existed to make a Linear
  comment look like a direct message. The cost-benefit was inverted.
- The user's next workstream is a `local` workspace tool provider that
  manipulates files in the repo. It has no need for the source-agnostic
  inbox shape; it does not generate inbox notifications. Keeping the shape
  for a hypothetical second provider was speculative generality.

## Conceptual Model After Collapse

- **Inbox** is a durable queue of messages addressed to durable agent ids. Each
  message has one sender, one receiver, one body, and a delivery status. The
  inbox knows nothing about providers.
- **`send_message`** is the only verb that writes into the inbox. Providers
  that observe external events (GitHub webhooks, future Linear-style provider
  pings) compose a normal-looking message and call `send_message` themselves;
  the inbox does not distinguish their messages from agent-authored ones.
- **`read_inbox_message`** returns the stored body. Nothing more — no
  breadcrumb, no provider context, no replyability flag.
- **Reply** is no longer a first-class inbox concept. An agent responding to
  another agent uses `send_message`. An agent responding inline on a PR or
  issue uses the provider's own tool (e.g. `github.comment_on_pr`). The agent
  makes that routing decision explicitly; the inbox does not hide it.
- **`workspace_tool_providers/`** remains the registration framework. After
  this work, no providers are registered by default. The user will register
  `local` (and any future providers) through `WorkspaceToolProviderRegistry.register`.
- **`ToolService`** stays the authoritative tool registration and access
  service. It loses the `provider_conversation_decision*` family because
  those decisions no longer have callers.

## Scope

**In scope:**

- Delete `src/cli_agent_orchestrator/linear/` and `test/linear/` in full.
- Decouple every module outside `linear/` from `linear.*` imports.
- Remove `LinearConfig`, `LinearToolAccessConfig`, and the `linear` field from
  `agent.py`. Remove the API request/response shapes that mirrored them.
- Remove `provider_conversation_decision*`, the
  `ProviderConversationAccessRequirement` infrastructure, and the
  `enabled = ("linear",)` fallback from `tool_service.py`.
- Drop the Linear hardcoded factory and conditional branch in
  `workspace_tool_providers/registry.py`. Drop the "Linear is the real owner"
  framing in `workspace_tool_providers/events.py`.
- Drop the Linear OAuth/webhook router include and Linear-specific endpoints
  from `api/main.py`. Drop the Linear-special-cased
  `/workspace-tool-providers/{provider}/role-access-schema` endpoint.
- Rename `DEFAULT_WORKSPACE_ID = "linear_delivery"` to `cao_default` in
  `workspaces/manager.py`. Drop Linear adapter wiring in
  `default_workspace_registry()`, `default_workspace_team_service()`, and
  `default_workspace_collaboration_manager()`. The default workspace becomes
  registered with no provider adapters until `local` lands.
- Drop `ProviderConversationMessageModel`, `ProviderConversationThreadModel`,
  `ProviderWorkItemModel`, `LinearMonitorWatermarkModel` exports from
  `clients/database.py`. Drop the `provider_conversation_store` module and
  the `_migrate_ensure_provider_conversation_tables` /
  `_migrate_ensure_linear_monitor_tables` migration steps.
- Collapse the inbox package: drop `source_kind`, `source_id`,
  `metadata_json` columns and fields; add `sender_agent_id` as a first-class
  column; delete `inbox/source_registry.py`; simplify `inbox/__init__.py`,
  `inbox/store.py`, `inbox/readiness.py`.
- Write a SQLite migration that drops the provider_conversation_* tables, the
  linear_monitor_watermarks table, and the obsolete inbox columns. Migration
  must preserve dependent foreign keys and indexes per
  `docs/criteria/implementation/migration-discipline.md`.
- Web UI: delete `web/src/components/timelineEventViews/linearCaoEventViews.tsx`.
  Strip Linear references from `AgentConfigTab.tsx`, `agentTomlSerialization.ts`,
  `api.ts`, the generated `caoEventPayloadTypes.ts`, and the affected test files.
  Rebuild the bundle and replace `src/cli_agent_orchestrator/web_ui/assets/*`.
- Mark ADR-0001 and ADR-0004 as superseded. Write a new ADR explaining the
  inbox collapse and the `send_message + provider tools` model.

**Out of scope:**

- Designing or implementing the `local` workspace tool provider. That is the
  next workstream; this plan only clears the path.
- Refactoring `tool_service.py` beyond removing the
  provider_conversation infrastructure. The remaining service stays as-is.
- Refactoring `workspaces/manager.py` beyond removing Linear wiring and
  renaming `DEFAULT_WORKSPACE_ID`. The workspace registry, team store,
  collaboration manager structure stays as-is.
- Renaming things outside the explicit scope above. Coding-discipline calls
  for minimal cohesive changes per task; do not chase tangentially related
  cleanup.

## Current State on Branch `delete-linear-provider`

The branch exists with uncommitted edits in five files. Edits are syntactically
valid, but the branch as a whole will not import because referenced linear
symbols still exist in modules I have not yet edited.

Already edited (Linear-free, syntax-clean):

- `src/cli_agent_orchestrator/workspace_tool_providers/events.py` — module
  docstring rewritten; no Linear deference framing.
- `src/cli_agent_orchestrator/workspace_tool_providers/registry.py` —
  `default_workspace_tool_provider_registry()` returns an empty registry; the
  `if name == "linear":` branch in `initialize_enabled_workspace_tool_providers`
  is gone.
- `src/cli_agent_orchestrator/mcp_server/server.py` — three Linear imports
  removed; `_read_inbox_message_impl` no longer dispatches on `source_kind`;
  `_provider_read_result_to_dict`, `_reply_to_inbox_message_impl`, and the
  `reply_to_inbox_message` MCP tool deleted; `_inbox_source_label` simplified
  to use `source_id` directly. (Note: `source_id` references will be replaced
  by `sender_agent_id` in Task 04.)
- `src/cli_agent_orchestrator/agent.py` — `LinearConfig`,
  `LinearToolAccessConfig`, the `linear` field, `_linear_config`,
  `_linear_tool_access_errors`, `_validate_linear_uniqueness`,
  `_linear_to_toml_mapping`, and all related validation / TOML
  serialization paths removed.
- `src/cli_agent_orchestrator/api/main.py` — Linear request/response models
  (`LinearToolAccessResponse`, `LinearConfigResponse`,
  `LinearToolAccessWriteRequest`, `LinearWriteRequest`), the `linear` field
  on `AgentConfigResponse` and `AgentWriteRequest`, the
  `app.include_router(linear_router)` line, and the
  `/workspace-tool-providers/{provider}/role-access-schema` endpoint are gone.
  Imports of `LinearConfig`, `LinearToolAccessConfig`, and `linear_router`
  are removed.

Still pending in Task 01:

- `src/cli_agent_orchestrator/services/tool_service.py` — large surgical
  cleanup of `provider_conversation_*` infrastructure.
- `src/cli_agent_orchestrator/workspaces/manager.py` — rename and drop Linear
  wiring.
- `src/cli_agent_orchestrator/clients/database.py` — drop linear/provider
  conversation model exports.
- `src/cli_agent_orchestrator/clients/database_migrations.py` — drop linear /
  provider_conversation migration setup. (The migration that drops the
  obsolete schema lives in Task 05; this task only removes the table-creation
  migrations.)

## Tasks

Each task is a self-contained file under `tasks/` so it can be dispatched
independently. Tasks have explicit preconditions and post-conditions so a
fresh agent can pick one up cold.

| Task | Title | Depends on |
|------|-------|------------|
| [01](tasks/01-cut-external-importers.md) | Cut external importers of `cli_agent_orchestrator.linear.*` | — |
| [02](tasks/02-delete-linear-package.md) | Delete the `linear/` package and `test/linear/` suite | 01 |
| [03](tasks/03-fix-test-breakage.md) | Run the test suite and fix breakage outside `linear/` | 02 |
| [04](tasks/04-simplify-inbox.md) | Collapse the inbox to agent-to-agent only | 03 |
| [05](tasks/05-db-migration.md) | SQLite migration: drop tables, drop inbox columns | 04 |
| [06](tasks/06-web-ui-cleanup.md) | Strip Linear from the web UI and rebuild the bundle | 03 |
| [07](tasks/07-adr-supersession.md) | Supersede ADR-0001 and ADR-0004; write the new ADR | 04 |
| [08](tasks/08-final-verification.md) | Full suite + manual flow verification | 05, 06, 07 |

Tasks 06 (UI) and 07 (ADR) can run in parallel with the inbox simplification
chain once Task 03 is green. Task 08 gates on all of the above.

## Criteria Acceptance

This plan changes production code, deletes production code, changes the
SQLite schema, changes tests, and changes the web UI. The catalog must be
consulted by each implementing task. Catalog discovery command:

```bash
uv run python scripts/catalog_criteria.py
```

Criteria likely to bind during implementation (final applicability is
determined by the implementer against the actual diff, not by this plan):

- `do-not-assume-backwards-compatibility` — Always. No aliases, shims, or
  compatibility branches for removed Linear surfaces. Migration drops the
  obsolete columns and tables outright.
- `migration-discipline` — The SQLite migration in Task 05 rebuilds tables
  with new shapes; dependent foreign keys, indexes, and triggers must be
  preserved or rebuilt to reference the final schema, not transitional names.
- `system-definitions-are-localized` — The inbox subsystem is being
  substantially reshaped. After Task 04, the inbox's API, models, and storage
  contract must live in `cli_agent_orchestrator/inbox/` only. No inbox
  knowledge bleeds into MCP server, providers, or workspaces.
- `prefer-public-surfaces` — Callers of the inbox use only the package's
  public surface (`send`, `read`, related public models). No deep imports
  into `inbox.store` or `inbox.readiness` from outside the inbox package.
- `minimal-cohesive-changes` — Each task stays within its explicit scope.
  Tangential cleanups are reported, not folded in. Per-task scopes are
  documented in each `tasks/*.md` file.
- `deep-systems` — Apply the deletion test to the collapsed inbox. The
  surface must be narrow (send / read) and the implementation must hide
  delivery scheduling, terminal resolution, and persistence. If a sub-helper
  becomes a one-line pass-through after the trim, fold it into its caller.
- `readable-and-explicit` — Names must reveal the new shape: `sender_agent_id`,
  `receiver_agent_id`, no "source"-prefixed leftovers. Comments that
  reference removed concepts (`provider_conversation`, `source_kind`,
  `replyable`) must be removed.
- `system-code-locality` — Adapters that must live in fixed locations (FastMCP
  tool registration in `mcp_server/server.py`) stay there but delegate back
  to the inbox package.
- `test-validity-preserved` — When tests are updated to match the new
  contracts, they must still validate target behavior. Replacing assertions
  with truthiness checks to keep a suite green is not allowed.
- `ui-changes-require-real-browser-verification` — Task 06 must include a
  real-browser pass against the backend-served bundle. Component tests are
  not enough.
- `target-behavior-must-not-be-mocked` — Inbox tests after Task 04 must hit
  the real inbox store, not mocks of `send` / `read`.
- `test-through-owner-surfaces` — Tests that exercise inbox behavior (in
  `test/inbox/` and any callers) must go through the public inbox API, not
  reach into `inbox.store` private helpers.

**Acceptance condition for each task:**

> After implementation, evaluate the pending changes against the criteria
> catalog. No criteria applicable to the completed diff may be violated. If
> a criterion is not satisfied, fix it or clearly report the reason in the
> task's completion notes.

## Open Questions

None blocking. The architectural decisions captured in the Conceptual Model
section are settled. Decisions made during chat that are recorded here:

- The inbox collapses entirely to agent-to-agent. Source-agnostic shape is
  abandoned.
- `reply_to_inbox_message` MCP tool is deleted. Agents use `send_message` to
  reply to other agents.
- The `workspace_tool_providers/` framework stays but is empty of registered
  providers after this work.
- `tool_service.py` keeps its tool-registry role but loses
  `provider_conversation_decision*`.
- `DEFAULT_WORKSPACE_ID` becomes `cao_default`. Bootstrap teams and tests
  follow the rename.
- Migrations drop tables outright; data loss is acceptable on this personal
  project.
