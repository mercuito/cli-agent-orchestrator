# Cross-Provider Examples

Agents that demonstrate cross-provider workflows where a supervisor on one
provider delegates to workers on different providers via the `provider` key in
their frontmatter.

## How It Works

Each worker agent is identical to its counterpart in `examples/assign/` except
for its provider configuration. When a supervisor calls `assign` or `handoff`
with one of these agents, CAO reads `cli_provider` and launches the worker on
that provider regardless of which provider the supervisor is running on.

## Agents

### Supervisor

| Agent | Description |
|---------|-------------|
| `cross_provider_supervisor.md` | Supervisor that delegates to cross-provider workers |

### Data Analysts (assign — parallel)

| Agent | Provider |
|---------|------------------|
| `data_analyst_claude_code.md` | `claude_code` |
| `data_analyst_gemini_cli.md` | `gemini_cli` |
| `data_analyst_kiro_cli.md` | `kiro_cli` |

### Additional Data Analysts

These are not referenced by the default supervisor agent but are available
if you want to use other providers:

| Agent | Provider |
|---------|------------------|
| `data_analyst_codex.md` | `codex` |
| `data_analyst_copilot_cli.md` | `copilot_cli` |

### Report Generator (handoff — sequential)

| Profile | Provider Override |
|---------|------------------|
| `report_generator_codex.md` | `codex` |

## Setup

1. Start the CAO server:
```bash
cao-server
```

2. Install the agents:
```bash
# Supervisor
cao install examples/cross-provider/cross_provider_supervisor.md

# Default worker agents (used by the supervisor)
cao install examples/cross-provider/data_analyst_claude_code.md
cao install examples/cross-provider/data_analyst_gemini_cli.md
cao install examples/cross-provider/data_analyst_kiro_cli.md
cao install examples/cross-provider/report_generator_codex.md
```

3. Launch the supervisor:
```bash
# Using Kiro CLI (workers on Claude Code + Gemini CLI + Kiro CLI + Codex)
cao agent start cross_provider_supervisor

# To use a different supervisor provider, edit cli_provider in agent.toml.
```

## Usage

In the supervisor terminal, try this example task:

```
Analyze these datasets and create a comprehensive report:
- Dataset A: [1, 2, 3, 4, 5]
- Dataset B: [10, 20, 30, 40, 50]
- Dataset C: [5, 15, 25, 35, 45]

Calculate mean, median, and standard deviation for each dataset.
Generate a professional report with the analysis results.
```

## Customizing the Supervisor

The default supervisor uses `data_analyst_claude_code`, `data_analyst_gemini_cli`,
and `data_analyst_kiro_cli` for data analysis, and `report_generator_codex` for
report generation. To use different providers:

1. Install the additional worker agents you need:

```bash
cao install examples/cross-provider/data_analyst_codex.md
cao install examples/cross-provider/data_analyst_copilot_cli.md
```

2. Copy and edit the supervisor agent to reference the agents you want:

```bash
cp examples/cross-provider/cross_provider_supervisor.md my_supervisor.md
```

3. In `my_supervisor.md`, update the **Worker Agents** table and the **Example**
   section to use your preferred agents. For example, to use Codex and Copilot CLI
   instead of Gemini CLI and Kiro CLI:

```markdown
| `data_analyst_claude_code` | Claude Code |
| `data_analyst_codex` | Codex |
| `data_analyst_copilot_cli` | Copilot CLI |
```

4. Install and launch your custom supervisor:

```bash
cao install my_supervisor.md
cao agent start my_supervisor
```

## Creating Your Own Cross-Provider Agent

To create a cross-provider version of any agent, set `cli_provider` in
`agent.toml`:

```yaml
---
name: my_agent_codex
description: My agent that runs on Codex
provider: codex
mcpServers:
  cao-mcp-server:
    type: stdio
    command: uvx
    args:
      - "--from"
      - "git+https://github.com/awslabs/cli-agent-orchestrator.git@main"
      - "cao-mcp-server"
---
```

Valid provider values: `kiro_cli`, `claude_code`, `codex`, `q_cli`, `gemini_cli`,
`kimi_cli`, `copilot_cli`.

## E2E Tests

See `test/e2e/test_cross_provider.py` for automated tests that verify the
cross-provider resolution works across Kiro CLI, Gemini CLI, and Claude Code.

```bash
uv run pytest -m e2e test/e2e/test_cross_provider.py -v -o "addopts="
```
