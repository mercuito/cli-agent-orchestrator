"""Formatter for monitoring session artifacts.

Pure-function transforms from the shapes produced by ``monitoring_service``
(session dict + messages list) into a human-readable Markdown artifact or a
structured JSON payload. See ``docs/plans/monitoring-sessions.md`` for layout.

No DB or HTTP concerns live here. The ``/log`` endpoint in ``api/main.py``
calls these functions after fetching session and messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def _iso(ts: datetime) -> str:
    """ISO 8601 timestamp for display. No tz suffix since InboxModel stores
    naive datetimes — matching the format avoids presenting values with a
    timezone we don't actually know."""
    return ts.isoformat()


def _quote(text: str) -> str:
    """Prefix every line with ``> `` so multi-line messages render as a
    single blockquote. Normalizes CRLF / CR line endings so stray carriage
    returns (e.g., from Windows authors or raw tmux output) don't leak into
    the quoted block."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join("> " + line for line in normalized.split("\n"))


def format_markdown(session: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    """Render a monitoring session artifact as Markdown.

    The session dict is whatever ``monitoring_service.get_session`` returns;
    the messages list is what ``get_session_messages`` returns (and must
    already be in the desired order — this formatter does not reorder).
    """
    title = session.get("label") or session["id"]
    peer_ids = session.get("peer_terminal_ids") or []
    peers_line = ", ".join(peer_ids) if peer_ids else "all"
    ended_display = (
        _iso(session["ended_at"]) if session.get("ended_at") else "ongoing"
    )

    header = "\n".join(
        [
            f"# Monitoring session: {title}",
            f"**Monitored:** {session['terminal_id']}",
            f"**Peers:** {peers_line}",
            f"**Window:** {_iso(session['started_at'])} → {ended_display}",
            "",
            "---",
        ]
    )

    message_blocks = []
    for m in messages:
        block_header = (
            f"**{_iso(m['created_at'])} — {m['sender_id']} → {m['receiver_id']}**"
        )
        message_blocks.append(block_header + "\n" + _quote(m["message"]))

    # Blank line separates header from body; messages are separated by blank
    # lines; trailing newline so file writes end cleanly.
    if message_blocks:
        return header + "\n\n" + "\n\n".join(message_blocks) + "\n"
    return header + "\n"


def format_json(
    session: Dict[str, Any], messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Structured payload for programmatic consumers of the log artifact."""
    return {"session": session, "messages": messages}
