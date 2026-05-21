# Delete Linear Provider Completion Report

Date: 2026-05-21

## Final Shape

Linear is removed as a built-in workspace tool provider. The
`cli_agent_orchestrator.linear` package, `test/linear`, Linear smoke scripts,
Linear API routes, Linear web timeline views, Linear config serialization, and
Linear provider-conversation access decisions are gone.

The inbox is now a CAO-owned, agent-to-agent notification queue. Inbox rows
store `sender_agent_id`, `receiver_agent_id`, `body`, `status`, `created_at`,
`delivered_at`, `failed_at`, and `error_detail`. The public inbox surface is
`send(...)` and `read(...)`; `reply_to_inbox_message` is removed, so agents
respond to agents with `send_message`, while future provider-specific replies
belong to provider-specific tools. The decision is recorded in
[ADR 0005](../../adr/0005-inbox-agent-to-agent-only.md); ADR 0001 and ADR 0004
now point there as superseded records, along with ADR 0003's intermediate
schema-collapse decision.

The `workspace_tool_providers/` framework remains, but the default registry no
longer registers any provider by name. The next `local` provider workstream can
register its provider explicitly without inheriting Linear-specific behavior.

## Deleted and Collapsed Surface

The cumulative diff removes roughly 29.9k lines and adds roughly 2.4k lines.
Major removals:

- `src/cli_agent_orchestrator/linear/` and `test/linear/`.
- Linear OAuth/webhook/API routes, dashboard Linear config fields, Linear event
  renderers, Linear smoke scripts, and the stale Linear-oriented example agent.
- Provider conversation access checks from `ToolService`, including
  `ProviderConversationAccessRequirement` and `provider_conversation_decision*`.
- Inbox source registry, source metadata, reply registry, replyability, and
  provider-context presentation.
- Runtime notification marker source-kind/source-id columns and payload fields;
  runtime notification idempotency now uses a single `idempotency_key`.
- Monitoring sessions are keyed by durable `agent_id`; old terminal-keyed
  session rows are migrated only when their terminal maps to an agent.
- Linear-owned persistence tables: `provider_conversation_threads`,
  `provider_conversation_messages`, `provider_conversation_inbox_notifications`,
  `processed_provider_events`, `provider_work_items`, and
  `linear_monitor_watermarks`.

One stale built-in skill, `discovery-partner`, was deleted because it was
Linear-shaped. The whole `src/cli_agent_orchestrator/skills` package was not
deleted because supervisor and worker bundled skills are still loaded by the
API/CLI and asserted by tests.

## Criteria Evaluation

- `do-not-assume-backwards-compatibility`: Removed Linear config, API routes,
  tools, tests, package paths, workspace id aliases, and the legacy
  `workspace_setup` team-file shape rather than keeping compatibility shims.
- `migration-discipline`: Startup migration rebuilds `inbox_notifications`
  into the final schema, drops obsolete Linear/provider-conversation tables,
  removes persisted Linear CAO event rows whose classes no longer exist, and
  backfills older flow tables before the daemon queries them. Regression tests
  cover old-shape inbox migration, provider table dropping, removed event-row
  cleanup, and final schema behavior.
- `system-definitions-are-localized` and `prefer-public-surfaces`: The inbox
  public API exposes direct `send` and `read` semantics. Persistence and
  terminal readiness stay inside `cli_agent_orchestrator.inbox`; transaction-
  scoped system services that already own database sessions use the database
  client surface rather than importing private inbox storage modules.
- `minimal-cohesive-changes`: The diff deletes Linear and collapses inbox only.
  It does not implement the future `local` provider or redesign unrelated
  workspace/team services.
- `deep-systems`: Source-kind polymorphism, reply dispatch, provider
  presentation helpers, terminal-addressed inbox read routes, terminal-id
  receiver fallbacks, baton terminal-holder inbox paths, runtime
  context-scoped receiver aliases, and notification receiver rehoming were
  folded away; direct sender/receiver/body fields are now the durable shape.
- `readable-and-explicit`: New inbox code and tests use `sender_agent_id`,
  `receiver_agent_id`, and `body`. Grep guards confirm no old source/reply
  concepts remain inside the inbox package.
- `system-code-locality`: FastMCP tool registration remains in
  `mcp_server/server.py`, while message reads delegate to the inbox package.
- `test-validity-preserved`, `target-behavior-must-not-be-mocked`, and
  `test-through-owner-surfaces`: Updated tests exercise real database/API/MCP
  surfaces for inbox, runtime notification, and migration behavior rather than
  replacing assertions with truthiness or mocks.
- `ui-changes-require-real-browser-verification`: The frontend was rebuilt and
  the backend-served dashboard was opened at `http://127.0.0.1:8765/` in the
  in-app browser. The app shell and Agents tab rendered from the built JS/CSS
  assets; the `implementation_partner` Config tab showed no Linear config
  section or OAuth/token controls; its Timeline tab loaded a runtime event
  without Linear-specific views; and the Workspace Teams tab rendered without
  500s or server errors. User-home agent data still contains stale Linear-named
  agents, but that is persisted runtime data outside this repo.

## Verification Log

- `uv run python -m compileall -q src/cli_agent_orchestrator`: passed.
- `uv run pytest -q --no-cov`: `1828 passed, 16 skipped, 73 deselected`.
- `uv run pytest -q`: `1828 passed, 16 skipped, 73 deselected`, coverage total
  87%.
- `uv run mypy src/`: passed with no issues.
- `cd web && npm run test:run`: 14 test files and 167 tests passed.
- `cd web && npm run build`: passed; Vite produced the backend static bundle.
- DB schema check against
  `~/.aws/cli-agent-orchestrator/db/cli-agent-orchestrator.db` showed
  `inbox_notifications(id, sender_agent_id, receiver_agent_id, body, status,
  created_at, delivered_at, failed_at, error_detail)` and no
  `provider_conversation_*` or `linear_monitor_*` tables.
- Grep guards were empty for Linear imports/config, provider conversation access
  decisions, old inbox source/reply metadata, stale `[linear]` type-check
  config, and removed terminal-addressed inbox routes.
- Browser verification after an earlier rebuild:
  `http://127.0.0.1:8765/` served `index-uVBD97Py.js` and `index-DnttTlVk.css`;
  Agents -> `implementation_partner` Config had no `[linear]`, access-token, or
  OAuth controls; Timeline loaded one `Runtime started` event with HTTP 200;
  Teams loaded with workspace/team/member/role controls and no 500 responses.
  A Safari pass against the backend-served Home dashboard opened an agent inbox
  panel and the server log showed
  `GET /agents/discovery_partner/inbox/messages?limit=50` with no
  terminal-addressed inbox request.
- Targeted post-review fixes passed:
  `uv run pytest -q test/test_agent.py::test_load_agent_rejects_removed_linear_config_section test/api/test_inbox_messages.py test/cli/commands/test_inbox.py test/runtime/test_agent_runtime.py::test_busy_notification_uses_agent_inbox_for_later_owner_delivery --no-cov`.
- Final post-review blocker fixes passed:
  `uv run pytest -q test/services/test_baton_watchdog_service.py test/services/test_baton_service.py test/mcp_server/test_baton_tools.py test/integration/test_baton_workflow_smoke.py test/services/test_inbox_service.py test/services/test_monitoring_service.py test/integration/test_monitoring_integration.py --no-cov`.
  The final full suites were rerun afterward:
  `uv run python -m compileall -q src/cli_agent_orchestrator && uv run mypy src/`,
  `uv run pytest -q --no-cov`, `uv run pytest -q`, and
  `cd web && npm run test:run`.
- The last durable-agent cleanup also reran:
  `uv run pytest -q test/runtime/test_agent_runtime.py test/events/test_cao_event_persistence.py test/clients/test_database.py test/services/test_cleanup_service.py test/mcp_server/test_baton_tools.py test/services/test_inbox_service.py --no-cov`,
  `uv run pytest -q test/api/test_agent_routes.py::test_agent_timeline_route_returns_participant_index_rows test/api/test_agent_routes.py::test_agent_timeline_route_preserves_broadcast_viewpoint test/api/test_agent_routes.py::test_agent_related_events_route_uses_envelope_threads test/mcp_server/test_workspace_collaboration.py::test_baton_create_rejects_different_team_before_service_call test/mcp_server/test_workspace_collaboration.py::test_baton_pass_rejects_missing_team_before_service_call --no-cov`,
  `uv run python -m compileall -q src/cli_agent_orchestrator && uv run pytest -q --no-cov`,
  `uv run pytest -q`, `uv run mypy src/`, `cd web && npm run test:run`,
  and `cd web && npm run build`.
- A fresh no-context review then found two migration/read-authorization
  leftovers. Those were fixed by preventing unresolved legacy source ids from
  becoming `sender_agent_id`, normalizing only mapped/explicit agent aliases
  during legacy receiver migration, and requiring exact receiver-agent matches
  for `read()`. The reset verification passed: `uv run mypy src/`,
  `uv run pytest -q --no-cov` (`1829 passed, 16 skipped, 73 deselected`),
  `uv run pytest -q` (`1829 passed, 16 skipped, 73 deselected`, 87% total
  coverage), `cd web && npm run test:run`, and `cd web && npm run build`.
- A later fresh no-context review found three stale API surfaces: MCP reads
  still returned legacy envelope fields, API/web inbox responses still exposed
  old message/sender/receiver names, and monitoring sessions were still
  terminal-keyed. Those were fixed by making MCP reads return only `body`,
  making API/web inbox payloads use `notification_id`, `sender_agent_id`,
  `receiver_agent_id`, `body`, and `status`, and moving monitoring
  API/service/CLI/web code to `agent_id`. Targeted backend, frontend, and
  mypy checks passed, followed by a full `uv run pytest -q --no-cov`
  (`1829 passed, 16 skipped, 73 deselected`) and final full coverage pytest
  (`1830 passed, 16 skipped, 73 deselected`, 87% total coverage).
- Review Loop 1 after that found four remaining contract issues: CLI inbox
  list still consumed `sender_id`/`message`, the web Teams panel still called
  the removed provider role-access schema endpoint, public API docs still
  documented removed inbox/monitoring fields, and an explicit
  `clients.inbox_store` compatibility facade was still re-exported through
  `clients.database`. Those were fixed by moving CLI/tests/docs to
  `sender_agent_id`/`receiver_agent_id`/`body` and agent-keyed monitoring,
  deleting the web role-access client/caller/tests, removing the unused API
  response model, deleting `clients.inbox_store`, and importing inbox storage
  from its localized owner `cli_agent_orchestrator.inbox.store`. Reset
  targeted checks passed: `uv run python -m compileall -q src/cli_agent_orchestrator && uv run mypy src/`,
  `uv run pytest -q test/clients/test_database.py test/services/test_baton_service.py test/services/test_baton_watchdog_service.py test/mcp_server/test_baton_tools.py test/runtime/test_agent_runtime.py --no-cov`,
  and `cd web && npm run test:run -- workspace-teams-panel`.
  Full reset verification then passed: `uv run pytest -q --no-cov`
  (`1830 passed, 16 skipped, 73 deselected`), `uv run pytest -q`
  (`1830 passed, 16 skipped, 73 deselected`, 87% total coverage),
  `cd web && npm run test:run`, and `cd web && npm run build`.
- The next reset Review Loop 1 found four more blockers: production code
  still imported inbox storage directly, stale enabled workspace providers
  were silently ignored, API inbox tests mocked happy-path inbox behavior, and
  `docs/monitoring.md` still documented terminal-keyed monitoring. Those were
  fixed by making `cli_agent_orchestrator.inbox` the public owner surface for
  notification listing/status/model helpers, routing production writes through
  `send(..., db=..., attempt_delivery=False)` where services need transaction
  atomicity, failing startup/tool-policy loading on unknown enabled workspace
  providers, isolating tests from user-home provider config, converting API
  inbox happy paths to real in-memory DB behavior, and updating monitoring
  docs to `--agent`/`agent_id`. Reset targeted checks passed:
  `uv run pytest -q test/api/test_inbox_messages.py test/clients/test_database.py::TestInboxOperations test/services/test_inbox_service.py test/runtime/test_agent_runtime.py::test_busy_notification_uses_agent_inbox_for_later_owner_delivery test/services/test_baton_service.py::test_create_baton_rolls_back_if_initial_message_enqueue_fails test/services/test_baton_service.py::test_pass_baton_rolls_back_state_if_transfer_message_enqueue_fails test/api/test_api_endpoints.py::TestLifespan::test_lifespan_fails_when_workspace_tool_provider_startup_fails --no-cov`
  and `uv run mypy src/`. Full backend verification after those fixes also
  passed: `uv run pytest -q --no-cov` (`1830 passed, 16 skipped, 73
  deselected`) and `uv run pytest -q` (`1830 passed, 16 skipped, 73
  deselected`, 87% total coverage).
- A final pre-review sweep found one dashboard mismatch: baton holders are now
  durable agent ids, but the Home dashboard's baton indicator still looked up
  batons by terminal id. That was fixed by keying the indicator by
  `agent_id`, updating the web store/tests, and correcting baton model field
  descriptions from terminal to agent terminology. Verification passed:
  `uv run mypy src/`, `cd web && npm run test:run -- components store`,
  `cd web && npm run build`, and full `cd web && npm run test:run` (14 test
  files, 167 tests). A Safari pass against the isolated-home backend served
  `index-B0pRm1P4.js` and `index-DnttTlVk.css` with HTTP 200s and rendered the
  Home dashboard.
- A reset no-context review then found four remaining blockers: the public
  inbox package still re-exported storage internals, `InboxDelivery` remained
  as a one-field wrapper around notifications, runtime CAO event payloads still
  used `inbox_receiver_id` / `sender_id`, and monitoring message docs/tests had
  drifted from the API response contract. Those were fixed by narrowing
  `cli_agent_orchestrator.inbox.__all__` to `send`, `read`, and public read
  models; moving production callers off deep `inbox.store` / `inbox.readiness`
  imports; deleting `InboxDelivery`; making pending-delivery helpers return
  `InboxNotification` directly; renaming runtime event fields to
  `receiver_agent_id` and `sender_agent_id`; and restoring `notification_id` in
  monitoring message responses.
- Final refresh after those fixes passed:
  `uv run python -m compileall -q src/cli_agent_orchestrator`,
  `uv run mypy src/`, `uv run pytest -q --no-cov`
  (`1828 passed, 16 skipped, 73 deselected`), `cd web && npm run test:run`
  (14 test files, 167 tests), and `cd web && npm run build`. The three
  migration regressions found by full pytest were fixed and rerun directly
  before the full backend pass.
- Final grep guards were empty for stale inbox delivery/runtime contract names:
  `InboxDelivery`, `inbox_delivery`, `inbox_receiver_id`,
  `list_inbox_deliveries`, `get_oldest_pending_inbox_delivery`,
  `list_pending_inbox_deliveries_for_sender`, `same_source`, and
  `different_sources`. The only deep inbox imports left are inside the inbox
  package itself plus direct readiness unit tests.
- Final in-app browser verification against the isolated-home backend served
  `index-Djdp30f6.js` and `index-DnttTlVk.css` with HTTP 200s. Home rendered,
  Agents rendered with no `[linear]`, OAuth, access-token, or Linear config
  controls, and Teams rendered without provider role-access schema UI or server
  errors. Historical user-home session names still include Linear wording; that
  is persisted runtime data outside this repo.
- The next reset Review Loop 1 found four blockers: monitoring creation still
  accepted the removed `peer_agent_ids` request field via Pydantic's default
  extra-field behavior; production code still consumed underscored inbox
  storage aliases from the package root; `docs/api.md` omitted
  `GET /agents/{agent_id}/inbox/messages`; and deselected E2E tests still
  asserted the old `message_id` / `sender_id` / `receiver_id` / `message`
  inbox response shape. Those were fixed by forbidding extra fields on
  `CreateMonitoringSessionRequest`, moving production to named inbox owner
  operations (`list_notifications`, `get_notification`,
  `list_notifications_involving_agent`, cleanup/runtime delivery helpers, and
  `schedule_log_delivery_watcher`), documenting the GET inbox route, and
  updating E2E assertions to `notification_id`, `sender_agent_id`,
  `receiver_agent_id`, and `body`. Targeted verification passed:
  `uv run mypy src/` and
  `uv run pytest -q test/services/test_cleanup_service.py test/api/test_monitoring_routes.py test/api/test_inbox_messages.py test/runtime/test_agent_runtime.py test/services/test_monitoring_service.py test/integration/test_monitoring_integration.py test/clients/test_database.py::TestInboxOperations test/clients/test_database.py::TestInitDb::test_inbox_schema_cutover_addresses_notifications_by_agent_and_drops_old_tables test/mcp_server/test_baton_tools.py test/integration/test_baton_workflow_smoke.py test/services/test_baton_service.py test/services/test_baton_watchdog_service.py test/services/test_inbox_service.py test/mcp_server/test_send_message.py --no-cov`
  (`213 passed`).

Manual inbox flow:

- Backend: `uv run uvicorn cli_agent_orchestrator.api.main:app --host 127.0.0.1 --port 8765`.
- Created temporary durable sender agent `verification_sender`, added it to
  team `cao_delivery`, and sent a message to live agent `implementation_partner`.
- API response:
  `notification_id=31`, `sender_agent_id=verification_sender`,
  `receiver_agent_id=implementation_partner`, `body=<verification body>`.
- Delivery status in the database became `DELIVERED`; terminal log
  `~/.aws/cli-agent-orchestrator/logs/terminal/cfa843be.log` contained the
  message body and `notification_id=31`.
- `implementation_partner` read notification 31 via `read_inbox_message` and
  received only the body in the result:
  `{'success': True, 'body': '<verification body>'}`.
- Built-in tool lookup confirmed `reply_to_inbox_message` is absent.
- The temporary verification agent and team membership were removed afterward.

## Follow-Up

- Clean or migrate user-home persisted agent/session data that still contains
  old Linear wording if the local dashboard should stop showing historical
  records.
- Keep `src/cli_agent_orchestrator/skills` until bundled supervisor/worker
  skill loading has a replacement; only the stale Linear-shaped
  `discovery-partner` skill was removable in this plan.
