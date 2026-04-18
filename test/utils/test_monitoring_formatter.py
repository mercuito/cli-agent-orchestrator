"""Tests for monitoring_formatter.

Phase 4 of the monitoring sessions feature. See docs/plans/monitoring-sessions.md.

Pure-function tests — no DB, no HTTP. Formatter input shapes match what the
service layer returns (session dict + messages list).
"""

from __future__ import annotations

from datetime import datetime

import pytest


def _session(**overrides):
    base = {
        "id": "sess-1",
        "terminal_id": "term-A",
        "label": None,
        "peer_terminal_ids": [],
        "started_at": datetime(2026, 4, 18, 10, 0, 0),
        "ended_at": None,
        "status": "active",
    }
    base.update(overrides)
    return base


def _msg(**overrides):
    base = {
        "id": 1,
        "sender_id": "A",
        "receiver_id": "B",
        "message": "hello",
        "status": "DELIVERED",
        "created_at": datetime(2026, 4, 18, 10, 0, 5),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------


class TestMarkdownHeader:
    def test_title_uses_label_when_present(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(label="review-v2"), [])
        assert out.startswith("# Monitoring session: review-v2")

    def test_title_falls_back_to_session_id_when_no_label(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(label=None), [])
        assert out.startswith("# Monitoring session: sess-1")

    def test_header_includes_monitored_terminal(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(terminal_id="term-A"), [])
        assert "**Monitored:** term-A" in out

    def test_peers_line_shows_all_when_empty(self):
        """Design decision #4: empty peer set = captures all peers."""
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(peer_terminal_ids=[]), [])
        assert "**Peers:** all" in out

    def test_peers_line_lists_peer_ids_when_scoped(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(peer_terminal_ids=["P1", "P2"]), [])
        assert "**Peers:** P1, P2" in out

    def test_window_shows_ongoing_when_not_ended(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(ended_at=None), [])
        assert "ongoing" in out
        assert "2026-04-18T10:00:00" in out  # started_at

    def test_window_shows_ended_at_when_ended(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(
            _session(ended_at=datetime(2026, 4, 18, 11, 0, 0)), []
        )
        assert "2026-04-18T11:00:00" in out
        assert "ongoing" not in out


class TestMarkdownMessages:
    def test_empty_messages_still_produces_header(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        out = format_markdown(_session(), [])
        # Header present, no message block
        assert out.startswith("# Monitoring session:")
        assert "—" not in out.split("---")[-1]  # no message lines after divider

    def test_single_message_rendering(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        msg = _msg(
            sender_id="A",
            receiver_id="B",
            message="hi",
            created_at=datetime(2026, 4, 18, 10, 0, 5),
        )
        out = format_markdown(_session(), [msg])
        assert "**2026-04-18T10:00:05 — A → B**" in out
        assert "> hi" in out

    def test_multiline_message_each_line_blockquoted(self):
        """Each line of a multi-line message must be prefixed with ``> ``,
        otherwise Markdown renders only the first line as quote and the rest
        as body text — breaking the intended grouping."""
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        msg = _msg(message="line one\nline two\nline three")
        out = format_markdown(_session(), [msg])
        assert "> line one\n> line two\n> line three" in out

    def test_messages_separated_by_blank_line(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        m1 = _msg(id=1, message="first")
        m2 = _msg(id=2, message="second")
        out = format_markdown(_session(), [m1, m2])
        # A blank line between the two message blocks
        assert "> first\n\n**" in out

    def test_messages_are_emitted_in_order_received(self):
        """The formatter does not reorder — ordering is the service's job."""
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        m_early = _msg(id=1, message="early", created_at=datetime(2026, 4, 18, 10, 0, 1))
        m_late = _msg(id=2, message="late", created_at=datetime(2026, 4, 18, 10, 0, 9))

        # Reversed list — formatter should emit them in the order given,
        # trusting the service layer.
        out = format_markdown(_session(), [m_late, m_early])
        assert out.index("late") < out.index("early")


class TestMarkdownGolden:
    """One end-to-end golden-file assertion pinning the overall shape so
    small accidental reformats break loudly."""

    def test_full_layout(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import (
            format_markdown,
        )

        session = _session(
            label="review-doc-v2",
            terminal_id="IMP",
            peer_terminal_ids=["R1", "R2"],
            started_at=datetime(2026, 4, 18, 10, 0, 0),
            ended_at=datetime(2026, 4, 18, 10, 5, 0),
            status="ended",
        )
        messages = [
            _msg(
                id=1,
                sender_id="IMP",
                receiver_id="R1",
                message="Please review section 3.",
                created_at=datetime(2026, 4, 18, 10, 0, 30),
            ),
            _msg(
                id=2,
                sender_id="R1",
                receiver_id="IMP",
                message="Looks good,\nbut check the edge case on line 42.",
                created_at=datetime(2026, 4, 18, 10, 2, 15),
            ),
        ]

        out = format_markdown(session, messages)
        expected = (
            "# Monitoring session: review-doc-v2\n"
            "**Monitored:** IMP\n"
            "**Peers:** R1, R2\n"
            "**Window:** 2026-04-18T10:00:00 → 2026-04-18T10:05:00\n"
            "\n"
            "---\n"
            "\n"
            "**2026-04-18T10:00:30 — IMP → R1**\n"
            "> Please review section 3.\n"
            "\n"
            "**2026-04-18T10:02:15 — R1 → IMP**\n"
            "> Looks good,\n"
            "> but check the edge case on line 42.\n"
        )
        assert out == expected


# ---------------------------------------------------------------------------
# Robustness against weird message bodies
# ---------------------------------------------------------------------------


class TestMarkdownRobustness:
    """The formatter is rendering arbitrary agent-authored strings. Keep the
    structural output sane for the common annoying cases."""

    def test_crlf_normalized_to_lf(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        msg = _msg(message="line one\r\nline two")
        out = format_markdown(_session(), [msg])
        assert "\r" not in out
        assert "> line one\n> line two" in out

    def test_lone_cr_normalized_to_lf(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        msg = _msg(message="a\rb")  # old-Mac style
        out = format_markdown(_session(), [msg])
        assert "\r" not in out
        assert "> a\n> b" in out

    def test_empty_message_body(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        msg = _msg(message="")
        out = format_markdown(_session(), [msg])
        assert "**2026-04-18T10:00:05 — A → B**" in out
        assert "> " in out

    def test_whitespace_only_message(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        msg = _msg(message="   ")
        out = format_markdown(_session(), [msg])
        assert ">    " in out

    def test_label_containing_markdown_syntax_preserved_verbatim(self):
        """We deliberately do not escape. The artifact is not a security
        boundary; reviewers read it raw. Document this behavior so a future
        change doesn't silently start escaping."""
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(label="**bold** `code`"), [])
        assert "# Monitoring session: **bold** `code`" in out

    def test_very_long_message_not_truncated(self):
        """The formatter does not truncate. Truncation, if ever needed,
        belongs in a later layer so the raw record stays complete."""
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        long_body = "x" * 10_000
        out = format_markdown(_session(), [_msg(message=long_body)])
        assert f"> {long_body}" in out


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestJsonFormat:
    def test_structure_has_session_and_messages_keys(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        out = format_json(_session(), [_msg()])
        assert set(out.keys()) == {"session", "messages"}

    def test_session_block_is_passthrough(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        sess = _session(label="x", peer_terminal_ids=["P1"])
        out = format_json(sess, [])
        assert out["session"] == sess

    def test_messages_block_is_passthrough(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        msgs = [_msg(id=1), _msg(id=2)]
        out = format_json(_session(), msgs)
        assert out["messages"] == msgs

    def test_empty_messages(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        out = format_json(_session(), [])
        assert out["messages"] == []
