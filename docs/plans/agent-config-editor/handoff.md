# Handoff: Agent Config Editor

## Goal

Execute the Agent Config Editor plan end to end as specified in
`docs/plans/agent-config-editor/plan.md` and
`docs/plans/agent-config-editor/tasks.md`. Land the work in dependency
order across the four phases. Each task lands as its own commit (or
PR), gated by reviewer, with the criteria-catalog acceptance bullet
satisfied against the task's diff.

The plan replaces raw-TOML editing for five commonly-edited agent
config fields (`display_name`, `description`, `cli_provider`, `model`,
`reasoning_effort`) with proper form controls, while keeping raw TOML
available as a collapsible escape hatch for unstructured fields
(including `workdir` and `session_name`, which are shown read-only in
the header but remain editable via raw TOML). The form's dropdowns are backed by a restored
`GET /providers` endpoint that exposes per-provider capability
declarations.

The `id` field is never editable through the dashboard. The raw TOML
section filters it out so users never type a change that would fail
save.

## Sources of truth (read these first)

- `docs/plans/agent-config-editor/plan.md` — locked design, field set,
  provider capability surface, validation model, panel layout,
  forbidden compatibility patterns, criteria catalog, phasing.
- `docs/plans/agent-config-editor/tasks.md` — 7 tasks with
  deliverables and acceptance criteria.
- `docs/criteria/implementation/` and `docs/criteria/tests/` — the
  criteria catalog. Run `uv run python scripts/catalog_criteria.py`
  to browse. Every task has a criteria-catalog acceptance bullet;
  apply every entry whose `when` clause matches the task's diff.
- The plan's "Criteria catalog (likely applicable)" section lists
  criteria identified at planning time — start there, but the
  implementer must run the catalog against the actual diff to
  confirm the final applicable set.

## Per-task workflow

Use the `coding-discipline` skill (in `.claude/skills/coding-discipline/`)
for each task. Before completing each task, invoke the skill via the
`Skill` tool (`Skill(skill="coding-discipline")`) and walk its
workflow against the task's diff.

For each of T01–T07 in order:

1. Read the task's deliverables and acceptance criteria in `tasks.md`.
2. Implement the deliverables.
3. Run the relevant test suite (`pytest` for backend, `npm test` /
   `vitest` for web).
4. Invoke the coding-discipline skill against the diff.
5. Commit with a message starting `T0N: <short description>` per the
   existing pattern.

## Operating principles

- **Phase 1 (T01–T03) is parallelizable** by task — each has clear
  boundaries (capability surface, endpoint, validation). **Phase 2
  (T04)** depends on T02. **Phase 3 (T05, T06)** depends on T03 and
  T04 and lands sequentially within the phase. **Phase 4 (T07)** is
  the final cleanup.
- **Hard cutover, no compatibility layers.** Forbidden: hardcoded
  provider lists in the dashboard, hardcoded `reasoning_effort`
  enums in the dashboard, duplicate provider enumeration in the
  backend, optional props falling back to old behavior, feature
  flags toggling between raw-only and structured-and-raw layouts.
  No carve-outs. If a task's natural implementation seems to require
  a compatibility layer, raise back.
- **Authoritative sources only.** `ProviderType` enum is the single
  source for provider names. Per-provider classmethods are the
  single source for reasoning_effort sets and suggested models. The
  dashboard imports nothing literal; it fetches from `/providers`.
- **`id` is never editable.** It does not appear in the structured
  form. The raw TOML section filters it out of the textarea content
  in edit mode.
- **Schema loading is blocking, not racing.** The form renders a
  loading state until the schema fetcher resolves. It does not
  render with empty dropdowns and "hydrate later" — that pattern is
  fragile and confusing.
- **Save is one round trip.** Edit mode covers structured fields,
  prompt, and (when expanded) raw TOML simultaneously. Save merges
  them into one `PUT /agents/{id}`.
- **Validation lives at the dataclass / service layer**, not only at
  the HTTP boundary. Direct calls to the agent writer cannot bypass
  it.
- **Reviewer gate per task.** No task is complete without reviewer
  approval.
- **Criteria catalog per task, not at the end.** Walk the catalog
  for each task's diff before marking it complete.

## What is explicitly out of scope

If you encounter these, flag them but do not address them in this
work:

- Structured editing for any Tier 2/3 fields (lists of strings,
  `mcp_servers`, the Linear `[linear]` block beyond the existing
  secrets summary, hooks, codex_config, workspace_context).
- A model registry or per-provider model validation. `model` stays
  as soft-suggested combobox.
- Rename support for `id`.
- Reorganizing the agent dataclass or changing the on-disk file
  shape.
- Changes to the Spawn Agent modal or the Create New Agent flow
  beyond consuming the new schema fetcher if convenient.
- Changes to the Timeline tab or any other Agents-tab UI surface
  outside `AgentConfigTab`.

## Definition of done

This work is done when **every item below is true**. Verify each one
explicitly; do not infer.

### Backend

- Each provider class declares `supported_reasoning_efforts()` and
  `suggested_models()` (or inherits the default None from the
  base).
- `claude_code` returns `("low", "medium", "high")` for
  `supported_reasoning_efforts`, matching what
  `claude_code.py:355` passes via `--effort`.
- `GET /providers` exists and returns one entry per `ProviderType`
  value with the fields named in the plan.
- `PUT /agents/{id}` returns 400 with field-level detail when
  `cli_provider` is not a `ProviderType` value, when
  `reasoning_effort` is set on a non-supporting provider, or when
  `reasoning_effort` is set to a value outside the provider's
  supported set.
- Validation cannot be bypassed by calling the service or dataclass
  layer directly.

### Frontend

- The Agents tab Config view shows five structured input fields
  above a collapsible raw-TOML disclosure, with `id`,
  `session_name`, and `workdir` shown read-only in the panel header
  (via the existing AgentDetailPanel header).
- Dropdown options for `cli_provider` and `reasoning_effort` come
  from `GET /providers` — `grep -rn "claude_code\|codex\|gemini_cli"
  web/src/components/agents-tab/` returns no hits inside option
  arrays, switch statements, or literal-string dropdowns.
- `reasoning_effort` is rendered disabled with an explanatory
  tooltip (NOT hidden) when the selected provider returns null for
  `supported_reasoning_efforts`.
- Save sends the merged structured + raw + prompt content to
  `PUT /agents/{id}`. Inline errors surface against the offending
  input on 400 responses.
- The `id` field never appears in the editable structured form and
  is stripped from the raw textarea contents in edit mode.
- The raw textarea also strips the five structured-form keys so
  users cannot double-edit them. `workdir` and `session_name`
  REMAIN in the raw textarea as the escape hatch.

### Tests

- The full backend test suite passes (`pytest` or the project's
  configured invocation).
- The full web test suite passes (`npm test` / `vitest`).
- Tests cover: provider capability declarations, `GET /providers`
  response shape, save-time validation rejection paths, schema
  fetcher caching, structured form rendering and edit mode,
  reasoning_effort visibility tied to provider capability, save
  merge correctness, inline error surfacing.

### Process

- All 7 tasks have landed commits referencing the task id (`T0N:
  ...`).
- Each commit passed the reviewer gate.
- Per-task criteria-catalog acceptance was applied — applicable
  criteria recorded in the task's PR description or commit message,
  not only in the task spec.

## When to escalate back to the operator

Raise back rather than improvise if:

- A criterion in the catalog seems to conflict with the plan's
  locked design.
- A task's natural implementation seems to require any of the
  forbidden compatibility patterns.
- The provider capability surface design needs to change (e.g. a
  provider has a complex schema that doesn't fit a flat
  `tuple[str, ...] | None` shape).
- Scope-expanding pressure arises (e.g. "should this also add
  structured editing for tools?" — answer is no, but flag it).
- A `reasoning_effort` value that the dashboard would send doesn't
  match what the launch path expects — that would mean the
  provider capability and the launch path are out of sync, which
  is its own bug.
- Tests reveal a behavior the plan didn't anticipate.
