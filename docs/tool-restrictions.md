# Tool Restrictions

CAO has more than one thing people casually call "tools." Keep these surfaces
separate when writing profiles or provider integrations.

## Surfaces

| Surface | Profile/config field | Meaning |
|---------|----------------------|---------|
| Runtime capabilities | `runtimeCapabilities` | Coarse provider-native actions such as reading files, writing files, listing files, and executing shell commands. |
| CAO MCP tools | `caoTools` | Named tools exposed by `cao-mcp-server`, such as `assign`, `send_message`, `read_inbox_message`, and `reply_to_inbox_message`. |
| Provider-mediated MCP tools | Provider config, such as Linear tool access config | Named tools supplied by a workspace provider and mediated through CAO. |
| External provider schema fields | Provider-specific config, such as Q/Kiro `allowedTools` | Fields CAO writes for an external CLI provider. These names are not CAO profile vocabulary. |

`role` is not a profile access-control field. Profiles should express their
identity in their name, prompt, skills, tags, and explicit access fields.

## Runtime Capabilities

Use `runtimeCapabilities` to describe broad provider-native access:

```yaml
---
name: reviewer
description: Read-only reviewer
runtimeCapabilities: ["@builtin", "fs_read", "fs_list"]
---
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

If `runtimeCapabilities` is omitted, CAO defaults to developer-like native
access: `@builtin`, `fs_*`, and `execute_bash`.

Profiles do not support `allowedTools`. Use `runtimeCapabilities` for
provider-native access and `caoTools` for named CAO MCP tools.

## CAO MCP Tools

Use `caoTools` to allow named tools from `cao-mcp-server`:

```yaml
---
name: discovery_partner
description: Opens discovery conversations and shapes work intake
runtimeCapabilities: ["@builtin", "fs_read", "fs_list"]
caoTools:
  - read_inbox_message
  - reply_to_inbox_message
---
```

`caoTools: []` explicitly denies all CAO MCP tools. `caoTools` omitted means no
profile-specific CAO MCP allowlist is configured; the current server startup path
falls open for older profiles. Prefer explicit `caoTools` on new profiles.

Provider-mediated MCP tools, such as Linear tools, are not listed in `caoTools`.
They are configured through the owning provider's access policy because the
provider owns that tool vocabulary.

## Launch Overrides

Use `--runtime-capability` to override profile runtime capabilities at launch:

```bash
cao launch --agents reviewer \
  --runtime-capability fs_read \
  --runtime-capability fs_list
```

`--auto-approve` only skips the confirmation prompt. It does not change access.

`--yolo` sets unrestricted runtime access (`["*"]`) and skips the confirmation
prompt:

```bash
cao launch --agents developer --yolo
```

## Confirmation Prompt

When a provider needs workspace access, CAO shows the resolved runtime
capabilities before launch:

```text
Agent 'reviewer' launching on claude_code:
  Runtime capabilities: @builtin, fs_read, fs_list
  Directory: /home/user/my-project

Proceed? [Y/n]
```

If the profile omits `runtimeCapabilities`, the prompt calls out the default
developer-like native access and points back to this document.

## Provider Enforcement

CAO translates runtime capabilities to each provider's native enforcement
mechanism where possible:

| Provider | Enforcement | How it works |
|----------|-------------|--------------|
| Claude Code | Hard | `--disallowedTools` flags block specific native tools. |
| Copilot CLI | Hard | `--deny-tool` flags override `--allow-all`. |
| Gemini CLI | Hard | Policy Engine TOML deny rules. |
| Kiro CLI | Hard | Provider agent JSON uses its own `allowedTools` schema field. |
| Q CLI | Hard | Provider agent JSON uses its own `allowedTools` schema field. |
| Kimi CLI | Soft | Security instructions in the prompt. |
| Codex | Soft | Security instructions in the prompt. |

Hard enforcement means the provider runtime prevents denied native actions.
Soft enforcement means CAO instructs the agent not to use denied actions; do not
rely on soft enforcement for security-critical workloads.

## Delegation

When one agent creates another terminal through CAO, the child terminal resolves
runtime capabilities from the child profile. The parent's access does not become
the child's access. The parent remains responsible for delegating to an
appropriate profile.

## Quick Reference

| I want to... | Do this |
|--------------|---------|
| Limit native filesystem/shell access | Set `runtimeCapabilities`. |
| Allow or deny CAO orchestration/inbox tools | Set `caoTools`. |
| Configure Linear or another workspace provider's MCP tools | Use that provider's access config. |
| Override runtime access at launch | Use `--runtime-capability`. |
| Skip confirmation in scripts/automation | Use `--auto-approve`. |
| Remove native runtime restrictions | Use `--yolo`. |

## Known Limitations

1. Claude Code mapping currently covers `Bash`, `Read`, `Edit`, `Write`,
   `Glob`, and `Grep`. Native tools outside that mapping are not denied by
   runtime capability translation yet.
2. Codex and Kimi CLI runtime capability enforcement is soft.
3. Q CLI and Kiro CLI still receive an `allowedTools` field in their generated
   provider agent JSON because that is the external provider schema, not CAO
   profile vocabulary.
