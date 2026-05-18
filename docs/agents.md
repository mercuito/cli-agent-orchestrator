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

## Workspace Setup

`[workspace]` is optional.

- `setup`: named CAO workspace setup membership, such as `"cao_delivery"`.

Agents without a workspace setup are still valid and start in their default
runtime workspace context. Provider event routing and setup-aware collaboration
only apply to agents that share the same non-empty setup.

## Linear

`[linear]` is optional. When present, it owns the Linear OAuth binding for the
agent. Every scalar field in `[linear]` is optional because an agent may be
configured before OAuth is completed:

- `app_key`: Linear app/presence key.
- `client_id`: OAuth client id.
- `client_secret`: OAuth client secret.
- `webhook_secret`: webhook verification secret.
- `oauth_redirect_uri`: callback URI registered with Linear.
- `access_token`: OAuth access token, managed by the callback writer.
- `refresh_token`: OAuth refresh token, managed by the callback writer.
- `token_expires_at`: OAuth expiration timestamp, managed by the callback
  writer.
- `app_user_id`: Linear app user id discovered through OAuth.
- `app_user_name`: Linear app user name discovered through OAuth.
- `oauth_state`: active OAuth state token.

Tool access policies live below `[linear.tool_access.<access_id>]`.

Required tool-access fields:

- `tools`: list of `cao_linear.*` tools.

Optional tool-access fields:

- `issues`: list of allowed issue identifiers or `"*"`. Required when any
  configured tool targets an existing issue, such as `cao_linear.get_issue`,
  `cao_linear.create_comment`, `cao_linear.open_agent_session_on_issue`, or
  `cao_linear.update_issue`; create-only access can omit it when the create
  policy fields below authorize the target.
- `create_team_ids`: Linear team ids allowed for issue creation.
- `create_project_ids`: Linear project ids allowed for issue creation.
- `create_parent_issues`: parent issue identifiers allowed for issue creation.
- `allow_top_level_create`: boolean, default false.
- `update_fields`: Linear issue fields allowed for `cao_linear.update_issue`.
- `reason`: explanation shown when access is denied.

Linear tool names and update fields are validated against the Linear provider's
authoritative tool catalogs.
