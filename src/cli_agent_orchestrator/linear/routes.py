"""HTTP routes for the Linear integration."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel

from cli_agent_orchestrator.linear import app_client, runtime
from cli_agent_orchestrator.linear import workspace_provider as linear_workspace_provider
from cli_agent_orchestrator.linear.webhook_ingestion import parse_linear_webhook_packet
from cli_agent_orchestrator.linear.workspace_events import (
    LinearIssueContextEvent,
    publish_linear_provider_event,
)
from cli_agent_orchestrator.workspace_providers import WorkspaceProviderConfigError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linear", tags=["linear"])


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


def _has_trusted_routing_source(verification: app_client.LinearWebhookVerification) -> bool:
    """Require a trusted Linear source before production webhook routing."""
    return bool(verification.verified and (verification.app_key or verification.app_user_id))


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

    if verification.app_key:
        payload["_cao_linear_app_key"] = verification.app_key
    if verification.agent_id:
        payload["_cao_linear_agent_id"] = verification.agent_id
    if verification.app_user_id:
        payload["_cao_linear_app_user_id"] = verification.app_user_id
    if verification.app_user_name:
        payload["_cao_linear_app_user_name"] = verification.app_user_name

    packet = parse_linear_webhook_packet(payload, header_event=header_event)
    event = packet.event_type
    action = packet.action
    if not _has_trusted_routing_source(verification):
        logger.warning(
            "Ignoring Linear webhook without trusted app/source metadata "
            "event=%s action=%s delivery=%s verified=%s",
            event,
            action,
            delivery,
            verification.verified,
        )
        return LinearWebhookResponse(
            ok=True,
            verified=verification.verified,
            event=event,
            action=action,
            delivery=delivery,
            app_key=verification.app_key,
            agent_session_id=packet.agent_session_id,
            routed=False,
        )

    publication = publish_linear_provider_event(
        payload,
        delivery_id=delivery,
        header_event=header_event,
    )
    provider_event = publication.event if publication is not None else None
    persisted = (
        runtime.persist_linear_provider_event(provider_event)
        if isinstance(provider_event, LinearIssueContextEvent)
        else None
    )
    agent_session_id = (
        provider_event.thread_id
        if isinstance(provider_event, LinearIssueContextEvent)
        else packet.agent_session_id
    )

    logger.info(
        "Received Linear webhook event=%s action=%s delivery=%s agent_session_id=%s verified=%s",
        event,
        action,
        delivery,
        agent_session_id,
        verification.verified,
    )

    notification_result = runtime.notify_or_retry_agent_for_persisted_event(
        persisted,
        provider_event,
    )
    duplicate_delivery = (
        persisted is not None
        and persisted.processed_event is not None
        and isinstance(provider_event, LinearIssueContextEvent)
        and provider_event.thread_id is not None
        and persisted.thread is None
        and persisted.message is None
    )
    routed = notification_result is not None or duplicate_delivery
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
