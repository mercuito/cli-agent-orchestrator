# CAO Agent Model Cleanup Tasks (Draft v1)

This task list derives from `plans/agent-model-cleanup.md`.

Policy: any task that changes code requires reviewer gate before it is
considered complete. The cutover (T07) is atomic — its deliverables land
together or not at all.

Every task includes a criteria-catalog acceptance bullet. Before completion,
the implementer walks the catalog at `docs/criteria/implementation/` and
`docs/criteria/tests/` (browseable via `python scripts/catalog_criteria.py`),
identifies every entry whose `when` clause applies to the task's changes,
and confirms the landed code satisfies it. This is not a one-time sweep at
the end of the plan — it runs per task, against that task's diff.

This is hard-cutover work. The `do-not-assume-backwards-compatibility`
criterion applies to every task. Specifically forbidden: shims, facades,
fallback chains, feature flags, deprecation warnings, function/module
aliases preserving old import paths, optional fields preserving old
defaults, and runtime translators between old and new shapes. There are no
carve-outs. Legacy call sites are migrated to the new shape or deleted,
never bridged. If a task's natural implementation seems to require any of
the forbidden patterns, raise back to the operator rather than improvising.

## Phase 1 — New model and tooling (parallel, no behavior change)

### T01 — Agent data model and file format spec

- owner_role: developer
- dispatch_mode: handoff
- depends_on: []
- deliverables:
  - `Agent` dataclass capturing the unified config: workdir, session_name,
    cli_provider, display_name, model, mcp_servers, tools allowlist, skills,
    reasoning_effort, plus optional `[linear]` sub-section (presence bindings
    and tool access policy) and any other provider sub-sections required by
    current code
  - written specification of the on-disk shape: `agents/<id>/agent.toml`
    fields, types, required vs optional; `agents/<id>/prompt.md` content
    rules; permission expectations (0600 for `agent.toml`, 0644 for
    `prompt.md`)
  - unit tests for the dataclass and its frozen/equality semantics
- acceptance:
  - the spec covers every field present in today's `AgentProfile`,
    `AgentIdentity`, and `LinearPresence` plus Linear `[tool_access]`
  - the spec explicitly enumerates which fields are required vs optional
  - the model rejects invalid combinations at construction time
    (e.g. workspace_context.enabled true without resolver_id)
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T02 — Directory loader

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T01]
- deliverables:
  - `load_agent(agent_id)` and `load_all_agents()` functions reading from
    `~/.aws/cli-agent-orchestrator/agents/<id>/`
  - parses `agent.toml`, reads `prompt.md`, assembles into the `Agent`
    dataclass
  - clear error types for missing dir, missing files, unparseable TOML,
    missing required fields
  - unit tests covering happy path, missing files, malformed TOML, edge
    cases (empty prompt, optional fields absent)
- acceptance:
  - given a synthetic agent directory, `load_agent` returns a fully populated
    `Agent` value
  - errors include the agent id and file path for diagnosis
  - reading two agents that share field names (e.g. two `[linear]` sections)
    produces independent `Agent` values with no shared state
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T03 — Directory writer with in-place TOML patching

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T02]
- deliverables:
  - `write_agent(agent)` that creates `agents/<id>/agent.toml` and
    `agents/<id>/prompt.md` atomically with correct permissions
  - `patch_agent_section(agent_id, section, values)` that updates specific
    keys within a named TOML section without rewriting the rest of the file
    — preserves comments, ordering, and unrelated keys (port the existing
    `_patch_toml_section_values` logic from
    `src/cli_agent_orchestrator/linear/workspace_provider.py`)
  - unit tests including round-trip (write → load → equal), patch with
    preserved formatting, atomic-write crash safety
- acceptance:
  - writing an agent then loading it produces an equivalent `Agent` value
  - patching one key in `[linear]` does not disturb `[linear.tool_access]`
    or any other section
  - the OAuth callback writer's expected usage pattern (patching
    access_token, refresh_token, app_user_id, token_expires_at) is exercised
    by a test
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T04 — Validation

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T03]
- deliverables:
  - validation pass over an agent dir: required fields present, types
    correct, Linear `[tool_access]` references only fields that exist in
    `LINEAR_PROVIDER_TOOLS` and `UPDATE_ISSUE_FIELDS`, agent_id matches
    directory name, `prompt.md` exists and is non-empty, `agent.toml`
    has 0600 permissions, `prompt.md` has 0644 permissions
  - exposed as a CLI subcommand or callable function the developer can
    run against `~/.aws/cli-agent-orchestrator/agents/` to verify the
    hand-performed migration before the T05 landing
  - clear error messages identifying the offending agent, file, and field
  - unit tests covering happy path and each failure mode
- acceptance:
  - given a hand-written agent directory matching the spec, validation
    passes silently with exit code 0
  - given a directory missing a required field, validation produces an
    error naming the agent id, file path, and missing field
  - given a Linear `[tool_access]` entry with an unknown tool name, the
    error names the unknown tool
  - given a file with wrong permissions, validation flags it
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

---

## Phase 2 — Read-path cutover (atomic)

### T05 — Rename agent manager/registry and swap API readers

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T04]
- deliverables:
  - `AgentIdentityManager` renamed to `AgentManager`, rewritten to read
    from the new agent directory shape; all references in the codebase
    updated
  - `AgentIdentityRegistry` renamed to `AgentRegistry`, rewritten as a
    dumb lookup table backed by the new loader; all references updated
  - module file `src/cli_agent_orchestrator/agent_identity.py` renamed to
    `agent.py` (or split into smaller modules if cleaner)
  - HTTP endpoints renamed: `/agents/identities` → `/agents`,
    `/agents/identities/{id}` → `/agents/{id}`,
    `/agents/identities/{id}/timeline` → `/agents/{id}/timeline`,
    `/agents/identities/{id}/events/{event_id}/related` →
    `/agents/{id}/events/{event_id}/related`. The old paths are removed,
    not aliased.
  - response models renamed (`AgentIdentityStatusResponse` →
    `AgentStatusResponse`, `AgentIdentityTimelineResponse` →
    `AgentTimelineResponse`, and similar) and extended to expose the full
    agent config (workdir, session_name, provider, Linear binding
    presence flags, tool access summary) — the previous responses missed
    workdir/session_name/workspace_context entirely
  - no `AgentIdentity*` class or symbol names and no `/agents/identities*`
    paths remain in code introduced or modified by this task
  - updated tests covering the renamed agent API endpoints
- acceptance:
  - prior to landing: developer has performed a one-shot manual migration
    of `agents.toml` + `linear.toml` + `agent_store/` references into
    `~/.aws/cli-agent-orchestrator/agents/<id>/` per the plan's Migration
    shape section, and T04 validation passes against the result
  - the `/agents/{id}` endpoint returns every field present in the
    agent's `agent.toml`
  - the Agents tab in the web UI continues to render the agent roster
    correctly (no UI label changes yet — read-path swap only; T14 owns
    the UI text renames)
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T06 — Migrate Linear provider to read presence and tool_access from agent dirs

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T05]
- deliverables:
  - `LinearWorkspaceProvider` rewritten to source presence bindings and
    tool access policies from each agent's `agent.toml [linear]` section
    instead of `linear.toml`
  - Linear OAuth callback writer updated to call `patch_agent_section`
    against the correct agent directory instead of `linear.toml`
  - `LinearPresence` / `LinearToolAccess` dataclasses kept as in-memory
    types but loaded from the new shape
  - `_load_structured_linear_config` and related TOML readers retired
  - tests covering OAuth token persistence under the new shape
- acceptance:
  - Linear OAuth callback writes tokens into the correct agent's
    `agent.toml [linear]` section
  - validation still cross-checks `agent_id` ↔ presence uniqueness and
    catches duplicate `app_user_id` / `app_user_name` / `oauth_state`
  - tool access policies are resolved per agent without `agent_profile`
    targeting
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T07 — Delete old subsystem (atomic)

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T05, T06]
- deliverables:
  - delete `src/cli_agent_orchestrator/models/agent_profile.py`,
    `src/cli_agent_orchestrator/utils/agent_profiles.py`, and all imports
  - delete the `/agents/profiles` and `/agents/providers` endpoints (the
    latter only if no remaining caller — check first)
  - delete multi-source template discovery plumbing in
    `services/settings_service.py` (`get_agent_dirs`,
    `get_extra_agent_dirs`, related setting keys), and the
    `/settings/agent-dirs` endpoints
  - delete Linear `legacy_env` code path:
    `_legacy_identity_for_presence`, `_legacy_configured_app_keys`,
    `_load_legacy_linear_config`, `has_legacy_linear_provider_config`,
    every `LINEAR_DISCOVERY_*` env var lookup, the `config.source ==
    "legacy_env"` branches
  - delete `~/.aws/cli-agent-orchestrator/agents.toml`,
    `~/.aws/cli-agent-orchestrator/workspace-providers/linear.toml`,
    `~/.aws/cli-agent-orchestrator/agent-store/` on the developer machine
  - test suite passes with all old code removed
- acceptance:
  - `grep -rn "AgentProfile\|agent_profiles\|legacy_env\|LINEAR_DISCOVERY\|AgentIdentity"
    src/` returns no hits — no "identity" class or module vocabulary
    survives (the lowercase `agent_identity_id` column rename happens at
    T08)
  - the running CAO process starts cleanly with only the new agent
    directories present on disk
  - all existing tests pass or are deleted as obsolete (no skipped tests
    for "old shape")
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

---

## Phase 3 — Spawn lockdown

### T08 — Terminal model migration

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T07]
- deliverables:
  - DB migration: rename `terminals.agent_identity_id` → `terminals.agent_id`,
    make NOT NULL, drop `terminals.agent_profile` column
  - the migration refuses to run if any existing row has
    `agent_identity_id IS NULL` — surfaces a clear list of offending rows
    so they can be cleaned up first (these are anonymous-spawn terminals
    that should be deleted before the schema change)
  - `Terminal` model and all references updated to use `agent_id`
  - tests covering migration up-path and the NOT NULL constraint
- acceptance:
  - on a developer database, the migration completes cleanly after
    anonymous-spawn rows are removed
  - schema enforces NOT NULL on `agent_id`
  - all read sites (services, API, web) use `agent_id`
  - `grep -rn "agent_identity_id\|agent_identity" src/ web/src/` returns
    no hits (column, ORM attribute, and field-level rename complete)
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T09 — Spawn API requires agent_id; enforce ≤1 instance

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T08]
- deliverables:
  - reshape `POST /sessions` and `POST /sessions/{name}/terminals` (or
    replace with a single new endpoint, e.g. `POST /agents/<id>/start`) so
    the only way to create a terminal is to name an existing agent
  - server rejects spawn when an active instance already exists for that
    agent — returns a structured error pointing to the existing terminal
  - corresponding ≤1 invariant check at the service layer, not only the
    HTTP layer
  - integration tests for: spawn happy path, spawn while live (rejected),
    spawn after stop (allowed)
- acceptance:
  - no anonymous spawn path remains in the HTTP surface
  - a second spawn attempt for the same agent receives a clear error and
    a reference to the live terminal
  - the constraint survives process restart (it's not in-memory only)
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T10 — Agent CRUD HTTP API

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T05]
- deliverables:
  - new endpoints under `/agents/<id>`:
    - `GET /agents` — list
    - `GET /agents/<id>` — show (config + current instance status)
    - `POST /agents` — create (request body: id + initial config; server
      writes the stub directory)
    - `PUT /agents/<id>` or `PATCH /agents/<id>` — update (writes through
      the patch path so unrelated formatting is preserved)
    - `DELETE /agents/<id>` — refuses if instance is live; otherwise
      removes the directory after explicit confirm flag in the request
  - response models cover the full agent config plus current instance
    status
  - validation errors return 400 with field-level detail
- acceptance:
  - end-to-end: create an agent via API, start it, edit a field while
    running (allowed), stop it, delete it
  - delete with live instance is refused with a clear error
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

---

## Phase 4 — New CLI surface

### T11 — `cao agent` command namespace

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T09, T10]
- deliverables:
  - new `cao agent` command group with subcommands `list`, `show`,
    `create`, `edit`, `delete`, `start`, `stop`
  - `start` attaches to the resulting tmux session (matching the existing
    `cao launch` UX); `stop` kills it cleanly
  - `edit` opens `$EDITOR` on the agent's `agent.toml` and validates
    on save (rejecting changes that produce an invalid agent)
  - help text covers each subcommand
  - tests covering each subcommand against a stub backend
- acceptance:
  - `cao agent list` shows the three current agents with their status
  - `cao agent start discovery_partner` opens a working terminal
  - `cao agent create foo` produces a valid stub at
    `~/.aws/cli-agent-orchestrator/agents/foo/`
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T12 — Remove `cao launch`

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T11]
- deliverables:
  - delete `src/cli_agent_orchestrator/cli/commands/launch.py` and the
    `cao launch` registration
  - update README and any docs referencing `cao launch`
- acceptance:
  - `cao launch` returns a "command not found" error
  - no doc, comment, or example references `cao launch`
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

---

## Phase 5 — Web UI rebuild

### T13 — Replace "Spawn Agent" modal with existing-agent picker + create flow

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T10]
- deliverables:
  - "Spawn Agent" button opens a modal that lists existing agents
    (showing live/stopped status) and offers "Start" for stopped agents
  - separate "Create new agent" entry that prompts for id + minimal stub
    fields, then opens the editor
  - removed: on-the-fly profile / provider / workdir prompts
  - "Add Agent to Session" button removed or repurposed (a session is now
    1:1 with an agent's running instance; this control no longer makes
    sense)
- acceptance:
  - clicking "Spawn Agent" never lets the user create a terminal without
    selecting or creating an agent
  - existing live agents cannot be "started" again — the button is
    disabled with a tooltip pointing to the running terminal
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

### T14 — Inline agent config + edit UI in Agents tab

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T10, T13]
- deliverables:
  - right-hand detail panel renders the full `agent.toml` (workdir,
    session_name, provider, model, MCP servers, tools, Linear bindings,
    Linear tool access) plus the current instance status
  - "Edit" toggles fields to editable; Save calls the agent update API
    and re-renders on success
  - Linear secret fields are masked by default with a reveal-on-click;
    OAuth tokens are read-only and labeled as managed by the OAuth
    callback
  - validation errors from the server are surfaced inline against the
    offending fields
  - UI text renamed: "AGENT IDENTITIES (N)" heading → "AGENTS (N)";
    "IDENTITY TIMELINE" heading → "AGENT TIMELINE"; any remaining
    "identity" wording in the panel updated to "agent"
  - component file `AgentIdentityTimelinePanel.tsx` renamed (e.g.
    `AgentDetailPanel.tsx`); imports and references updated
- acceptance:
  - editing `display_name` and saving updates `agent.toml` and the UI
    reflects the change
  - editing prompt/MCP/tools fields (previously locked inside the
    profile markdown) works through the same UI
  - the agent timeline view (formerly "IDENTITY TIMELINE") renders all
    events for the selected agent with no regression from the previous
    implementation, including the related-events expansion behavior
  - `grep -rn "Identity\|identity" web/src/` returns hits only in
    historic file references kept for git history or in comments
    explaining the rename — not in component names, headings, or
    user-visible strings
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code

---

## Phase 6 — Final tidy

### T15 — Move `agent_store/` to `examples/`; documentation pass

- owner_role: developer
- dispatch_mode: handoff
- depends_on: [T07, T12, T14]
- deliverables:
  - `git mv src/cli_agent_orchestrator/agent_store examples/agents` (or
    similar — exact path chosen during the move)
  - examples are no longer packaged with the CAO distribution
  - README updates: new agent concept model, new CLI surface, how to
    bootstrap an agent (including "copy an example into a new directory")
  - CHANGELOG entry covering the cutover with explicit list of removed
    commands, removed env vars, and removed config files
  - search for stragglers: TODO/FIXME referencing the old model, dead
    imports, comments referring to `agent_profile` as a separate concept
- acceptance:
  - the `examples/` directory contains the previously-shipped templates
    as plain markdown
  - README's "getting started" walkthrough uses `cao agent create` and
    `cao agent start`; no references to `cao launch`, `agent_profile`,
    or `agent-store`
  - CHANGELOG entry mentions Linear `legacy_env` removal and points
    affected users at the migration script
  - no backwards-compatibility layer introduced — no shims, facades,
    fallback chains, feature flags, deprecation warnings, aliases, or
    runtime shape translators; legacy call sites are migrated or deleted,
    not bridged
  - criteria catalog applied: every entry in
    `docs/criteria/implementation/` and `docs/criteria/tests/` whose
    `when` clause matches this task's changes has been satisfied by the
    landed code
