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

logger = logging.getLogger(__name__)

WATCHDOG_ACTOR_ID = "baton-watchdog"
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


def _expected_next_action(row: BatonModel) -> str:
    return row.expected_next_action or (
        "Use pass_baton, return_baton, complete_baton, or block_baton when ready."
    )


def _nudge_message(row: BatonModel) -> str:
    return (
        "[CAO Baton] Gentle reminder\n\n"
        f"Baton id: {row.id}\n"
        f"Title: {row.title}\n"
        f"Expected next action: {_expected_next_action(row)}\n\n"
        "You are still the current holder for this active baton. "
        "If you are actively working, continue. "
        "If you are waiting on another agent to make the next move, pass the baton "
        "to that agent with pass_baton. "
        "If another agent has already responded and you need to act, continue from "
        "their message. "
        "If the work is done, call complete_baton. "
        "If control should go back to the previous holder, call return_baton. "
        "If you cannot proceed, call block_baton with the reason. "
        "Idle detection is advisory; CAO will not complete or pass this baton for you."
    )


def _orphan_message(row: BatonModel, previous_holder_id: str) -> str:
    return (
        "[CAO Baton] Baton orphaned\n\n"
        f"Baton id: {row.id}\n"
        f"Title: {row.title}\n"
        f"Previous holder: {previous_holder_id}\n"
        f"Expected next action: {_expected_next_action(row)}\n\n"
        "CAO could not find terminal metadata or a live provider for the current holder, "
        "so this baton was marked orphaned. Inspect the baton and create or reassign "
        "follow-up ownership as needed."
    )


def _mark_orphaned(db, row: BatonModel, *, now: datetime) -> None:
    previous_holder_id = row.current_holder_id
    if previous_holder_id is None:
        return

    message = _orphan_message(row, previous_holder_id)
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
    db_module.create_inbox_delivery(
        WATCHDOG_ACTOR_ID,
        row.originator_id,
        message,
        db=db,
    )


def _nudge_holder(db, row: BatonModel, *, now: datetime) -> None:
    holder_id = row.current_holder_id
    if holder_id is None:
        return

    message = _nudge_message(row)
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
    db_module.create_inbox_delivery(
        WATCHDOG_ACTOR_ID,
        holder_id,
        message,
        db=db,
    )


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
