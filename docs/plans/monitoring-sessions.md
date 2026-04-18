# Monitoring Sessions — Implementation Plan

**Status:** shipped. All six phases complete with reviewer sign-off per phase. Integration tests and live E2E smoke test both passed. This document is retained as the design record; update it only if the feature's model genuinely changes.

## Goal

Give operators retrospective visibility into agent-to-agent conversations so that workflow variants (e.g., "does 3 reviewers beat 1?") can be compared and the reasoning behind an agent's output can be audited.

The feature intentionally does **not** introduce a first-class "conversation" concept. A monitoring session is a query window — a terminal, a time range, and an optional peer set — that filters the existing `inbox` messages table.

## Design decisions (and why)

1. **No side log / no message duplication.** The existing `inbox` table already captures every agent-to-agent message (send_message, assign, handoff all land there). A monitoring session is metadata that scopes a query over that table.

2. **Sessions are not exposed to agents.** No `@mcp.tool()` registration. The monitoring API lives only on the HTTP server and is driven by procedures (yards) or operators, not by LLM agents. Agents cannot start, stop, or query sessions.

3. **Pair filter is retroactive by default.** Adding a peer mid-session exposes earlier in-window messages involving that peer. Users who want prospective-per-peer semantics end the session and start a new one with the expanded peer set. We ship without a `rotate` convenience endpoint; add it only if procedures find end+start clunky.

4. **Null / empty peer set means "all peers."** No rows in `monitoring_session_peers` for a session = unscoped (capture all I/O of the monitored terminal). One or more rows = scoped to that set.

5. **Free-form `label` only, no structured metadata blob.** Procedures that need structured correlation either store it in yards instance state or encode it into the label. Revisit only if a concrete query demands it.

6. **Persisted until explicit delete.** No TTL, no auto-archive. Sessions are tiny.

7. **Deleting a session does not delete messages.** Messages have their own retention story. Deleting a session removes the query window only. FK CASCADE applies only to the peer rows.

8. **Ended sessions are immutable w.r.t. peer set.** Add/remove peer on an ended session returns 409. No reason to mutate a historical window.

9. **Timestamp source is `inbox.created_at`** (sender side). Windows map to when the sender emitted, not when the recipient received. Simpler and intuitive.

10. **Overlapping sessions on the same terminal are allowed.** A procedure may want run-level + step-level windows concurrently. No conflict — each session is an independent query.

## Schema

```
monitoring_sessions
  id            TEXT PRIMARY KEY
  terminal_id   TEXT NOT NULL
  label         TEXT NULL
  started_at    DATETIME NOT NULL
  ended_at      DATETIME NULL              -- NULL = still recording

monitoring_session_peers
  session_id        TEXT NOT NULL
  peer_terminal_id  TEXT NOT NULL
  PRIMARY KEY (session_id, peer_terminal_id)
  FOREIGN KEY (session_id) REFERENCES monitoring_sessions(id) ON DELETE CASCADE
```

No ALTER TABLE required. `Base.metadata.create_all()` picks up the new tables on startup.

## API surface

All routes on the HTTP server (`src/cli_agent_orchestrator/api/main.py`). **Not** on the MCP tool surface.

| Method | Path | Notes |
|---|---|---|
| POST | `/monitoring/sessions` | body: `{terminal_id, peer_terminal_ids?, label?}` → 201 |
| POST | `/monitoring/sessions/{id}/end` | 409 if already ended |
| POST | `/monitoring/sessions/{id}/peers` | body: `{peer_terminal_ids}`; 409 if ended |
| DELETE | `/monitoring/sessions/{id}/peers/{peer_id}` | 409 if ended |
| GET | `/monitoring/sessions` | filters: `terminal_id`, `peer_terminal_id`, `involves`, `status`, `label`, `started_after`, `started_before`, `limit`, `offset` |
| GET | `/monitoring/sessions/{id}` | 404 if missing |
| GET | `/monitoring/sessions/{id}/messages` | ordered JSON list |
| GET | `/monitoring/sessions/{id}/log?format=markdown\|json` | default markdown — implemented in Phase 4 alongside the formatter |
| DELETE | `/monitoring/sessions/{id}` | 204 |

### Message query (`get_session_messages`)

```sql
SELECT * FROM inbox
WHERE (sender_id = :terminal_id OR receiver_id = :terminal_id)
  AND (
    NOT EXISTS (SELECT 1 FROM monitoring_session_peers WHERE session_id = :sid)
    OR sender_id   IN (SELECT peer_terminal_id FROM monitoring_session_peers WHERE session_id = :sid)
    OR receiver_id IN (SELECT peer_terminal_id FROM monitoring_session_peers WHERE session_id = :sid)
  )
  AND created_at >= :started_at
  AND (:ended_at IS NULL OR created_at <= :ended_at)
ORDER BY created_at
```

## CLI surface

```
cao monitor start    --terminal T [--peer P ...] [--label ...]   # prints session_id
cao monitor end      <session_id>
cao monitor add-peer <session_id> <peer_id>
cao monitor remove-peer <session_id> <peer_id>
cao monitor list     [--terminal T] [--peer P] [--involves X] [--active] [--label ...]
cao monitor show     <session_id>
cao monitor log      <session_id> [--format markdown|json]        # stdout
cao monitor delete   <session_id>
```

CLI commands call the local HTTP API (mirror `cli/commands/launch.py`).

## Phases

Each phase is a separately committable unit. TDD: tests first, then implementation. Do not mark a phase "done" until tests pass and the reviewer has signed off.

### Phase 1 — Data layer

**Files:**
- Modify: `src/cli_agent_orchestrator/clients/database.py` — add `MonitoringSessionModel`, `MonitoringSessionPeerModel`
- Add: `test/clients/test_monitoring_tables.py`

**Tests must cover:**
- Tables exist after `init_db()`
- Insert session, insert peer row referencing it
- FK CASCADE: deleting a session deletes its peer rows
- `ended_at` nullable; `label` nullable

**Acceptance:** fresh DB has both tables; tests green.

### Phase 2 — Service layer

**Files:**
- Add: `src/cli_agent_orchestrator/services/monitoring_service.py`
- Add: `test/services/test_monitoring_service.py`

**Functions:**
```
create_session(terminal_id, peer_terminal_ids=None, label=None) -> dict
end_session(session_id) -> dict
get_session(session_id) -> dict | None
list_sessions(**filters, limit=50, offset=0) -> list[dict]
delete_session(session_id) -> None
add_peers(session_id, peer_terminal_ids) -> None           # raise on ended
remove_peer(session_id, peer_terminal_id) -> None          # raise on ended
get_session_messages(session_id) -> list[dict]
```

**Tests must cover:**
- Happy-path create/get/end/delete
- `end_session` on already-ended session raises
- `add_peers` / `remove_peer` on ended session raises
- `list_sessions` filter combinations (terminal_id, peer_terminal_id, involves, status, label, time range)
- `get_session_messages` retroactive peer filter: add peer mid-window, earlier in-window messages with that peer become visible
- Empty peer set = captures all I/O of the monitored terminal
- `involves=X` matches both `terminal_id=X` and `X in peers`
- Session still recording (`ended_at=NULL`): messages query bounded upper by "now"

**Acceptance:** service tests cover every behavioral decision above; run with in-memory SQLite.

### Phase 3 — HTTP API

**Files:**
- Modify: `src/cli_agent_orchestrator/api/main.py` — routes inline, matching
  the existing convention of decorating ``@app`` directly. An initial
  `APIRouter` split was reverted for consistency; if we later want split
  routers, do it as a codebase-wide refactor, not a one-off for this feature.
- Add: `test/api/test_monitoring_routes.py`

**Must confirm before implementing:** these routes are NOT registered as MCP tools.

**Tests must cover:**
- Each endpoint happy path (8 routes — `/log` deferred to Phase 4)
- 404 on missing session
- 409 on mutation of ended session
- 422 on malformed body (FastAPI's default for Pydantic validation failures)
- List pagination + filter combinations

**Acceptance:** full feature (minus `/log`) driveable from curl.

### Phase 4 — Artifact formatter + `/log` endpoint

**Files:**
- Add: `src/cli_agent_orchestrator/utils/monitoring_formatter.py` — pure
  transforms (`format_markdown`, `format_json`) belong in `utils/`, not
  `services/`. `services/*_service.py` is reserved for modules that
  coordinate state/DB/orchestration; a formatter is in the same family as
  `utils/template.py`.
- Add: `test/utils/test_monitoring_formatter.py`
- Modify: `src/cli_agent_orchestrator/api/main.py` — add `GET /log`
- Modify: `test/api/test_monitoring_routes.py` — add `/log` endpoint tests

**Functions:**
```
format_markdown(session: dict, messages: list[dict]) -> str
format_json(session: dict, messages: list[dict]) -> dict
```

**Markdown layout:**
```
# Monitoring session: {label or session_id}
**Monitored:** {terminal_id}
**Peers:** {peer list or "all"}
**Window:** {started_at} → {ended_at or "ongoing"}

---

**{timestamp} — {sender} → {recipient}**
> {message}
```

**Tests must cover:** golden markdown for representative input; JSON round-trip.

### Phase 5 — CLI wrapper

**Files:**
- Add: `src/cli_agent_orchestrator/cli/commands/monitor.py`
- Modify: `src/cli_agent_orchestrator/cli/main.py` to register the group
- Add: `test/cli/test_monitor_commands.py`

**Tests must cover:** each subcommand with `CliRunner` + mocked HTTP.

### Phase 6 — End-to-end verification + docs

- Live test: spin up `cao-server`, spawn two terminals, start monitoring, send messages via `assign`, end session, fetch markdown log, eyeball.
- Add `docs/monitoring.md` (or a section in an existing doc) with a short yards procedure example.
- No agent-facing docs (no agent surface).

## Review protocol

One reviewer per phase, spawned fresh each time. The reviewer:

1. Reads this plan document in full.
2. Reads the commits / working tree for the phase under review.
3. Checks:
   - Were tests written first (evidenced by test file present and covering the behavioral decisions listed for this phase)?
   - Does the implementation actually make the tests pass?
   - Does the code drift from the plan? If yes: is it a legitimate discovery that warrants updating the plan, or drift that should be corrected?
   - Are there behavioral decisions in the plan not covered by tests?
   - Any obvious bugs, security issues, or tight coupling to unrelated code?
4. Reports gaps as a punch list. Not a rubber stamp — reviewers must push back when the plan is underspecified or the implementation is weak.

Implementer addresses gaps. If the reviewer is wrong, the implementer pushes back and the disagreement surfaces to the user. If the plan is genuinely wrong, update the plan *and* the code in the same pass so the document stays canonical.

A phase is "done" when: tests green, reviewer has no open items, user has approved the commit.
