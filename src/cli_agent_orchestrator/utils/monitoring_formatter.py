"""Formatter for monitoring session artifacts.

Pure-function transforms from the shapes produced by ``monitoring_service``
(session dict + messages list) into a human-readable Markdown artifact or a
structured JSON payload. See ``docs/plans/monitoring-sessions.md`` for layout.

Sessions under the current model record everything involving a terminal;
filtering (by peer, by time sub-window) happens at read time. When a filter
was applied, the artifact records that in its header so a reader knows they
are looking at a slice of a larger recording, not the whole thing.

No DB or HTTP concerns live here. The ``/log`` endpoint in ``api/main.py``
calls these functions after fetching session and messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def _iso(ts: datetime) -> str:
    """ISO 8601 timestamp for display."""
    return ts.isoformat()


def _quote(text: str) -> str:
    """Prefix every line with ``> `` so multi-line messages render as a
    single blockquote. Normalizes CRLF / CR line endings so stray carriage
    returns don't leak into the quoted block."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join("> " + line for line in normalized.split("\n"))


def _filter_description(applied_filter: Optional[Dict[str, Any]]) -> Optional[str]:
    """Render the applied query-time filter as a human-readable string,
    or return None if no filter was applied."""
    if not applied_filter:
        return None
    parts: List[str] = []
    peers = applied_filter.get("peers")
    if peers:
        parts.append(f"peers = {', '.join(peers)}")
    after = applied_filter.get("started_after")
    if after is not None:
        parts.append(f"after {_iso(after)}")
    before = applied_filter.get("started_before")
    if before is not None:
        parts.append(f"before {_iso(before)}")
    return "; ".join(parts) if parts else None


def format_markdown(
    session: Dict[str, Any],
    messages: List[Dict[str, Any]],
    applied_filter: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a monitoring session artifact as Markdown.

    The session dict is whatever ``monitoring_service.get_session`` returns;
    the messages list is what ``get_session_messages`` returns (and must
    already be in the desired order — this formatter does not reorder).
    When ``applied_filter`` is provided, a "Filter:" line is added to the
    header so the artifact self-describes what slice it represents.
    """
    title = session.get("label") or session["id"]
    ended_display = (
        _iso(session["ended_at"]) if session.get("ended_at") else "ongoing"
    )

    header_lines = [
        f"# Monitoring session: {title}",
        f"**Monitored:** {session['terminal_id']}",
        f"**Window:** {_iso(session['started_at'])} → {ended_display}",
    ]
    filter_str = _filter_description(applied_filter)
    if filter_str:
        header_lines.append(f"**Filter:** {filter_str}")

    header = "\n".join(header_lines) + "\n\n---"

    message_blocks = []
    for m in messages:
        block_header = (
            f"**{_iso(m['created_at'])} — {m['sender_id']} → {m['receiver_id']}**"
        )
        message_blocks.append(block_header + "\n" + _quote(m["message"]))

    if message_blocks:
        return header + "\n\n" + "\n\n".join(message_blocks) + "\n"
    return header + "\n"


def format_json(
    session: Dict[str, Any],
    messages: List[Dict[str, Any]],
    applied_filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured payload for programmatic consumers of the log artifact.

    Includes ``filter`` only when one was meaningfully applied (has at
    least one non-None field). A dict of all-None values is treated the
    same as ``None`` — same contract as the markdown formatter, so both
    renderers stay in sync.
    """
    payload: Dict[str, Any] = {"session": session, "messages": messages}
    if _filter_description(applied_filter) is not None:
        payload["filter"] = applied_filter
    return payload
