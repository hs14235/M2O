"""Bounded public exploration without shared identities or private credentials."""

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..access_policy import consume_visitor_usage, workspace_access
from ..auth import Principal, digest, hasher
from ..demo_fixtures import DEPARTMENTS, FIXTURES
from ..models import (
    AuthSession,
    DemoAdmission,
    Meeting,
    Membership,
    Participant,
    User,
    VisitorUsage,
    Workspace,
    now,
)
from ..schemas import IndexInput
from ..settings import settings
from .errors import ServiceError
from .meetings import MeetingService


class DemoService:
    def __init__(self, session: Session):
        self.session = session

    def start(self) -> tuple[User, str, str]:
        if not settings.visitor_demo_enabled:
            raise ServiceError(status_code=403, error="Public exploration is unavailable", where="client")
        insert = pg_insert if self.session.get_bind().dialect.name == "postgresql" else sqlite_insert
        self.session.execute(insert(DemoAdmission).values(id=1).on_conflict_do_nothing())
        self.session.scalar(select(DemoAdmission).where(DemoAdmission.id == 1).with_for_update())
        retained = (
            self.session.scalar(select(func.count()).select_from(User).where(User.is_visitor.is_(True))) or 0
        )
        active = (
            self.session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.is_visitor.is_(True), User.active.is_(True), User.visitor_expires_at > now())
            )
            or 0
        )
        if retained >= settings.visitor_retained_limit or active >= settings.visitor_active_limit:
            raise ServiceError(
                status_code=429, error="The demo is at capacity; please try again later", where="client"
            )
        expires = now() + timedelta(hours=settings.visitor_hours)
        user = User(
            email="visitor-" + secrets.token_hex(16) + "@demo.invalid",
            name="Demo explorer",
            password_hash=hasher.hash(secrets.token_urlsafe(32)),
            is_visitor=True,
            visitor_expires_at=expires,
        )
        self.session.add(user)
        self.session.flush()
        self.session.add(VisitorUsage(user_id=user.id))
        for department, department_name in DEPARTMENTS.items():
            workspace = Workspace(
                name=department_name + " demo", department=department, is_demo=True, demo_expires_at=expires
            )
            self.session.add(workspace)
            self.session.flush()
            self.session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
            for name, role in (
                ("Alex", "Synthetic coordinator"),
                ("Alex", "Synthetic teammate"),
                ("Morgan", "Synthetic reviewer"),
                ("Taylor", "Synthetic facilitator"),
            ):
                self.session.add(
                    Participant(
                        workspace_id=workspace.id, name=name, role=role, aliases=[], confirmed_by=user.id
                    )
                )
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.session.add(
            AuthSession(token_hash=digest(token), user_id=user.id, csrf_hash=digest(csrf), expires_at=expires)
        )
        self.session.flush()
        return user, token, csrf

    def load(self, principal: Principal, fixture_id: str) -> dict:
        user, workspace, _ = workspace_access(self.session, principal)
        if not user.is_visitor or not workspace.is_demo:
            raise ServiceError(
                status_code=403, error="Use the private transcript editor for this workspace", where="client"
            )
        fixture = FIXTURES.get(fixture_id)
        if not fixture or fixture["department"] not in {None, workspace.department}:
            raise ServiceError(status_code=404, error="Demo example not found", where="client")
        self.session.scalar(select(VisitorUsage).where(VisitorUsage.user_id == user.id).with_for_update())
        self.session.scalar(select(Workspace).where(Workspace.id == workspace.id).with_for_update())
        slug = "demo-" + fixture_id
        meeting = self.session.scalar(
            select(Meeting).where(Meeting.workspace_id == workspace.id, Meeting.slug == slug)
        )
        if meeting:
            if meeting.archived_at:
                raise ServiceError(
                    status_code=409,
                    error="This example was archived; choose another example or start a fresh demo",
                    where="client",
                )
            return {
                "ok": True,
                "meeting_id": slug,
                "version": meeting.version,
                "reindexed": False,
                "job_id": None,
                "synthetic": True,
            }
        consume_visitor_usage(self.session, principal, jobs=True)
        result = MeetingService(self.session, principal).index(
            IndexInput(
                meeting_id=slug,
                title=fixture["title"],
                transcript=fixture["transcript"],
                visibility="restricted",
                occurred_on=now().date(),
                timezone="UTC",
            ),
            trusted_demo_fixture=True,
        )
        return {**result, "synthetic": True}
