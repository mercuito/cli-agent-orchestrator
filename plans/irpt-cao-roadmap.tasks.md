# CAO IRPT/Yards Enablement Roadmap (Tasks v1)

This task list derives from `plans/irpt-cao-roadmap.md`.

Policy: any task that changes code requires reviewer gate before it is considered complete.

## Task index

### T01 — Agent profile metadata (provider/role/tags/reasoning_effort) (DONE)

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - `src/.../models/agent_profile.py` (schema updates)
  - `src/.../utils/agent_profiles.py` (listing/metadata surface)
  - `docs/...` (doc update)
- definition_of_done:
  - unit tests cover backwards-compat loading
  - existing examples still load

### T02 — MCP: list/get agent profiles (DONE)

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - `src/.../mcp_server/...` new tools
  - unit tests for tool outputs

### T03 — Cross-provider dispatch for `assign`/`handoff` (DONE)

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01, T02]
- deliverables:
  - `src/.../mcp_server/...` tool param changes
  - `src/.../services/...` provider override wiring
  - docs updates describing provider selection rules

### T04 — Orchestrator MCP lifecycle + introspection tools

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - `get_terminal(terminal_id)`
  - `exit_terminal(terminal_id)`
  - `get_terminal_output(terminal_id, mode=full|last)`
  - optional: `list_terminals(session_name?)`
  - unit tests for tool wiring

### T05 — MCP inbox receive tools (callbacks)

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T04]
- deliverables:
  - `list_inbox_messages(terminal_id, status?, limit?)`
  - optional: `wait_for_inbox_message(terminal_id, ...)`
  - unit tests for tool wiring

### T06 — Reference orchestrator/developer/reviewer profiles + templates

- owner_role: documenter
- dispatch_mode: handoff
- depends_on: [T01, T02, T03, T04, T05]
- deliverables:
  - `examples/...` reference profiles
  - `plans/...` templates for `*.plan.md`, `*.tasks.md`, `tasks/Txx*.task.md`

### T07 — Per-worker persistence conventions (agent dir + worktree docs)

- owner_role: documenter
- dispatch_mode: handoff
- depends_on: [T06]
- deliverables:
  - docs for `~/.aws/cli-agent-orchestrator/worktrees/...` conventions
  - branch strategy explanation (worktree ≠ merge; commits must be merged/cherry-picked)
  - recommended artifact/worklog directory conventions per task/worker

### T08 — Opt-in E2E / diagnostics for orchestrator workflow

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T03, T04, T05, T06]
- deliverables:
  - opt-in E2E runner (offline default; online requires explicit allow-billing)
  - docs explaining how to run the check
