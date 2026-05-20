# Handoff: CAO Agent Model Cleanup

## Goal

Execute the CAO agent model cleanup end to end as specified in
`docs/plans/agent-model-cleanup/plan.md` and
`docs/plans/agent-model-cleanup/tasks.md`. Land the work in dependency order
across the six phases. Each task lands as its own commit (or PR), gated by
reviewer, with the criteria-catalog acceptance bullet satisfied against the
task's diff.

Do not deviate from the plan's locked design (two-layer model, directory
shape, dropped templates, `cao agent <subcmd>` CLI, hard cutover) without
raising the change back to the operator first.

## Sources of truth (read these first)

- `docs/plans/agent-model-cleanup/plan.md` — locked design, migration shape,
  goals, non-goals, phasing overview.
- `docs/plans/agent-model-cleanup/tasks.md` — 15 tasks with deliverables,
  acceptance criteria, and dependency edges.
- `docs/criteria/implementation/` and `docs/criteria/tests/` — the criteria
  catalog. Run `python scripts/catalog_criteria.py` to browse. Every task
  has a criteria-catalog acceptance bullet; apply every entry whose `when`
  clause matches the task's diff.

## Operating principles

- **Phase 1 is parallel-safe** (T01–T04 add new code without touching
  runtime). **T07 is atomic** — its deliverables land together or not at
  all. **Phases 3–6 are sequential** by their dependency edges.
- **Hard cutover, no deprecation, no compatibility layers.** Do not keep
  legacy code paths "for safety." Specifically forbidden: shims, facades,
  fallback chains, feature flags, deprecation warnings, function/module
  aliases preserving old import paths, optional fields preserving old
  defaults, and runtime translators between old and new shapes. No
  carve-outs. The `legacy_env` Linear path, `cao launch` verb,
  `agent_profile`-as-identity pattern, and anonymous spawn endpoints all
  get removed in the same landing that introduces their replacements.
  Legacy call sites are migrated to the new shape or deleted, never
  bridged. If a task's natural implementation seems to require a
  compatibility layer, raise back to the operator rather than improvising.
- **No automated migration script.** The agent roster is small enough
  that the developer performs a one-shot manual migration of their own
  config (per the plan's "Migration shape" section) before T05 lands.
  T04's validator verifies the result. Do not build a script.
- **No anonymous terminals.** After T09, there must be no code path that
  creates a `terminals` row without an `agent_id`.
- **≤1 instance per agent.** The constraint is enforced at the service
  layer and survives process restart.
- **OAuth tokens must keep working through the cutover.** T06 ports the
  callback writer to the new file location; verify with a real OAuth round
  trip, not only unit tests.
- **Criteria catalog per task, not at the end.** Walk the catalog for each
  task's diff before marking it complete. If a criterion is genuinely N/A
  for a given task, that's fine — the bullet asks for applicable criteria,
  not all of them.
- **Reviewer gate per task.** No task is complete without reviewer
  approval.

## What is explicitly out of scope

If you encounter these, flag them but do not address them in this work:
- New agent capabilities, providers, or runtime features
- Changes to baton, monitoring, or flow subsystems beyond the rename
  `agent_identity_id → agent_id`
- Re-architecting the `contexts/` workspace-context layout
- Adding a template engine, template inheritance, or stamp-from-template
  CLI feature
- UI polish beyond what T13/T14 specifies

## Definition of done

This work is done when **every item below is true**. Verify each one
explicitly; do not infer.

### On-disk shape

- For each agent currently configured, `~/.aws/cli-agent-orchestrator/agents/<id>/`
  contains a valid `agent.toml` (0600 perms) and `prompt.md` (0644 perms).
- The following files no longer exist on the developer machine:
  - `~/.aws/cli-agent-orchestrator/agents.toml`
  - any old provider-specific Linear config backup/source
  - `~/.aws/cli-agent-orchestrator/agent-store/`
- `src/cli_agent_orchestrator/agent_store/` has been moved to `examples/`
  (or equivalent path under the repo, not packaged with the distribution).

### Code surface

- `grep -rn "AgentProfile\|agent_profiles\|legacy_env\|LINEAR_DISCOVERY"
  src/` returns no hits.
- `grep -rn "agent_profile" src/` returns hits only in migration code, in
  documentation explaining the rename, or in test fixtures verifying the
  rename — not in live data models, API responses, or runtime services.
- `grep -rn "AgentIdentity\|agent_identity\|agent_identity_id" src/ web/src/`
  returns no hits. The "identity" vocabulary is gone from the new code
  surface: `AgentIdentityManager` → `AgentManager`,
  `AgentIdentityRegistry` → `AgentRegistry`, the
  `/agents/identities*` HTTP paths → `/agents*`, the
  `terminals.agent_identity_id` column → `agent_id`, the
  `AgentIdentityTimelinePanel.tsx` component → renamed (e.g.
  `AgentDetailPanel.tsx`), and all UI labels updated.
- The following modules/files are deleted:
  - `src/cli_agent_orchestrator/models/agent_profile.py`
  - `src/cli_agent_orchestrator/utils/agent_profiles.py`
  - `src/cli_agent_orchestrator/cli/commands/launch.py`
  - Any `legacy_env` helpers in `src/cli_agent_orchestrator/linear/workspace_tool_provider.py`
- The following HTTP endpoints are removed:
  - `GET /agents/profiles`
  - `GET /settings/agent-dirs` (and its PUT counterpart)
  - Anonymous spawn endpoints accepting loose profile/provider/workdir
    (replaced by `/agents/<id>/start` or equivalent)
- The `cao launch` command is unregistered. `cao launch ...` returns a
  shell-level "command not found" or the CLI's equivalent unknown-subcommand
  error.
- No backwards-compatibility layers remain in the codebase:
  - no shims detecting and falling back to the old shape
  - no facades wrapping new types in old names (e.g. `AgentProfile` as a
    thin wrapper around `Agent`)
  - no fallback chains across data formats
  - no feature flags toggling between old and new behavior
  - no deprecation warnings or aliases preserving old import paths
  - no optional fields preserving old defaults where the new model
    requires them
  - no runtime translators between old and new shapes
- No automated migration script was committed. The developer's one-shot
  manual migration was performed and validated via T04 before T05 landed.

### Behavior

- `cao agent list` returns every configured agent with its current
  instance status.
- `cao agent show <id>` returns the full agent config plus current
  instance status.
- `cao agent start <id>` opens a working terminal attached to the agent.
- A second `cao agent start <id>` while the first instance is live is
  rejected with a structured error pointing at the existing terminal.
- `cao agent stop <id>` cleanly terminates the instance.
- `cao agent create <id>` creates a stub agent directory with valid
  defaults; `cao agent show <id>` immediately afterwards succeeds.
- `cao agent edit <id>` opens `$EDITOR` on the agent's `agent.toml` and
  validates on save.
- `cao agent delete <id>` refuses when an instance is live and succeeds
  otherwise.
- The web Agents tab right panel shows the full `agent.toml` inline
  (workdir, session_name, provider, model, MCP servers, tools, Linear
  bindings, Linear tool access) plus the current instance status.
- The web "Edit" affordance updates the agent config via the new API and
  re-renders on success.
- The web "Spawn Agent" modal lists existing agents and offers a separate
  "Create new agent" entry — never on-the-fly profile/provider/workdir
  prompts.
- The Linear OAuth callback persists tokens into the correct agent's
  `agent.toml [linear]` section (verify with a real round trip).

### Database

- `terminals.agent_id` exists and is NOT NULL.
- `terminals.agent_profile` column is dropped.
- The migration refuses to run when anonymous-spawn rows exist; those rows
  are removed before the schema change.

### Tests

- Full test suite passes (`pytest` or whatever the project's standard
  invocation is — confirm with the operator if unclear).
- No tests are skipped with reason "old shape" or similar.
- Every task's acceptance criteria are exercised by at least one test
  unless the criterion is intrinsically manual (e.g. "the web UI renders
  correctly" — manual verification + a screenshot is acceptable).

### Process

- All 15 tasks have landed commits referencing the task id (e.g. "T05:
  ...").
- Each commit passed the reviewer gate.
- The criteria-catalog acceptance bullet was applied per task — record
  the applicable criteria in the task's PR description or commit message,
  not only in the task spec.
- A CHANGELOG entry describes the cutover: removed commands, removed env
  vars, removed config files, the migration script's role.

## When to escalate back to the operator

Raise back rather than improvise if:
- A criterion in the catalog seems to conflict with the plan's locked
  design.
- The migration script encounters a state it cannot reconcile (e.g. an
  agent referenced in Linear `tool_access` that doesn't exist in
  `agents.toml`).
- A scope question arises that the plan doesn't answer (e.g. should the
  agent's `workspace_context` config carry over verbatim, or be revisited?).
- Tests reveal a behavior the plan didn't anticipate (e.g. a third caller
  of an "anonymous spawn" endpoint that we didn't catalog).
- Any decision would require a deprecation period, a backwards-compat
  shim, or relaxing the ≤1 instance invariant.
- A task's natural implementation appears to require any of the forbidden
  compatibility patterns (shim, facade, fallback chain, feature flag,
  deprecation warning, alias, optional field preserving old default,
  runtime shape translator). Do not improvise an exception.
