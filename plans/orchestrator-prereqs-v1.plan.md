# Orchestrator Subagents via CAO (Prereqs Plan v1)

Status: draft

This plan covers the prerequisite work needed to support an “orchestrator agent” workflow where:
- a plan doc (`*.plan.md`) and tasks doc (`*.tasks.md`) are created
- an orchestrator reads tasks and dispatches subagents via CAO
- a reviewer gates code-changing work
- the worker pool is a set of installed agent profiles with metadata (provider/model/reasoning/prompt/etc)

## Goals

- Enable cross-provider dispatch: orchestrator can launch workers on different providers based on agent profile metadata.
- Enable profile discovery: orchestrator can list/get available agent profiles (metadata-first; optionally include prompt body).
- Enable deterministic worker cleanup: orchestrator can exit/kill worker terminals via MCP tooling.
- Make failures diagnosable: when a provider needs user interaction (login/config), fail fast with an actionable message.

## Non-goals (v1)

- A full workflow engine/state machine embedded in CAO.
- Automatically converting arbitrary prose into correct tasks with no templates/prompts.
- A “perfect” plan/tasks schema (expect iteration).

## Constraints

- Backwards compatible agent profiles: existing profiles without metadata must still load and run.
- Default test suite stays offline and free; online/billable E2E is opt-in behind explicit flags.
- Orchestrator is dispatch-only for code changes (no direct edits); developer/reviewer do the work.

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

## Open questions

- Should `get_agent_profile()` return system prompt text by default, or require `include_prompt=true`?
- Do we want a project-level “preferred workers” file (like `workers.yml`) or rely purely on profile metadata + tags?

