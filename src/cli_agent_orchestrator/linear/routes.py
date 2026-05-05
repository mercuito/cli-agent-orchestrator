"""HTTP routes for the Linear integration."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel

from cli_agent_orchestrator.linear import app_client, runtime
from cli_agent_orchestrator.linear.presence_provider import (
    LinearPresenceProvider,
    payload_with_header_event,
)
from cli_agent_orchestrator.presence.manager import (
    UnknownPresenceProviderError,
    presence_provider_manager,
)
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linear", tags=["linear"])
_linear_presence_provider = LinearPresenceProvider()


def _ensure_linear_presence_provider() -> None:
    try:
        presence_provider_manager.get_provider(_linear_presence_provider.name)
        return
    except UnknownPresenceProviderError:
        pass

    presence_provider_manager.register_provider(
        _linear_presence_provider.name,
        _linear_presence_provider,
    )


def _should_run_smoke_runtime(persisted: Optional[PersistedPresenceEvent]) -> bool:
    if persisted is None:
        return False
    return persisted.thread is not None


class LinearOAuthCallbackResponse(BaseModel):
    """Response returned after a Linear app actor OAuth install."""

    ok: bool
    viewer_id: str
    viewer_name: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None
    state_verified: bool


class LinearWebhookResponse(BaseModel):
    """Response returned after receiving a Linear webhook."""

    ok: bool
    verified: bool
    event: Optional[str] = None
    action: Optional[str] = None
    delivery: Optional[str] = None
    agent_session_id: Optional[str] = None
    routed: bool = False


@router.get("/oauth/callback", response_model=LinearOAuthCallbackResponse)
def oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
) -> LinearOAuthCallbackResponse:
    """Complete Linear app actor OAuth installation."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_description or error,
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Linear OAuth code",
        )

    try:
        result = app_client.install_linear_app(code, state)
    except app_client.LinearConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except app_client.LinearOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    viewer = result["viewer"]
    return LinearOAuthCallbackResponse(
        ok=True,
        viewer_id=viewer["id"],
        viewer_name=viewer.get("name"),
        token_type=result.get("token_type"),
        expires_in=result.get("expires_in"),
        state_verified=result["state_verified"],
    )


@router.post("/webhooks/agent", response_model=LinearWebhookResponse)
async def agent_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> LinearWebhookResponse:
    """Receive Linear agent/session webhooks."""
    raw_body = await request.body()
    signature = request.headers.get("Linear-Signature")
    delivery = request.headers.get("Linear-Delivery")
    header_event = request.headers.get("Linear-Event")

    try:
        payload = app_client.parse_webhook_payload(raw_body)
        verified = app_client.verify_webhook(raw_body, signature, payload)
    except app_client.LinearWebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    _ensure_linear_presence_provider()
    provider_payload = payload_with_header_event(payload, header_event=header_event)
    presence_event = presence_provider_manager.normalize_event(
        "linear",
        provider_payload,
        delivery_id=delivery,
    )
    persisted = presence_provider_manager.ingest_event(
        "linear",
        provider_payload,
        delivery_id=delivery,
    )
    presence_event = presence_event if presence_event is not None else None
    event = app_client.webhook_event_type(
        payload,
        header_event=header_event,
    )
    agent_session_id = presence_event.thread.ref.id if presence_event and presence_event.thread else None
    action = payload.get("action")

    logger.info(
        "Received Linear webhook event=%s action=%s delivery=%s agent_session_id=%s verified=%s",
        event,
        action,
        delivery,
        agent_session_id,
        verified,
    )

    routed = presence_event is not None or persisted is not None
    if presence_event is not None and _should_run_smoke_runtime(persisted):
        background_tasks.add_task(runtime.handle_presence_event, presence_event)

    return LinearWebhookResponse(
        ok=True,
        verified=verified,
        event=event,
        action=action,
        delivery=delivery,
        agent_session_id=agent_session_id,
        routed=routed,
    )
