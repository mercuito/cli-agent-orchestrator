# CAO Plan→Tasks→Orchestrate Workflow (Draft v1)

Status: draft (intentionally experimental)

This document proposes a document-driven workflow that uses CLI Agent Orchestrator (CAO) as the execution substrate:
- humans + “planner” produce a plan (`*.plan.md`)
- tasks are derived (`*.tasks.md` + `tasks/Txx*.task.md`)
- an orchestrator dispatches worker agents via CAO (MCP tools)
- a reviewer gates code-changing steps

The goal is to make this workflow runnable on demand (and diagnosable) while still allowing rapid iteration on the doc format.

---

## Goals

- Make a repeatable end-to-end workflow for: brainstorm → plan → tasks → dispatch → review → merge artifacts.
- Treat “worker pool” as **agent profiles + metadata** (provider/model/reasoning/prompt), not hardcoded roles.
- Allow orchestrator to spawn **cross-provider** workers (e.g., Codex orchestrator dispatches Claude Code reviewer).
- Keep the default unit test suite free/fast; provide opt-in E2E/diagnostics when needed.
- Ensure spawned CLIs are “ready to go” without interactive setup (inherit auth + known-good global config where possible; fail fast and report if user action is required).

## Non-goals (v1)

- A fully productized “workflow engine” inside CAO (no large new scheduling/state machine beyond existing CAO).
- Perfectly stable plan/tasks schema (expect iteration).
- Automatic parsing of arbitrary prose plans into tasks without guidance (planner prompt + templates guide this).

---

## Repository Layout

### Where workflow artifacts live (per-project / per-run)

Primary: `work/plans/<plan-name>/`

Contains:
- `<plan-name>.plan.md`
- `<plan-name>.tasks.md`
- `workers.yml` (optional; see “Worker Pool” section)
- `tasks/Txx-<slug>.task.md`
- `reviews/Rxx-Txx-<slug>.review.md`
- `artifacts/` (worker outputs, logs, diffs, summaries)

Rationale: keeps experimental artifacts out of the repo root and reduces merge noise.

### Where the workflow spec lives (this doc)

This spec lives under `plans/` so it’s visible and reviewable, but doesn’t imply we’re committing any particular plan/task instances yet.

---

## Document Types (Draft Formats)

### 1) `<plan-name>.plan.md` (decision memory)

Keep the plan primarily constraint- and interface-focused:
- Goal / non-goals
- constraints (security, time, compatibility, “don’t touch X”)
- interfaces / invariants
- acceptance criteria
- risks / unknowns and de-risking steps
- milestones (high-level)

Avoid step-by-step implementation instructions here (those belong in tasks).

### 2) `<plan-name>.tasks.md` (execution backlog)

Task index with IDs and dependencies. Each task points to a task spec file.

Recommended fields per task entry:
- `task_id` (T01, T02…)
- `owner_role` (developer/reviewer/documenter/…)
- `dispatch_mode` (`handoff` for blocking, `assign` for parallel)
- `depends_on`
- `deliverables` (expected file paths)
- `requires_review` (or implicit policy: all code-changing tasks require review)

### 3) `tasks/Txx-*.task.md` (task spec; YAML frontmatter + body)

Frontmatter (minimum):
```yaml
id: T01
title: "Implement X"
owner_role: developer
dispatch_mode: handoff
depends_on: []
requires_review: true
deliverables:
  - "src/..."
definition_of_done:
  - "uv run pytest -q"
```

Body:
- the “do this” instructions
- links to plan sections
- constraints / must-not
- artifact expectations (where to write results)
- callback instructions (see “Worker callback envelope”)

### 4) Worker callback envelope (message contract)

Workers should reply to orchestrator via `send_message` using a consistent envelope that’s easy to skim and optionally parse:

```
[CAO][RESULT]
task_id: T01
status: success|blocked|needs-review
deliverables:
  - path: /abs/path/to/file
notes: |
  Summary...
next_steps: |
  ...
[/CAO][RESULT]
```

---

## Worker Pool (Agent Profiles + Metadata)

### Concept

The “pool” is the set of installed agent profiles, enhanced to include enough metadata to route tasks:
- which provider should be used (codex/claude_code/q_cli/kiro_cli)
- what role(s) the profile is suited for
- optional tags for specialization

Model/reasoning/prompt should remain in the agent profile itself (existing fields) so the “pool” stays stable across projects. Provider-specific “startup readiness” knobs can also live in the profile (e.g., Codex `codexConfig`, MCP server expectations, trust level).

### Agent profile metadata additions (minimal v1)

Add to agent profile YAML frontmatter:
- `provider: codex|claude_code|q_cli|kiro_cli`
- `role: orchestrator|developer|reviewer|documenter|...`
- `tags: [python, frontend, security, ...]` (optional)

Provider-specific config:
- Codex: continue using `codexConfig` for things like `model_reasoning_effort`
- All: continue using `model` where supported

Optional (recommended) “startup readiness” fields:
- `mcpServers`: list of MCP servers the worker expects configured (or expects CAO to provision)
- `trust`: list of working directories (or patterns) that should be pre-trusted for non-interactive startup

### Discoverability requirement

The orchestrator should be able to list profiles + metadata without filesystem spelunking.

Add `cao-mcp-server` tools:
- `list_agent_profiles()` → list installed + built-in profiles with `{name, description, provider, role, tags}`
- `get_agent_profile(name)` → return full profile metadata (and optionally system prompt content)

---

## Orchestrator Behavior (v1)

Policy: dispatch-only for code.

Responsibilities:
1) Read `*.plan.md` and derive/update `*.tasks.md`.
2) Materialize each task into `tasks/Txx*.task.md` before dispatch.
3) Choose workers by reasoning over `list_agent_profiles()` results:
   - match `role` first
   - then match `tags` if specified by task or plan
   - then prefer same provider unless task explicitly wants a different provider
4) Dispatch:
   - `handoff` for sequential tasks with “must return output”
   - `assign` for parallel tasks; require callbacks to orchestrator’s `CAO_TERMINAL_ID`
5) Review gate:
   - for any task that changes code: dispatch reviewer after developer completes
   - if reviewer requests changes: create follow-up task spec and re-dispatch developer
6) Cleanup:
   - ensure worker terminals are exited/killed once their contribution is captured

---

## CAO / MCP Prerequisites (Implementation Work)

This section is intentionally short. The detailed backlog/roadmap for enabling yard/IRPT-style orchestration in CAO lives in:
- `plans/irpt-cao-roadmap.md`
- `plans/irpt-cao-roadmap.tasks.md`

---

## Testing & Diagnostics

### Unit tests (default suite)

- `list_agent_profiles/get_agent_profile` tool behavior (mock FS and built-in store)
- `assign/handoff` provider override wiring (API call params)
- `exit_terminal/get_terminal/get_last_output` tool wiring

### Opt-in E2E

- Add an E2E that runs the orchestrator minimally in a real tmux session (offline mode by default).
- Online/billable mode requires an explicit flag, similar to `cao diagnostics --mode online --allow-billing`.

---

## Open Questions (to resolve during implementation)

- Should `workers.yml` exist at all in v1 if profiles become the pool?
  - Option A: no `workers.yml` (orchestrator chooses from profiles dynamically)
  - Option B: keep `workers.yml` only for project-specific preferences (e.g., “prefer codex_developer over q_cli_developer”)
- How much profile content should `get_agent_profile` return by default?
  - likely: metadata only by default, with an explicit `include_prompt=true` to fetch system prompt content.
