"""Browser lifecycle endpoints; secret links are submitted in bodies, never query URLs."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from .auth import Principal, authenticate, workspace_principal
from .database import get_session
from .limits import consume
from .schemas import (
    AccountErasureInput,
    InvitationAcceptInput,
    InvitationInput,
    InvitationTokenInput,
    RecordId,
    RecoveryInput,
    RecoveryRequestInput,
    WorkspaceErasureInput,
)
from .services.errors import ServiceError
from .services.lifecycle import InvitationService, RecoveryService
from .services.privacy import PrivacyService
from .settings import settings

router = APIRouter()
ROOT = "/api/workspaces/{workspace_id}"


def origin(request: Request) -> None:
    if request.headers.get("Origin") != settings.app_origin:
        raise ServiceError(status_code=403, error="Request origin is not allowed", where="client")


def optional_browser(request: Request, session: Session) -> Principal | None:
    if request.headers.get("Authorization"):
        raise ServiceError(
            status_code=403, error="Accept invitations in your signed-in browser", where="client"
        )
    if not request.cookies.get("mtt_session"):
        return None
    try:
        return authenticate(request, session)
    except ServiceError as exc:
        if exc.status_code != 401:
            raise
        return None


@router.post(ROOT + "/invitations", status_code=201)
def issue_invitation(
    payload: InvitationInput,
    response: Response,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    consume("invitation:" + principal.scope, 30, 3600)
    response.headers["Cache-Control"] = "no-store"
    return InvitationService(session).issue(principal, payload)


@router.get(ROOT + "/invitations")
def invitations(
    response: Response,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    return InvitationService(session).list(principal)


@router.delete(ROOT + "/invitations/{invitation_id}")
def revoke_invitation(
    invitation_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return InvitationService(session).revoke(principal, invitation_id)


@router.post("/api/invitations/inspect")
def inspect_invitation(
    payload: InvitationTokenInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session, scope="function"),
):
    origin(request)
    consume("invitation-inspect:" + (request.client.host if request.client else "unknown"), 30)
    response.headers["Cache-Control"] = "no-store"
    return InvitationService(session).inspect(payload.token)


@router.post("/api/invitations/accept")
def accept_invitation(
    payload: InvitationAcceptInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session, scope="function"),
):
    origin(request)
    consume("invitation-accept:" + (request.client.host if request.client else "unknown"), 15)
    response.headers["Cache-Control"] = "no-store"
    return InvitationService(session).accept(payload, optional_browser(request, session))


@router.post("/api/auth/recovery/request", status_code=202)
def recovery_request(payload: RecoveryRequestInput, request: Request):
    origin(request)
    consume("recovery-request:" + (request.client.host if request.client else "unknown"), 10)
    return {
        "accepted": True,
        "delivery": "manual_operator",
        "message": "Contact the M2O operator to verify your identity and request a private recovery link. This form does not send email.",
    }


@router.post("/api/auth/recovery/reset")
def recovery_reset(
    payload: RecoveryInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session, scope="function"),
):
    origin(request)
    consume("recovery-reset:" + (request.client.host if request.client else "unknown"), 10)
    result = RecoveryService(session).reset(payload)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie("mtt_session", path="/")
    response.delete_cookie("mtt_csrf", path="/")
    return result


@router.get("/api/privacy/account/export")
def export_account(
    response: Response,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    if not principal.session_hash:
        raise ServiceError(
            status_code=403, error="Export account data from your signed-in browser", where="client"
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = 'attachment; filename="m2o-account-export.json"'
    return PrivacyService(session).account_export(principal)


@router.get(ROOT + "/privacy/export")
def export_workspace(
    response: Response,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = 'attachment; filename="m2o-workspace-export.json"'
    return PrivacyService(session).workspace_export(principal)


@router.get(ROOT + "/privacy")
def workspace_privacy(
    workspace_id: RecordId,
    response: Response,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    return PrivacyService(session).workspace_status(
        Principal(
            principal.user_id,
            workspace_id,
            token_workspace_id=principal.token_workspace_id,
            auth_version=principal.auth_version,
        )
    )


@router.post(ROOT + "/privacy/erase")
def erase_workspace(
    workspace_id: RecordId,
    payload: WorkspaceErasureInput,
    response: Response,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    consume("workspace-erasure:" + principal.user_id, 10, 3600)
    response.headers["Cache-Control"] = "no-store"
    scoped = Principal(
        principal.user_id,
        workspace_id,
        token_workspace_id=principal.token_workspace_id,
        auth_version=principal.auth_version,
    )
    result = PrivacyService(session).erase_workspace(scoped, payload)
    if result["state"] == "pending_erasure":
        response.status_code = 202
    return result


@router.post("/api/privacy/account/erase")
def erase_account(
    payload: AccountErasureInput,
    response: Response,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    if not principal.session_hash:
        raise ServiceError(
            status_code=403, error="Delete your account from a signed-in browser", where="client"
        )
    consume("account-erasure:" + principal.user_id, 5, 3600)
    result = PrivacyService(session).erase_account(principal, payload.password)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie("mtt_session", path="/")
    response.delete_cookie("mtt_csrf", path="/")
    return result
