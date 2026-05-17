# Settings

CAO stores user configuration in `~/.aws/cli-agent-orchestrator/settings.json`.
The settings file is reserved for runtime preferences that are not part of a
durable agent definition.

## Durable Agents

Agents are no longer discovered through configurable directory lists. Each
agent lives under:

```text
~/.aws/cli-agent-orchestrator/agents/<id>/
```

Each directory contains `agent.toml` and `prompt.md`. Use `cao agent create`,
`cao agent edit`, `cao agent list`, and the web Agents page to manage this
roster.

## Provider Runtime Settings

Provider runtime settings tune volatile terminal/TUI behavior without changing
provider code. CAO ships packaged defaults in
`providers/runtime_defaults.json`; values in `settings.json` override those
defaults.

```json
{
  "provider_runtime": {
    "codex": {
      "paste_enter_count": 3
    }
  }
}
```

`paste_enter_count` controls how many Enter keys CAO sends after bracketed
pasting text into a provider TUI. If a CLI changes how pasted text is submitted,
update this setting; subsequent sends resolve the current value from settings.
