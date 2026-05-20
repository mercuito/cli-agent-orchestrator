"""Watchdog for active baton reminders and orphan recovery."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import BatonEventModel, BatonModel, TerminalModel
from cli_agent_orchestrator.models.baton import BatonEventType, BatonStatus
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.manager import provider_manager
from cli_agent_orchestrator.services import baton_service
from cli_agent_orchestrator.services.collaboration_policy import require_terminal_workspace_team
from cli_agent_orchestrator.workspaces import WorkspaceConfigError

logger = logging.getLogger(__name__)

WATCHDOG_ACTOR_ID = "baton-watchdog"
_BATON_HOLDER_TOOLS = ("pass_baton", "return_baton", "complete_baton", "block_baton")
DEFAULT_INTERVAL_SECONDS = float(os.environ.get("CAO_BATON_WATCHDOG_INTERVAL_SECONDS", "30"))
DEFAULT_GRACE_SECONDS = float(os.environ.get("CAO_BATON_IDLE_GRACE_SECONDS", "300"))
DEFAULT_NUDGE_RATE_LIMIT_SECONDS = float(
    os.environ.get("CAO_BATON_NUDGE_RATE_LIMIT_SECONDS", "900")
)


@dataclass(frozen=True)
class BatonWatchdogConfig:
    """Runtime timing controls for baton watchdog scans."""

    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    grace_seconds: float = DEFAULT_GRACE_SECONDS
    nudge_rate_limit_seconds: float = DEFAULT_NUDGE_RATE_LIMIT_SECONDS


@dataclass(frozen=True)
class BatonWatchdogScanResult:
    """Summary of one active-baton scan."""

    scanned: int = 0
    nudged: int = 0
    orphaned: int = 0


def _append_event(
    db,
    *,
    baton_id: str,
    event_type: BatonEventType,
    actor_id: str,
    from_holder_id: Optional[str] = None,
    to_holder_id: Optional[str] = None,
    message: Optional[str] = None,
    created_at: datetime,
) -> None:
    db.add(
        BatonEventModel(
            baton_id=baton_id,
            event_type=event_type.value,
            actor_id=actor_id,
            from_holder_id=from_holder_id,
            to_holder_id=to_holder_id,
            message=message,
            created_at=created_at,
        )
    )


def _latest_baton_event_at(db, baton_id: str) -> Optional[datetime]:
    return (
        db.query(func.max(BatonEventModel.created_at))
        .filter(BatonEventModel.baton_id == baton_id)
        .scalar()
    )


def _last_baton_activity_at(db, row: BatonModel) -> datetime:
    latest_event_at = _latest_baton_event_at(db, row.id)
    candidates = [row.updated_at]
    if latest_event_at is not None:
        candidates.append(latest_event_at)
    return max(candidates)


def _idle_long_enough(
    db,
    row: BatonModel,
    *,
    now: datetime,
    grace: timedelta,
) -> bool:
    return now - _last_baton_activity_at(db, row) >= grace


def _nudge_rate_limit_elapsed(
    row: BatonModel,
    *,
    now: datetime,
    rate_limit: timedelta,
) -> bool:
    if row.last_nudged_at is None:
        return True
    return now - row.last_nudged_at >= rate_limit


def _expected_next_action(db, row: BatonModel) -> str:
    tools = _available_baton_holder_tools(db, row.current_holder_id)
    if not tools and row.expected_next_action is None:
        return "No baton lifecycle tools are currently available in this terminal."
    return row.expected_next_action or (
        f"Use available baton tools ({', '.join(tools)}) when ready."
    )


def _nudge_message(db, row: BatonModel) -> str:
    tools = _available_baton_holder_tools(db, row.current_holder_id)
    if not tools:
        action_text = (
            "This terminal currently has no baton lifecycle tools available. "
            "Continue the work if possible and ask the originator or operator to "
            "move, complete, or block the baton."
        )
    else:
        actions = []
        if "pass_baton" in tools:
            actions.append(
                "If you are waiting on another agent to make the next move, pass "
                "the baton to that agent with pass_baton."
            )
        if "complete_baton" in tools:
            actions.append("If the work is done, call complete_baton.")
        if "return_baton" in tools:
            actions.append("If control should go back to the previous holder, call return_baton.")
        if "block_baton" in tools:
            actions.append("If you cannot proceed, call block_baton with the reason.")
        action_text = " ".join(actions)
    return (
        "[CAO Baton] Gentle reminder\n\n"
        f"Baton id: {row.id}\n"
        f"Title: {row.title}\n"
        f"Expected next action: {_expected_next_action(db, row)}\n\n"
        "You are still the current holder for this active baton. "
        "If you are actively working, continue. "
        f"{action_text} "
        "Idle detection is advisory; CAO will not complete or pass this baton for you."
    )


def _available_baton_holder_tools(db, terminal_id: Optional[str]) -> tuple[str, ...]:
    return baton_service.available_baton_holder_tools(db, terminal_id)


def _orphan_message(db, row: BatonModel, previous_holder_id: str) -> str:
    return (
        "[CAO Baton] Baton orphaned\n\n"
        f"Baton id: {row.id}\n"
        f"Title: {row.title}\n"
        f"Previous holder: {previous_holder_id}\n"
        f"Expected next action: {_expected_next_action(db, row)}\n\n"
        "CAO could not find terminal metadata or a live provider for the current holder, "
        "so this baton was marked orphaned. Inspect the baton and create or reassign "
        "follow-up ownership as needed."
    )


def _queue_watchdog_message(db, *, receiver_id: str, message: str) -> None:
    require_terminal_workspace_team(receiver_id, db=db, role="Watchdog receiver")
    db_module.create_inbox_delivery(
        WATCHDOG_ACTOR_ID,
        receiver_id,
        message,
        db=db,
    )


def _mark_orphaned(db, row: BatonModel, *, now: datetime) -> None:
    previous_holder_id = row.current_holder_id
    if previous_holder_id is None:
        return

    message = _orphan_message(db, row, previous_holder_id)
    row.status = BatonStatus.ORPHANED.value
    row.current_holder_id = None
    row.updated_at = now
    _append_event(
        db,
        baton_id=row.id,
        event_type=BatonEventType.ORPHAN,
        actor_id=WATCHDOG_ACTOR_ID,
        from_holder_id=previous_holder_id,
        to_holder_id=row.originator_id,
        message=message,
        created_at=now,
    )
    try:
        _queue_watchdog_message(db, receiver_id=row.originator_id, message=message)
    except WorkspaceConfigError as exc:
        logger.warning(
            "Baton watchdog marked baton %s orphaned but did not notify originator %s: %s",
            row.id,
            row.originator_id,
            exc,
        )


def _nudge_holder(db, row: BatonModel, *, now: datetime) -> None:
    holder_id = row.current_holder_id
    if holder_id is None:
        return

    message = _nudge_message(db, row)
    row.last_nudged_at = now
    _append_event(
        db,
        baton_id=row.id,
        event_type=BatonEventType.NUDGE,
        actor_id=WATCHDOG_ACTOR_ID,
        from_holder_id=holder_id,
        to_holder_id=holder_id,
        message=message,
        created_at=now,
    )
    _queue_watchdog_message(db, receiver_id=holder_id, message=message)


def scan_active_batons(
    *,
    config: Optional[BatonWatchdogConfig] = None,
    now: Optional[datetime] = None,
) -> BatonWatchdogScanResult:
    """Scan active batons and queue advisory nudges or orphan notices."""
    cfg = config or BatonWatchdogConfig()
    scan_now = now or datetime.now()
    grace = timedelta(seconds=cfg.grace_seconds)
    rate_limit = timedelta(seconds=cfg.nudge_rate_limit_seconds)
    scanned = nudged = orphaned = 0

    with db_module.SessionLocal() as db:
        rows = (
            db.query(BatonModel)
            .filter(
                BatonModel.status == BatonStatus.ACTIVE.value,
                BatonModel.current_holder_id.isnot(None),
            )
            .order_by(BatonModel.updated_at.asc(), BatonModel.created_at.asc())
            .all()
        )

        for row in rows:
            scanned += 1
            holder_id = row.current_holder_id
            if holder_id is None:
                continue

            metadata = db.query(TerminalModel).filter(TerminalModel.id == holder_id).first()
            provider = None
            if metadata is not None:
                try:
                    provider = provider_manager.get_provider(holder_id)
                except Exception as exc:
                    logger.warning(
                        "Could not find provider for baton holder %s: %s",
                        holder_id,
                        exc,
                    )
            if metadata is None or provider is None:
                _mark_orphaned(db, row, now=scan_now)
                db.commit()
                orphaned += 1
                continue
            try:
                require_terminal_workspace_team(holder_id, db=db, role="Baton holder")
            except WorkspaceConfigError as exc:
                logger.warning(
                    "Marking baton %s orphaned because holder %s is outside workspace team policy: %s",
                    row.id,
                    holder_id,
                    exc,
                )
                _mark_orphaned(db, row, now=scan_now)
                db.commit()
                orphaned += 1
                continue

            try:
                status = provider.get_status()
            except Exception as exc:
                logger.warning("Could not read status for baton holder %s: %s", holder_id, exc)
                continue

            if status not in (TerminalStatus.IDLE, TerminalStatus.COMPLETED):
                continue
            if not _idle_long_enough(db, row, now=scan_now, grace=grace):
                continue
            if not _nudge_rate_limit_elapsed(row, now=scan_now, rate_limit=rate_limit):
                continue

            _nudge_holder(db, row, now=scan_now)
            db.commit()
            nudged += 1

    return BatonWatchdogScanResult(scanned=scanned, nudged=nudged, orphaned=orphaned)


async def baton_watchdog_loop(config: Optional[BatonWatchdogConfig] = None) -> None:
    """Periodically run the baton watchdog until cancelled."""
    cfg = config or BatonWatchdogConfig()
    logger.info("Baton watchdog started")
    try:
        while True:
            await asyncio.sleep(cfg.interval_seconds)
            try:
                result = scan_active_batons(config=cfg)
                if result.nudged or result.orphaned:
                    logger.info(
                        "Baton watchdog scan: scanned=%s nudged=%s orphaned=%s",
                        result.scanned,
                        result.nudged,
                        result.orphaned,
                    )
            except Exception as exc:
                logger.error("Baton watchdog scan failed: %s", exc)
    except asyncio.CancelledError:
        logger.info("Baton watchdog stopped")
        raise
