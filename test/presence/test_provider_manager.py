"""Tests for provider-neutral presence provider contracts and routing."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Mapping, Optional

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import Base
from cli_agent_orchestrator.presence.manager import (
    DuplicatePresenceProviderError,
    PresenceProviderManager,
    PresenceProviderMismatchError,
    UnknownPresenceProviderError,
    presence_provider_manager,
)
from cli_agent_orchestrator.presence.models import (
    ConversationMessage,
    ConversationThread,
    ExternalRef,
    MessageKind,
    PresenceEvent,
    StopAcknowledgement,
    WorkItem,
)
from cli_agent_orchestrator.presence.persistence import get_processed_event, get_thread


def _test_session(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(bind=engine))


class WorkspaceStyleProvider:
    """Fake provider shaped like a dedicated external work conversation service."""

    def __init__(self, name: str = "workspace") -> None:
        self.name = name
        self.thread = ConversationThread(
            ref=ExternalRef(provider=name, id="thread-1", url=f"https://{name}/thread-1"),
            work_item=WorkItem(
                ref=ExternalRef(provider=name, id="work-1"),
                identifier="WORK-1",
                title="Workspace task",
            ),
        )
        self.messages = [
            ConversationMessage(
                kind="prompt",
                body="Please take this task",
                ref=ExternalRef(provider=name, id="message-1"),
            )
        ]
        self.replies: List[Dict[str, Any]] = []
        self.stop_requests: List[Dict[str, Any]] = []

    def normalize_event(
        self,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        if raw_event.get("ignore"):
            return None

        thread_id = str(raw_event["thread"]["id"])
        work = raw_event.get("work")
        message = raw_event.get("message")
        thread = ConversationThread(
            ref=ExternalRef(provider=self.name, id=thread_id),
            work_item=(
                WorkItem(
                    ref=ExternalRef(provider=self.name, id=str(work["id"])),
                    identifier=str(work.get("identifier")),
                    title=str(work.get("title")),
                )
                if isinstance(work, Mapping)
                else None
            ),
        )
        return PresenceEvent(
            provider=self.name,
            event_type=str(raw_event.get("type", "thread_event")),
            action=str(raw_event.get("action")) if raw_event.get("action") else None,
            thread=thread,
            message=(
                ConversationMessage(
                    kind="prompt",
                    body=str(message.get("body")),
                    ref=ExternalRef(provider=self.name, id=str(message["id"])),
                )
                if isinstance(message, Mapping)
                else None
            ),
            delivery_id=delivery_id,
            raw_payload=dict(raw_event),
        )

    def fetch_thread(self, thread_ref: ExternalRef) -> ConversationThread:
        return ConversationThread(
            ref=thread_ref,
            work_item=self.thread.work_item,
            kind=self.thread.kind,
            state=self.thread.state,
            prompt_context=self.thread.prompt_context,
        )

    def fetch_messages(self, thread_ref: ExternalRef) -> List[ConversationMessage]:
        return list(self.messages)

    def reply_to_thread(
        self,
        thread_ref: ExternalRef,
        body: str,
        *,
        kind: MessageKind = "response",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ConversationMessage:
        self.replies.append(
            {"thread_ref": thread_ref, "body": body, "kind": kind, "metadata": metadata}
        )
        return ConversationMessage(
            kind=kind,
            body=body,
            ref=ExternalRef(provider=self.name, id=f"reply-{len(self.replies)}"),
            direction="outbound",
            state="delivered",
        )

    def acknowledge_stop(
        self,
        thread_ref: ExternalRef,
        *,
        message_ref: Optional[ExternalRef] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> StopAcknowledgement:
        self.stop_requests.append(
            {
                "thread_ref": thread_ref,
                "message_ref": message_ref,
                "reason": reason,
                "metadata": metadata,
            }
        )
        return StopAcknowledgement(
            thread_ref=thread_ref,
            supported=True,
            message=ConversationMessage(
                kind="response",
                body=reason,
                ref=ExternalRef(provider=self.name, id=f"stop-{len(self.stop_requests)}"),
                direction="outbound",
                state="acknowledged",
            ),
        )


class TicketStyleProvider(WorkspaceStyleProvider):
    """Fake provider shaped like issue comments where stop is unsupported."""

    def __init__(self, name: str = "tickets") -> None:
        super().__init__(name)
        self.thread = ConversationThread(
            ref=ExternalRef(provider=name, id="discussion-1"),
            work_item=WorkItem(
                ref=ExternalRef(provider=name, id="ticket-1"),
                identifier="TICK-1",
                title="Ticket task",
            ),
            kind="work_item_discussion",
        )
        self.messages = [
            ConversationMessage(
                kind="comment",
                body="Ticket comment",
                ref=ExternalRef(provider=name, id="comment-1"),
            )
        ]

    def normalize_event(
        self,
        raw_event: Mapping[str, Any],
        *,
        delivery_id: Optional[str] = None,
    ) -> Optional[PresenceEvent]:
        ticket = raw_event.get("ticket")
        comment = raw_event.get("comment")
        if not isinstance(ticket, Mapping):
            return None

        thread_id = str(ticket.get("discussion_id", ticket["id"]))
        return PresenceEvent(
            provider=self.name,
            event_type=str(raw_event.get("event", "ticket_comment")),
            action=str(raw_event.get("action")) if raw_event.get("action") else None,
            thread=ConversationThread(
                ref=ExternalRef(provider=self.name, id=thread_id),
                work_item=WorkItem(
                    ref=ExternalRef(provider=self.name, id=str(ticket["id"])),
                    identifier=str(ticket.get("key")),
                    title=str(ticket.get("summary")),
                ),
                kind="work_item_discussion",
            ),
            message=(
                ConversationMessage(
                    kind="comment",
                    body=str(comment.get("body")),
                    ref=ExternalRef(provider=self.name, id=str(comment["id"])),
                )
                if isinstance(comment, Mapping)
                else None
            ),
            delivery_id=delivery_id,
            raw_payload=dict(raw_event),
        )

    def acknowledge_stop(
        self,
        thread_ref: ExternalRef,
        *,
        message_ref: Optional[ExternalRef] = None,
        reason: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> StopAcknowledgement:
        return StopAcknowledgement(
            thread_ref=thread_ref,
            supported=False,
            reason="stop acknowledgement is not supported by this provider",
        )


@pytest.fixture
def singleton_registry():
    presence_provider_manager.clear_providers()
    yield presence_provider_manager
    presence_provider_manager.clear_providers()


def test_register_and_lookup_provider_by_name():
    provider = WorkspaceStyleProvider()
    manager = PresenceProviderManager()

    assert manager.register_provider("workspace", provider) is provider
    assert manager.get_provider("workspace") is provider
    assert manager.list_providers() == ["workspace"]


def test_duplicate_registration_requires_explicit_replacement():
    first = WorkspaceStyleProvider()
    replacement = WorkspaceStyleProvider()
    manager = PresenceProviderManager()
    manager.register_provider("workspace", first)

    with pytest.raises(DuplicatePresenceProviderError, match="already registered"):
        manager.register_provider("workspace", replacement)

    manager.register_provider("workspace", replacement, replace=True)

    assert manager.get_provider("workspace") is replacement


def test_unknown_provider_lookup_and_routes_fail_clearly():
    manager = PresenceProviderManager()

    with pytest.raises(UnknownPresenceProviderError, match="Unknown presence provider: missing"):
        manager.get_provider("missing")
    with pytest.raises(UnknownPresenceProviderError, match="Unknown presence provider: missing"):
        manager.reply_to_thread(ExternalRef(provider="missing", id="thread-1"), "hello")


def test_reply_to_thread_routes_by_external_ref_provider():
    workspace = WorkspaceStyleProvider("workspace")
    tickets = TicketStyleProvider("tickets")
    manager = PresenceProviderManager({"workspace": workspace, "tickets": tickets})

    reply = manager.reply_to_thread(
        ExternalRef(provider="tickets", id="discussion-1"),
        "I am on it",
        kind="comment",
    )

    assert reply.ref == ExternalRef(provider="tickets", id="reply-1")
    assert workspace.replies == []
    assert tickets.replies[0]["body"] == "I am on it"


def test_fetch_thread_and_messages_route_by_external_ref_provider():
    workspace = WorkspaceStyleProvider("workspace")
    tickets = TicketStyleProvider("tickets")
    manager = PresenceProviderManager({"workspace": workspace, "tickets": tickets})

    thread = manager.fetch_thread(ExternalRef(provider="tickets", id="discussion-1"))
    messages = manager.fetch_messages(ExternalRef(provider="tickets", id="discussion-1"))

    assert thread.kind == "work_item_discussion"
    assert messages[0].kind == "comment"


def test_provider_normalized_event_ingestion_persists_neutral_records(monkeypatch):
    _test_session(monkeypatch)
    provider = WorkspaceStyleProvider("workspace")
    manager = PresenceProviderManager({"workspace": provider})

    persisted = manager.ingest_event(
        "workspace",
        {
            "type": "thread_event",
            "action": "message_added",
            "thread": {"id": "thread-1"},
            "work": {"id": "work-1", "identifier": "WORK-1", "title": "Task"},
            "message": {"id": "message-1", "body": "Please take this task"},
        },
        delivery_id="delivery-1",
    )
    repeated = manager.ingest_event(
        "workspace",
        {
            "type": "thread_event",
            "action": "message_added",
            "thread": {"id": "thread-1"},
            "work": {"id": "work-1", "identifier": "WORK-1", "title": "Task"},
            "message": {"id": "message-1", "body": "Please take this task"},
        },
        delivery_id="delivery-1",
    )

    assert persisted is not None
    assert persisted.thread is not None
    assert persisted.message is not None
    assert get_thread("workspace", "thread-1").external_id == "thread-1"
    assert get_processed_event("workspace", "delivery-1").event_type == "thread_event"
    assert repeated is not None
    assert repeated.thread is None


def test_ingest_event_rejects_events_normalized_for_another_provider(monkeypatch):
    _test_session(monkeypatch)

    class MismatchedProvider(WorkspaceStyleProvider):
        def normalize_event(
            self,
            raw_event: Mapping[str, Any],
            *,
            delivery_id: Optional[str] = None,
        ) -> Optional[PresenceEvent]:
            event = super().normalize_event(raw_event, delivery_id=delivery_id)
            assert event is not None
            return replace(event, provider="tickets")

    manager = PresenceProviderManager({"workspace": MismatchedProvider("workspace")})

    with pytest.raises(
        PresenceProviderMismatchError,
        match="Provider workspace normalized event for provider tickets",
    ):
        manager.ingest_event(
            "workspace",
            {"thread": {"id": "thread-1"}},
            delivery_id="delivery-1",
        )

    assert get_processed_event("workspace", "delivery-1") is None


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("thread", "thread ref"),
        ("work_item", "work item ref"),
        ("message", "message ref"),
    ],
)
def test_ingest_event_rejects_nested_refs_for_another_provider(
    monkeypatch,
    field,
    expected,
):
    _test_session(monkeypatch)

    class MismatchedNestedRefProvider(WorkspaceStyleProvider):
        def normalize_event(
            self,
            raw_event: Mapping[str, Any],
            *,
            delivery_id: Optional[str] = None,
        ) -> Optional[PresenceEvent]:
            event = super().normalize_event(raw_event, delivery_id=delivery_id)
            assert event is not None
            assert event.thread is not None

            if field == "thread":
                thread = replace(
                    event.thread,
                    ref=ExternalRef(provider="tickets", id=event.thread.ref.id),
                )
                return replace(event, thread=thread)
            if field == "work_item":
                assert event.thread.work_item is not None
                work_item = replace(
                    event.thread.work_item,
                    ref=ExternalRef(provider="tickets", id=event.thread.work_item.ref.id),
                )
                return replace(event, thread=replace(event.thread, work_item=work_item))

            assert event.message is not None
            assert event.message.ref is not None
            message = replace(
                event.message,
                ref=ExternalRef(provider="tickets", id=event.message.ref.id),
            )
            return replace(event, message=message)

    manager = PresenceProviderManager({"workspace": MismatchedNestedRefProvider("workspace")})

    with pytest.raises(
        PresenceProviderMismatchError,
        match=f"Provider workspace normalized {expected} for provider tickets",
    ):
        manager.ingest_event(
            "workspace",
            {
                "thread": {"id": "thread-1"},
                "work": {"id": "work-1", "identifier": "WORK-1", "title": "Task"},
                "message": {"id": "message-1", "body": "Please take this task"},
            },
            delivery_id="delivery-1",
        )

    assert get_processed_event("workspace", "delivery-1") is None
    assert get_thread("tickets", "thread-1") is None


def test_stop_acknowledgement_can_be_supported_or_explicitly_unsupported():
    workspace = WorkspaceStyleProvider("workspace")
    tickets = TicketStyleProvider("tickets")
    manager = PresenceProviderManager({"workspace": workspace, "tickets": tickets})

    supported = manager.acknowledge_stop(
        ExternalRef(provider="workspace", id="thread-1"),
        message_ref=ExternalRef(provider="workspace", id="message-1"),
        reason="Stopping now",
    )
    unsupported = manager.acknowledge_stop(ExternalRef(provider="tickets", id="discussion-1"))

    assert supported.supported is True
    assert supported.message is not None
    assert unsupported.supported is False
    assert "not supported" in unsupported.reason


def test_singleton_registry_can_be_cleared_for_test_isolation(singleton_registry):
    singleton_registry.register_provider("workspace", WorkspaceStyleProvider("workspace"))
    assert singleton_registry.list_providers() == ["workspace"]

    singleton_registry.clear_providers()

    assert singleton_registry.list_providers() == []
    with pytest.raises(UnknownPresenceProviderError):
        singleton_registry.get_provider("workspace")


def test_singleton_registry_fixture_starts_empty_after_previous_test(singleton_registry):
    assert singleton_registry.list_providers() == []


def test_two_provider_input_shapes_use_the_same_generic_interface():
    workspace = WorkspaceStyleProvider("workspace")
    tickets = TicketStyleProvider("tickets")
    manager = PresenceProviderManager({"workspace": workspace, "tickets": tickets})

    workspace_event = manager.normalize_event(
        "workspace",
        {
            "thread": {"id": "thread-1"},
            "work": {"id": "work-1", "identifier": "WORK-1", "title": "Task"},
            "message": {"id": "message-1", "body": "Workspace body"},
        },
    )
    ticket_event = manager.normalize_event(
        "tickets",
        {
            "ticket": {
                "id": "ticket-1",
                "discussion_id": "discussion-1",
                "key": "TICK-1",
                "summary": "Ticket task",
            },
            "comment": {"id": "comment-1", "body": "Ticket body"},
        },
    )

    assert workspace_event is not None
    assert workspace_event.thread.ref.provider == "workspace"
    assert ticket_event is not None
    assert ticket_event.thread.kind == "work_item_discussion"
    assert ticket_event.message.kind == "comment"


def test_reply_routing_does_not_inspect_provider_specific_raw_payload_metadata():
    workspace = WorkspaceStyleProvider("workspace")
    tickets = TicketStyleProvider("tickets")
    manager = PresenceProviderManager({"workspace": workspace, "tickets": tickets})

    reply = manager.reply_to_thread(
        ExternalRef(provider="tickets", id="discussion-1"),
        "Route by ref only",
        metadata={"raw_payload": {"provider": "workspace", "thread": {"id": "thread-1"}}},
    )

    assert reply.ref.provider == "tickets"
    assert workspace.replies == []
    assert tickets.replies[0]["metadata"] == {
        "raw_payload": {"provider": "workspace", "thread": {"id": "thread-1"}}
    }
