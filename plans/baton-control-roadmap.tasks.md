# CAO Baton Control Roadmap Tasks (Draft v1)

This task list derives from `plans/baton-control-roadmap.md`.

Policy: any task that changes code requires reviewer gate before it is
considered complete.

## Task index

### T01 — Baton domain model and persistence

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - database models for `batons` and `baton_events`
  - idempotent startup migration
  - typed model objects for baton status and event types
  - unit tests for schema creation and migration idempotency
- acceptance:
  - CAO starts with a fresh database and creates baton tables
  - CAO starts with an existing database and applies the migration once
  - status values cover `active`, `completed`, `blocked`, `canceled`, and `orphaned`

### T02 — Baton service

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - service methods for create, pass, return, complete, block, cancel, reassign
  - event append logic for every state transition
  - current-holder authorization checks for agent-facing transitions
  - unit tests for stack behavior and invalid transitions
- acceptance:
  - `pass_baton` pushes the previous holder and sets the new holder
  - `return_baton` pops the previous holder and sends control back
  - `complete_baton` resolves the baton and notifies the originator
  - non-holder transitions fail unless using operator/admin recovery methods

### T03 — Inbox-integrated transfer delivery

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - transfer operations queue inbox messages as part of the service operation
  - message templates include baton id, title, expected next action, and tool instructions
  - tests proving state update and message queueing stay coupled
- acceptance:
  - create/pass/return/complete/block all produce appropriate inbox messages
  - a failed message enqueue does not leave baton state silently advanced
  - transfer messages are readable without prior chat context

### T04 — MCP baton tools

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T03]
- deliverables:
  - `create_baton`
  - `pass_baton`
  - `return_baton`
  - `complete_baton`
  - `block_baton`
  - `get_my_batons`
  - `get_baton`
  - role/tool restriction updates as needed
  - MCP unit tests
- acceptance:
  - agents can create and transfer batons through MCP
  - tool results are structured and include baton id/status/current holder
  - non-holder mutation attempts return actionable errors

### T05 — Baton watchdog and idle nudges

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02, T03]
- deliverables:
  - periodic active-baton scan
  - holder terminal status lookup
  - grace-period and rate-limit config
  - orphan detection when holder terminal is missing
  - unit tests with mocked terminal status/provider state
- acceptance:
  - idle/completed current holders receive a reminder after the grace period
  - reminders are rate-limited
  - processing holders are not nudged
  - missing holders mark the baton orphaned and notify the originator

### T06 — HTTP API and CLI inspection

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - `GET /batons`
  - `GET /batons/{id}`
  - `GET /batons/{id}/events`
  - operator recovery routes for cancel/reassign
  - `cao baton list/show/log/cancel/reassign`
  - API and CLI tests
- acceptance:
  - operators can inspect active batons and their event history
  - recovery actions are available without exposing them as normal agent tools
  - output includes current holder, originator, status, return chain, and last movement

### T07 — Dashboard visibility

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T06]
- deliverables:
  - web API client methods for baton listing/details
  - store state for active batons by current holder
  - terminal row/card baton indicator
  - read-only baton detail panel or popover
  - component tests
- acceptance:
  - dashboard shows which terminal currently holds each active baton
  - baton UI is visually distinct from the monitoring indicator
  - detail view shows return chain, expected next action, and recent events
  - UI remains useful when a terminal holds more than one active baton

### T08 — Agent profile and protocol docs

- owner_role: documenter
- dispatch_mode: handoff
- depends_on: [T04]
- deliverables:
  - supervisor protocol update explaining baton vs assign vs handoff
  - worker protocol update explaining holder responsibilities
  - reviewer/implementer prompt snippets for review-loop baton passing
  - README or docs update with a minimal example
- acceptance:
  - agents are instructed to use transfer tools instead of separate `send_message`
  - docs explicitly describe current-holder responsibility and return-stack behavior
  - examples cover implementer-to-reviewer-to-implementer flow

### T09 — End-to-end baton workflow smoke test

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T04, T05, T08]
- deliverables:
  - opt-in or mocked E2E that exercises create -> pass -> return -> complete
  - proof that originator receives completion message
  - proof that idle nudges are emitted under controlled timing
- acceptance:
  - smoke test demonstrates the intended async review loop
  - default test suite remains offline and fast
  - online/billable provider execution, if added, is explicitly opt-in

## MVP cut

The smallest useful slice is T01 through T05 plus enough of T08 to make agents
use the tools correctly. T06 and T07 make the feature pleasant and observable
for operators. T09 proves the model after the pieces exist.
