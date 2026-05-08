"""Tests for terminal inbox HTTP endpoints."""

from datetime import datetime
from unittest.mock import patch

import pytest

from cli_agent_orchestrator.models.inbox import (
    InboxDelivery,
    InboxMessageRecord,
    InboxNotification,
    MessageStatus,
)


@pytest.fixture
def sample_inbox_deliveries():
    """Create sample notification-backed inbox deliveries for endpoint tests."""
    return [
        InboxDelivery(
            message=InboxMessageRecord(
                id=11,
                sender_id="sender1",
                body="Hello world",
                source_kind="terminal",
                source_id="sender1",
                origin=None,
                route_kind=None,
                route_id=None,
                created_at=datetime(2026, 5, 7, 12, 0, 0),
            ),
            notification=InboxNotification(
                id=1,
                receiver_id="abcdef12",
                body="Hello world",
                source_kind="terminal",
                source_id="sender1",
                metadata=None,
                status=MessageStatus.PENDING,
                created_at=datetime(2026, 5, 7, 12, 0, 0),
            ),
        ),
        InboxDelivery(
            message=InboxMessageRecord(
                id=12,
                sender_id="sender2",
                body="Another message",
                source_kind="terminal",
                source_id="sender2",
                origin=None,
                route_kind=None,
                route_id=None,
                created_at=datetime(2026, 5, 7, 12, 5, 0),
            ),
            notification=InboxNotification(
                id=2,
                receiver_id="abcdef12",
                body="Another message",
                source_kind="terminal",
                source_id="sender2",
                metadata=None,
                status=MessageStatus.DELIVERED,
                created_at=datetime(2026, 5, 7, 12, 5, 0),
            ),
        ),
    ]


class TestGetInboxMessagesEndpoint:
    """GET /terminals/{terminal_id}/inbox/messages."""

    def test_get_all_messages_uses_semantic_deliveries(self, client, sample_inbox_deliveries):
        with patch("cli_agent_orchestrator.api.main.list_inbox_deliveries") as mock_list:
            mock_list.return_value = sample_inbox_deliveries

            response = client.get("/terminals/abcdef12/inbox/messages")

        assert response.status_code == 200
        data = response.json()
        assert data[0] == {
            "notification_id": 1,
            "message_id": 11,
            "sender_id": "sender1",
            "receiver_id": "abcdef12",
            "message": "Hello world",
            "source_kind": "terminal",
            "source_id": "sender1",
            "status": "pending",
            "created_at": "2026-05-07T12:00:00",
        }
        mock_list.assert_called_once_with("abcdef12", limit=10, status=None)

    def test_get_messages_with_status_and_limit(self, client, sample_inbox_deliveries):
        with patch("cli_agent_orchestrator.api.main.list_inbox_deliveries") as mock_list:
            mock_list.return_value = sample_inbox_deliveries[:1]

            response = client.get("/terminals/abcdef12/inbox/messages?status=pending&limit=5")

        assert response.status_code == 200
        assert len(response.json()) == 1
        mock_list.assert_called_once_with("abcdef12", limit=5, status=MessageStatus.PENDING)

    def test_invalid_status_parameter(self, client):
        response = client.get("/terminals/abcdef12/inbox/messages?status=invalid_status")

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_limit_exceeds_maximum(self, client):
        response = client.get("/terminals/abcdef12/inbox/messages?limit=150")

        assert response.status_code == 422

    def test_database_error_handling(self, client):
        with patch("cli_agent_orchestrator.api.main.list_inbox_deliveries") as mock_list:
            mock_list.side_effect = Exception("Database connection failed")

            response = client.get("/terminals/abcdef12/inbox/messages")

        assert response.status_code == 500
        assert "Failed to retrieve inbox messages" in response.json()["detail"]

    def test_terminal_not_found_error(self, client):
        with patch("cli_agent_orchestrator.api.main.list_inbox_deliveries") as mock_list:
            mock_list.side_effect = ValueError("Terminal not found")

            response = client.get("/terminals/deadbeef/inbox/messages")

        assert response.status_code == 404
        assert "Terminal not found" in response.json()["detail"]

    def test_empty_message_list(self, client):
        with patch("cli_agent_orchestrator.api.main.list_inbox_deliveries") as mock_list:
            mock_list.return_value = []

            response = client.get("/terminals/abcdef12/inbox/messages")

        assert response.status_code == 200
        assert response.json() == []


class TestCreateInboxMessageEndpoint:
    """POST /terminals/{receiver_id}/inbox/messages."""

    def test_create_message_returns_notification_and_durable_message_ids(self, client):
        delivery = InboxDelivery(
            message=InboxMessageRecord(
                id=41,
                sender_id="sender1",
                body="Hello world",
                source_kind="terminal",
                source_id="sender1",
                origin=None,
                route_kind=None,
                route_id=None,
                created_at=datetime(2026, 5, 7, 12, 0, 0),
            ),
            notification=InboxNotification(
                id=7,
                receiver_id="abcdef12",
                body="Hello world",
                source_kind="terminal",
                source_id="sender1",
                metadata=None,
                status=MessageStatus.PENDING,
                created_at=datetime(2026, 5, 7, 12, 0, 0),
            ),
        )
        with patch("cli_agent_orchestrator.api.main.create_inbox_delivery") as mock_create:
            with patch(
                "cli_agent_orchestrator.api.main.inbox_service.check_and_send_pending_messages"
            ) as mock_deliver:
                mock_create.return_value = delivery

                response = client.post(
                    "/terminals/abcdef12/inbox/messages",
                    params={"sender_id": "sender1", "message": "Hello world"},
                )

        assert response.status_code == 200
        body = response.json()
        assert body["notification_id"] == 7
        assert body["message_id"] == 41
        assert "id" not in body
        mock_create.assert_called_once_with("sender1", "abcdef12", "Hello world")
        mock_deliver.assert_called_once_with("abcdef12")
