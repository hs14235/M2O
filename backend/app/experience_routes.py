"""Calendar reads and Google Meet exact import boundaries."""

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import Field
from sqlalchemy.orm import Session

from .auth import Principal, authenticate, workspace_principal
from .database import get_session
from .google_meet import GoogleMeetAdapter
from .schemas import Contract, Identifier, RecordId
from .services.calendar import CalendarService
from .services.errors import ServiceError
from .services.meet_import import MeetImportService
from .settings import settings

router = APIRouter()
ROOT = "/api/workspaces/{workspace_id}"


class ImportPreviewInput(Contract):
    pass


class ImportSaveInput(Contract):
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=200)
    meeting_id: Identifier
    visibility: Literal["workspace", "restricted"] = "restricted"


@router.get(ROOT + "/calendar")
def calendar(
    start: date,
    end: date,
    response: Response,
    meeting_id: Identifier | None = None,
    include_unscheduled: bool = True,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    return CalendarService(session, principal).list(
        start, end, meeting_id=meeting_id, include_unscheduled=include_unscheduled, limit=limit, offset=offset
    )


@router.get(ROOT + "/integrations/google-meet")
def status(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return GoogleMeetAdapter().status(session, principal)


@router.post(ROOT + "/integrations/google-meet/connect")
def connect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return GoogleMeetAdapter().begin(session, principal)


@router.delete("/api/integrations/google-meet")
def disconnect(
    principal: Principal = Depends(authenticate), session: Session = Depends(get_session, scope="function")
):
    return GoogleMeetAdapter().disconnect(session, principal)


@router.delete(ROOT + "/integrations/google-meet")
def disconnect_scoped(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return GoogleMeetAdapter().disconnect(session, principal)


@router.get("/api/integrations/google-meet/callback")
async def callback(
    state: str = Query(min_length=1, max_length=200),
    code: str | None = Query(None, min_length=1, max_length=2000),
    error: str | None = Query(None, max_length=200),
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    workspace_id = await GoogleMeetAdapter().complete(session, principal, state, code, bool(error))
    return RedirectResponse(
        settings.app_origin + "/workspaces/" + workspace_id + "/integrations", status_code=303
    )


@router.post(ROOT + "/imports/google-meet/preview")
async def preview(
    payload: ImportPreviewInput,
    response: Response,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        async with asyncio.timeout(25):
            return await MeetImportService(session, principal).preview()
    except TimeoutError as exc:
        raise ServiceError(
            status_code=504,
            error="Google import timed out; no partial transcript was saved",
            where="google_meet",
        ) from exc


@router.post(ROOT + "/imports/google-meet/{preview_id}/save", status_code=202)
def save(
    preview_id: RecordId,
    payload: ImportSaveInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return MeetImportService(session, principal).save(
        preview_id, payload.payload_hash, payload.title, payload.meeting_id, visibility=payload.visibility
    )
