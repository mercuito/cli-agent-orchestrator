# CLI Agent Orchestrator

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/awslabs/cli-agent-orchestrator)

CLI Agent Orchestrator(CAO, pronounced as "kay-oh"), is a lightweight orchestration system for managing multiple AI agent sessions in tmux terminals. Enables Multi-agent collaboration via MCP server.

## Hierarchical Multi-Agent System

CLI Agent Orchestrator (CAO) implements a hierarchical multi-agent system that enables complex problem-solving through specialized division of CLI Developer Agents.

![CAO Architecture](./docs/assets/cao_architecture.png)

### Key Features

* **Hierarchical orchestration** – CAO's supervisor agent coordinates workflow management and task delegation to specialized worker agents. The supervisor maintains overall project context while agents focus on their domains of expertise.
* **Session-based isolation** – Each agent operates in isolated tmux sessions, ensuring proper context separation while enabling seamless communication through Model Context Protocol (MCP) servers. This provides both coordination and parallel processing capabilities.
* **Intelligent task delegation** – CAO automatically routes tasks to appropriate specialists based on project requirements, expertise matching, and workflow dependencies. The system adapts between individual agent work and coordinated team efforts through three orchestration patterns:
    - **Handoff** - Synchronous task transfer with wait-for-completion
    - **Assign** - Asynchronous task spawning for parallel execution  
    - **Send Message** - Direct communication with existing agents
* **Flexible workflow patterns** – CAO supports both sequential coordination for dependent tasks and parallel processing for independent work streams. This allows optimization of both development speed and quality assurance processes.
* **Flow - Scheduled runs** – Automated execution of workflows at specified intervals using cron-like scheduling, enabling routine tasks and monitoring workflows to run unattended.
* **Context preservation** – The supervisor agent provides only necessary context to each worker agent, avoiding context pollution while maintaining workflow coherence.
* **Direct worker interaction and steering** – Users can interact directly with worker agents to provide additional steering, distinguishing from sub-agents features by allowing real-time guidance and course correction.
* **Tool restrictions** – Control what each durable agent can do through `runtime_capabilities`, `cao_tools`, provider-native `tools`, and provider access sections such as `[linear.tool_access.*]`. CAO translates restrictions to each provider's native enforcement mechanism. See [Tool Restrictions](#tool-restrictions).
* **Advanced CLI integration** – CAO agents have full access to advanced features of the developer CLI, such as the [sub-agents](https://docs.claude.com/en/docs/claude-code/sub-agents) feature of Claude Code, [Custom Agent](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/command-line-custom-agents.html) of Amazon Q Developer for CLI and so on.

For detailed project structure and architecture, see [CODEBASE.md](CODEBASE.md).

## Installation

### Requirements

- **curl** and **git** — For downloading installers and cloning the repo
- **Python 3.10 or higher** — CAO requires Python >=3.10 (see [pyproject.toml](pyproject.toml))
- **tmux 3.3+** — Used for agent session isolation
- **[uv](https://docs.astral.sh/uv/)** — Fast Python package installer and virtual environment manager

### 1. Install Python 3.10+

If you don't have Python 3.10+ installed, use your platform's package manager:

```bash
# macOS (Homebrew)
brew install python@3.12

# Ubuntu/Debian
sudo apt update && sudo apt install python3.12 python3.12-venv

# Amazon Linux 2023 / Fedora
sudo dnf install python3.12
```

Verify your Python version:

```bash
python3 --version   # Should be 3.10 or higher
```

> **Note:** We recommend using [uv](https://docs.astral.sh/uv/) to manage Python environments instead of system-wide installations like Anaconda. `uv` automatically handles virtual environments and Python version resolution per-project.

### 2. Install tmux (version 3.3 or higher required)

```bash
bash <(curl -s https://raw.githubusercontent.com/awslabs/cli-agent-orchestrator/refs/heads/main/tmux-install.sh)
```

### 3. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # Add uv to PATH (or restart your shell)
```

### 4. Install CLI Agent Orchestrator

```bash
uv tool install git+https://github.com/awslabs/cli-agent-orchestrator.git@main --upgrade
```

### Development Setup

For local development, clone the repo and install with `uv sync`:

```bash
git clone https://github.com/awslabs/cli-agent-orchestrator.git
cd cli-agent-orchestrator/
uv sync          # Creates .venv/ and installs all dependencies
uv run cao --help  # Verify installation
```

For development workflow, testing, code quality checks, and project structure, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Prerequisites

Before using CAO, install at least one supported CLI agent tool:

| Provider | Documentation | Authentication |
|----------|---------------|----------------|
| **Kiro CLI** (default) | [Provider docs](docs/kiro-cli.md) · [Installation](https://kiro.dev/docs/kiro-cli) | AWS credentials |
| **Claude Code** | [Provider docs](docs/claude-code.md) · [Installation](https://docs.anthropic.com/en/docs/claude-code/getting-started) | Anthropic API key |
| **Codex CLI** | [Provider docs](docs/codex-cli.md) · [Installation](https://github.com/openai/codex) | OpenAI API key |
| **Gemini CLI** | [Provider docs](docs/gemini-cli.md) · [Installation](https://github.com/google-gemini/gemini-cli) | Google AI API key |
| **Kimi CLI** | [Provider docs](docs/kimi-cli.md) · [Installation](https://platform.moonshot.cn/docs/kimi-cli) | Moonshot API key |
| **GitHub Copilot CLI** | [Provider docs](docs/copilot-cli.md) · [Installation](https://github.com/features/copilot/cli) | GitHub auth |
| **Q CLI** | [Installation](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/command-line.html) | AWS credentials |

## Quick Start

### 1. Create Durable Agents

Each CAO agent lives in `~/.aws/cli-agent-orchestrator/agents/<id>/` with an
`agent.toml` config file and a `prompt.md` prompt file. Create a supervisor
agent in the current project:

```bash
cao agent create code_supervisor --provider codex --workdir "$PWD"
cp examples/agents/code_supervisor.md ~/.aws/cli-agent-orchestrator/agents/code_supervisor/prompt.md
```

Create worker agents the same way:

```bash
cao agent create developer --provider codex --workdir "$PWD"
cp examples/agents/developer.md ~/.aws/cli-agent-orchestrator/agents/developer/prompt.md

cao agent create reviewer --provider codex --workdir "$PWD"
cp examples/agents/reviewer.md ~/.aws/cli-agent-orchestrator/agents/reviewer/prompt.md
```

Use `cao agent edit <id>` to change provider, model, MCP servers, tools, Linear
access, or workspace settings in `agent.toml`. You can also copy any markdown
file into a new agent directory's `prompt.md` after `cao agent create`.

```bash
cao agent edit code_supervisor
cao agent list
```

For the full agent file format, see [docs/agents.md](docs/agents.md).

### 2. Start the Server

```bash
cao-server
```

### 3. Start the Supervisor

In another terminal, start the supervisor agent:

```bash
cao agent start code_supervisor
```

The supervisor will coordinate and delegate tasks to worker agents (developer, reviewer, etc.) as needed using the orchestration patterns.

### 4. Shutdown

```bash
# Shutdown all cao sessions
cao shutdown --all

# Shutdown specific session
cao shutdown --session cao-my-session
```

### Working with tmux Sessions

All agent sessions run in tmux. Useful commands:

```bash
# List all sessions
tmux list-sessions

# Attach to a session
tmux attach -t <session-name>

# Detach from session (inside tmux)
Ctrl+b, then d

# Switch between windows (inside tmux)
Ctrl+b, then n          # Next window
Ctrl+b, then p          # Previous window
Ctrl+b, then <number>   # Go to window number (0-9)
Ctrl+b, then w          # List all windows (interactive selector)

# Delete a session
cao shutdown --session <session-name>
```

**List all windows (Ctrl+b, w):**

![Tmux Window Selector](./docs/assets/tmux_all_windows.png)

## Web UI

CAO includes a web dashboard for managing agents, terminals, and flows from the browser.

![CAO Web UI](https://github.com/user-attachments/assets/e7db9261-62b1-4422-b9f5-6fe5f65bdea4)

### Additional Requirements

- **Node.js 18+** — Required for the frontend dev server and Codex CLI

```bash
# macOS (Homebrew)
brew install node

# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs

# Amazon Linux 2023 / Fedora
sudo dnf install nodejs20

# Verify
node --version   # Should be 18 or higher
```

### Starting the Web UI

**Option A: Development mode** (hot-reload, two terminals needed)

```bash
# Terminal 1 — start the backend server
cao-server

# Terminal 2 — start the frontend dev server
cd web/
npm install        # First time only
npm run dev        # Starts on http://localhost:5173
```

Open http://localhost:5173 in your browser.

**Option B: Production mode** (single server, no Vite needed)

The built Web UI is bundled into the CAO wheel, so a plain `uv tool install` ships everything you need. Just start the server:

```bash
cao-server
```

To rebuild the frontend from source:

```bash
cd web/
npm install && npm run build   # Outputs to src/cli_agent_orchestrator/web_ui/
uv tool install . --reinstall
```

Open http://localhost:9889 in your browser.

> **Custom host/port:** `cao-server --host 0.0.0.0 --port 9889` exposes the server to the network — see Security note below.

**Remote machine access** — If you're running CAO on a remote host (e.g. dev desktop), set up an SSH tunnel:

```bash
# Dev mode (proxy both frontend and backend)
ssh -L 5173:localhost:5173 -L 9889:localhost:9889 your-remote-host

# Production mode (backend serves UI directly)
ssh -L 9889:localhost:9889 your-remote-host
```

Then open the same URLs (localhost:5173 or localhost:9889) in your local browser.

### Features

Manage sessions, spawn agents, create scheduled flows, configure agent directories, and interact with live terminals — all from the browser. Includes live status badges, an inbox for agent-to-agent messaging, output viewer, and provider auto-detection.

For frontend architecture and component details, see [web/README.md](web/README.md). For agent directory configuration, see [docs/settings.md](docs/settings.md).

## MCP Server Tools and Orchestration Modes

CAO provides a local HTTP server that processes orchestration requests. CLI agents can interact with this server through MCP tools to coordinate multi-agent workflows.

### How It Works

Each agent terminal is assigned a unique `CAO_TERMINAL_ID` environment variable. The server uses this ID to:

- Route messages between agents
- Track terminal status (IDLE, PROCESSING, COMPLETED, ERROR)
- Manage terminal-to-terminal communication via inbox
- Coordinate orchestration operations

When an agent calls an MCP tool, the server identifies the caller by their `CAO_TERMINAL_ID` and orchestrates accordingly.

### Provider Selection (Assign/Handoff)

When `handoff`/`assign` spawns a worker terminal, CAO determines which provider to use:

1. If the agent frontmatter sets `provider: ...`, that provider is used.
2. Otherwise, if `CAO_TERMINAL_ID` is set (tool called from inside a CAO terminal), the worker inherits the caller's provider.
3. Otherwise, CAO uses `DEFAULT_PROVIDER`.

### Orchestration Modes

CAO supports three orchestration patterns:

> **Note:** All orchestration modes support optional `working_directory` parameter when enabled via `CAO_ENABLE_WORKING_DIRECTORY=true`. See [Working Directory Support](#working-directory-support) for details.

**1. Handoff** - Transfer control to another agent and wait for completion

- Creates a new terminal with the specified agent
- Sends the task message and waits for the agent to finish
- Returns the agent's output to the caller
- Automatically exits the agent after completion
- Use when you need **synchronous** task execution with results

Example: Sequential code review workflow

![Handoff Workflow](./docs/assets/handoff-workflow.png)

**2. Assign** - Spawn an agent to work independently (async)

- Creates a new terminal with the specified agent
- Sends the task message with callback instructions
- Returns immediately with the terminal ID
- Agent continues working in the background
- Assigned agent sends results back to supervisor via `send_message` when complete
- Messages are queued for delivery if the supervisor is busy (common in parallel workflows)
- Use for **asynchronous** task execution or fire-and-forget operations

Example: A supervisor assigns parallel data analysis tasks to multiple analysts while using handoff to sequentially generate a report template, then combines all results.

See [examples/assign](examples/assign) for the complete working example.

![Parallel Data Analysis](./docs/assets/parallel-data-analysis.png)

**3. Send Message** - Communicate with an existing agent

- Sends a message to a specific terminal's inbox
- Messages are queued and delivered when the terminal is idle
- Enables ongoing collaboration between agents
- Common for **swarm** operations where multiple agents coordinate dynamically
- Use for iterative feedback or multi-turn conversations

Example: Multi-role feature development

![Multi-role Feature Development](./docs/assets/multi-role-feature-development.png)

### Custom Orchestration

The `cao-server` runs on `http://localhost:9889` by default and exposes REST APIs for session management, terminal control, and messaging. The CLI commands (`cao agent start`, `cao shutdown`) and MCP server tools (`handoff`, `assign`, `send_message`) are just examples of how these APIs can be packaged together.

You can combine the three orchestration modes above into custom workflows, or create entirely new orchestration patterns using the underlying APIs to fit your specific needs.

For complete API documentation, see [docs/api.md](docs/api.md).

## Flows - Scheduled Agent Sessions

Flows allow you to schedule agent sessions to run automatically based on cron expressions.

### Prerequisites

Create the durable agent you want to use:

```bash
cao agent create developer --provider codex --workdir "$PWD"
cp examples/agents/developer.md ~/.aws/cli-agent-orchestrator/agents/developer/prompt.md
```

### Quick Start

The example flow asks a simple world trivia question every morning at 7:30 AM.

```bash
# 1. Start the cao server
cao-server

# 2. In another terminal, add a flow
cao flow add examples/flow/morning-trivia.md

# 3. List flows to see schedule and status
cao flow list

# 4. Manually run a flow (optional - for testing)
cao flow run morning-trivia

# 5. View flow execution (after it runs)
tmux list-sessions
tmux attach -t <session-name>

# 6. Cleanup session when done
cao shutdown --session <session-name>
```

**IMPORTANT:** The `cao-server` must be running for flows to execute on schedule.

### Example 1: Simple Scheduled Task

A flow that runs at regular intervals with a static prompt (no script needed):

**File: `daily-standup.md`**

```yaml
---
name: daily-standup
schedule: "0 9 * * 1-5"  # 9am weekdays
agent_id: developer
provider: kiro_cli  # Optional, defaults to kiro_cli
---

Review yesterday's commits and create a standup summary.
```

### Example 2: Conditional Execution with Health Check

A flow that monitors a service and only executes when there's an issue:

**File: `monitor-service.md`**

```yaml
---
name: monitor-service
schedule: "*/5 * * * *"  # Every 5 minutes
agent_id: developer
script: ./health-check.sh
---

The service at [[url]] is down (status: [[status_code]]).
Please investigate and triage the issue:
1. Check recent deployments
2. Review error logs
3. Identify root cause
4. Suggest remediation steps
```

**Script: `health-check.sh`**

```bash
#!/bin/bash
URL="https://api.example.com/health"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$URL")

if [ "$STATUS" != "200" ]; then
  # Service is down - execute flow
  echo "{\"execute\": true, \"output\": {\"url\": \"$URL\", \"status_code\": \"$STATUS\"}}"
else
  # Service is healthy - skip execution
  echo "{\"execute\": false, \"output\": {}}"
fi
```

### Flow Commands

```bash
# Add a flow
cao flow add daily-standup.md

# List all flows (shows schedule, next run time, enabled status)
cao flow list

# Enable/disable a flow
cao flow enable daily-standup
cao flow disable daily-standup

# Manually run a flow (ignores schedule)
cao flow run daily-standup

# Remove a flow
cao flow remove daily-standup
```

## Working Directory Support

CAO supports specifying working directories for agent handoff/delegation operations. By default this is disabled to prevent agents from hallucinating directory paths.

All paths are canonicalized via `realpath` and validated against a security policy:

- **Allowed:** any real directory that is not a blocked system path — including `~/`, external volumes (e.g., `/Volumes/workplace`), and custom paths like `/opt/projects`
- **Blocked:** system directories (`/`, `/etc`, `/var`, `/tmp`, `/proc`, `/sys`, `/root`, `/boot`, `/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`, `/lib`, `/lib64`, `/dev`)

For configuration and usage details, see [docs/working-directory.md](docs/working-directory.md).

## Cross-Provider Orchestration

Each durable agent declares its provider in `agent.toml`. To run specific agents on different providers, edit the agent config:

```toml
id = "developer"
display_name = "Developer"
cli_provider = "claude_code"
```

Valid values: `kiro_cli`, `claude_code`, `codex`, `q_cli`, `gemini_cli`, `kimi_cli`, `copilot_cli`.

When a supervisor calls `assign` or `handoff`, CAO reads the worker's durable agent config and uses the declared provider.

For ready-to-use examples, see [`examples/cross-provider/`](examples/cross-provider/).

## Tool Restrictions

CAO controls what tools each durable agent can use through explicit config in
`agent.toml`. Use `runtime_capabilities` for broad provider-native access,
`cao_tools` for named CAO MCP tools, provider-native `tools` for external CLI
tool settings, and provider sections such as `[linear.tool_access.<id>]` for
mediated provider tools. CAO translates restrictions to each provider's native
enforcement mechanism where available.

```toml
id = "reviewer"
display_name = "Reviewer"
cli_provider = "codex"
workdir = "/path/to/project"
session_name = "reviewer"
runtime_capabilities = ["@builtin", "fs_read", "fs_list"]
cao_tools = ["send_message"]
```

```bash
cao agent start code_supervisor
cao agent show code_supervisor
cao agent edit code_supervisor
```

For the full reference — roles, tool vocabulary, custom roles, provider enforcement, and known limitations — see [docs/tool-restrictions.md](docs/tool-restrictions.md).

## Skills

Skills are portable, structured guides (following the universal [SKILL.md](https://github.com/anthropics/skills) format) that encode domain knowledge for AI agents. They work across AI coding assistants (Claude Code, Kiro CLI, Gemini CLI, Codex CLI, Kimi CLI, GitHub Copilot, Cursor, OpenCode, LobeHub), agent frameworks ([Strands Agents SDK](https://strandsagents.com/docs/user-guide/concepts/plugins/skills/), [Microsoft Agent Framework](https://devblogs.microsoft.com/agent-framework/give-your-agents-domain-expertise-with-agent-skills-in-microsoft-agent-framework/)), and other tools that support the SKILL.md format — allowing any agent to follow the same expert playbook regardless of provider.

CAO includes the following built-in skills:

| Skill | Description |
|-------|-------------|
| **[cao-provider](skills/cao-provider/SKILL.md)** | Scaffold a new CLI agent provider for CAO. Guides through the full implementation: ProviderType enum, provider class with regex patterns and status detection, ProviderManager registration, tool restriction wiring, unit/e2e tests, and documentation. Includes 20 lessons learnt from building 7 existing providers. |

### Loading Skills

Each AI coding tool loads skills from a different location. Copy or symlink the skill directory to the appropriate path for your tool:

| Tool | Skill Location | Command |
|------|---------------|---------|
| **Claude Code** | `.claude/skills/` | `cp -r skills/cao-provider .claude/skills/` |
| **Kiro CLI** | `.kiro/skills/` | `cp -r skills/cao-provider .kiro/skills/` |
| **Amazon Q CLI** | `.amazonq/skills/` | `cp -r skills/cao-provider .amazonq/skills/` |
| **Other tools** | Check your tool's docs for skill/prompt loading conventions |

Then ask your AI coding assistant to create a new provider:

```
> I want to add support for Aider CLI as a new CAO provider
```

The assistant will follow the skill's step-by-step guide, reference the provider template, and apply lessons learnt from existing providers.

### Managed Skills

CAO also manages skills that are shared across all agent sessions. Builtin skills (`cao-supervisor-protocols`, `cao-worker-protocols`) are auto-seeded when the `cao-server` starts — no `cao init` required.

```bash
# List installed skills
cao skills list

# Install a custom skill from a local folder
cao skills add ./my-coding-standards

# Update an existing skill (overwrite)
cao skills add ./my-coding-standards --force

# Remove a skill
cao skills remove my-coding-standards
```

Skills are delivered to each provider automatically:

| Provider | Delivery Method |
|----------|----------------|
| Kiro CLI | Native `skill://` resources (progressive loading) |
| Claude Code, Codex, Gemini CLI, Kimi CLI | Runtime prompt injection (every terminal creation) |
| Copilot CLI | Runtime prompt injection from the durable agent prompt |

When you add or remove a skill, all providers pick up the change automatically. Copilot agent files are refreshed immediately; other providers pick up changes on the next terminal creation.

**Updating skills:** Use `cao skills add ./my-skill --force` to overwrite an existing skill. Without `--force`, the command errors if the skill already exists. Builtin skills are auto-seeded on server startup but are never overwritten — to update a builtin after a CAO upgrade, remove it first with `cao skills remove` then restart the server.

For full details, see [docs/skills.md](docs/skills.md).

## Security

The server is designed for **localhost-only use**. The WebSocket terminal endpoint (`/terminals/{id}/ws`) provides full PTY access and will reject connections from non-loopback addresses. Do not expose the server to untrusted networks without adding authentication.

### DNS Rebinding Protection

The CAO server validates HTTP `Host` headers to prevent [DNS rebinding attacks](https://owasp.org/www-community/attacks/DNS_Rebinding). Only `localhost` and `127.0.0.1` are accepted by default — requests with other hostnames are rejected with `400 Bad Request`.

**Note:** If you need to expose the server on a network (not recommended for development use), be aware that the Host header validation will reject requests unless the hostname matches the allowed list.

See [SECURITY.md](SECURITY.md) for vulnerability reporting, security scanning, and best practices.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project.

## License

This project is licensed under the Apache-2.0 License.
