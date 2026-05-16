# CAO Agent Model Cleanup (Draft v1)

Status: draft

This document captures the cleanup of CAO's agent concepts: unifying the
existing `AgentProfile` (template) + `AgentIdentity` (instance config) split
into a single `Agent` concept, hardening the boundary between configuration
and runtime, and removing identity-blind spawn paths.

The motivating problems are:

- Two parallel "what is an agent" tracks exist today. `AgentProfile` (markdown
  in `agent_store/`) and `AgentIdentity` (TOML entries in `agents.toml`) carry
  overlapping concerns with a live link between them.
- A third config file (`workspace-providers/linear.toml`) holds per-agent
  Linear OAuth bindings and tool access policies, with its own keying.
- Terminals can be spawned anonymously (`POST /sessions`, `cao launch`, web
  "Spawn Agent" modal) — these terminals have `agent_identity_id = None` and
  never appear in the Agents tab timeline.
- A `legacy_env` code path in the Linear provider fabricates ephemeral
  identities from `LINEAR_DISCOVERY_*` env vars, predating `agents.toml`.

The cleanup commits to a single coherent chain: every terminal exists because
some instance spawned it, every instance backs one agent, every agent owns its
config and persistent state in one place.

---

## Locked design

Two layers:

- **Agent** — durable, named, owns its persistent directory at
  `~/.aws/cli-agent-orchestrator/agents/<id>/`. Two-file layout:
  - `agent.toml` (0600) — structured config: workdir, session_name, provider,
    model, MCP servers, tools allowlist, Linear OAuth bindings, Linear tool
    access policies, etc.
  - `prompt.md` (0644) — system prompt as pure markdown.
  - Existing runtime state subdirectories (e.g. `contexts/`) continue to live
    alongside these files.
- **Instance** — the live runtime: exactly one terminal at a time backing an
  agent. Hard ≤1 invariant prevents state-directory race conditions across
  parallel terminals pointing at the same agent.

The `agent_store/` subsystem (templates, multi-source discovery, the
`/agents/profiles` endpoint, `load_agent_profile`, settings-driven template
dirs) is removed entirely. Pre-built templates were load-bearing only in the
old live-link model; in two-layer stamp-or-stub creation they collapse to thin
scaffolding for a setup step that runs a few times per agent lifetime. The
existing files at `src/cli_agent_orchestrator/agent_store/*.md` move to
`examples/` as documentation; `cao agent create <name>` produces a minimal
stub. Copying from an example is a manual file copy, not a CLI feature.

New CLI surface — one namespace, singular noun:

```
cao agent list
cao agent show <name>      # config + current instance status
cao agent create <name>    # stub agent.toml + empty prompt.md
cao agent edit <name>
cao agent delete <name>
cao agent start <name>     # spawn the instance
cao agent stop <name>      # kill the instance
```

The existing `cao launch` verb is removed outright — hard cutover, no
deprecation.

## Migration shape

Hard cutover; no deprecation period. The migration script reads:

- `~/.aws/cli-agent-orchestrator/agents.toml` (per-agent durable config)
- `~/.aws/cli-agent-orchestrator/workspace-providers/linear.toml` (per-agent
  Linear bindings keyed by `agent_id`, plus tool access policies)
- The `agent_profile` markdown referenced by each agent (system prompt and
  template-level config: MCP servers, tools allowlist, model, etc.)

…and emits one directory per agent at `~/.aws/cli-agent-orchestrator/agents/<id>/`
containing `agent.toml` (with merged config including the Linear bindings) and
`prompt.md` (with the system prompt). Existing per-agent state subdirectories
at the same path are preserved.

Linear tool access policies that target `agent_profile` (fan-out targeting,
matching all identities using a given profile) are expanded at migration time
into per-agent policies. The `agent_profile` targeting capability does not
survive into the new model.

The Linear `legacy_env` path (`_legacy_identity_for_presence`,
`_legacy_configured_app_keys`, all `LINEAR_DISCOVERY_*` env var lookups) is
removed outright. Users on legacy env config must migrate to a structured
config first; this is documented in the migration notes but not enforced by
backwards-compatible shims.

After migration the old files are deleted:

- `~/.aws/cli-agent-orchestrator/agents.toml`
- `~/.aws/cli-agent-orchestrator/workspace-providers/linear.toml`
- `~/.aws/cli-agent-orchestrator/agent-store/` (templates moved to repo
  `examples/`)

## Goals

- One unified `Agent` data model spanning what was previously split between
  `AgentProfile` and `AgentIdentity`.
- One on-disk shape per agent: directory with `agent.toml` + `prompt.md`.
- Provider-specific config (currently Linear, future GitHub/Slack/etc.) lives
  as a sub-section inside the agent's own config — no separate
  `workspace-providers/<name>.toml` files.
- All terminal creation goes through an agent instance. No anonymous spawn.
- ≤1 live instance per agent, enforced at spawn time.
- New `cao agent <subcmd>` CLI namespace covers both config and runtime
  operations.
- Web "Spawn Agent" UI becomes "pick an existing agent" + "create a new
  agent" — never on-the-fly profile+provider+workdir prompts.
- Web Agents tab right panel shows the full agent config inline and supports
  editing.

## Non-goals

- No new agent capabilities, providers, or runtime features. This is pure
  cleanup of an existing concept.
- No template engine, no template inheritance, no stamp-from-template
  CLI feature. Examples are documentation, not infrastructure.
- No deprecation period for `cao launch`, `legacy_env`, or `linear.toml`.
  These are removed in the same landing that introduces their replacements.
- No multi-instance-per-agent or instance pooling. The ≤1 invariant is
  intentional and not a stepping stone.
- No changes to the existing `contexts/` workspace-context runtime state
  layout beyond what's required to keep it working under the new agent path.
- No changes to baton, monitoring, or flow subsystems beyond following the
  renamed agent identifier (`agent_identity_id` → `agent_id`).

---

## Phasing

The cleanup lands in six phases. Phase 1 builds the new shape in parallel
without changing any runtime behavior. Phase 2 is the atomic cutover where
read paths swap and old code is deleted. Phases 3–6 then harden the spawn
boundary, build the new CLI/UI surface, and tidy up.

### Phase 1 — New model and tooling (parallel, no behavior change)

Establish the `Agent` data model, directory loader/writer, validation, and
migration script. All existing code paths remain unchanged; the new code is
reachable from tests but not yet wired into the running system.

### Phase 2 — Read-path cutover (atomic)

Run migration on developer machines to convert existing config. Swap all
readers (identity manager, Linear provider, API endpoints, web) to the new
model in a single landing. Delete the old subsystems: `AgentProfile`,
`agent_profiles.py`, `agent_store/` at the old location, the `legacy_env`
path, multi-source discovery plumbing, `/agents/profiles` endpoint,
`linear.toml`.

### Phase 3 — Spawn lockdown

Tighten the terminal model: drop the `agent_profile` column, rename
`agent_identity_id` → `agent_id`, make it NOT NULL. Reshape the spawn API to
require an `agent_id`. Enforce ≤1 live instance per agent at spawn time. Add
the HTTP API surface for agent CRUD.

### Phase 4 — New CLI surface

Add `cao agent <list|show|create|edit|delete|start|stop>` backed by the agent
HTTP API. Drop the `cao launch` verb.

### Phase 5 — Web UI rebuild

Replace the "Spawn Agent" modal with an existing-agent picker plus a "Create
new agent" entry point. Update the Agents tab right panel to show the full
agent config inline and support inline editing.

### Phase 6 — Final tidy

Move `src/cli_agent_orchestrator/agent_store/*.md` to `examples/`. Sweep for
stragglers. Update README and CHANGELOG.

The full task breakdown lives in `plans/agent-model-cleanup.tasks.md`.
