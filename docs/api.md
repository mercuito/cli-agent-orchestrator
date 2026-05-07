# CLI Agent Orchestrator API Documentation

Base URL: `http://localhost:9889` (default)

## Health Check

### GET /health
Check if the server is running.

**Response:**
```json
{
  "status": "ok",
  "service": "cli-agent-orchestrator"
}
```

---

## Providers

### GET /agents/providers
List available providers with installation status.

**Response:** Array of provider objects
```json
[
  {
    "name": "kiro_cli",
    "binary": "kiro-cli",
    "installed": true
  },
  {
    "name": "claude_code",
    "binary": "claude",
    "installed": true
  },
  {
    "name": "q_cli",
    "binary": "q",
    "installed": false
  },
  {
    "name": "codex",
    "binary": "codex",
    "installed": true
  },
  {
    "name": "gemini_cli",
    "binary": "gemini",
    "installed": true
  },
  {
    "name": "kimi_cli",
    "binary": "kimi",
    "installed": false
  },
  {
    "name": "copilot_cli",
    "binary": "copilot",
    "installed": false
  }
]
```

**Note:** The `installed` field checks if the provider binary is available in the system PATH via `shutil.which()`.

---

## Sessions

### POST /sessions
Create a new session with one terminal.

**Parameters:**
- `provider` (string, required): Provider type ("kiro_cli", "claude_code", "codex", "gemini_cli", "kimi_cli", "copilot_cli", or "q_cli")
- `agent_profile` (string, required): Agent profile name
- `session_name` (string, optional): Custom session name
- `working_directory` (string, optional): Working directory for the agent session

**Response:** Terminal object (201 Created)

### GET /sessions
List all sessions.

**Response:** Array of session objects

### GET /sessions/{session_name}
Get details of a specific session.

**Response:** Session object with terminals list

### DELETE /sessions/{session_name}
Delete a session and all its terminals.

**Response:**
```json
{
  "success": true
}
```

---

## Terminals

**Note:** All `terminal_id` path parameters must be 8-character hexadecimal strings (e.g., "a1b2c3d4").

### POST /sessions/{session_name}/terminals
Create an additional terminal in an existing session.

**Parameters:**
- `provider` (string, required): Provider type
- `agent_profile` (string, required): Agent profile name
- `working_directory` (string, optional): Working directory for the terminal

**Response:** Terminal object (201 Created)

### GET /sessions/{session_name}/terminals
List all terminals in a session.

**Response:** Array of terminal objects

### GET /terminals/{terminal_id}
Get terminal details.

**Response:** Terminal object
```json
{
  "id": "string",
  "name": "string",
  "provider": "kiro_cli|claude_code|codex|gemini_cli|kimi_cli|copilot_cli|q_cli",
  "session_name": "string",
  "agent_profile": "string",
  "status": "idle|processing|completed|waiting_user_answer|error",
  "last_active": "timestamp"
}
```

### POST /terminals/{terminal_id}/input
Send input to a terminal.

**Parameters:**
- `message` (string, required): Message to send

**Response:**
```json
{
  "success": true
}
```

### GET /terminals/{terminal_id}/output
Get terminal output.

**Parameters:**
- `mode` (string, optional): Output mode - "full" (default), "last", or "tail"

**Response:**
```json
{
  "output": "string",
  "mode": "string"
}
```

### GET /terminals/{terminal_id}/working-directory
Get the current working directory of a terminal's pane.

**Response:**
```json
{
  "working_directory": "/home/user/project"
}
```

**Note:** Returns `null` if working directory is unavailable.

### POST /terminals/{terminal_id}/exit
Send provider-specific exit command to terminal.

**Behavior:**
- Calls the provider's `exit_cli()` method to get the exit command
- Text commands (e.g., `/exit`, `quit`) are sent as literal text via `send_input()`
- Key sequences prefixed with `C-` or `M-` (e.g., `C-d` for Ctrl+D) are sent as tmux key sequences via `send_special_key()`, which tmux interprets as actual key presses

| Provider | Exit Command | Type |
|----------|-------------|------|
| kiro_cli | `/exit` | Text |
| claude_code | `/exit` | Text |
| codex | `/exit` | Text |
| gemini_cli | `/exit` | Text |
| kimi_cli | `/exit` | Text |
| copilot_cli | `/exit` | Text |
| q_cli | `/exit` | Text |

**Response:**
```json
{
  "success": true
}
```

### DELETE /terminals/{terminal_id}
Delete a terminal.

**Response:**
```json
{
  "success": true
}
```

---

## Inbox (Terminal-to-Terminal Messaging)

### POST /terminals/{receiver_id}/inbox/messages
Send a message to another terminal's inbox.

**Parameters:**
- `sender_id` (string, required): Sender terminal ID
- `message` (string, required): Message content

**Response:**
```json
{
  "success": true,
  "notification_id": 123,
  "message_id": 456,
  "sender_id": "string",
  "receiver_id": "string",
  "created_at": "timestamp"
}
```

**Behavior:**
- Messages are queued and delivered when the receiver terminal is IDLE
- `notification_id` identifies the per-recipient delivery record; `message_id`
  identifies the durable backing message
- Messages are delivered in order (oldest first)
- Delivery is automatic via watchdog file monitoring

---

## Monitoring Sessions

Retrospective visibility into agent-to-agent conversations. See
[`monitoring.md`](monitoring.md) for the conceptual overview and yards
integration example. Monitoring routes are operator-facing and **not**
exposed as MCP tools — agents cannot see or call them.

### POST /monitoring/sessions
Start recording a terminal.

**Request body:**
```json
{
  "terminal_id": "impl-abc123",
  "label": "review-v2"
}
```
`label` is optional. **Idempotent on active state:** if `terminal_id` already
has an active session, that session is returned unchanged (label argument
ignored). Status code is `201` in both cases.

**Response (201):** session object with fields `id`, `terminal_id`, `label`,
`started_at`, `ended_at`, `status`.

### GET /monitoring/sessions
List sessions. Query params: `terminal_id`, `status` (`active`|`ended`),
`label`, `started_after`, `started_before`, `limit` (1–500), `offset`.

### GET /monitoring/sessions/{session_id}
Show a single session. `404` if missing.

### POST /monitoring/sessions/{session_id}/end
End an active session. `409` if already ended; `404` if missing.

### GET /monitoring/sessions/{session_id}/messages
Inbox messages captured by the session, ordered by creation time.

**Query params (all optional):**
- `peer` (repeatable): filter to messages whose sender OR receiver is one of
  the listed peers. Omit for all messages.
- `started_after` / `started_before` (ISO datetime): narrow to a sub-window
  inside the session's bounds.

### GET /monitoring/sessions/{session_id}/log
Rendered artifact.

**Query params:**
- `format=markdown` (default) or `format=json`.
- `peer` (repeatable), `started_after`, `started_before`: same as
  `/messages`. When any filter is applied, the artifact declares it in a
  `**Filter:** ...` header line (Markdown) or `filter` key (JSON).

Markdown returns `text/markdown`; JSON returns `{session, messages}` (plus
`filter` when applicable).

### DELETE /monitoring/sessions/{session_id}
Delete the session metadata. Does **not** delete messages. Returns `204`.

---

## Error Responses

All endpoints return standard HTTP status codes:

- `200 OK`: Success
- `201 Created`: Resource created
- `204 No Content`: Success with no body
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Resource not found
- `409 Conflict`: Operation conflicts with resource state (e.g., ending an already-ended session)
- `422 Unprocessable Entity`: Request body/params failed validation
- `500 Internal Server Error`: Server error

Error response format:
```json
{
  "detail": "Error message"
}
```

---
