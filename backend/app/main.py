import logging
from contextlib import asynccontextmanager
from datetime import date
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .access_policy import aware, require_private_account, require_private_scope, user_is_active
from .auth import Principal, authenticate, create_session, require_role, workspace_principal
from .database import check_database, get_session, must_get
from .demo_fixtures import scenarios
from .experience_routes import router as experience_router
from .jira import JiraAdapter, connection_status
from .lifecycle_routes import router as lifecycle_router
from .limits import consume
from .linkedin import LinkedInAdapter
from .linkedin_publishing_routes import router as linkedin_publishing_router
from .models import (
    AuditEvent,
    AuthSession,
    ExtractionRun,
    JiraOperation,
    JiraProposal,
    Job,
    LinkedInProfile,
    Meeting,
    Membership,
    TranscriptRevision,
    User,
    WorkItem,
    Workspace,
    now,
)
from .observability import configure_logging
from .schemas import (
    ApprovalInput,
    DemoLoadInput,
    ExportInput,
    GitHubBindingInput,
    Identifier,
    IndexInput,
    ItemPatch,
    JiraApprovalInput,
    JiraDestinationInput,
    JiraPreviewInput,
    LoginInput,
    MeetingPatch,
    MemberInput,
    MentionConfirmation,
    ParticipantInput,
    PlanInput,
    PlanPatch,
    PreviewInput,
    RecordId,
    RoleInput,
    SearchInput,
    WorkspaceInput,
)
from .services.common import audit, meeting_access
from .services.demo import DemoService
from .services.errors import ServiceError
from .services.issues import IssueService
from .services.jira_delivery import JiraDeliveryService
from .services.lifecycle import owner_lock
from .services.meetings import MeetingService
from .services.planning import PlanningService
from .services.retrieval import RetrievalService
from .services.review import ReviewService
from .settings import settings
from .slack_routes import router as slack_router

configure_logging()
log = logging.getLogger("meeting.api")


@asynccontextmanager
async def lifespan(app):
    check_database()
    yield


app = FastAPI(title="Meeting to Outcomes", version="1.0.0", lifespan=lifespan)
app.include_router(slack_router)
app.include_router(linkedin_publishing_router)
app.include_router(lifecycle_router)
app.include_router(experience_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(
        {
            (urlsplit(settings.app_origin).hostname or "localhost"),
            "localhost",
            "127.0.0.1",
            "testserver",
            "api",
        }
    ),
)


@app.middleware("http")
async def observe(request: Request, call_next):
    request_id, started = str(uuid4()), perf_counter()
    request.state.request_id = request_id
    if (
        request.headers.get("content-length", "").isdigit()
        and int(request.headers["content-length"]) > settings.max_upload_bytes + 65536
    ):
        return JSONResponse(
            status_code=413, content={"error": "Request body exceeds the limit", "request_id": request_id}
        )
    original_receive, received = request._receive, 0

    async def bounded_receive():
        nonlocal received
        message = await original_receive()
        received += len(message.get("body", b""))
        if received > settings.max_upload_bytes + 65536:
            raise ServiceError(status_code=413, error="Request body exceeds the limit", where="client")
        return message

    request._receive = bounded_receive
    try:
        response = await call_next(request)
    except ServiceError as exc:
        response = JSONResponse(status_code=exc.status_code, content={**exc.detail, "request_id": request_id})
    except Exception as exc:  # noqa: BLE001 -- Last request boundary returns a safe error.
        log.error("request_failed", extra={"request_id": request_id, "error_code": type(exc).__name__})
        response = JSONResponse(
            status_code=500, content={"error": "Request failed", "request_id": request_id}
        )
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        }
    )
    log.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        },
    )
    return response


@app.exception_handler(ServiceError)
async def service_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code, content={**exc.detail, "request_id": request.state.request_id}
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": "Request validation failed",
            "fields": [{"location": list(error["loc"]), "type": error["type"]} for error in exc.errors()],
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(ValidationError)
async def contract_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Request validation failed", "request_id": request.state.request_id},
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    log.warning("constraint_conflict", extra={"request_id": request.state.request_id})
    return JSONResponse(
        status_code=409,
        content={
            "error": "This change conflicts with an existing record",
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    log.error(
        "database_error", extra={"request_id": request.state.request_id, "error_code": type(exc).__name__}
    )
    return JSONResponse(
        status_code=503,
        content={"error": "Database is temporarily unavailable", "request_id": request.state.request_id},
    )


@app.get("/healthz")
def health():
    return {"status": "alive"}


@app.get("/readyz")
def ready(session: Session = Depends(get_session, scope="function")):
    session.execute(text("SELECT 1"))
    version = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {"status": "ready", "schema": version}


@app.post("/api/auth/login")
def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    session: Session = Depends(get_session, scope="function"),
):
    if request.headers.get("Origin") != settings.app_origin:
        raise ServiceError(status_code=403, error="Request origin is not allowed", where="client")
    consume("login-ip:" + (request.client.host if request.client else "unknown"), 30)
    consume("login-account:" + payload.email.casefold(), 10)
    user, token, csrf = create_session(session, payload.email, payload.password)
    response.set_cookie(
        "mtt_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "mtt_csrf",
        csrf,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    return {"id": user.id, "name": user.name, "csrf_token": csrf}


@app.post("/api/auth/logout")
def logout(
    response: Response,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    if principal.session_hash:
        session.execute(delete(AuthSession).where(AuthSession.token_hash == principal.session_hash))
    response.delete_cookie("mtt_session", path="/")
    response.delete_cookie("mtt_csrf", path="/")
    return {"ok": True}


@app.get("/api/me")
def me(
    principal: Principal = Depends(authenticate), session: Session = Depends(get_session, scope="function")
):
    user = must_get(session, User, principal.user_id)
    profile = session.get(LinkedInProfile, user.id)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_visitor": user.is_visitor,
        "expires_at": user.visitor_expires_at.isoformat() if user.visitor_expires_at else None,
        "capabilities": {
            "demo_mode": settings.public_demo_mode or user.is_visitor,
            "linkedin_configured": settings.linkedin_configured and not user.is_visitor,
            "ollama_model": settings.ollama_model if not user.is_visitor else None,
            "embedding_provider": settings.embed_provider if not user.is_visitor else "hash",
            "allowed_repos": [
                repo.strip() for repo in settings.github_allowed_repos.split(",") if repo.strip()
            ]
            if not user.is_visitor
            else [],
            "can_upload_transcript": not user.is_visitor,
        },
        "linkedin": {
            "connected": bool(profile),
            "profile": profile.profile if profile else None,
            "provenance": "linkedin_oidc_self",
            "identity_verified": False,
        },
    }


@app.get("/api/demo/scenarios")
def demo_scenarios():
    return {"enabled": settings.visitor_demo_enabled, "scenarios": scenarios()}


@app.post("/api/demo/start", status_code=201)
def start_demo(
    request: Request, response: Response, session: Session = Depends(get_session, scope="function")
):
    if request.headers.get("Origin") != settings.app_origin:
        raise ServiceError(status_code=403, error="Request origin is not allowed", where="client")
    from .auth import digest

    current_token = request.cookies.get("mtt_session")
    browser = session.get(AuthSession, digest(current_token)) if current_token else None
    if browser and aware(browser.expires_at) > now() and user_is_active(session.get(User, browser.user_id)):
        raise ServiceError(
            status_code=409,
            error="You are already signed in; sign out before starting a fresh demo",
            where="client",
        )
    consume("visitor-ip:" + (request.client.host if request.client else "unknown"), 10, 3600)
    user, token, csrf = DemoService(session).start()
    for name, value, http_only in (("mtt_session", token, True), ("mtt_csrf", csrf, False)):
        response.set_cookie(
            name,
            value,
            httponly=http_only,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.visitor_hours * 3600,
            path="/",
        )
    return {
        "id": user.id,
        "name": user.name,
        "is_visitor": True,
        "csrf_token": csrf,
        "expires_at": user.visitor_expires_at.isoformat() if user.visitor_expires_at else None,
    }


@app.get("/api/workspaces")
def workspaces(
    principal: Principal = Depends(authenticate), session: Session = Depends(get_session, scope="function")
):
    query = (
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == principal.user_id)
    )
    if principal.token_workspace_id:
        query = query.where(Workspace.id == principal.token_workspace_id)
    user = must_get(session, User, principal.user_id)
    query = query.where(Workspace.is_demo == user.is_visitor)
    query = query.where(
        or_(Workspace.is_demo.is_(False), Workspace.demo_expires_at > now()),
        Workspace.erasure_requested_at.is_(None),
        Workspace.erased_at.is_(None),
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "department": row.department,
            "role": role,
            "is_demo": row.is_demo,
            "expires_at": row.demo_expires_at.isoformat() if row.demo_expires_at else None,
        }
        for row, role in session.execute(query.order_by(Workspace.name))
    ]


@app.post("/api/workspaces", status_code=201)
def create_workspace(
    payload: WorkspaceInput,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    require_private_account(session, principal)
    if principal.token_workspace_id:
        raise ServiceError(status_code=403, error="Scoped tokens cannot create workspaces", where="client")
    consume("workspace:" + principal.user_id, 10, 3600)
    workspace = Workspace(**payload.model_dump())
    session.add(workspace)
    session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=principal.user_id, role="owner"))
    audit(session, Principal(principal.user_id, workspace.id, "owner"), "workspace.created", workspace.id)
    return {"id": workspace.id, "name": workspace.name, "department": workspace.department, "role": "owner"}


ROOT = "/api/workspaces/{workspace_id}"


@app.post(ROOT + "/demo/load", status_code=202)
def load_demo(
    payload: DemoLoadInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return DemoService(session).load(principal, payload.fixture_id)


@app.get(ROOT + "/integrations/github")
def github_destination_status(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return IssueService(session, principal).destination_status()


@app.post(ROOT + "/integrations/github/destination")
def github_destination(
    payload: GitHubBindingInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return IssueService(session, principal).bind(payload.repo, payload.expected_version)


@app.get(ROOT + "/operations/{operation_id}")
def github_operation(
    operation_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return IssueService(session, principal).operation(operation_id)


@app.get(ROOT + "/meetings/{meeting_id}/deliveries/github")
def github_history(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return IssueService(session, principal).history(meeting_id)


@app.get(ROOT + "/members")
def members(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    require_role(principal, {"owner"})
    return [
        {"id": user.id, "name": user.name, "email": user.email, "role": role}
        for user, role in session.execute(
            select(User, Membership.role)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.workspace_id == principal.workspace_id)
        )
    ]


@app.post(ROOT + "/members", status_code=201)
def add_member(
    payload: MemberInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    require_role(principal, {"owner"})
    require_private_scope(session, principal)
    raise ServiceError(
        status_code=409,
        error="Create an invitation; each person accepts their own membership and chooses their own password",
        where="client",
    )


@app.patch(ROOT + "/members/{user_id}")
def change_role(
    user_id: RecordId,
    payload: RoleInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    require_role(principal, {"owner"})
    require_private_scope(session, principal)
    session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
    session.scalars(
        select(Membership)
        .where(
            Membership.workspace_id == principal.scope, Membership.user_id.in_({principal.user_id, user_id})
        )
        .order_by(Membership.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    owner_lock(session, principal)
    member = session.get(Membership, (principal.workspace_id, user_id))
    if not member:
        raise ServiceError(status_code=404, error="Member not found", where="client")
    owners = session.scalar(
        select(func.count())
        .select_from(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.workspace_id == principal.workspace_id,
            Membership.role == "owner",
            User.active.is_(True),
        )
    )
    target = session.get(User, user_id)
    if member.role == "owner" and target and target.active and payload.role != "owner" and (owners or 0) <= 1:
        raise ServiceError(status_code=409, error="A workspace must retain an owner", where="client")
    member.role = payload.role
    audit(session, principal, "membership.role_changed", user_id, {"role": payload.role})
    return {"ok": True}


@app.get(ROOT + "/participants")
def participants(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return ReviewService(session, principal).participants()


@app.post(ROOT + "/participants", status_code=201)
def add_participant(
    payload: ParticipantInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return ReviewService(session, principal).add_participant(payload)


@app.get(ROOT + "/meetings")
def list_meetings(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    q: str | None = Query(None, min_length=1, max_length=200),
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return MeetingService(session, principal).list(offset, limit, q)


@app.post(ROOT + "/index", status_code=202)
def index(
    payload: IndexInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    require_private_scope(session, principal)
    consume("index:" + principal.scope, 60, 3600)
    return MeetingService(session, principal).index(payload)


@app.post(ROOT + "/upload", status_code=202)
async def upload(
    file: UploadFile = File(...),
    meeting_id: str = Form(...),
    title: str = Form(""),
    expected_version: int | None = Form(None),
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    require_private_scope(session, principal)
    service = MeetingService(session, principal)
    service.validate_upload_filename(file.filename)
    raw = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    payload = IndexInput(
        meeting_id=meeting_id,
        title=title,
        transcript=service.decode_upload_text(file.filename, raw),
        expected_version=expected_version,
    )
    consume("index:" + principal.scope, 60, 3600)
    return service.index(payload)


@app.get(ROOT + "/meetings/{meeting_id}")
def get_meeting(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return MeetingService(session, principal).get(meeting_id)


@app.patch(ROOT + "/meetings/{meeting_id}")
def rename(
    meeting_id: Identifier,
    payload: MeetingPatch,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return MeetingService(session, principal).rename(meeting_id, payload.title, payload.expected_version)


@app.delete(ROOT + "/meetings/{meeting_id}")
def archive(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return MeetingService(session, principal).delete(meeting_id)


@app.post(ROOT + "/meetings/{meeting_id}/extract", status_code=202)
def extract(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    consume(
        "extract:" + principal.scope,
        60,
        3600,
        session=session if must_get(session, User, principal.user_id).is_visitor else None,
    )
    return MeetingService(session, principal).enqueue_extraction(meeting_id)


@app.post(ROOT + "/meetings/{meeting_id}/search")
def search(
    meeting_id: Identifier,
    payload: SearchInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return RetrievalService(session, principal).search(meeting_id, payload.q, payload.k)


@app.patch(ROOT + "/meetings/{meeting_id}/outcomes/{item_id}")
def patch_item(
    meeting_id: Identifier,
    item_id: RecordId,
    payload: ItemPatch,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return ReviewService(session, principal).patch(meeting_id, item_id, payload)


@app.get(ROOT + "/plan")
def daily_plan(
    day: date,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return PlanningService(session, principal).list(day)


@app.post(ROOT + "/meetings/{meeting_id}/outcomes/{item_id}/plan", status_code=201)
def plan_outcome(
    meeting_id: Identifier,
    item_id: RecordId,
    payload: PlanInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return PlanningService(session, principal).add(meeting_id, item_id, payload)


@app.patch(ROOT + "/meetings/{meeting_id}/outcomes/{item_id}/plan")
def update_plan(
    meeting_id: Identifier,
    item_id: RecordId,
    payload: PlanPatch,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return PlanningService(session, principal).patch(meeting_id, item_id, payload)


@app.delete(ROOT + "/meetings/{meeting_id}/outcomes/{item_id}/plan")
def remove_plan(
    meeting_id: Identifier,
    item_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return PlanningService(session, principal).remove(meeting_id, item_id)


@app.get(ROOT + "/meetings/{meeting_id}/outcomes/{item_id}/history")
def item_history(
    meeting_id: Identifier,
    item_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return ReviewService(session, principal).history(meeting_id, item_id)


@app.get(ROOT + "/meetings/{meeting_id}/revisions/{number}")
def revision(
    meeting_id: Identifier,
    number: int,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    meeting = meeting_access(session, principal, meeting_id)
    row = session.scalar(
        select(TranscriptRevision).where(
            TranscriptRevision.meeting_id == meeting.id, TranscriptRevision.number == number
        )
    )
    if not row:
        raise ServiceError(status_code=404, error="Revision not found", where="client")
    runs = session.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.revision_id == row.id)
        .order_by(ExtractionRun.created_at.desc())
    ).all()
    return {
        "id": row.id,
        "number": row.number,
        "raw_text": row.raw_text,
        "tasks": ReviewService(session, principal).list_items(meeting, row.id),
        "extractions": [
            {"mode": run.mode, "coverage": run.coverage, "created_at": run.created_at.isoformat()}
            for run in runs
        ],
    }


@app.post(ROOT + "/meetings/{meeting_id}/mentions/{mention_id}/confirm")
def confirm(
    meeting_id: Identifier,
    mention_id: RecordId,
    payload: MentionConfirmation,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return ReviewService(session, principal).confirm_mention(meeting_id, mention_id, payload.participant_id)


@app.post(ROOT + "/meetings/{meeting_id}/preview")
def preview(
    meeting_id: Identifier,
    payload: PreviewInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return IssueService(session, principal).preview(meeting_id, payload)


@app.get(ROOT + "/integrations")
def integrations(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    from .services.delivery import integration_catalog

    return integration_catalog(session, principal)


@app.post(ROOT + "/meetings/{meeting_id}/export")
def export_reviewed(
    meeting_id: Identifier,
    payload: ExportInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    from .services.delivery import export_outcomes

    return export_outcomes(session, principal, meeting_id, payload)


@app.post(ROOT + "/proposals/{proposal_id}/approve", status_code=202)
def approve(
    proposal_id: RecordId,
    payload: ApprovalInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return IssueService(session, principal).approve(proposal_id, payload.payload_hash)


@app.get(ROOT + "/jobs/{job_id}")
def job_status(
    job_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    job = session.get(Job, job_id)
    if not job or job.workspace_id != principal.workspace_id:
        raise ServiceError(status_code=404, error="Job not found", where="client")
    if job.meeting_id:
        meeting = must_get(session, Meeting, job.meeting_id)
        meeting_access(session, principal, meeting.slug)
    return {
        "id": job.id,
        "kind": job.kind,
        "state": job.state,
        "result": job.result,
        "error_code": job.error_code,
        "attempts": job.attempts,
    }


@app.get(ROOT + "/integrations/jira/metadata")
async def jira_metadata(
    issue_type_id: str | None = Query(default=None, pattern=r"^[0-9]{1,20}$"),
    issue_key: str | None = Query(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,39}-[1-9][0-9]{0,19}$"),
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await JiraDeliveryService(session, principal).metadata(issue_type_id, issue_key)


@app.post(ROOT + "/meetings/{meeting_id}/jira/preview")
async def jira_preview(
    meeting_id: Identifier,
    payload: JiraPreviewInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await JiraDeliveryService(session, principal).preview(meeting_id, payload)


@app.post(ROOT + "/jira/proposals/{proposal_id}/approve", status_code=202)
async def jira_approve(
    proposal_id: RecordId,
    payload: JiraApprovalInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await JiraDeliveryService(session, principal).approve(
        proposal_id, payload.payload_hash, retry_rejected=payload.retry_rejected
    )


@app.get(ROOT + "/jira/operations/{operation_id}")
def jira_receipt(
    operation_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    operation, proposal = JiraDeliveryService(session, principal).receipt(operation_id)
    return {
        "operation_id": operation.id,
        "state": operation.state,
        "result": operation.result,
        "proposal": JiraDeliveryService.serialize(proposal),
    }


@app.get(ROOT + "/meetings/{meeting_id}/jira/deliveries")
def jira_deliveries(
    meeting_id: Identifier,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    meeting = meeting_access(session, principal, meeting_id)
    rows = session.execute(
        select(JiraOperation, JiraProposal)
        .join(JiraProposal)
        .where(
            JiraProposal.meeting_id == meeting.id,
            JiraProposal.workspace_id == principal.scope,
            JiraProposal.actor_id == principal.user_id,
        )
        .order_by(JiraOperation.created_at.desc())
        .limit(50)
    )
    return [
        {
            "operation_id": operation.id,
            "state": operation.state,
            "result": operation.result,
            "action": proposal.action,
            "item_id": proposal.snapshot["item_id"],
            "item_version": proposal.snapshot["version"],
            "project_key": proposal.destination["project_key"],
        }
        for operation, proposal in rows
    ]


@app.post(ROOT + "/jira/operations/{operation_id}/reconcile")
async def jira_reconcile(
    operation_id: RecordId,
    issue_key: str = Query(pattern=r"^[A-Z][A-Z0-9_]{1,39}-[1-9][0-9]{0,19}$"),
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await JiraDeliveryService(session, principal).reconcile(operation_id, issue_key)


@app.post(ROOT + "/operations/{operation_id}/reconcile")
async def reconcile(
    operation_id: RecordId,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await IssueService(session, principal).reconcile(operation_id)


@app.get(ROOT + "/summary")
def summary(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    kinds = ("action", "decision", "blocker", "follow_up", "risk")
    counts = [
        func.count(WorkItem.id).filter(WorkItem.kind == kind, WorkItem.status != "dismissed").label(kind)
        for kind in kinds
    ]
    query = (
        select(
            *counts,
            func.count(WorkItem.id)
            .filter(
                WorkItem.assignee_hint.is_not(None),
                WorkItem.assignee_hint != "",
                WorkItem.owner_id.is_(None),
                WorkItem.status == "draft",
            )
            .label("unconfirmed_owners"),
            func.count(WorkItem.id).filter(WorkItem.status == "draft").label("review_pending"),
        )
        .join(Meeting, Meeting.id == WorkItem.meeting_id)
        .join(TranscriptRevision, TranscriptRevision.id == WorkItem.revision_id)
        .where(
            Meeting.workspace_id == principal.workspace_id,
            Meeting.archived_at.is_(None),
            TranscriptRevision.number == Meeting.current_revision,
        )
    )
    if principal.role not in {"owner", "reviewer"}:
        query = query.where(or_(Meeting.visibility == "workspace", Meeting.created_by == principal.user_id))
    totals = session.execute(query).mappings().one()
    return {
        "counts": {kind: totals[kind] for kind in kinds},
        "unconfirmed_owners": totals["unconfirmed_owners"],
        "review_pending": totals["review_pending"],
    }


@app.get(ROOT + "/audit")
def audit_log(
    limit: int = Query(50, ge=1, le=100),
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    require_role(principal, {"owner", "reviewer"})
    return [
        {
            "action": row.action,
            "target_id": row.target_id,
            "actor_id": row.actor_id,
            "details": row.details,
            "created_at": row.created_at.isoformat(),
        }
        for row in session.scalars(
            select(AuditEvent)
            .where(AuditEvent.workspace_id == principal.workspace_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
    ]


@app.post(ROOT + "/integrations/jira/connect")
def jira_connect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return JiraAdapter().begin(session, principal)


@app.get(ROOT + "/integrations/jira")
def jira_status(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return connection_status(session, principal)


@app.get(ROOT + "/integrations/jira/sites")
async def jira_sites(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await JiraAdapter().sites(session, principal)


@app.post(ROOT + "/integrations/jira/destination")
async def jira_destination(
    payload: JiraDestinationInput,
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return await JiraAdapter().choose(session, principal, payload)


@app.delete(ROOT + "/integrations/jira")
def jira_disconnect(
    principal: Principal = Depends(workspace_principal),
    session: Session = Depends(get_session, scope="function"),
):
    return JiraAdapter().disconnect(session, principal)


@app.get("/api/integrations/jira/callback")
async def jira_callback(
    state: str = Query(min_length=1, max_length=200),
    code: str | None = Query(None, min_length=1, max_length=2000),
    error: str | None = Query(None, max_length=200),
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    workspace = await JiraAdapter().complete(session, principal, state, code, bool(error))
    return RedirectResponse(
        settings.app_origin + "/workspaces/" + workspace + "/integrations", status_code=303
    )


@app.post("/api/integrations/linkedin/connect")
def linkedin_connect(
    principal: Principal = Depends(authenticate), session: Session = Depends(get_session, scope="function")
):
    require_private_account(session, principal)
    return LinkedInAdapter().begin(session, principal)


@app.get("/api/integrations/linkedin/callback")
async def linkedin_callback(
    state: str = Query(min_length=1, max_length=200),
    code: str | None = Query(None, max_length=2000),
    error: str | None = Query(None, max_length=200),
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
):
    require_private_account(session, principal)
    result = await LinkedInAdapter().complete(session, principal, state, code, denied=bool(error))
    session.commit()
    return RedirectResponse(
        settings.app_origin + ("/?linkedin=connected" if result["connected"] else "/?linkedin=cancelled"),
        status_code=303,
    )


@app.delete("/api/integrations/linkedin")
def linkedin_disconnect(
    principal: Principal = Depends(authenticate), session: Session = Depends(get_session, scope="function")
):
    require_private_account(session, principal)
    return LinkedInAdapter().disconnect(session, principal)
