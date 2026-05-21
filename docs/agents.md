# CAO Agent Directory Format

CAO's durable agent model lives under
`~/.aws/cli-agent-orchestrator/agents/<id>/`.

Each agent directory contains:

- `agent.toml`, mode `0600`: structured configuration.
- `prompt.md`, mode `0644`: the agent's system prompt as markdown.
- Runtime state directories such as `contexts/`, owned by CAO and providers.

`<id>` must be a single filesystem path segment. The `id` field in
`agent.toml` is required and must match the directory name.

## Required `agent.toml` Fields

- `id`: durable agent id.
- `display_name`: human-readable name.
- `cli_provider`: provider id from CAO's provider enum.
- `workdir`: working directory used when the agent starts.
- `session_name`: CAO tmux session name stem.

`prompt.md` must exist and be non-empty for validation.

## Optional Core Fields

- `model`: provider model preference.
- `reasoning_effort`: provider reasoning-effort preference.
- `description`: migrated profile description text.
- `tools`: provider-native tool allowlist.
- `tool_aliases`: provider-native tool aliases.
- `tools_settings`: provider-native tool settings.
- `cao_tools`: CAO MCP tool allowlist.
- `skills`: CAO/Codex skill names to materialize for the agent.
- `tags`: migrated profile tags.
- `resources`: provider-native resource references.
- `hooks`: provider-native hook config.
- `use_legacy_mcp_json`: migrated Q-style MCP config switch when present.
- `runtime_capabilities`: provider runtime capability categories.
- `[mcp_servers.<name>]`: MCP server config passed to provider runtimes.
- `[codex_config]`: Codex-specific config overlay.

The old profile `provider` field is represented by required `cli_provider`.
The old profile prompt fields are flattened into the two-file agent shape:

- `AgentProfile.prompt` and `AgentProfile.system_prompt` are represented by
  `prompt.md`; there is no separate prompt reference or template lookup.
- `AgentIdentity.agent_profile` is removed as a live link. Profile-level
  settings that used to be reached through that link are copied into the
  agent's own `agent.toml` fields, and the durable agent `id` is the runtime
  identity.

## Workspace Team

`[workspace]` is optional.

- `team`: named CAO workspace team membership, such as `"cao_delivery"`.

Agents without a workspace team are still valid and start in their default
runtime workspace context. Team-aware collaboration applies to agents that share
the same non-empty team. The team's selected workspace is derived from the
persisted team definition, not from the agent config.

## Removed Provider Config

`[linear]` and `[linear.tool_access.*]` are not part of the durable agent file
format. Agent TOML files that still contain those sections should be edited to
remove them before startup.
