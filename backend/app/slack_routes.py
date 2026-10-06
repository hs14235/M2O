"""HTTP boundary for Slack; browser mutations retain normal CSRF and workspace checks."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .auth import Principal, authenticate, workspace_principal
from .database import get_session
from .schemas import (
    Identifier,
    RecordId,
    SlackApprovalInput,
    SlackDestinationInput,
    SlackLinkConfirmation,
    SlackLinkInput,
    SlackPreviewInput,
    SlackReconcileInput,
)
from .services.errors import ServiceError
from .services.slack_delivery import SlackDeliveryService
from .settings import settings
from .slack import SlackAdapter, connection_status
from .slack_actions import MAX_BODY, SlackActions, verify_request

router = APIRouter()
ROOT = "/api/workspaces/{workspace_id}"


@router.post(ROOT + "/integrations/slack/connect")
def connect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackAdapter().begin(session, principal)


@router.get(ROOT + "/integrations/slack")
def status(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return connection_status(session, principal)


@router.post(ROOT + "/integrations/slack/destination")
async def destination(
    payload: SlackDestinationInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await SlackAdapter().choose(session, principal, payload)


@router.delete(ROOT + "/integrations/slack")
def disconnect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackAdapter().disconnect(session, principal)


@router.get("/api/integrations/slack/callback")
async def callback(
    state: str = Query(min_length=1, max_length=200),
    code: str | None = Query(None, min_length=1, max_length=2000),
    error: str | None = Query(None, max_length=200),
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    workspace = await SlackAdapter().complete(session, principal, state, code, bool(error))
    return RedirectResponse(
        settings.app_origin + "/workspaces/" + workspace + "/integrations", status_code=303
    )


@router.post(ROOT + "/meetings/{meeting_id}/slack/preview")
async def preview(
    meeting_id: Identifier,
    payload: SlackPreviewInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await SlackDeliveryService(session, principal).preview(meeting_id, payload)


@router.post(ROOT + "/slack/proposals/{proposal_id}/approve", status_code=202)
async def approve(
    proposal_id: RecordId,
    payload: SlackApprovalInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await SlackDeliveryService(session, principal).approve(
        proposal_id, payload.payload_hash, retry_rejected=payload.retry_rejected
    )


@router.get(ROOT + "/slack/operations/{operation_id}")
def receipt(
    operation_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    service = SlackDeliveryService(session, principal)
    return service.receipt_payload(*service.receipt(operation_id))


@router.get(ROOT + "/meetings/{meeting_id}/slack/deliveries")
def history(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackDeliveryService(session, principal).history(meeting_id)


@router.post(ROOT + "/slack/operations/{operation_id}/reconcile")
async def reconcile(
    operation_id: RecordId,
    payload: SlackReconcileInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await SlackDeliveryService(session, principal).reconcile(operation_id, payload.message_ts)


@router.get(ROOT + "/integrations/slack/actions")
def action_status(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackActions(session).link_status(principal)


@router.post(ROOT + "/integrations/slack/link")
def link(
    payload: SlackLinkInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackActions(session).begin_link(principal, payload.connection_id)


@router.get(ROOT + "/integrations/slack/link/{challenge_id}")
def pending(
    challenge_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackActions(session).pending_link(principal, challenge_id)


@router.post(ROOT + "/integrations/slack/link/confirm")
def confirm_link(
    payload: SlackLinkConfirmation,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackActions(session).confirm_link(principal, payload.challenge_id, payload.slack_user_id)


@router.delete(ROOT + "/integrations/slack/link/{connection_id}")
def unlink(
    connection_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return SlackActions(session).unlink(principal, connection_id)


async def receive_slack(request: Request, session: Session, interactive: bool):
    if (
        request.headers.get("content-type", "").split(";")[0].strip().casefold()
        != "application/x-www-form-urlencoded"
    ):
        raise ServiceError(status_code=415, error="Slack requires a form-encoded request", where="slack")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise ServiceError(status_code=413, error="Slack request exceeds the limit", where="slack")
    raw = bytes(body)
    request_hash = verify_request(
        raw,
        request.headers.getlist("x-slack-request-timestamp"),
        request.headers.getlist("x-slack-signature"),
    )
    return await SlackActions(session).receive(raw, request_hash, interactive=interactive)


@router.post("/api/integrations/slack/commands")
async def command(request: Request, session: Session = Depends(get_session, scope="function")):
    return await receive_slack(request, session, False)


@router.post("/api/integrations/slack/interactions")
async def interaction(request: Request, session: Session = Depends(get_session, scope="function")):
    return await receive_slack(request, session, True)
