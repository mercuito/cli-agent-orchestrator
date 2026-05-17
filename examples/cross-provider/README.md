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

2. Create the durable agents and copy the example prompts:
```bash
# Supervisor
cao agent create cross_provider_supervisor --provider kiro_cli --workdir "$PWD"
cp examples/cross-provider/cross_provider_supervisor.md ~/.aws/cli-agent-orchestrator/agents/cross_provider_supervisor/prompt.md

# Default worker agents (used by the supervisor)
cao agent create data_analyst_claude_code --provider claude_code --workdir "$PWD"
cp examples/cross-provider/data_analyst_claude_code.md ~/.aws/cli-agent-orchestrator/agents/data_analyst_claude_code/prompt.md

cao agent create data_analyst_gemini_cli --provider gemini_cli --workdir "$PWD"
cp examples/cross-provider/data_analyst_gemini_cli.md ~/.aws/cli-agent-orchestrator/agents/data_analyst_gemini_cli/prompt.md

cao agent create data_analyst_kiro_cli --provider kiro_cli --workdir "$PWD"
cp examples/cross-provider/data_analyst_kiro_cli.md ~/.aws/cli-agent-orchestrator/agents/data_analyst_kiro_cli/prompt.md

cao agent create report_generator_codex --provider codex --workdir "$PWD"
cp examples/cross-provider/report_generator_codex.md ~/.aws/cli-agent-orchestrator/agents/report_generator_codex/prompt.md
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

1. Create the additional worker agents you need:

```bash
cao agent create data_analyst_codex --provider codex --workdir "$PWD"
cp examples/cross-provider/data_analyst_codex.md ~/.aws/cli-agent-orchestrator/agents/data_analyst_codex/prompt.md

cao agent create data_analyst_copilot_cli --provider copilot_cli --workdir "$PWD"
cp examples/cross-provider/data_analyst_copilot_cli.md ~/.aws/cli-agent-orchestrator/agents/data_analyst_copilot_cli/prompt.md
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

4. Create and launch your custom supervisor:

```bash
cao agent create my_supervisor --provider kiro_cli --workdir "$PWD"
cp my_supervisor.md ~/.aws/cli-agent-orchestrator/agents/my_supervisor/prompt.md
cao agent start my_supervisor
```

## Creating Your Own Cross-Provider Agent

To create a cross-provider version of any agent, set `cli_provider` in
`agent.toml`:

```toml
id = "my_agent_codex"
display_name = "My Codex Agent"
cli_provider = "codex"

[mcp_servers.cao-mcp-server]
type = "stdio"
command = "cao-mcp-server"
```

Valid provider values: `kiro_cli`, `claude_code`, `codex`, `q_cli`, `gemini_cli`,
`kimi_cli`, `copilot_cli`.

## E2E Tests

See `test/e2e/test_cross_provider.py` for automated tests that verify the
cross-provider resolution works across Kiro CLI, Gemini CLI, and Claude Code.

```bash
uv run pytest -m e2e test/e2e/test_cross_provider.py -v -o "addopts="
```
