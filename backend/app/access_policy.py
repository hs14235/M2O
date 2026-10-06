"""Authority and lifetime rules shared by HTTP, services and background jobs."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Membership, User, VisitorUsage, Workspace, now
from .services.errors import ServiceError
from .settings import settings

if TYPE_CHECKING:
    from .auth import Principal


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def user_is_active(user: User | None) -> bool:
    return bool(
        user
        and user.active
        and (not user.is_visitor or user.visitor_expires_at and aware(user.visitor_expires_at) > now())
    )


def workspace_is_active(workspace: Workspace | None) -> bool:
    return bool(
        workspace
        and workspace.erasure_requested_at is None
        and workspace.erased_at is None
        and (not workspace.is_demo or workspace.demo_expires_at and aware(workspace.demo_expires_at) > now())
    )


def account(session: Session, principal: "Principal") -> User:
    user = session.scalar(
        select(User).where(User.id == principal.user_id).execution_options(populate_existing=True)
    )
    if (
        not user_is_active(user)
        or user is not None
        and principal.auth_version is not None
        and user.auth_version != principal.auth_version
    ):
        raise ServiceError(
            status_code=401, error="Your session ended; sign in or start a fresh demo", where="client"
        )
    assert user is not None
    return user


def workspace_access(session: Session, principal: "Principal") -> tuple[User, Workspace, Membership]:
    user = account(session, principal)
    workspace = session.scalar(
        select(Workspace).where(Workspace.id == principal.scope).execution_options(populate_existing=True)
    )
    member = session.scalar(
        select(Membership)
        .where(Membership.workspace_id == principal.scope, Membership.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    if (
        not workspace_is_active(workspace)
        or not member
        or workspace is None
        or user.is_visitor != workspace.is_demo
        or principal.token_workspace_id
        and principal.token_workspace_id != workspace.id
    ):
        raise ServiceError(status_code=404, error="Workspace not found", where="client")
    if principal.role is not None and member.role != principal.role:
        raise ServiceError(
            status_code=403,
            error="Your workspace permissions changed; reload before continuing",
            where="client",
        )
    return user, workspace, member


def is_private_scope(session: Session, principal: "Principal") -> bool:
    user, workspace, _ = workspace_access(session, principal)
    return not user.is_visitor and not workspace.is_demo


def require_private_account(session: Session, principal: "Principal") -> User:
    user = account(session, principal)
    if user.is_visitor:
        raise ServiceError(
            status_code=403, error="This action requires an invited private account", where="client"
        )
    return user


def require_private_scope(session: Session, principal: "Principal") -> None:
    if not is_private_scope(session, principal):
        raise ServiceError(
            status_code=403,
            error="Live integrations and administration require a private workspace",
            where="client",
        )


def consume_visitor_usage(session: Session, principal: "Principal", *, jobs: bool = False) -> None:
    user = account(session, principal)
    if not user.is_visitor:
        return
    usage = session.scalar(select(VisitorUsage).where(VisitorUsage.user_id == user.id).with_for_update())
    if usage is None:
        raise ServiceError(status_code=403, error="Demo authority is unavailable", where="client")
    field, maximum = (
        ("jobs", settings.visitor_job_limit) if jobs else ("mutations", settings.visitor_mutation_limit)
    )
    if getattr(usage, field) >= maximum:
        raise ServiceError(
            status_code=429, error="This demo reached its limit; start a fresh demo later", where="client"
        )
    setattr(usage, field, getattr(usage, field) + 1)
