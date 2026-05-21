# CLI Agent Orchestrator Codebase

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Entry Points                                │
├─────────────────────────────┬───────────────────────────────────────┤
│       CLI Commands          │         MCP Server                    │
│       (cao agent start)     │    (handoff, send_message)            │
└──────────────┬──────────────┴──────────────┬────────────────────────┘
               │                             │
               └─────────────┬───────────────┘
                             │
                      ┌──────▼──────┐
                      │  FastAPI    │
                      │  HTTP API   │
                      │  (:9889)    │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │  Services   │
                      │  Layer      │
                      ├─────────────┤
                      │ • session   │
                      │ • terminal  │
                      │ • inbox     │
                      │ • flow      │
                      └──────┬──────┘
                             │
                ┌────────────┴────────────┐
                │                         │
           ┌────▼────┐               ┌────▼─────┐
           │ Clients │               │Providers │
           ├─────────┤               ├──────────┤
           │ • tmux  │               │ • kiro   │
           │ • db    │               │   _cli   │
           └────┬────┘               │ • q_cli  │
                │                    │ • claude │
         ┌──────┴──────┐             │   _code  │
         │             │             │ • codex  │
    ┌────▼────┐  ┌─────▼─────┐      │          │
    │  Tmux   │  │  SQLite   │      │          │
    │ Sessions│  │  Database │      │          │
    └─────────┘  └───────────┘      └────┬─────┘
                                         │
                                   ┌─────▼──────┐
                                   │ CLI Tools  │
                                   │• Kiro CLI  │
                                   │  (default) │
                                   │• Claude    │
                                   │  Code      │
                                   │• Codex CLI │
                                   └────────────┘
```

## Directory Structure

```
src/cli_agent_orchestrator/
├── cli/commands/          # Entry Point: CLI commands
│   ├── agent.py           # Manage durable agents and start/stop agent terminals
│   ├── info.py            # Show session info (cao info)
│   ├── mcp_server.py      # Start MCP server (cao mcp-server)
│   └── init.py            # Initializes database
├── mcp_server/            # Entry Point: MCP server
│   ├── server.py          # Handoff & send_message tools
│   └── models.py          # HandoffResult model
├── api/                   # Entry Point: HTTP API
│   └── main.py            # FastAPI endpoints (port 9889)
├── services/              # Service Layer: Business logic
│   ├── session_service.py # List, get, delete sessions
│   ├── terminal_service.py# Create, get, send input (+ mark_input_received), get output, delete terminals
│   ├── inbox_service.py   # Terminal-to-terminal messaging with watchdog
│   └── flow_service.py    # Scheduled flow execution
├── clients/               # Client Layer: External systems
│   ├── tmux.py            # Tmux operations (sets CAO_AGENT_ID, send_keys, send_keys_via_paste for bracketed paste)
│   └── database.py        # SQLite with terminals & inbox_messages tables
├── providers/             # Provider Layer: CLI tool integration
│   ├── base.py            # Abstract provider interface (mark_input_received hook)
│   ├── manager.py         # Maps terminal_id → provider
│   ├── kiro_cli.py        # Kiro CLI provider (kiro_cli) - default
│   ├── q_cli.py           # Amazon Q CLI provider (q_cli)
│   ├── claude_code.py     # Claude Code provider (claude_code, ❯ prompt, trust prompt handling)
│   └── codex.py           # Codex/ChatGPT CLI provider (codex, developer_instructions, › prompt + • bullet detection, trust prompt handling)
├── models/                # Data models
│   ├── terminal.py        # Terminal, TerminalStatus
│   ├── session.py         # Session model
│   ├── inbox.py           # InboxMessage, MessageStatus
│   └── flow.py            # Flow model
├── utils/                 # Utilities
│   ├── terminal.py        # Generate IDs, wait for shell/status
│   ├── logging.py         # File-based logging
│   └── template.py        # Template rendering
└── constants.py           # Application constants
```

## Data Flow Examples

### Terminal Creation Flow
```
cao agent start code_sup
  ↓
agent_runtime.ensure_started()
  ↓
terminal_service.create_terminal_for_agent()
  ↓
tmux_client.create_session(terminal_id)  # Sets CAO_AGENT_ID
  ↓
database.create_terminal()
  ↓
provider_manager.create_provider()
  ↓
provider.initialize()  # Waits for shell (all providers), sends command, waits for IDLE
  ↓
inbox_service.register_terminal()  # Starts watchdog observer
  ↓
Returns Terminal model
```

### Inbox Message Flow
```
MCP: send_message(receiver_agent_id, body)
  ↓
API: POST /agents/{receiver_agent_id}/inbox/messages
  ↓
database.create_inbox_message()  # Status: PENDING
  ↓
inbox_service.check_and_send_pending_messages()
  ↓
If receiver IDLE → send immediately
If receiver PROCESSING → watchdog monitors log file
  ↓
On log change → detect IDLE pattern → send message
  ↓
Update message status: DELIVERED
```

### Handoff Flow
```
MCP: handoff(agent_id, message)
  ↓
API: POST /sessions/{session}/terminals
  ↓
Wait for agent IDLE
  ↓
API: POST /terminals/{id}/input
  ↓
Poll until status = COMPLETED
  ↓
API: GET /terminals/{id}/output?mode=last
  ↓
API: POST /terminals/{id}/exit
  ↓
Return output to caller
```
