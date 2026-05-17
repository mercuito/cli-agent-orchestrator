# Tool Restrictions

CAO has more than one thing people casually call "tools." Keep these surfaces
separate when writing agents or provider integrations.

## Surfaces

| Surface | Agent config field | Meaning |
|---------|----------------------|---------|
| Runtime capabilities | `runtime_capabilities` | Coarse provider-native actions such as reading files, writing files, listing files, and executing shell commands. |
| CAO MCP tools | `cao_tools` | Named tools exposed by `cao-mcp-server`, such as `assign`, `send_message`, `read_inbox_message`, and `reply_to_inbox_message`. |
| Provider-mediated MCP tools | Provider config, such as Linear tool access config | Named tools supplied by a workspace provider and mediated through CAO. |
| External provider schema fields | Provider-specific config | Fields CAO writes for an external CLI provider. These names are not CAO agent vocabulary. |

`role` is not an agent access-control field. Agents should express their
identity in their name, prompt, skills, tags, and explicit access fields.

## Runtime Capabilities

Use `runtime_capabilities` to describe broad provider-native access:

```toml
id = "reviewer"
display_name = "Reviewer"
runtime_capabilities = ["@builtin", "fs_read", "fs_list"]
```

Current runtime capability vocabulary:

| Capability | Meaning | Example: Claude Code | Example: Gemini CLI |
|------------|---------|---------------------|---------------------|
| `execute_bash` | Run shell commands | `Bash` | `run_shell_command` |
| `fs_read` | Read files | `Read` | `read_file` |
| `fs_write` | Write/edit files | `Edit`, `Write` | `write_file`, `replace` |
| `fs_list` | Search/list files | `Glob`, `Grep` | `list_directory`, `glob` |
| `fs_*` | Filesystem read/write/list capabilities | All filesystem entries above | All filesystem entries above |
| `@builtin` | Provider built-in non-MCP capabilities | Provider specific | Provider specific |
| `*` | Unrestricted runtime access | All provider-native tools | All provider-native tools |

If `runtime_capabilities` is omitted, CAO defaults to developer-like native
access: `@builtin`, `fs_*`, and `execute_bash`.

Agents do not support a CAO-level allowed-tools field. Use
`runtime_capabilities` for provider-native access and `cao_tools` for named CAO
MCP tools.

## CAO MCP Tools

Use `cao_tools` to allow named tools from `cao-mcp-server`:

```toml
id = "discovery_partner"
display_name = "Discovery Partner"
runtime_capabilities = ["@builtin", "fs_read", "fs_list"]
cao_tools = ["read_inbox_message", "reply_to_inbox_message"]
```

`cao_tools = []` explicitly denies all CAO MCP tools. `cao_tools` omitted means no
agent-specific CAO MCP allowlist is configured. Prefer explicit `cao_tools` on
new agents.

Provider-mediated MCP tools, such as Linear tools, are not listed in `cao_tools`.
They are configured through the owning provider's access policy because the
provider owns that tool vocabulary.

## Launch Overrides

Configure runtime capabilities in `agent.toml` before launch:

```bash
cao agent edit reviewer
cao agent start reviewer
```

Provider-specific approval behavior is configured by each provider and the
agent's runtime capability settings.

## Confirmation Prompt

When a provider needs workspace access, CAO shows the resolved runtime
capabilities before launch:

```text
Agent 'reviewer' launching on claude_code:
  Runtime capabilities: @builtin, fs_read, fs_list
  Directory: /home/user/my-project

Proceed? [Y/n]
```

If the agent omits `runtime_capabilities`, the prompt calls out the default
developer-like native access and points back to this document.

## Provider Enforcement

CAO translates runtime capabilities to each provider's native enforcement
mechanism where possible:

| Provider | Enforcement | How it works |
|----------|-------------|--------------|
| Claude Code | Hard | `--disallowedTools` flags block specific native tools. |
| Copilot CLI | Hard | `--deny-tool` flags override `--allow-all`. |
| Gemini CLI | Hard | Policy Engine TOML deny rules. |
| Kiro CLI | Hard | Provider agent JSON receives the resolved runtime capability policy. |
| Q CLI | Hard | Provider agent JSON receives the resolved runtime capability policy. |
| Kimi CLI | Soft | Security instructions in the prompt. |
| Codex | Soft | Security instructions in the prompt. |

Hard enforcement means the provider runtime prevents denied native actions.
Soft enforcement means CAO instructs the agent not to use denied actions; do not
rely on soft enforcement for security-critical workloads.

## Delegation

When one agent creates another terminal through CAO, the child terminal resolves
runtime capabilities from the child agent. The parent's access does not become
the child's access. The parent remains responsible for delegating to an
appropriate agent.

## Quick Reference

| I want to... | Do this |
|--------------|---------|
| Limit native filesystem/shell access | Set `runtime_capabilities`. |
| Allow or deny CAO orchestration/inbox tools | Set `cao_tools`. |
| Configure Linear or another workspace provider's MCP tools | Use that provider's access config. |
| Change runtime access | Edit `runtime_capabilities` in `agent.toml`. |
| Skip provider-specific confirmations | Configure the provider-specific approval setting. |
| Remove native runtime restrictions | Set unrestricted runtime capabilities in `agent.toml`. |

## Known Limitations

1. Claude Code mapping currently covers `Bash`, `Read`, `Edit`, `Write`,
   `Glob`, and `Grep`. Native tools outside that mapping are not denied by
   runtime capability translation yet.
2. Codex and Kimi CLI runtime capability enforcement is soft.
3. Q CLI and Kiro CLI receive provider-native policy config generated from the
   durable agent's runtime capability settings.
