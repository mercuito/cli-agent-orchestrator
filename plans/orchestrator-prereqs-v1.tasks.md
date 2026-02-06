# Orchestrator Subagents via CAO (Prereqs Tasks v1)

This task list derives from `plans/orchestrator-prereqs-v1.plan.md`.

Policy: any task that changes code requires reviewer gate before it is considered complete.

## Task index

### T01 — Agent profile metadata (provider/role/tags)

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - `src/.../agent_profiles...` (schema/loader updates)
  - `docs/...` (doc update)
- definition_of_done:
  - unit tests cover backwards-compat loading
  - existing examples still load

### T02 — MCP: list/get agent profiles

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - `src/.../mcp_server/...` new tools
  - unit tests for tool outputs

### T03 — Cross-provider dispatch for `assign`/`handoff`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01, T02]
- deliverables:
  - `src/.../mcp_server/...` tool param changes
  - `src/.../services/...` provider override wiring
  - docs updates describing provider selection rules

### T04 — Worker lifecycle MCP tools

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - `exit_terminal(terminal_id)`
  - `get_terminal(terminal_id)`
  - optional: `get_last_output(terminal_id)`
  - unit tests for tool wiring

### T05 — Reference orchestrator/developer/reviewer profiles + templates

- owner_role: documenter
- dispatch_mode: handoff
- depends_on: [T01, T02, T03, T04]
- deliverables:
  - `examples/...` reference profiles
  - `plans/...` templates for `*.plan.md`, `*.tasks.md`, `tasks/Txx*.task.md`

### T06 — Opt-in E2E / diagnostics for orchestrator workflow

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T03, T04, T05]
- deliverables:
  - opt-in E2E runner (offline default; online requires explicit allow-billing)
  - docs explaining how to run the check

