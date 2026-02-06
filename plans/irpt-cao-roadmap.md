# CAO IRPT/Yards Enablement Roadmap (Draft v1)

Status: draft

This roadmap tracks the CAO functionality needed to run a yard/IRPT-style multi-agent workflow the way we want:
- IRPT is document-driven (`*.plan.md` → `*.tasks.md` → `tasks/Txx*.task.md`)
- an orchestrator dispatches subagents (workers) by **agent profile**
- the worker pool is **profiles + metadata** (provider/model/reasoning/system prompt, etc.)
- reviewers gate code-changing work
- providers start “ready” (no interactive login/trust prompts in managed terminals)

## Goals

- Enable cross-provider dispatch: orchestrator can launch workers on different providers based on agent profile metadata.
- Enable profile discovery: orchestrator can list/get available agent profiles (metadata-first; optionally include prompt body).
- Enable deterministic worker cleanup: orchestrator can exit/kill worker terminals via MCP tooling.
- Make failures diagnosable: when a provider needs user interaction (login/config), fail fast with an actionable message.
- Enable per-worker isolation and persistence: workers can write worklogs/artifacts to stable per-run directories, and can use isolated git worktrees when needed.

## Non-goals (v1)

- A full workflow engine/state machine embedded in CAO.
- Automatically converting arbitrary prose into correct tasks with no templates/prompts.
- A “perfect” plan/tasks schema (expect iteration).

## Decisions (locked in)

- Modify the existing agent profile schema/model (no subclassing).
- `reasoning_effort` is one canonical field in the profile; each provider translates (or ignores).
- Worker pool selection uses profile metadata (`provider`, `role`, `tags`) + system prompt content.
- Work isolation defaults to **git worktree per worker** (created via `git` directly; not an MCP worktree tool).
- Worktrees live under CAO home by default (e.g. `~/.aws/cli-agent-orchestrator/worktrees/...`).

## Constraints

- Backwards compatible agent profiles: existing profiles without metadata must still load and run.
- Default test suite stays offline and free; online/billable E2E is opt-in behind explicit flags.
- Orchestrator is dispatch-only for code changes (no direct edits); developer/reviewer do the work.

## Current State (high level)

Already implemented in CAO:
- Per-terminal `CODEX_HOME` provisioning for Codex provider (isolated config + MCP servers + AGENTS.md).
- Provider diagnostics runner (`cao diagnostics`) with an opt-in Codex E2E.
- `cao-mcp-server` has agent profile discovery tools:
  - `list_agent_profiles()`
  - `get_agent_profile(agent_name, include_prompt=false)`

## Success criteria

- `cao-mcp-server` exposes tools:
  - list profiles + metadata
  - get a profile by name
  - assign/handoff a worker with an explicit provider (or inferred from the profile)
  - exit a worker terminal by terminal id
- A reference orchestrator prompt can:
  - pick a worker based on role/provider/tags
  - dispatch a task
  - receive a callback and proceed
- A runtime diagnostic or opt-in E2E can validate that providers start “ready” (no interactive login prompts) and that status detection works.

## Risks & mitigations

- **Providers/CLIs change output formats frequently.**
  - Mitigation: keep parsing tolerant; add opt-in diagnostics/E2E that can be run on demand after CLI updates.
- **Workers may hang waiting for user intervention (auth, trust prompts).**
  - Mitigation: explicitly provision trust/config (when safe), detect “needs user input” states, and surface a clear error.

## Roadmap (backlog overview)

See `plans/irpt-cao-roadmap.tasks.md` for the task breakdown and acceptance criteria.

High-level remaining items:
- Enhance agent profile schema with `provider`, `role`, `tags`, `reasoning_effort`.
- Cross-provider spawning support in `assign/handoff` based on profile metadata.
- Orchestrator-grade MCP tools to manage workers and inspect output/status (wrappers around existing HTTP endpoints).
- MCP inbox “receive” tooling (list messages / wait-for message patterns).
- Per-worker persistence conventions (artifact/worklog directory) + documentation for worktree + branch strategy.

## Open questions

- Should `get_agent_profile()` return system prompt text by default, or require `include_prompt=true`?
- Do we want a project-level “preferred workers” file (like `workers.yml`) or rely purely on profile metadata + tags?
