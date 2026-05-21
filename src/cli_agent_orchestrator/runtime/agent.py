"""Provider-facing runtime handle for CAO agents."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import cli_agent_orchestrator.runtime.events as runtime_events
from cli_agent_orchestrator.agent import (
    Agent,
    AgentWorkspaceContextRuntimePaths,
    ensure_agent_workspace_context_runtime_paths,
)
from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.constants import SESSION_PREFIX
from cli_agent_orchestrator.events import CaoEvent
from cli_agent_orchestrator.models.inbox import InboxDelivery, MessageStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import AgentRuntimeLaunchContext
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.services import terminal_service
from cli_agent_orchestrator.services.agent_manager import (
    AgentManager,
    default_agent_manager,
)

logger = logging.getLogger(__name__)

RUNTIME_FINGERPRINT_SCHEMA_VERSION = "cao-agent-runtime-fingerprint.v1"
RUNTIME_STATE_SCHEMA_VERSION = "cao-agent-runtime-state.v1"
RUNTIME_STATE_FILENAME = "runtime-state.json"


class AgentRuntimeStatus(str, Enum):
    """Provider-friendly status for a mapped CAO agent runtime."""

    NOT_STARTED = "not_started"
    IDLE = "idle"
    BUSY = "busy"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    ERROR = "error"
    UNREACHABLE = "unreachable"


class AgentRuntimeFreshnessAction(str, Enum):
    """Outcome of freshness reconciliation before terminal-send delivery."""

    REUSED = "reused"
    STARTED = "started"
    RESTARTED = "restarted"
    DEFERRED = "deferred"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentRuntimeTerminal:
    """Terminal manifestation of a CAO agent."""

    id: str
    agent_id: str
    workspace_context_id: str
    session_name: str
    window_name: str
    provider: str
    resume_supported: bool
    context_preservation: str


@dataclass(frozen=True)
class AgentRuntimeState:
    """CAO-owned runtime envelope for a durable agent."""

    schema_version: str
    agent_id: str
    workspace_context_id: str
    provider: str
    terminal_id: str | None


@dataclass(frozen=True)
class TerminalRuntimeState:
    """CAO-owned runtime envelope for a terminal manifestation."""

    schema_version: str
    terminal_id: str
    provider: str


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
class AgentRuntimeFreshnessResult:
    """Result of making an agent runtime fresh enough for delivery."""

    action: AgentRuntimeFreshnessAction
    status: AgentRuntimeStatus
    terminal_id: Optional[str]
    ready: bool
    fresh: bool
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
    freshness: Optional[AgentRuntimeFreshnessResult] = None


class AgentRuntimeInvariantError(RuntimeError):
    """Raised when a durable agent has conflicting terminal manifestations."""


class AgentRuntimeHandle:
    """Provider-facing operational contract for one durable CAO agent."""

    def __init__(
        self,
        agent: Agent,
        workspace_context_id: str | None = None,
        *,
        agent_manager: AgentManager | None = None,
    ) -> None:
        self._agent_manager = agent_manager or default_agent_manager()
        registered_agent = self._agent_manager.require_registered_agent(agent)
        if workspace_context_id is None:
            workspace_context_id = db_module.ensure_default_workspace_context(
                registered_agent.id
            ).id
        self.workspace_context_id = workspace_context_id
        self.agent = registered_agent.for_workspace_context(workspace_context_id)
        self._last_freshness_result: Optional[AgentRuntimeFreshnessResult] = None
        self._last_agent_ready_delivery_error: str | None = None

    @property
    def inbox_receiver_id(self) -> str:
        """Stable inbox receiver id used before and after terminal startup."""
        return f"agent:{self.agent.id}:context:{self.workspace_context_id}"

    @property
    def session_name(self) -> str:
        """Canonical managed tmux session name for this agent."""
        return canonical_agent_session_name(self.agent.session_name)

    def status(self) -> AgentRuntimeStatus:
        """Return a provider-friendly runtime status without exposing terminal details."""
        terminal = self._terminal()
        if terminal is None:
            return AgentRuntimeStatus.NOT_STARTED
        return self._status_for_terminal(terminal)

    def _status_for_terminal(self, terminal: AgentRuntimeTerminal) -> AgentRuntimeStatus:
        """Return provider-friendly status for a known terminal manifestation."""
        provider = provider_manager.get_provider(terminal.id)
        if provider is None:
            return AgentRuntimeStatus.UNREACHABLE

        try:
            terminal_status = provider.get_status()
        except Exception as exc:
            logger.warning("Unable to query runtime status for agent %s: %s", self.agent.id, exc)
            return AgentRuntimeStatus.UNREACHABLE

        return _map_terminal_status(terminal_status)

    def ensure_started(self) -> AgentRuntimeTerminal:
        """Create or reuse the mapped terminal for this agent."""
        existing = self._terminal()
        if existing is not None:
            self._publish_runtime_lifecycle_result(
                self._runtime_lifecycle_result_for_terminal(
                    existing,
                    action=AgentRuntimeFreshnessAction.REUSED,
                    fresh=self._existing_terminal_is_fresh(existing.id),
                ),
                causing_event=None,
                publish_ready_event=False,
            )
            return existing

        desired_fingerprint = self._desired_runtime_fingerprint()
        switch_result = self._deactivate_other_context_terminal_for_switch(
            causing_event=None,
        )
        if switch_result is not None:
            raise RuntimeError(switch_result.error or "workspace context switch failed")
        started = self._start_with_fingerprint(desired_fingerprint)
        self._refresh_provider_runtime_cache_for_terminal(
            started.id,
            desired_fingerprint,
        )
        self._publish_runtime_lifecycle_result(
            self._runtime_lifecycle_result_for_terminal(
                started,
                action=AgentRuntimeFreshnessAction.STARTED,
                fresh=True,
            ),
            causing_event=None,
            publish_ready_event=False,
        )
        return started

    def ensure_fresh_started(
        self,
        *,
        causing_event: CaoEvent | None = None,
        publish_lifecycle_event: bool = True,
    ) -> AgentRuntimeFreshnessResult:
        """Ensure the agent runtime is started, fresh, and ready for delivery."""
        desired_fingerprint = self._desired_runtime_fingerprint()
        terminal = self._terminal()
        if terminal is None:
            switch_result = self._deactivate_other_context_terminal_for_switch(
                causing_event=causing_event,
            )
            if switch_result is not None:
                return self._publish_runtime_lifecycle_result(
                    switch_result,
                    causing_event=causing_event,
                    publish_event=publish_lifecycle_event,
                )
            try:
                started = self._start_with_fingerprint(desired_fingerprint)
                self._refresh_provider_runtime_cache_for_terminal(
                    started.id,
                    desired_fingerprint,
                )
            except Exception as exc:
                logger.warning("Unable to start runtime for agent %s: %s", self.agent.id, exc)
                return self._publish_runtime_lifecycle_result(
                    AgentRuntimeFreshnessResult(
                        action=AgentRuntimeFreshnessAction.FAILED,
                        status=AgentRuntimeStatus.NOT_STARTED,
                        terminal_id=None,
                        ready=False,
                        fresh=False,
                        error=str(exc),
                    ),
                    causing_event=causing_event,
                    publish_event=publish_lifecycle_event,
                )
            return self._publish_runtime_lifecycle_result(
                self._freshness_result_for_started_terminal(
                    started,
                    action=AgentRuntimeFreshnessAction.STARTED,
                    fresh=True,
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )

        status = self._status_for_terminal(terminal)
        if status is AgentRuntimeStatus.UNREACHABLE:
            self._move_pending_terminal_notifications_to_agent(terminal.id)
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.FAILED,
                    status=status,
                    terminal_id=terminal.id,
                    ready=False,
                    fresh=False,
                    error="runtime status is unreachable",
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )
        if status is AgentRuntimeStatus.ERROR:
            self._move_pending_terminal_notifications_to_agent(terminal.id)
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.FAILED,
                    status=status,
                    terminal_id=terminal.id,
                    ready=False,
                    fresh=False,
                    error="runtime is in error state",
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )

        fresh = self._applied_runtime_fingerprint(terminal.id) == desired_fingerprint
        if fresh:
            if status in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED):
                try:
                    self._refresh_provider_runtime_cache_for_terminal(
                        terminal.id,
                        desired_fingerprint,
                    )
                except Exception as exc:
                    logger.warning(
                        "Unable to update provider runtime cache for agent %s terminal %s: %s",
                        self.agent.id,
                        terminal.id,
                        exc,
                    )
                    return self._publish_runtime_lifecycle_result(
                        AgentRuntimeFreshnessResult(
                            action=AgentRuntimeFreshnessAction.FAILED,
                            status=status,
                            terminal_id=terminal.id,
                            ready=False,
                            fresh=True,
                            error=str(exc),
                        ),
                        causing_event=causing_event,
                        publish_event=publish_lifecycle_event,
                    )
                return self._publish_runtime_lifecycle_result(
                    AgentRuntimeFreshnessResult(
                        action=AgentRuntimeFreshnessAction.REUSED,
                        status=status,
                        terminal_id=terminal.id,
                        ready=True,
                        fresh=True,
                    ),
                    causing_event=causing_event,
                    publish_event=publish_lifecycle_event,
                )
            self._move_pending_terminal_notifications_to_agent(terminal.id)
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.DEFERRED,
                    status=status,
                    terminal_id=terminal.id,
                    ready=False,
                    fresh=True,
                    error=f"runtime is {status.value}; delivery deferred",
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )

        self._move_pending_terminal_notifications_to_agent(terminal.id)
        if status in (AgentRuntimeStatus.BUSY, AgentRuntimeStatus.WAITING_USER):
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.DEFERRED,
                    status=status,
                    terminal_id=terminal.id,
                    ready=False,
                    fresh=False,
                    error=f"runtime is stale and {status.value}; delivery deferred",
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )

        try:
            self._save_live_provider_runtime_state(terminal.id)
            self._write_applied_runtime_state(
                terminal.id,
                self._applied_runtime_fingerprint(terminal.id) or "",
            )
        except Exception as exc:
            logger.warning(
                "Unable to discover provider runtime state for agent %s terminal %s: %s",
                self.agent.id,
                terminal.id,
                exc,
            )
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.FAILED,
                    status=status,
                    terminal_id=terminal.id,
                    ready=False,
                    fresh=False,
                    error=str(exc),
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )
        if status not in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED):
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.FAILED,
                    status=status,
                    terminal_id=terminal.id,
                    ready=False,
                    fresh=False,
                    error=f"stale runtime cannot be refreshed while {status.value}",
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )

        try:
            terminal_service.delete_terminal(terminal.id, require_window_killed=True)
            restarted = self._start_with_fingerprint(desired_fingerprint)
            self._refresh_provider_runtime_cache_for_terminal(
                restarted.id,
                desired_fingerprint,
            )
        except Exception as exc:
            logger.warning("Unable to refresh runtime for agent %s: %s", self.agent.id, exc)
            return self._publish_runtime_lifecycle_result(
                AgentRuntimeFreshnessResult(
                    action=AgentRuntimeFreshnessAction.FAILED,
                    status=status,
                    terminal_id=None,
                    ready=False,
                    fresh=False,
                    error=str(exc),
                ),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )
        return self._publish_runtime_lifecycle_result(
            self._freshness_result_for_started_terminal(
                restarted,
                action=AgentRuntimeFreshnessAction.RESTARTED,
                fresh=True,
            ),
            causing_event=causing_event,
            publish_event=publish_lifecycle_event,
        )

    def current_terminal(self) -> Optional[AgentRuntimeTerminal]:
        """Return the current terminal manifestation without starting one."""
        return self._terminal()

    def notify(
        self,
        message: str,
        *,
        sender_id: str = "workspace-tool-provider",
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
        ensure_started: bool = True,
        attempt_delivery: bool = True,
        causing_event: CaoEvent | None = None,
    ) -> AgentRuntimeNotifyResult:
        """Durably accept a provider notification and optionally deliver it.

        Acceptance is independent from terminal liveness. ``source_kind`` and
        ``source_id`` act as an idempotency key when supplied together.
        """
        notification = self._create_or_get_notification(
            sender_id=sender_id,
            receiver_id=self.inbox_receiver_id,
            message=message,
            source_kind=source_kind,
            source_id=source_id,
        )
        original_status = notification.delivery.notification.status
        if notification.created:
            self._publish_notification_accepted(
                notification,
                causing_event=causing_event,
            )

        delivery = (
            self.try_deliver_pending(
                ensure_started=ensure_started,
                causing_event=causing_event,
                publish_lifecycle_event=notification.created,
            )
            if attempt_delivery
            else AgentRuntimeDeliveryResult(
                status=self.status(),
                terminal_id=self._terminal_id(),
                attempted=False,
                delivered=False,
            )
        )
        freshness = self._last_freshness_result if attempt_delivery else None
        started = bool(
            freshness
            and freshness.action
            in (AgentRuntimeFreshnessAction.STARTED, AgentRuntimeFreshnessAction.RESTARTED)
        )
        notification = self._refresh_notification_receiver(notification)
        self._publish_notification_delivery_if_new_fact(
            notification,
            delivery,
            original_status=original_status,
            causing_event=causing_event,
        )
        return AgentRuntimeNotifyResult(
            notification=notification,
            status=delivery.status,
            terminal_id=delivery.terminal_id,
            started=started,
            delivery=delivery,
            error=delivery.error,
            freshness=freshness,
        )

    def accept_notification(
        self,
        notification: AgentRuntimeNotification,
        *,
        ensure_started: bool = True,
        attempt_delivery: bool = True,
        causing_event: CaoEvent | None = None,
    ) -> AgentRuntimeNotifyResult:
        """Start or wake the runtime for an inbox notification created by another owner.

        Provider integrations sometimes need a CAO-owned inbox surface to create
        the backing message because that surface owns idempotency or reply refs.
        This method keeps terminal lifecycle and busy/idle delivery behavior
        behind the runtime handle for those already-durable notifications.
        """
        original_status = notification.delivery.notification.status
        if notification.created:
            self._publish_notification_accepted(
                notification,
                causing_event=causing_event,
            )

        delivery = (
            self.try_deliver_pending(
                ensure_started=ensure_started,
                causing_event=causing_event,
                publish_lifecycle_event=notification.created,
            )
            if attempt_delivery
            else AgentRuntimeDeliveryResult(
                status=self.status(),
                terminal_id=self._terminal_id(),
                attempted=False,
                delivered=False,
            )
        )
        freshness = self._last_freshness_result if attempt_delivery else None
        started = bool(
            freshness
            and freshness.action
            in (AgentRuntimeFreshnessAction.STARTED, AgentRuntimeFreshnessAction.RESTARTED)
        )
        notification = self._refresh_notification_receiver(notification)
        self._publish_notification_delivery_if_new_fact(
            notification,
            delivery,
            original_status=original_status,
            causing_event=causing_event,
        )
        return AgentRuntimeNotifyResult(
            notification=notification,
            status=delivery.status,
            terminal_id=delivery.terminal_id,
            started=started,
            delivery=delivery,
            error=delivery.error,
            freshness=freshness,
        )

    def try_deliver_pending(
        self,
        *,
        ensure_started: bool = True,
        causing_event: CaoEvent | None = None,
        publish_lifecycle_event: bool = True,
    ) -> AgentRuntimeDeliveryResult:
        """Best-effort delivery of pending notifications when the runtime is ready."""
        self._last_agent_ready_delivery_error = None
        terminal_id_before_freshness = self._terminal_id()
        pending_before_ready_event_ids = self._pending_delivery_ids_for_receivers(
            self._runtime_delivery_receiver_ids(terminal_id_before_freshness)
        )
        freshness = (
            self.ensure_fresh_started(
                causing_event=causing_event,
                publish_lifecycle_event=publish_lifecycle_event,
            )
            if ensure_started
            else self._publish_runtime_lifecycle_result(
                self._freshness_without_starting(),
                causing_event=causing_event,
                publish_event=publish_lifecycle_event,
            )
        )
        self._last_freshness_result = freshness
        if not freshness.ready or freshness.terminal_id is None:
            return AgentRuntimeDeliveryResult(
                status=freshness.status,
                terminal_id=freshness.terminal_id,
                attempted=False,
                delivered=False,
                error=freshness.error,
            )

        terminal_id = freshness.terminal_id
        if freshness.status not in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED):
            return AgentRuntimeDeliveryResult(
                status=freshness.status,
                terminal_id=terminal_id,
                attempted=False,
                delivered=False,
            )

        if self._last_agent_ready_delivery_error is not None:
            return AgentRuntimeDeliveryResult(
                status=freshness.status,
                terminal_id=terminal_id,
                attempted=True,
                delivered=False,
                error=self._last_agent_ready_delivery_error,
            )
        delivered = self._any_delivery_completed(pending_before_ready_event_ids)

        return AgentRuntimeDeliveryResult(
            status=freshness.status,
            terminal_id=terminal_id,
            attempted=bool(pending_before_ready_event_ids),
            delivered=delivered,
        )

    def _terminal(self) -> Optional[AgentRuntimeTerminal]:
        terminals = db_module.list_terminals_by_agent(self.agent.id)
        if len(terminals) > 1:
            raise AgentRuntimeInvariantError(
                "Multiple terminal manifestations exist for CAO agent " f"{self.agent.id!r}"
            )
        terminals = [
            terminal
            for terminal in terminals
            if terminal.get("workspace_context_id") == self.workspace_context_id
        ]
        if not terminals:
            return None
        if len(terminals) > 1:
            raise AgentRuntimeInvariantError(
                "Multiple terminal manifestations exist for CAO agent " f"{self.agent.id!r}"
            )
        return _terminal_from_metadata(terminals[0])

    def _other_context_terminal(self) -> AgentRuntimeTerminal | None:
        terminals = db_module.list_terminals_by_agent(self.agent.id)
        if len(terminals) > 1:
            raise AgentRuntimeInvariantError(
                "Multiple terminal manifestations exist for CAO agent " f"{self.agent.id!r}"
            )
        if not terminals:
            return None
        terminal = _terminal_from_metadata(terminals[0])
        if terminal.workspace_context_id == self.workspace_context_id:
            return None
        return terminal

    def _deactivate_other_context_terminal_for_switch(
        self,
        *,
        causing_event: CaoEvent | None = None,
    ) -> AgentRuntimeFreshnessResult | None:
        terminal = self._other_context_terminal()
        if terminal is None:
            return None

        status = self._status_for_terminal(terminal)
        if status in (AgentRuntimeStatus.BUSY, AgentRuntimeStatus.WAITING_USER):
            self._publish_workspace_context_switch_event(
                terminal=terminal,
                status=status,
                outcome="deferred",
                error=f"runtime is {status.value}; context switch deferred",
                causing_event=causing_event,
            )
            return AgentRuntimeFreshnessResult(
                action=AgentRuntimeFreshnessAction.DEFERRED,
                status=status,
                terminal_id=terminal.id,
                ready=False,
                fresh=False,
                error=f"runtime is {status.value}; context switch deferred",
            )
        if status not in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED):
            self._publish_workspace_context_switch_event(
                terminal=terminal,
                status=status,
                outcome="failed",
                error=f"runtime is {status.value}; context switch failed",
                causing_event=causing_event,
            )
            return AgentRuntimeFreshnessResult(
                action=AgentRuntimeFreshnessAction.FAILED,
                status=status,
                terminal_id=terminal.id,
                ready=False,
                fresh=False,
                error=f"runtime is {status.value}; context switch failed",
            )

        other_handle = AgentRuntimeHandle(
            self.agent,
            workspace_context_id=terminal.workspace_context_id,
            agent_manager=self._agent_manager,
        )
        try:
            other_handle._save_live_provider_runtime_state(terminal.id)
            other_handle._write_applied_runtime_state(
                terminal.id,
                other_handle._applied_runtime_fingerprint(terminal.id) or "",
            )
            other_handle._move_pending_terminal_notifications_to_agent(terminal.id)
            terminal_service.delete_terminal(terminal.id, require_window_killed=True)
            db_module.set_context_workspace_active_terminal(
                agent_id=self.agent.id,
                workspace_context_id=terminal.workspace_context_id,
                terminal_id=None,
            )
        except Exception as exc:
            logger.warning(
                "Unable to switch agent %s from workspace context %s to %s: %s",
                self.agent.id,
                terminal.workspace_context_id,
                self.workspace_context_id,
                exc,
            )
            self._publish_workspace_context_switch_event(
                terminal=terminal,
                status=status,
                outcome="failed",
                error=str(exc),
                causing_event=causing_event,
            )
            return AgentRuntimeFreshnessResult(
                action=AgentRuntimeFreshnessAction.FAILED,
                status=status,
                terminal_id=terminal.id,
                ready=False,
                fresh=False,
                error=str(exc),
            )

        self._publish_workspace_context_switch_event(
            terminal=terminal,
            status=status,
            outcome="succeeded",
            error=None,
            causing_event=causing_event,
        )
        return None

    def _start_with_fingerprint(
        self,
        desired_fingerprint: str,
    ) -> AgentRuntimeTerminal:
        created = terminal_service.create_terminal_for_agent(self.agent)
        self._ensure_context_workspace(active_terminal_id=created.id)
        self._write_applied_runtime_state(
            created.id,
            desired_fingerprint,
        )
        provider_value = getattr(created.provider, "value", created.provider)
        provider_name = str(provider_value)
        return AgentRuntimeTerminal(
            id=created.id,
            agent_id=self.agent.id,
            workspace_context_id=self.workspace_context_id,
            session_name=created.session_name,
            window_name=created.name,
            provider=provider_name,
            resume_supported=provider_manager.provider_supports_resume(provider_name),
            context_preservation=_context_preservation_message(provider_name),
        )

    def _freshness_result_for_started_terminal(
        self,
        terminal: AgentRuntimeTerminal,
        *,
        action: AgentRuntimeFreshnessAction,
        fresh: bool,
    ) -> AgentRuntimeFreshnessResult:
        status = self._status_for_terminal(terminal)
        if status in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED):
            return AgentRuntimeFreshnessResult(
                action=action,
                status=status,
                terminal_id=terminal.id,
                ready=True,
                fresh=fresh,
            )
        if status in (AgentRuntimeStatus.BUSY, AgentRuntimeStatus.WAITING_USER):
            self._move_pending_terminal_notifications_to_agent(terminal.id)
            return AgentRuntimeFreshnessResult(
                action=AgentRuntimeFreshnessAction.DEFERRED,
                status=status,
                terminal_id=terminal.id,
                ready=False,
                fresh=fresh,
                error=f"runtime is {status.value}; delivery deferred",
            )
        self._move_pending_terminal_notifications_to_agent(terminal.id)
        return AgentRuntimeFreshnessResult(
            action=AgentRuntimeFreshnessAction.FAILED,
            status=status,
            terminal_id=terminal.id,
            ready=False,
            fresh=fresh,
            error=f"runtime is {status.value}",
        )

    def _runtime_lifecycle_result_for_terminal(
        self,
        terminal: AgentRuntimeTerminal,
        *,
        action: AgentRuntimeFreshnessAction,
        fresh: bool,
    ) -> AgentRuntimeFreshnessResult:
        try:
            status = self._status_for_terminal(terminal)
        except Exception as exc:
            logger.warning(
                "Unable to query lifecycle status for agent %s terminal %s: %s",
                self.agent.id,
                terminal.id,
                exc,
            )
            status = AgentRuntimeStatus.UNREACHABLE
        ready = status in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED)
        return AgentRuntimeFreshnessResult(
            action=action,
            status=status,
            terminal_id=terminal.id,
            ready=ready,
            fresh=fresh,
            error=None if ready else f"runtime is {status.value}",
        )

    def _existing_terminal_is_fresh(self, terminal_id: str) -> bool:
        try:
            return self._applied_runtime_fingerprint(terminal_id) == (
                self._desired_runtime_fingerprint()
            )
        except Exception as exc:
            logger.warning(
                "Unable to evaluate runtime freshness for agent %s terminal %s: %s",
                self.agent.id,
                terminal_id,
                exc,
            )
            return False

    def _freshness_without_starting(self) -> AgentRuntimeFreshnessResult:
        terminal = self._terminal()
        if terminal is None:
            return AgentRuntimeFreshnessResult(
                action=AgentRuntimeFreshnessAction.DEFERRED,
                status=AgentRuntimeStatus.NOT_STARTED,
                terminal_id=None,
                ready=False,
                fresh=False,
            )
        status = self._status_for_terminal(terminal)
        fresh = (
            self._applied_runtime_fingerprint(terminal.id) == self._desired_runtime_fingerprint()
        )
        if not fresh:
            self._move_pending_terminal_notifications_to_agent(terminal.id)
        return AgentRuntimeFreshnessResult(
            action=(
                AgentRuntimeFreshnessAction.REUSED
                if fresh
                else AgentRuntimeFreshnessAction.DEFERRED
            ),
            status=status,
            terminal_id=terminal.id,
            ready=fresh and status in (AgentRuntimeStatus.IDLE, AgentRuntimeStatus.COMPLETED),
            fresh=fresh,
            error=None if fresh else "runtime is stale; delivery deferred",
        )

    def _terminal_id(self) -> Optional[str]:
        terminal = self._terminal()
        return terminal.id if terminal is not None else None

    def _runtime_delivery_receiver_ids(self, terminal_id: str | None) -> tuple[str, ...]:
        if terminal_id is None:
            return (self.inbox_receiver_id,)
        return (self.inbox_receiver_id, terminal_id)

    def _pending_delivery_ids_for_receivers(self, receiver_ids: tuple[str, ...]) -> set[int]:
        normalized_receiver_ids = tuple(dict.fromkeys(receiver_ids))
        if not normalized_receiver_ids:
            return set()
        with db_module.SessionLocal() as session:
            rows = (
                session.query(db_module.InboxNotificationModel.id)
                .filter(
                    db_module.InboxNotificationModel.receiver_agent_id.in_(normalized_receiver_ids),
                    db_module.InboxNotificationModel.status == MessageStatus.PENDING.value,
                )
                .all()
            )
        return {int(row[0]) for row in rows}

    def _any_delivery_completed(self, notification_ids: set[int]) -> bool:
        if not notification_ids:
            return False
        with db_module.SessionLocal() as session:
            return (
                session.query(db_module.InboxNotificationModel.id)
                .filter(
                    db_module.InboxNotificationModel.id.in_(list(notification_ids)),
                    db_module.InboxNotificationModel.status == MessageStatus.DELIVERED.value,
                )
                .first()
                is not None
            )

    def _desired_runtime_fingerprint(self) -> str:
        runtime_inputs = terminal_service.resolve_terminal_runtime_inputs(
            self.agent.id,
        )
        runtime_paths = self._runtime_paths()
        context = AgentRuntimeLaunchContext(
            agent=self.agent,
            agent_data_dir=runtime_paths.agent_data_dir,
            provider_data_dir=runtime_paths.provider_data_dir,
            terminal_id="<desired>",
            session_name=self.session_name,
            window_name=self.agent.id,
            working_directory=self.agent.workdir,
            agent_id=self.agent.id,
            allowed_tools=runtime_inputs.allowed_tools,
        )
        provider_descriptor = provider_manager.runtime_fingerprint_contribution(
            self.agent.cli_provider,
            launch_context=context,
        )
        mcp_surface_fingerprint = _mcp_surface_fingerprint_for_agent(self.agent)
        mcp_runtime_generation_fingerprint = _mcp_runtime_generation_fingerprint_for_agent(
            self.agent
        )
        descriptor = {
            "schema_version": RUNTIME_FINGERPRINT_SCHEMA_VERSION,
            "agent": {
                "id": self.agent.id,
                "workspace_context_id": self.workspace_context_id,
                "provider": self.agent.cli_provider,
                "agent_id": self.agent.id,
                "workdir": os.path.realpath(self.agent.workdir or os.getcwd()),
                "session_name": self.session_name,
                "allowed_tools": runtime_inputs.allowed_tools,
                "agent_material": runtime_inputs.agent_material,
            },
            "provider": {
                "schema_version": provider_descriptor.schema_version,
                "material": provider_descriptor.material,
            },
            "mcp_surface": {
                "schema_version": "cao-agent-mcp-surface-fingerprint.v1",
                "fingerprint": mcp_surface_fingerprint,
            },
            "mcp_runtime_generation": {
                "schema_version": "cao-agent-mcp-runtime-generation-fingerprint.v1",
                "fingerprint": mcp_runtime_generation_fingerprint,
            },
        }
        return hashlib.sha256(_canonical_json_bytes(descriptor)).hexdigest()

    def _runtime_state_path(self) -> Path:
        runtime_paths = self._runtime_paths()
        return runtime_paths.provider_data_dir / RUNTIME_STATE_FILENAME

    def _runtime_paths(self) -> AgentWorkspaceContextRuntimePaths:
        return ensure_agent_workspace_context_runtime_paths(
            self.agent,
            self.workspace_context_id,
            self.agent.cli_provider,
        )

    def _applied_runtime_fingerprint(self, terminal_id: str) -> Optional[str]:
        data = self._read_runtime_state_data()
        if data is None:
            return None
        if data.get("schema_version") != RUNTIME_STATE_SCHEMA_VERSION:
            return None
        if data.get("terminal_id") != terminal_id:
            return None
        value = data.get("fingerprint")
        return str(value) if isinstance(value, str) else None

    def _save_live_provider_runtime_state(
        self,
        terminal_id: str,
    ) -> None:
        capability = provider_manager.runtime_state_capability(self.agent.cli_provider)
        if capability is None:
            return
        runtime_paths = self._runtime_paths()
        state = capability.discover_current_runtime_state(
            terminal_id=terminal_id,
            provider_data_dir=runtime_paths.provider_data_dir,
        )
        if state is None:
            capability.clear_runtime_state(provider_data_dir=runtime_paths.provider_data_dir)
            return
        capability.save_runtime_state(state)

    def _refresh_provider_runtime_cache_for_terminal(
        self,
        terminal_id: str,
        fingerprint: str,
    ) -> None:
        capability = provider_manager.runtime_state_capability(self.agent.cli_provider)
        if capability is None:
            return
        runtime_paths = self._runtime_paths()
        state = capability.discover_current_runtime_state(
            terminal_id=terminal_id,
            provider_data_dir=runtime_paths.provider_data_dir,
        )
        if state is None:
            capability.clear_runtime_state(provider_data_dir=runtime_paths.provider_data_dir)
        else:
            capability.save_runtime_state(state)
        self._write_applied_runtime_state(
            terminal_id,
            fingerprint,
        )

    def _read_runtime_state_data(self) -> dict[str, Any] | None:
        path = self._runtime_state_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _write_applied_runtime_state(
        self,
        terminal_id: str,
        fingerprint: str,
    ) -> None:
        path = self._runtime_state_path()
        path.write_text(
            json.dumps(
                {
                    "schema_version": RUNTIME_STATE_SCHEMA_VERSION,
                    "agent_id": self.agent.id,
                    "workspace_context_id": self.workspace_context_id,
                    "provider": self.agent.cli_provider,
                    "terminal_id": terminal_id,
                    "fingerprint": fingerprint,
                    "applied_at": datetime.now().isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

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
                        agent_id=self.agent.id,
                        source_kind=source_kind,
                        source_id=source_id,
                        inbox_notification_id=delivery.notification.id,
                        created_at=datetime.now(),
                    )
                    .on_conflict_do_nothing(index_elements=["agent_id", "source_kind", "source_id"])
                )
                if inserted.rowcount != 1:
                    session.query(db_module.InboxNotificationModel).filter(
                        db_module.InboxNotificationModel.id == delivery.notification.id
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
                db_module.AgentRuntimeNotificationModel.agent_id == self.agent.id,
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

    def _move_pending_terminal_notifications_to_agent(self, terminal_id: str) -> None:
        db_module.move_pending_inbox_notifications(terminal_id, self.inbox_receiver_id)

    def _ensure_context_workspace(self, *, active_terminal_id: str | None = None) -> None:
        runtime_paths = ensure_agent_workspace_context_runtime_paths(
            self.agent,
            self.workspace_context_id,
            self.agent.cli_provider,
        )
        db_module.ensure_context_workspace(
            agent_id=self.agent.id,
            workspace_context_id=self.workspace_context_id,
            root_path=runtime_paths.context_data_dir,
        )
        db_module.set_context_workspace_active_terminal(
            agent_id=self.agent.id,
            workspace_context_id=self.workspace_context_id,
            terminal_id=active_terminal_id,
        )

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

    def _publish_notification_accepted(
        self,
        notification: AgentRuntimeNotification,
        *,
        causing_event: CaoEvent | None,
    ) -> None:
        delivery = notification.delivery
        sender_id = (
            delivery.message.sender_id
            if delivery.message is not None
            else delivery.notification.source_kind
        )
        runtime_events.publish_runtime_event(
            runtime_events.notification_accepted_event(
                agent_id=self.agent.id,
                workspace_context_id=self.workspace_context_id,
                inbox_notification_id=delivery.notification.id,
                inbox_receiver_id=self.inbox_receiver_id,
                sender_id=sender_id,
                source_kind=delivery.notification.source_kind,
                source_id=delivery.notification.source_id,
                causing_event=causing_event,
            )
        )

    def _publish_notification_delivery_if_new_fact(
        self,
        notification: AgentRuntimeNotification,
        delivery: AgentRuntimeDeliveryResult,
        *,
        original_status: MessageStatus,
        causing_event: CaoEvent | None,
    ) -> None:
        current_status = notification.delivery.notification.status
        if not notification.created and current_status == original_status:
            return

        outcome = "deferred"
        if current_status == MessageStatus.FAILED:
            outcome = "failed"
        elif delivery.delivered or current_status == MessageStatus.DELIVERED:
            outcome = "delivered"
        elif delivery.error and delivery.status not in (
            AgentRuntimeStatus.BUSY,
            AgentRuntimeStatus.WAITING_USER,
        ):
            outcome = "failed"

        runtime_events.publish_runtime_event(
            runtime_events.notification_delivery_event(
                agent_id=self.agent.id,
                workspace_context_id=self.workspace_context_id,
                inbox_notification_id=notification.delivery.notification.id,
                inbox_receiver_id=self.inbox_receiver_id,
                terminal_id=delivery.terminal_id,
                runtime_status=delivery.status.value,
                outcome=outcome,
                attempted=delivery.attempted,
                delivered=delivery.delivered,
                error=delivery.error,
                source_kind=notification.delivery.notification.source_kind,
                message_body=(
                    notification.delivery.message.body
                    if notification.delivery.message is not None
                    else None
                ),
                causing_event=causing_event,
            )
        )

    def _publish_runtime_lifecycle_result(
        self,
        result: AgentRuntimeFreshnessResult,
        *,
        causing_event: CaoEvent | None,
        publish_event: bool = True,
        publish_ready_event: bool = True,
    ) -> AgentRuntimeFreshnessResult:
        if publish_event:
            runtime_events.publish_runtime_event(
                runtime_events.lifecycle_event(
                    agent_id=self.agent.id,
                    workspace_context_id=self.workspace_context_id,
                    action=result.action.value,
                    runtime_status=result.status.value,
                    terminal_id=result.terminal_id,
                    ready=result.ready,
                    fresh=result.fresh,
                    error=result.error,
                    causing_event=causing_event,
                )
            )
        if publish_ready_event and result.ready and result.terminal_id is not None:
            self._publish_agent_ready_event(
                terminal_id=result.terminal_id,
                causing_event=causing_event,
            )
        return result

    def _publish_agent_ready_event(
        self,
        *,
        terminal_id: str,
        causing_event: CaoEvent | None,
    ) -> None:
        try:
            runtime_events.publish_runtime_event(
                runtime_events.agent_ready_event(
                    agent_id=self.agent.id,
                    terminal_id=terminal_id,
                    causing_event=causing_event,
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to publish agent ready event for agent %s terminal %s: %s",
                self.agent.id,
                terminal_id,
                exc,
            )
            self._last_agent_ready_delivery_error = str(exc)
            return

    def _publish_workspace_context_switch_event(
        self,
        *,
        terminal: AgentRuntimeTerminal,
        status: AgentRuntimeStatus,
        outcome: str,
        error: str | None,
        causing_event: CaoEvent | None,
    ) -> None:
        runtime_events.publish_runtime_event(
            runtime_events.workspace_context_switch_event(
                agent_id=self.agent.id,
                from_workspace_context_id=terminal.workspace_context_id,
                to_workspace_context_id=self.workspace_context_id,
                terminal_id=terminal.id,
                runtime_status=status.value,
                outcome=outcome,
                error=error,
                causing_event=causing_event,
            )
        )


def canonical_agent_session_name(session_name: str) -> str:
    """Return a managed CAO session name for an agent."""
    if session_name.startswith(SESSION_PREFIX):
        return session_name
    return f"{SESSION_PREFIX}{session_name}"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _mcp_surface_fingerprint_for_agent(agent: Agent) -> str:
    from cli_agent_orchestrator.mcp_server.server import (
        build_mcp_surface_fingerprint_for_agent,
    )

    return build_mcp_surface_fingerprint_for_agent(agent)


def _mcp_runtime_generation_fingerprint_for_agent(agent: Agent) -> str:
    from cli_agent_orchestrator.mcp_server.server import (
        build_mcp_runtime_generation_fingerprint_for_agent,
    )

    return build_mcp_runtime_generation_fingerprint_for_agent(agent)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _terminal_from_metadata(metadata: dict[str, object]) -> AgentRuntimeTerminal:
    provider = str(metadata["provider"])
    workspace_context_id = metadata.get("workspace_context_id")
    if not isinstance(workspace_context_id, str) or not workspace_context_id.strip():
        raise AgentRuntimeInvariantError(
            "Managed terminal metadata is missing workspace_context_id"
        )
    return AgentRuntimeTerminal(
        id=str(metadata["id"]),
        agent_id=str(metadata["agent_id"]),
        workspace_context_id=workspace_context_id,
        session_name=str(metadata["tmux_session"]),
        window_name=str(metadata["tmux_window"]),
        provider=provider,
        resume_supported=provider_manager.provider_supports_resume(provider),
        context_preservation=_context_preservation_message(provider),
    )


def _context_preservation_message(provider: str) -> str:
    if provider_manager.provider_supports_resume(provider):
        return "provider supports agent-scoped runtime context preservation"
    return f"provider {provider!r} does not support resume; restarted context is unavailable"


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
