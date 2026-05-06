"""HTTP routes for the Linear integration."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel

from cli_agent_orchestrator.linear import app_client
from cli_agent_orchestrator.linear import inbox_bridge as linear_inbox_bridge
from cli_agent_orchestrator.linear import runtime
from cli_agent_orchestrator.linear import workspace_provider as linear_workspace_provider
from cli_agent_orchestrator.linear.presence_provider import (
    LinearPresenceProvider,
    payload_with_header_event,
)
from cli_agent_orchestrator.presence.manager import (
    UnknownPresenceProviderError,
    presence_provider_manager,
)
from cli_agent_orchestrator.presence.models import PersistedPresenceEvent
from cli_agent_orchestrator.workspace_providers import WorkspaceProviderConfigError

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


def _require_linear_workspace_provider_enabled() -> None:
    """Honor explicit workspace-provider enablement while preserving no-config compatibility."""
    try:
        enabled = linear_workspace_provider.should_enable_linear_routes()
    except WorkspaceProviderConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Linear workspace provider is not enabled",
        )


class LinearOAuthCallbackResponse(BaseModel):
    """Response returned after a Linear app actor OAuth install."""

    ok: bool
    app_key: Optional[str] = None
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
    app_key: Optional[str] = None
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
    _require_linear_workspace_provider_enabled()
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
        app_key=result.get("app_key"),
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
    _require_linear_workspace_provider_enabled()
    raw_body = await request.body()
    signature = request.headers.get("Linear-Signature")
    delivery = request.headers.get("Linear-Delivery")
    header_event = request.headers.get("Linear-Event")

    try:
        payload = app_client.parse_webhook_payload(raw_body)
        verification = app_client.verify_webhook_source(raw_body, signature, payload)
    except app_client.LinearWebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    _ensure_linear_presence_provider()
    if verification.app_key:
        payload["_cao_linear_app_key"] = verification.app_key
    if verification.agent_id:
        payload["_cao_linear_agent_id"] = verification.agent_id
    if verification.app_user_id:
        payload["_cao_linear_app_user_id"] = verification.app_user_id
    if verification.app_user_name:
        payload["_cao_linear_app_user_name"] = verification.app_user_name
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
    agent_session_id = (
        presence_event.thread.ref.id if presence_event and presence_event.thread else None
    )
    action = payload.get("action")

    logger.info(
        "Received Linear webhook event=%s action=%s delivery=%s agent_session_id=%s verified=%s",
        event,
        action,
        delivery,
        agent_session_id,
        verification.verified,
    )

    notification = linear_inbox_bridge.notify_receiver_for_persisted_event(persisted)

    routed = presence_event is not None or persisted is not None or notification is not None
    if notification is None and presence_event is not None and _should_run_smoke_runtime(persisted):
        background_tasks.add_task(runtime.handle_presence_event, presence_event)

    return LinearWebhookResponse(
        ok=True,
        verified=verification.verified,
        event=event,
        action=action,
        delivery=delivery,
        app_key=verification.app_key,
        agent_session_id=agent_session_id,
        routed=routed,
    )
