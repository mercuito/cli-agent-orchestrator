"""Provider-facing runtime handle for CAO agent identities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from cli_agent_orchestrator.agent_identity import AgentIdentity
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.constants import SESSION_PREFIX
from cli_agent_orchestrator.models.inbox import InboxDelivery
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.services import inbox_service, terminal_service

logger = logging.getLogger(__name__)


class AgentRuntimeStatus(str, Enum):
    """Provider-friendly status for a mapped CAO agent runtime."""

    NOT_STARTED = "not_started"
    IDLE = "idle"
    BUSY = "busy"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    ERROR = "error"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class AgentRuntimeTerminal:
    """Terminal manifestation of a CAO agent identity."""

    id: str
    session_name: str
    window_name: str
    provider: str
    agent_profile: Optional[str]

    def as_terminal_metadata(self) -> dict[str, object]:
        """Return the legacy terminal metadata shape used by compatibility callers."""
        return {
            "id": self.id,
            "tmux_session": self.session_name,
            "tmux_window": self.window_name,
            "provider": self.provider,
            "agent_profile": self.agent_profile,
        }


@dataclass(frozen=True)
class AgentRuntimeNotification:
    """Durable notification accepted for a CAO agent runtime."""

    delivery: InboxDelivery
    created: bool

    @property
    def receiver_id(self) -> str:
        return self.delivery.notification.receiver_id


@dataclass(frozen=True)
class AgentRuntimeDeliveryResult:
    """Best-effort delivery attempt result for pending runtime notifications."""

    status: AgentRuntimeStatus
    terminal_id: Optional[str]
    attempted: bool
    delivered: bool
    error: Optional[str] = None


@dataclass(frozen=True)
class AgentRuntimeNotifyResult:
    """Result of accepting and optionally delivering a runtime notification."""

    notification: AgentRuntimeNotification
    status: AgentRuntimeStatus
    terminal_id: Optional[str]
    started: bool
    delivery: AgentRuntimeDeliveryResult
    error: Optional[str] = None


class AgentRuntimeHandle:
    """Provider-facing operational contract for one durable CAO agent identity."""

    def __init__(self, identity: AgentIdentity) -> None:
        self.identity = identity

    @property
    def inbox_receiver_id(self) -> str:
        """Stable inbox receiver id used before and after terminal startup."""
        return f"agent:{self.identity.id}"

    @property
    def session_name(self) -> str:
        """Canonical managed tmux session name for this identity."""
        return canonical_agent_session_name(self.identity.session_name)

    def status(self) -> AgentRuntimeStatus:
        """Return a provider-friendly runtime status without exposing terminal details."""
        terminal = self._terminal()
        if terminal is None:
            return AgentRuntimeStatus.NOT_STARTED

        provider = provider_manager.get_provider(terminal.id)
        if provider is None:
            return AgentRuntimeStatus.UNREACHABLE

        try:
            terminal_status = provider.get_status()
        except Exception as exc:
            logger.warning("Unable to query runtime status for agent %s: %s", self.identity.id, exc)
            return AgentRuntimeStatus.UNREACHABLE

        return _map_terminal_status(terminal_status)

    def ensure_started(self) -> AgentRuntimeTerminal:
        """Create or reuse the mapped terminal for this identity."""
        existing = self._terminal()
        if existing is not None:
            return existing

        created = terminal_service.create_terminal(
            provider=self.identity.cli_provider,
            agent_profile=self.identity.agent_profile,
            session_name=self.session_name,
            new_session=not tmux_client.session_exists(self.session_name),
            working_directory=self.identity.workdir,
        )
        provider_value = getattr(created.provider, "value", created.provider)
        return AgentRuntimeTerminal(
            id=created.id,
            session_name=created.session_name,
            window_name=created.name,
            provider=str(provider_value),
            agent_profile=created.agent_profile,
        )

    def current_terminal(self) -> Optional[AgentRuntimeTerminal]:
        """Return the current terminal manifestation without starting one."""
        return self._terminal()

    def notify(
        self,
        message: str,
        *,
        sender_id: str = "workspace-provider",
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
        ensure_started: bool = True,
        attempt_delivery: bool = True,
    ) -> AgentRuntimeNotifyResult:
        """Durably accept a provider notification and optionally deliver it.

        Acceptance is independent from terminal liveness. ``source_kind`` and
        ``source_id`` act as an idempotency key when supplied together.
        """
        terminal = self._terminal()
        notification = self._create_or_get_notification(
            sender_id=sender_id,
            receiver_id=terminal.id if terminal is not None else self.inbox_receiver_id,
            message=message,
            source_kind=source_kind,
            source_id=source_id,
        )

        started = False
        error = None
        if ensure_started and self.status() is AgentRuntimeStatus.NOT_STARTED:
            try:
                terminal = self.ensure_started()
                self._move_pending_agent_notifications_to_terminal(terminal.id)
                notification = self._refresh_notification_receiver(notification)
                started = True
            except Exception as exc:
                error = str(exc)
                logger.warning(
                    "Accepted notification for offline agent %s: %s", self.identity.id, exc
                )

        delivery = (
            self.try_deliver_pending()
            if attempt_delivery
            else AgentRuntimeDeliveryResult(
                status=self.status(),
                terminal_id=self._terminal_id(),
                attempted=False,
                delivered=False,
            )
        )
        return AgentRuntimeNotifyResult(
            notification=notification,
            status=delivery.status,
            terminal_id=delivery.terminal_id,
            started=started,
            delivery=delivery,
            error=error or delivery.error,
        )

    def accept_notification(
        self,
        notification: AgentRuntimeNotification,
        *,
        ensure_started: bool = True,
        attempt_delivery: bool = True,
    ) -> AgentRuntimeNotifyResult:
        """Start or wake the runtime for an inbox notification created by another owner.

        Provider integrations sometimes need a CAO-owned inbox surface to create
        the backing message because that surface owns idempotency or reply refs.
        This method keeps terminal lifecycle and busy/idle delivery behavior
        behind the runtime handle for those already-durable notifications.
        """
        terminal = self._terminal()
        started = False
        error = None
        if ensure_started and self.status() is AgentRuntimeStatus.NOT_STARTED:
            try:
                terminal = self.ensure_started()
                self._move_pending_agent_notifications_to_terminal(terminal.id)
                notification = self._refresh_notification_receiver(notification)
                started = True
            except Exception as exc:
                error = str(exc)
                logger.warning(
                    "Accepted notification for offline agent %s: %s", self.identity.id, exc
                )

        delivery = (
            self.try_deliver_pending()
            if attempt_delivery
            else AgentRuntimeDeliveryResult(
                status=self.status(),
                terminal_id=self._terminal_id(),
                attempted=False,
                delivered=False,
            )
        )
        return AgentRuntimeNotifyResult(
            notification=notification,
            status=delivery.status,
            terminal_id=delivery.terminal_id,
            started=started,
            delivery=delivery,
            error=error or delivery.error,
        )

    def try_deliver_pending(self) -> AgentRuntimeDeliveryResult:
        """Best-effort delivery of pending notifications when the runtime is ready."""
        terminal = self._terminal()
        status = self.status()
        terminal_id = terminal.id if terminal is not None else None
        if terminal is None:
            return AgentRuntimeDeliveryResult(
                status=status,
                terminal_id=None,
                attempted=False,
                delivered=False,
            )
        self._move_pending_agent_notifications_to_terminal(terminal.id)
        if status not in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED):
            return AgentRuntimeDeliveryResult(
                status=status,
                terminal_id=terminal.id,
                attempted=False,
                delivered=False,
            )

        if db_module.get_oldest_pending_inbox_delivery(terminal.id) is None:
            return AgentRuntimeDeliveryResult(
                status=status,
                terminal_id=terminal.id,
                attempted=False,
                delivered=False,
            )

        try:
            delivered = inbox_service.check_and_send_pending_messages(terminal.id)
        except Exception as exc:
            logger.error(
                "Failed to deliver runtime notifications to agent %s terminal %s: %s",
                self.identity.id,
                terminal.id,
                exc,
            )
            return AgentRuntimeDeliveryResult(
                status=status,
                terminal_id=terminal.id,
                attempted=True,
                delivered=False,
                error=str(exc),
            )

        return AgentRuntimeDeliveryResult(
            status=status,
            terminal_id=terminal.id,
            attempted=True,
            delivered=delivered,
        )

    def _terminal(self) -> Optional[AgentRuntimeTerminal]:
        terminals = db_module.list_terminals_by_session(self.session_name)
        if not terminals:
            return None
        return _terminal_from_metadata(terminals[0])

    def _terminal_id(self) -> Optional[str]:
        terminal = self._terminal()
        return terminal.id if terminal is not None else None

    def _create_or_get_notification(
        self,
        *,
        sender_id: str,
        receiver_id: str,
        message: str,
        source_kind: Optional[str],
        source_id: Optional[str],
    ) -> AgentRuntimeNotification:
        if not message:
            raise ValueError("message is required")
        if (source_kind is None) != (source_id is None):
            raise ValueError("source_kind and source_id must be provided together")

        with db_module.SessionLocal() as session:
            if source_kind is not None and source_id is not None:
                existing = self._get_existing_runtime_notification(
                    session,
                    source_kind=source_kind,
                    source_id=source_id,
                )
                if existing is not None:
                    return AgentRuntimeNotification(
                        created=False,
                        delivery=existing,
                    )

            delivery = db_module.create_inbox_delivery(
                sender_id=sender_id,
                receiver_id=receiver_id,
                message=message,
                db=session,
                source_kind=source_kind,
                source_id=source_id,
            )
            if source_kind is not None and source_id is not None:
                inserted = session.execute(
                    sqlite_insert(db_module.AgentRuntimeNotificationModel)
                    .values(
                        agent_id=self.identity.id,
                        source_kind=source_kind,
                        source_id=source_id,
                        inbox_notification_id=delivery.notification.id,
                        created_at=datetime.now(),
                    )
                    .on_conflict_do_nothing(index_elements=["agent_id", "source_kind", "source_id"])
                )
                if inserted.rowcount != 1:
                    if delivery.message is None:
                        raise RuntimeError(
                            "message-backed runtime notification lost its durable message"
                        )
                    session.query(db_module.InboxNotificationModel).filter(
                        db_module.InboxNotificationModel.id == delivery.notification.id
                    ).delete()
                    session.query(db_module.InboxMessageModel).filter(
                        db_module.InboxMessageModel.id == delivery.message.id
                    ).delete()
                    existing = self._get_existing_runtime_notification(
                        session,
                        source_kind=source_kind,
                        source_id=source_id,
                    )
                    if existing is None:
                        raise RuntimeError(
                            "agent runtime notification insert conflicted without existing row"
                        )
                    session.commit()
                    return AgentRuntimeNotification(
                        created=False,
                        delivery=existing,
                    )
            session.commit()
            return AgentRuntimeNotification(
                created=True,
                delivery=delivery,
            )

    def _get_existing_runtime_notification(
        self,
        session,
        *,
        source_kind: str,
        source_id: str,
    ) -> Optional[InboxDelivery]:
        marker = (
            session.query(db_module.AgentRuntimeNotificationModel)
            .filter(
                db_module.AgentRuntimeNotificationModel.agent_id == self.identity.id,
                db_module.AgentRuntimeNotificationModel.source_kind == source_kind,
                db_module.AgentRuntimeNotificationModel.source_id == source_id,
            )
            .first()
        )
        if marker is None:
            return None

        if marker.inbox_notification_id is None:
            raise RuntimeError("agent runtime notification marker has no semantic notification id")
        delivery = db_module.get_inbox_delivery(marker.inbox_notification_id, db=session)
        if delivery is None:
            raise RuntimeError(
                "inbox notification "
                f"{marker.inbox_notification_id} for agent runtime notification not found"
            )
        return delivery

    def _move_pending_agent_notifications_to_terminal(self, terminal_id: str) -> None:
        db_module.move_pending_inbox_notifications(self.inbox_receiver_id, terminal_id)

    def _refresh_notification_receiver(
        self,
        notification: AgentRuntimeNotification,
    ) -> AgentRuntimeNotification:
        delivery = db_module.get_inbox_delivery(notification.delivery.notification.id)
        if delivery is None:
            return notification
        return AgentRuntimeNotification(
            created=notification.created,
            delivery=delivery,
        )


def canonical_agent_session_name(session_name: str) -> str:
    """Return a managed CAO session name for an agent identity."""
    if session_name.startswith(SESSION_PREFIX):
        return session_name
    return f"{SESSION_PREFIX}{session_name}"


def _terminal_from_metadata(metadata: dict[str, object]) -> AgentRuntimeTerminal:
    return AgentRuntimeTerminal(
        id=str(metadata["id"]),
        session_name=str(metadata["tmux_session"]),
        window_name=str(metadata["tmux_window"]),
        provider=str(metadata["provider"]),
        agent_profile=str(metadata["agent_profile"]) if metadata.get("agent_profile") else None,
    )


def _map_terminal_status(status: TerminalStatus) -> AgentRuntimeStatus:
    if status == TerminalStatus.IDLE:
        return AgentRuntimeStatus.IDLE
    if status == TerminalStatus.PROCESSING:
        return AgentRuntimeStatus.BUSY
    if status == TerminalStatus.WAITING_USER_ANSWER:
        return AgentRuntimeStatus.WAITING_USER
    if status == TerminalStatus.COMPLETED:
        return AgentRuntimeStatus.COMPLETED
    if status == TerminalStatus.ERROR:
        return AgentRuntimeStatus.ERROR
    return AgentRuntimeStatus.UNREACHABLE
