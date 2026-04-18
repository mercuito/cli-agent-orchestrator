"""Tests for monitoring_formatter under the single-session, query-time-filter
model. See docs/plans/monitoring-sessions.md.
"""

from __future__ import annotations

from datetime import datetime


def _session(**overrides):
    base = {
        "id": "sess-1",
        "terminal_id": "term-A",
        "label": None,
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
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(label="review-v2"), [])
        assert out.startswith("# Monitoring session: review-v2")

    def test_title_falls_back_to_session_id_when_no_label(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(label=None), [])
        assert out.startswith("# Monitoring session: sess-1")

    def test_header_includes_monitored_terminal(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(terminal_id="term-A"), [])
        assert "**Monitored:** term-A" in out

    def test_header_omits_peers_line_entirely(self):
        """Sessions no longer have peer sets — that line is gone from the
        header. When a query-time filter is applied, a separate Filter
        line appears instead."""
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [])
        assert "Peers:" not in out

    def test_window_shows_ongoing_when_not_ended(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(ended_at=None), [])
        assert "ongoing" in out

    def test_window_shows_ended_at_when_ended(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(
            _session(ended_at=datetime(2026, 4, 18, 11, 0, 0)), []
        )
        assert "2026-04-18T11:00:00" in out
        assert "ongoing" not in out


class TestMarkdownFilterLine:
    """When a query-time filter is applied, the artifact must say so —
    otherwise a slice of a recording could be mistaken for the whole
    thing."""

    def test_no_filter_omits_filter_line(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [])
        assert "Filter:" not in out

    def test_none_filter_omits_filter_line(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [], applied_filter=None)
        assert "Filter:" not in out

    def test_peer_filter_renders(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(
            _session(), [], applied_filter={"peers": ["R1", "R2"]}
        )
        assert "**Filter:** peers = R1, R2" in out

    def test_time_window_filter_renders(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(
            _session(),
            [],
            applied_filter={
                "started_after": datetime(2026, 4, 18, 10, 5),
                "started_before": datetime(2026, 4, 18, 10, 10),
            },
        )
        assert "after 2026-04-18T10:05:00" in out
        assert "before 2026-04-18T10:10:00" in out

    def test_peer_and_time_combined(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(
            _session(),
            [],
            applied_filter={
                "peers": ["R1"],
                "started_after": datetime(2026, 4, 18, 10, 5),
            },
        )
        assert "peers = R1" in out
        assert "after 2026-04-18T10:05:00" in out

    def test_empty_applied_filter_treated_as_no_filter(self):
        """A filter dict with only None/empty values still shouldn't render
        a dangling 'Filter:' line."""
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(
            _session(),
            [],
            applied_filter={"peers": None, "started_after": None, "started_before": None},
        )
        assert "Filter:" not in out


class TestMarkdownMessages:
    def test_empty_messages_still_produces_header(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [])
        assert out.startswith("# Monitoring session:")

    def test_single_message_rendering(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

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
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        msg = _msg(message="line one\nline two\nline three")
        out = format_markdown(_session(), [msg])
        assert "> line one\n> line two\n> line three" in out

    def test_messages_separated_by_blank_line(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        m1 = _msg(id=1, message="first")
        m2 = _msg(id=2, message="second")
        out = format_markdown(_session(), [m1, m2])
        assert "> first\n\n**" in out

    def test_messages_emitted_in_order_received(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        m_early = _msg(id=1, message="early", created_at=datetime(2026, 4, 18, 10, 0, 1))
        m_late = _msg(id=2, message="late", created_at=datetime(2026, 4, 18, 10, 0, 9))
        out = format_markdown(_session(), [m_late, m_early])
        assert out.index("late") < out.index("early")


class TestMarkdownGolden:
    def test_full_layout_no_filter(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        session = _session(
            label="review-doc-v2",
            terminal_id="IMP",
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

    def test_full_layout_with_filter(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        session = _session(label="review", terminal_id="IMP", ended_at=None)
        messages = [_msg(sender_id="IMP", receiver_id="R1", message="hi")]
        out = format_markdown(
            session, messages, applied_filter={"peers": ["R1"]}
        )
        assert "**Filter:** peers = R1" in out
        assert "> hi" in out


class TestMarkdownRobustness:
    def test_crlf_normalized_to_lf(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [_msg(message="line one\r\nline two")])
        assert "\r" not in out
        assert "> line one\n> line two" in out

    def test_lone_cr_normalized_to_lf(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [_msg(message="a\rb")])
        assert "\r" not in out
        assert "> a\n> b" in out

    def test_empty_message_body(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(), [_msg(message="")])
        assert "> " in out

    def test_label_containing_markdown_syntax_preserved_verbatim(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        out = format_markdown(_session(label="**bold** `code`"), [])
        assert "# Monitoring session: **bold** `code`" in out

    def test_very_long_message_not_truncated(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_markdown

        long_body = "x" * 10_000
        out = format_markdown(_session(), [_msg(message=long_body)])
        assert f"> {long_body}" in out


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestJsonFormat:
    def test_structure_has_session_and_messages_keys_by_default(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        out = format_json(_session(), [_msg()])
        assert set(out.keys()) == {"session", "messages"}

    def test_session_block_is_passthrough(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        sess = _session(label="x")
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

    def test_filter_block_omitted_when_no_filter(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        assert "filter" not in format_json(_session(), [])
        assert "filter" not in format_json(_session(), [], applied_filter=None)

    def test_filter_block_included_when_filter_applied(self):
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        out = format_json(
            _session(), [], applied_filter={"peers": ["R1"]}
        )
        assert out["filter"] == {"peers": ["R1"]}

    def test_all_none_filter_treated_as_no_filter(self):
        """Must match the markdown formatter's contract: a filter dict
        whose every value is None/empty is equivalent to no filter. Keeps
        the two renderers honest."""
        from cli_agent_orchestrator.utils.monitoring_formatter import format_json

        out = format_json(
            _session(),
            [],
            applied_filter={"peers": None, "started_after": None, "started_before": None},
        )
        assert "filter" not in out
