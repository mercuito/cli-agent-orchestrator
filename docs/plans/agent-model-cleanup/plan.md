# CAO Agent Model Cleanup (Draft v1)

Status: draft

This document captures the cleanup of CAO's agent concepts: unifying the
existing `AgentProfile` (template) + `AgentIdentity` (instance config) split
into a single `Agent` concept, hardening the boundary between configuration
and runtime, and removing anonymous (no-agent) spawn paths.

The motivating problems are:

- Two parallel "what is an agent" tracks exist today. `AgentProfile` (markdown
  in `agent_store/`) and `AgentIdentity` (TOML entries in `agents.toml`) carry
  overlapping concerns with a live link between them.
- The old Linear provider config file held per-agent Linear OAuth bindings and
  tool access policies with its own keying instead of storing them in each
  agent's `agent.toml`.
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

Hard cutover; no deprecation period; no automated migration script. The
agent roster is small enough (currently 3) that the developer performs a
one-shot manual migration of their own config before the read-path cutover
(T05) lands. The validator from T04 verifies the new directory shape is
well-formed.

For each existing agent:

1. Read the entry in `~/.aws/cli-agent-orchestrator/agents.toml` and the
   referenced `agent_profile` markdown in `agent_store/`.
2. Read the corresponding provider-specific Linear presence and tool-access
   blocks from the old pre-agent-directory config backup/source.
3. Hand-write `~/.aws/cli-agent-orchestrator/agents/<id>/agent.toml`
   containing the merged config (workdir, session_name, provider, plus
   profile-level config — MCP servers, tools allowlist, model, etc. —
   plus a `[linear]` section with the OAuth bindings and tool access
   policy if applicable).
4. Hand-write `~/.aws/cli-agent-orchestrator/agents/<id>/prompt.md` with
   the system prompt body from the original `agent_profile` markdown.
5. Run T04's validator to confirm the directory is well-formed.

Linear `tool_access` entries that target `agent_profile` (fan-out
targeting, matching all identities using a given profile) are expanded by
hand into one entry per affected agent during migration. The
`agent_profile` targeting capability does not survive into the new model.

The Linear `legacy_env` path (`_legacy_identity_for_presence`,
`_legacy_configured_app_keys`, all `LINEAR_DISCOVERY_*` env var lookups)
is removed outright. The developer does not currently use legacy env
config; if they did, they would convert to structured `linear.toml` first
before performing the manual migration above.

After manual migration and the T05/T06/T07 landings, the following files
no longer exist on the developer machine:

- `~/.aws/cli-agent-orchestrator/agents.toml`
- any old provider-specific Linear config backup/source
- `~/.aws/cli-agent-orchestrator/agent-store/` (templates moved to repo
  `examples/`)

## Forbidden compatibility patterns

This is hard-cutover work and the `do-not-assume-backwards-compatibility`
criterion (`docs/criteria/implementation/`, `when: Always`) is unusually
load-bearing here. No task may introduce any of the following:

- Shims that detect the old shape and fall back to it.
- Facades preserving old types as wrappers around new types (e.g. keeping
  `AgentProfile` as a thin wrapper around `Agent`).
- Fallback chains (`try new format; on failure, try old format`).
- Feature flags switching between old and new behavior at runtime.
- Deprecation warnings emitted instead of removing the old path.
- Function or module aliases keeping old import paths working.
- Optional fields preserving old defaults where the new model requires
  them.
- Runtime translators between old and new shapes.

No compatibility carve-outs exist in this plan. Every legacy call site is
migrated to the new shape or deleted. None are bridged.

If a task's natural implementation seems to require any of the above,
raise back to the operator rather than improvising.

## Goals

- One unified `Agent` data model spanning what was previously split between
  `AgentProfile` and `AgentIdentity`.
- One on-disk shape per agent: directory with `agent.toml` + `prompt.md`.
- Provider-specific config (currently Linear, future GitHub/Slack/etc.) lives
  as a sub-section inside the agent's own config. The only workspace tool
  provider config outside agent directories is the flat global enablement file
  `workspace-tool-providers.toml`.
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

Developer performs the one-shot manual config migration on their machine.
Swap all readers (agent manager/registry, Linear provider, API endpoints,
web) to the new model — including renaming `AgentIdentityManager` →
`AgentManager` and `AgentIdentityRegistry` → `AgentRegistry`, and renaming
the `/agents/identities*` HTTP paths to `/agents*`. Delete the old
subsystems: `AgentProfile`, `agent_profiles.py`, `agent_store/` at the
old location, the `legacy_env` path, multi-source discovery plumbing,
`/agents/profiles` endpoint, `linear.toml`. No "identity" vocabulary
survives in the new code surface.

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

The full task breakdown lives in `docs/plans/agent-model-cleanup/tasks.md`.
