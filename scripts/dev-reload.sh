#!/usr/bin/env bash
# Rebuild web and restart cao-server when relevant files have changed since
# the last invocation. Invoked by the Claude Code Stop hook in
# .claude/settings.json (and runnable manually).
#
# Marker lives in .git/ so it's automatically untracked and survives across
# Claude Code sessions but resets if the repo is re-cloned.
#
# Reads any input on stdin (the Claude hook input JSON) and discards it.
# Emits a {"systemMessage": "..."} JSON line on stdout when it took action so
# Claude surfaces a brief summary in the UI.

set -euo pipefail

# Always operate from the repo root regardless of how we were invoked.
if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  exit 0
fi
cd "$REPO_ROOT"

MARKER=".git/cao-last-deploy-commit"
CAO_SERVER_BIN="${REPO_ROOT}/.venv/bin/cao-server"
CAO_SERVER_ARGS=(--host 127.0.0.1 --port 9889)

# Drain stdin (hook input JSON) — we don't use it.
cat >/dev/null 2>&1 || true

HEAD="$(git rev-parse HEAD 2>/dev/null || true)"
[ -z "$HEAD" ] && exit 0

LAST="$(cat "$MARKER" 2>/dev/null || true)"

if [ "$HEAD" = "$LAST" ]; then
  exit 0
fi

if [ -z "$LAST" ] || ! git cat-file -e "$LAST" 2>/dev/null; then
  RANGE="HEAD~1..HEAD"
else
  RANGE="${LAST}..HEAD"
fi

CHANGED="$(git diff --name-only "$RANGE" 2>/dev/null || git diff --name-only HEAD~1..HEAD 2>/dev/null || true)"

WEB_CHANGED=0
PY_CHANGED=0
if echo "$CHANGED" | grep -qE '^(web/src/|web/package\.json|web/vite\.config|web/tsconfig)'; then
  WEB_CHANGED=1
fi
if echo "$CHANGED" | grep -qE '^src/cli_agent_orchestrator/'; then
  PY_CHANGED=1
fi

ACTIONS=()

if [ "$WEB_CHANGED" = 1 ]; then
  if (cd web && npm run build > /tmp/cao-dev-reload-web.log 2>&1); then
    ACTIONS+=("rebuilt web")
  else
    printf '{"systemMessage":"cao dev-reload: web rebuild FAILED — see /tmp/cao-dev-reload-web.log"}\n'
    # Don't update marker so the next run retries.
    exit 0
  fi
fi

if [ "$PY_CHANGED" = 1 ]; then
  PID="$(pgrep -f '\.venv/bin/cao-server' | head -1 || true)"
  if [ -n "$PID" ]; then
    kill -TERM "$PID" 2>/dev/null || true
    # Wait up to 3s for graceful exit.
    for _ in 1 2 3 4 5 6; do
      if ! kill -0 "$PID" 2>/dev/null; then break; fi
      sleep 0.5
    done
    if kill -0 "$PID" 2>/dev/null; then
      kill -KILL "$PID" 2>/dev/null || true
    fi
    if [ -x "$CAO_SERVER_BIN" ]; then
      nohup "$CAO_SERVER_BIN" "${CAO_SERVER_ARGS[@]}" > /tmp/cao-server.log 2>&1 &
      disown
      ACTIONS+=("restarted cao-server (was PID $PID)")
    else
      ACTIONS+=("backend changed; cao-server killed but binary at $CAO_SERVER_BIN missing — restart manually")
    fi
  else
    ACTIONS+=("backend changed; no running cao-server detected — skipped restart")
  fi
fi

echo "$HEAD" > "$MARKER"

if [ ${#ACTIONS[@]} -gt 0 ]; then
  MSG="cao dev-reload: $(IFS='; '; echo "${ACTIONS[*]}")"
  # Escape any double quotes in the message before embedding.
  ESCAPED_MSG="${MSG//\"/\\\"}"
  printf '{"systemMessage":"%s"}\n' "$ESCAPED_MSG"
fi
