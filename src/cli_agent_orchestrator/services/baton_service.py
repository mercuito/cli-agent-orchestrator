"""Baton service.

This layer owns baton state transitions, audit events, and the coupled inbox
message that wakes the next responsible terminal.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from cli_agent_orchestrator.clients import database as db_module
from cli_agent_orchestrator.clients.database import BatonEventModel, BatonModel
from cli_agent_orchestrator.models.baton import Baton, BatonEventType, BatonStatus


class BatonError(Exception):
    """Base class for baton service errors."""


class BatonNotFound(BatonError):
    """Raised when a baton does not exist."""


class BatonAuthorizationError(BatonError):
    """Raised when an actor is not allowed to mutate a baton."""


class BatonInvalidTransition(BatonError):
    """Raised when a transition is invalid for the baton's current status."""


_FINAL_STATUSES = {BatonStatus.COMPLETED.value, BatonStatus.CANCELED.value}


def _load_baton(db: Session, baton_id: str) -> BatonModel:
    row = db.query(BatonModel).filter(BatonModel.id == baton_id).first()
    if row is None:
        raise BatonNotFound(baton_id)
    return row


def _require_active(row: BatonModel) -> None:
    if row.status != BatonStatus.ACTIVE.value:
        raise BatonInvalidTransition(f"baton {row.id} is {row.status}; expected active")


def _require_not_final(row: BatonModel) -> None:
    if row.status in _FINAL_STATUSES:
        raise BatonInvalidTransition(
            f"baton {row.id} is {row.status}; final batons cannot be changed"
        )


def _require_current_holder(row: BatonModel, actor_id: str) -> None:
    if row.current_holder_id != actor_id:
        raise BatonAuthorizationError(f"actor {actor_id} is not current holder for baton {row.id}")


def _require_valid_pass_receiver(row: BatonModel, actor_id: str, receiver_id: str) -> None:
    if receiver_id == actor_id:
        raise BatonInvalidTransition(f"cannot pass baton {row.id} to yourself; you already hold it")

    stack = _decode_stack(row)
    if receiver_id in stack:
        raise BatonInvalidTransition(
            f"cannot pass baton {row.id} to {receiver_id} because {receiver_id} "
            "is waiting for this baton to come back from you. Use return_baton "
            f"to send control back to {receiver_id}."
        )

    if receiver_id == row.originator_id and stack:
        raise BatonInvalidTransition(
            f"cannot pass baton {row.id} to originator {receiver_id} because another "
            "holder is still waiting in the return path. Use return_baton to unwind "
            "control, or use complete_baton/block_baton if the originator should be "
            "notified that the workflow is finished or blocked."
        )


def _decode_stack(row: BatonModel) -> List[str]:
    return list(json.loads(row.return_stack_json or "[]"))


def _encode_stack(row: BatonModel, stack: List[str]) -> None:
    row.return_stack_json = json.dumps(stack)


def _append_event(
    db: Session,
    *,
    baton_id: str,
    event_type: BatonEventType,
    actor_id: str,
    from_holder_id: Optional[str] = None,
    to_holder_id: Optional[str] = None,
    message: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> None:
    db.add(
        BatonEventModel(
            baton_id=baton_id,
            event_type=event_type.value,
            actor_id=actor_id,
            from_holder_id=from_holder_id,
            to_holder_id=to_holder_id,
            message=message,
            created_at=created_at or datetime.now(),
        )
    )


def _format_artifacts(artifact_paths: Optional[Sequence[str]]) -> str:
    if not artifact_paths:
        return ""
    return "\n\nArtifacts:\n" + "\n".join(f"- {path}" for path in artifact_paths)


def _expectation_text(expected_next_action: Optional[str]) -> str:
    return expected_next_action or (
        "Use the baton tools to pass, return, complete, or block this baton when ready."
    )


def _holder_guidance(baton_id: str) -> str:
    return (
        "Next tool guidance: when your obligation is done, call one of "
        f'pass_baton(baton_id="{baton_id}", ...), '
        f'return_baton(baton_id="{baton_id}", ...), '
        f'complete_baton(baton_id="{baton_id}", ...), or '
        f'block_baton(baton_id="{baton_id}", ...). '
        "Do not use send_message to transfer baton ownership."
    )


def _originator_guidance(baton_id: str) -> str:
    return (
        "Next tool guidance: inspect the baton with "
        f'get_baton(baton_id="{baton_id}") or create/pass another baton if follow-up '
        "ownership is needed."
    )


def _baton_message(
    *,
    action: str,
    baton_id: str,
    title: str,
    body: Optional[str],
    expected_next_action: Optional[str],
    guidance: str,
    artifact_paths: Optional[Sequence[str]] = None,
) -> str:
    message_body = body or "(no additional message)"
    return (
        f"[CAO Baton] {action}\n\n"
        f"Baton id: {baton_id}\n"
        f"Title: {title}\n"
        f"Current expectation: {_expectation_text(expected_next_action)}\n\n"
        f"Message:\n{message_body}\n\n"
        f"{guidance}"
        f"{_format_artifacts(artifact_paths)}"
    )


def _queue_baton_message(
    db: Session,
    *,
    sender_id: str,
    receiver_id: str,
    action: str,
    baton_id: str,
    title: str,
    body: Optional[str],
    expected_next_action: Optional[str],
    guidance: str,
    artifact_paths: Optional[Sequence[str]] = None,
) -> None:
    db_module.create_inbox_delivery(
        sender_id,
        receiver_id,
        _baton_message(
            action=action,
            baton_id=baton_id,
            title=title,
            body=body,
            expected_next_action=expected_next_action,
            guidance=guidance,
            artifact_paths=artifact_paths,
        ),
        db=db,
    )


def _finish(db: Session, row: BatonModel) -> Baton:
    db.commit()
    db.refresh(row)
    return db_module.baton_from_model(row)


def create_baton(
    *,
    title: str,
    originator_id: str,
    holder_id: str,
    message: Optional[str] = None,
    expected_next_action: Optional[str] = None,
    baton_id: Optional[str] = None,
    artifact_paths: Optional[Sequence[str]] = None,
) -> Baton:
    """Create a baton with ``holder_id`` as the first current holder."""
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = BatonModel(
            id=baton_id or str(uuid.uuid4()),
            title=title,
            status=BatonStatus.ACTIVE.value,
            originator_id=originator_id,
            current_holder_id=holder_id,
            return_stack_json="[]",
            expected_next_action=expected_next_action,
            created_at=now,
            updated_at=now,
            last_nudged_at=None,
            completed_at=None,
        )
        db.add(row)
        db.flush()
        _append_event(
            db,
            baton_id=row.id,
            event_type=BatonEventType.CREATE,
            actor_id=originator_id,
            to_holder_id=holder_id,
            message=message,
            created_at=now,
        )
        _queue_baton_message(
            db,
            sender_id=originator_id,
            receiver_id=holder_id,
            action="You now hold a new baton.",
            baton_id=row.id,
            title=title,
            body=message,
            expected_next_action=expected_next_action,
            guidance=_holder_guidance(row.id),
            artifact_paths=artifact_paths,
        )
        return _finish(db, row)


def pass_baton(
    *,
    baton_id: str,
    actor_id: str,
    receiver_id: str,
    message: Optional[str] = None,
    expected_next_action: Optional[str] = None,
    artifact_paths: Optional[Sequence[str]] = None,
) -> Baton:
    """Pass an active baton to another holder and push the actor on the stack."""
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = _load_baton(db, baton_id)
        _require_active(row)
        _require_current_holder(row, actor_id)
        _require_valid_pass_receiver(row, actor_id, receiver_id)

        stack = _decode_stack(row)
        stack.append(actor_id)
        _encode_stack(row, stack)
        row.current_holder_id = receiver_id
        row.expected_next_action = expected_next_action
        row.updated_at = now
        _append_event(
            db,
            baton_id=baton_id,
            event_type=BatonEventType.PASS,
            actor_id=actor_id,
            from_holder_id=actor_id,
            to_holder_id=receiver_id,
            message=message,
            created_at=now,
        )
        _queue_baton_message(
            db,
            sender_id=actor_id,
            receiver_id=receiver_id,
            action="A baton has been passed to you.",
            baton_id=baton_id,
            title=row.title,
            body=message,
            expected_next_action=expected_next_action,
            guidance=_holder_guidance(baton_id),
            artifact_paths=artifact_paths,
        )
        return _finish(db, row)


def return_baton(
    *,
    baton_id: str,
    actor_id: str,
    message: Optional[str] = None,
    expected_next_action: Optional[str] = None,
    artifact_paths: Optional[Sequence[str]] = None,
) -> Baton:
    """Return an active baton to the previous holder.

    If the return stack is empty, the baton returns to the originator. This
    keeps a one-hop originator -> worker -> originator flow usable without
    forcing the worker to complete the baton.
    """
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = _load_baton(db, baton_id)
        _require_active(row)
        _require_current_holder(row, actor_id)

        stack = _decode_stack(row)
        receiver_id = stack.pop() if stack else row.originator_id
        _encode_stack(row, stack)
        row.current_holder_id = receiver_id
        row.expected_next_action = expected_next_action
        row.updated_at = now
        _append_event(
            db,
            baton_id=baton_id,
            event_type=BatonEventType.RETURN,
            actor_id=actor_id,
            from_holder_id=actor_id,
            to_holder_id=receiver_id,
            message=message,
            created_at=now,
        )
        _queue_baton_message(
            db,
            sender_id=actor_id,
            receiver_id=receiver_id,
            action="A baton has been returned to you.",
            baton_id=baton_id,
            title=row.title,
            body=message,
            expected_next_action=expected_next_action,
            guidance=_holder_guidance(baton_id),
            artifact_paths=artifact_paths,
        )
        return _finish(db, row)


def complete_baton(
    *,
    baton_id: str,
    actor_id: str,
    message: Optional[str] = None,
    artifact_paths: Optional[Sequence[str]] = None,
) -> Baton:
    """Complete an active baton and clear the current holder."""
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = _load_baton(db, baton_id)
        _require_active(row)
        _require_current_holder(row, actor_id)

        previous_holder = row.current_holder_id
        originator_id = row.originator_id
        title = row.title
        row.status = BatonStatus.COMPLETED.value
        row.current_holder_id = None
        row.expected_next_action = None
        row.updated_at = now
        row.completed_at = now
        _append_event(
            db,
            baton_id=baton_id,
            event_type=BatonEventType.COMPLETE,
            actor_id=actor_id,
            from_holder_id=previous_holder,
            to_holder_id=row.originator_id,
            message=message,
            created_at=now,
        )
        _queue_baton_message(
            db,
            sender_id=actor_id,
            receiver_id=originator_id,
            action="A baton has been completed.",
            baton_id=baton_id,
            title=title,
            body=message,
            expected_next_action="Review the completion message and decide whether follow-up is needed.",
            guidance=_originator_guidance(baton_id),
            artifact_paths=artifact_paths,
        )
        return _finish(db, row)


def block_baton(
    *,
    baton_id: str,
    actor_id: str,
    reason: str,
    artifact_paths: Optional[Sequence[str]] = None,
) -> Baton:
    """Block an active baton while keeping the current holder visible."""
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = _load_baton(db, baton_id)
        _require_active(row)
        _require_current_holder(row, actor_id)

        originator_id = row.originator_id
        title = row.title
        row.status = BatonStatus.BLOCKED.value
        row.updated_at = now
        _append_event(
            db,
            baton_id=baton_id,
            event_type=BatonEventType.BLOCK,
            actor_id=actor_id,
            from_holder_id=actor_id,
            to_holder_id=row.originator_id,
            message=reason,
            created_at=now,
        )
        _queue_baton_message(
            db,
            sender_id=actor_id,
            receiver_id=originator_id,
            action="A baton is blocked.",
            baton_id=baton_id,
            title=title,
            body=reason,
            expected_next_action="Review the blocker and provide the decision or resource needed to unblock work.",
            guidance=_originator_guidance(baton_id),
            artifact_paths=artifact_paths,
        )
        return _finish(db, row)


def cancel_baton(
    *,
    baton_id: str,
    actor_id: str,
    message: Optional[str] = None,
    operator_recovery: bool = False,
) -> Baton:
    """Cancel an unresolved baton.

    By default the actor must be the current holder. Passing
    ``operator_recovery=True`` explicitly marks this as an originator/operator
    recovery path and bypasses current-holder authorization.
    """
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = _load_baton(db, baton_id)
        _require_not_final(row)
        if not operator_recovery:
            _require_current_holder(row, actor_id)

        previous_holder = row.current_holder_id
        row.status = BatonStatus.CANCELED.value
        row.current_holder_id = None
        row.expected_next_action = None
        row.updated_at = now
        _append_event(
            db,
            baton_id=baton_id,
            event_type=BatonEventType.CANCEL,
            actor_id=actor_id,
            from_holder_id=previous_holder,
            message=message,
            created_at=now,
        )
        return _finish(db, row)


def reassign_baton(
    *,
    baton_id: str,
    actor_id: str,
    receiver_id: str,
    message: Optional[str] = None,
    expected_next_action: Optional[str] = None,
    operator_recovery: bool = False,
) -> Baton:
    """Reassign an unresolved baton without changing its return stack.

    By default the actor must be the current holder. Passing
    ``operator_recovery=True`` explicitly marks this as an originator/operator
    recovery path and bypasses current-holder authorization.
    """
    now = datetime.now()
    with db_module.SessionLocal() as db:
        row = _load_baton(db, baton_id)
        _require_not_final(row)
        if not operator_recovery:
            _require_current_holder(row, actor_id)

        previous_holder = row.current_holder_id
        row.status = BatonStatus.ACTIVE.value
        row.current_holder_id = receiver_id
        row.expected_next_action = expected_next_action
        row.updated_at = now
        _append_event(
            db,
            baton_id=baton_id,
            event_type=BatonEventType.REASSIGN,
            actor_id=actor_id,
            from_holder_id=previous_holder,
            to_holder_id=receiver_id,
            message=message,
            created_at=now,
        )
        return _finish(db, row)
