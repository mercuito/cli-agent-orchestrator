# Task 10b: Baton agent ownership

Part of: [../plan.md](../plan.md) — Event Emission and Resolver
Consultation in API Endpoints → baton identity.

## Goal

Baton ownership belongs to durable CAO agents, not their ephemeral backing
terminals. Today the baton service stores terminal ids in `originator_id`,
`current_holder_id`, and `return_stack_json`, and holder authorization compares
against those terminal ids. Cross-plan delivery can restart a receiver in a new
terminal via `AgentRuntimeHandle.notify(...)`; the baton must remain owned by
the same agent across that restart.

This task migrates baton ownership and return-stack semantics to durable agent
ids. Terminal ids remain useful as caller/runtime/delivery facts, but they must
not be the source of truth for who owns or may act on a baton.

## Dependencies

- Task 03 (baton events exist for later wiring).
- Task 04 (`apply_outbound_resolution` exists for later wiring).

## Files Touched

- `src/cli_agent_orchestrator/services/baton_service.py`
- `src/cli_agent_orchestrator/clients/baton_store.py`
- `src/cli_agent_orchestrator/clients/database_migrations.py` if schema
  changes/backfills are needed.
- `src/cli_agent_orchestrator/services/baton_watchdog_service.py`
- `src/cli_agent_orchestrator/models/baton.py`
- `src/cli_agent_orchestrator/mcp_server/server.py`
- `src/cli_agent_orchestrator/api/main.py`
- `test/services/test_baton_service.py`
- watchdog/storage migration tests as needed.

## What to do

1. Add durable ownership fields for baton rows:
   - `originator_agent_id`
   - `current_holder_agent_id`
   - `return_stack_agent_ids_json`
2. Move explicit holder/receiver public inputs to agent ids:
   - `create_baton` accepts the initial holder agent id;
   - `pass_baton` accepts the receiver agent id;
   - operator/API reassignment accepts the replacement holder agent id;
   - `CAO_TERMINAL_ID` is still used only to identify the calling runtime and
     resolve the caller's agent id.
3. Update MCP tool descriptions, API request/response models, and baton domain
   models so user-facing ownership fields are agent-owned. Do not keep
   terminal-id aliases unless the plan explicitly names them as delivery/debug
   metadata.
4. Keep terminal ids only as runtime/delivery compatibility fields. Existing
   event fields ending in `_terminal_id` should still carry the terminal that
   caused or received a specific transition, but holder authorization and baton
   ownership must use the new agent fields.
5. Update baton create/pass/return/complete/block persistence paths so every
   ownership transition writes agent ids to the durable fields. The return
   stack stores agent ids, preserving ordering and duplicates.
6. Update `_require_current_holder` so it resolves the caller terminal id to
   its owning agent id, then compares that agent id to
   `current_holder_agent_id`.
7. Update listing/view authorization surfaces:
   - `list_batons` and `list_batons_held_by` filter by
     `originator_agent_id` / `current_holder_agent_id`;
   - `get_my_batons` resolves the caller terminal to its agent id before
     querying;
   - `_actor_can_view_baton` compares the caller agent id against
     originator/current-holder/return-stack agent ids.
8. Update baton watchdog logic to inspect the current holder agent/runtime
   state instead of treating a missing old terminal id as an orphaned baton.
   If the agent has a live or restartable runtime, a replaced terminal id must
   not orphan the baton.
9. Provide migration/backfill behavior for existing rows whose
   `originator_id`, `current_holder_id`, and `return_stack_json` contain
   terminal ids:
   - resolve terminal ids to agent ids when terminal metadata exists;
   - preserve old terminal-id fields for delivery/debug compatibility;
   - handle unresolved legacy terminal ids explicitly as legacy/orphan
     diagnostics rather than silently mapping them to a different agent.
10. Ensure Task 11's post-commit notification path uses the receiver agent id
   as the baton owner and the runtime handle's returned terminal id only as
   delivery metadata. No terminal-reference remap helper should be needed.

## Out of scope

- Changing the user-facing baton API shape beyond what is required for
  durable ownership and compatibility.
- Baton timeline UI changes.

## Definition of Done

1. Baton rows persist durable `originator_agent_id`,
   `current_holder_agent_id`, and `return_stack_agent_ids_json` ownership
   data.
2. Baton transitions update the durable ownership fields for create, pass,
   return, complete, and block.
3. `_require_current_holder` authorizes by resolved caller agent id, so a
   holder can act from a replacement terminal owned by the same agent.
4. MCP/API baton create/pass/reassign inputs and list/view filters are
   agent-id based, while `CAO_TERMINAL_ID` remains only caller runtime
   metadata.
5. Cross-plan baton create/pass/return where notify restarts the receiver:
   durable ownership stays on the receiver agent, and terminal ids are used
   only for delivery/event metadata.
6. `get_my_batons` and operator list filters still find batons after the
   caller's/holder's terminal id is replaced because they query by agent id.
7. Baton watchdog does not orphan a baton merely because a previous holder
   terminal id disappeared or changed while the holder agent remains valid.
8. Existing baton rows with terminal-id ownership are backfilled or reported
   through explicit legacy/orphan diagnostics according to the migration
   rules above.

## Review Gate

After implementing this task, run a review loop. The reviewer compares
the landed implementation against each item in Definition of Done above
plus all applicable entries in the `docs/criteria` catalog (run
`uv run python scripts/catalog_criteria.py` and load any criterion whose
`when` clause matches the task's actual diff).

Any valid finding confirmed by the implementer must be fixed, then the
review loop restarts with a fresh reviewer. For every review finding that
requires an implementation change, the implementer updates
[../completion-report.md](../completion-report.md) under this task's
heading, recording what the reviewer found, why it was accepted as valid,
how it was fixed, and what evidence verifies the fix.

This task is complete only after two successive review loops report zero
valid findings for this task, and those two clean review passes are
recorded in the completion report.
