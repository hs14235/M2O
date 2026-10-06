"""Workspace-scoped local drafts and separately authorized LinkedIn member publishing."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .auth import Principal, authenticate, workspace_principal
from .database import get_session
from .schemas import (
    ApprovalInput,
    Identifier,
    LinkedInDraftInput,
    LinkedInDraftPatch,
    LinkedInPreviewInput,
    RecordId,
)
from .services.errors import ServiceError
from .services.linkedin_drafts import LinkedInDraftService
from .services.linkedin_publishing import LinkedInPublishingService
from .settings import settings

router = APIRouter()
ROOT = "/api/workspaces/{workspace_id}"


@router.get(ROOT + "/meetings/{meeting_id}/linkedin/drafts")
def drafts(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInDraftService(session, principal).list(meeting_id)


@router.post(ROOT + "/meetings/{meeting_id}/linkedin/drafts", status_code=201)
def create_draft(
    meeting_id: Identifier,
    payload: LinkedInDraftInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInDraftService(session, principal).create(meeting_id, payload)


@router.patch(ROOT + "/meetings/{meeting_id}/linkedin/drafts/{draft_id}")
def update_draft(
    meeting_id: Identifier,
    draft_id: RecordId,
    payload: LinkedInDraftPatch,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInDraftService(session, principal).update(meeting_id, draft_id, payload)


@router.get(ROOT + "/integrations/linkedin/publishing")
def status(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).status()


@router.post(ROOT + "/integrations/linkedin/publishing/connect")
def connect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).begin()


@router.delete(ROOT + "/integrations/linkedin/publishing")
def disconnect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).disconnect()


@router.delete("/api/integrations/linkedin/publishing")
def disconnect_account(
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    if not principal.session_hash:
        raise ServiceError(
            status_code=403,
            error="Disconnect an account-wide grant from your signed-in browser",
            where="client",
        )
    return LinkedInPublishingService(session, principal).disconnect_account()


@router.get("/api/integrations/linkedin/publishing/callback")
async def callback(
    state: str = Query(min_length=1, max_length=200),
    code: str | None = Query(default=None, min_length=1, max_length=2000),
    error: str | None = Query(default=None, max_length=200),
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    result = await LinkedInPublishingService(session, principal).complete(state, code, denied=bool(error))
    return RedirectResponse(
        settings.app_origin + "/workspaces/" + result["workspace_id"] + "/integrations", status_code=303
    )


@router.post(ROOT + "/meetings/{meeting_id}/linkedin/preview")
def preview(
    meeting_id: Identifier,
    payload: LinkedInPreviewInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).preview(meeting_id, payload)


@router.post(ROOT + "/linkedin/proposals/{proposal_id}/approve", status_code=202)
def approve(
    proposal_id: RecordId,
    payload: ApprovalInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).approve(proposal_id, payload.payload_hash)


@router.get(ROOT + "/linkedin/operations/{operation_id}")
def operation(
    operation_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).operation(operation_id)


@router.get(ROOT + "/meetings/{meeting_id}/deliveries/linkedin")
def history(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return LinkedInPublishingService(session, principal).history(meeting_id)
