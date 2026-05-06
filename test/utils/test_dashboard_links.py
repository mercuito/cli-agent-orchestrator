from cli_agent_orchestrator.utils import dashboard_links


def test_terminal_dashboard_token_validates_for_same_terminal(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    token = dashboard_links.create_terminal_dashboard_token("term-1", now=100, ttl_seconds=60)

    assert dashboard_links.validate_terminal_dashboard_token(token, "term-1", now=120)


def test_terminal_dashboard_token_rejects_wrong_terminal(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    token = dashboard_links.create_terminal_dashboard_token("term-1", now=100, ttl_seconds=60)

    assert not dashboard_links.validate_terminal_dashboard_token(token, "term-2", now=120)


def test_terminal_dashboard_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    token = dashboard_links.create_terminal_dashboard_token("term-1", now=100, ttl_seconds=60)

    assert not dashboard_links.validate_terminal_dashboard_token(token, "term-1", now=161)


def test_terminal_dashboard_token_rejects_malformed_token(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    assert not dashboard_links.validate_terminal_dashboard_token("not-a-token", "term-1", now=120)
    assert not dashboard_links.validate_terminal_dashboard_token("bad.payload", "term-1", now=120)


def test_terminal_dashboard_token_rejects_tampered_signature(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")
    token = dashboard_links.create_terminal_dashboard_token("term-1", now=100, ttl_seconds=60)
    payload, _signature = token.split(".", 1)

    assert not dashboard_links.validate_terminal_dashboard_token(
        f"{payload}.bad", "term-1", now=120
    )


def test_agent_dashboard_token_validates_for_same_agent(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    token = dashboard_links.create_agent_dashboard_token("discovery_partner", now=100)

    assert dashboard_links.validate_agent_dashboard_token(
        token, "discovery_partner", now=120
    )


def test_agent_dashboard_token_rejects_wrong_agent(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    token = dashboard_links.create_agent_dashboard_token("discovery_partner", now=100)

    assert not dashboard_links.validate_agent_dashboard_token(
        token, "implementation_partner", now=120
    )


def test_agent_dashboard_token_rejects_terminal_token(monkeypatch):
    monkeypatch.setattr(dashboard_links, "_dashboard_link_secret", lambda: b"test-secret")

    token = dashboard_links.create_terminal_dashboard_token("discovery_partner", now=100)

    assert not dashboard_links.validate_agent_dashboard_token(
        token, "discovery_partner", now=120
    )
