"""Email-bound invitations and operator-issued recovery without implicit messaging."""

import secrets
from datetime import timedelta

from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..access_policy import require_private_account, user_is_active, workspace_is_active
from ..auth import Principal, aware, digest, hasher
from ..models import (
    ApiToken,
    AuthSession,
    IntegrationOAuthState,
    Invitation,
    Job,
    Membership,
    OAuthState,
    PasswordRecovery,
    User,
    Workspace,
    now,
)
from ..schemas import InvitationAcceptInput, InvitationInput, RecoveryInput
from ..settings import settings
from .common import audit
from .errors import ServiceError


def owner_lock(session: Session, principal: Principal, *, allow_erasing: bool = False) -> Workspace:
    if principal.token_workspace_id and principal.token_workspace_id != principal.scope:
        raise ServiceError(status_code=404, error="Workspace not found", where="client")
    user = session.scalar(
        select(User)
        .where(User.id == principal.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    member = session.scalar(
        select(Membership)
        .where(Membership.workspace_id == principal.scope, Membership.user_id == principal.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    workspace = session.scalar(
        select(Workspace)
        .where(Workspace.id == principal.scope)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        not user_is_active(user)
        or not member
        or member.role != "owner"
        or not workspace
        or user is not None
        and principal.auth_version is not None
        and user.auth_version != principal.auth_version
    ):
        raise ServiceError(
            status_code=403, error="Current workspace owner access is required", where="client"
        )
    if (
        user is None
        or user.is_visitor
        or workspace.is_demo
        or workspace.erased_at
        or principal.token_workspace_id
        and principal.token_workspace_id != workspace.id
        or not allow_erasing
        and not workspace_is_active(workspace)
    ):
        raise ServiceError(
            status_code=403, error="Private workspace administration is unavailable", where="client"
        )
    return workspace


def reauthenticate(session: Session, principal: Principal, password: str) -> User:
    user = require_private_account(session, principal)
    try:
        valid = hasher.verify(user.password_hash, password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid:
        raise ServiceError(status_code=403, error="Password confirmation failed", where="client")
    return user


class InvitationService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def summary(row: Invitation) -> dict:
        return {
            "id": row.id,
            "email": row.email,
            "role": row.role,
            "expires_at": aware(row.expires_at).isoformat(),
            "state": "revoked"
            if row.revoked_at
            else "accepted"
            if row.consumed_at
            else "expired"
            if aware(row.expires_at) <= now()
            else "pending",
        }

    def issue(self, principal: Principal, payload: InvitationInput) -> dict:
        workspace = owner_lock(self.session, principal)
        email = payload.email.casefold()
        existing = self.session.scalar(select(User).where(User.email == email))
        if existing and (
            existing.is_visitor
            or not existing.active
            or self.session.get(Membership, (workspace.id, existing.id))
        ):
            raise ServiceError(
                status_code=409,
                error="This address cannot receive a new membership invitation",
                where="client",
            )
        pending = self.session.scalars(
            select(Invitation).where(
                Invitation.workspace_id == workspace.id,
                Invitation.revoked_at.is_(None),
                Invitation.consumed_at.is_(None),
                Invitation.expires_at > now(),
            )
        ).all()
        if len(pending) >= 30:
            raise ServiceError(
                status_code=429, error="Revoke an unused invitation before creating another", where="client"
            )
        for row in pending:
            if row.email == email:
                row.revoked_at = now()
        token = secrets.token_urlsafe(32)
        issuer = self.session.get(User, principal.user_id)
        assert issuer is not None
        row = Invitation(
            workspace_id=workspace.id,
            issued_by=principal.user_id,
            issuer_auth_version=issuer.auth_version,
            email=email,
            role=payload.role,
            token_hash=digest(token),
            expires_at=now() + timedelta(hours=settings.invite_hours),
        )
        self.session.add(row)
        self.session.flush()
        audit(self.session, principal, "invitation.issued", row.id, {"role": row.role})
        return {
            **self.summary(row),
            "accept_url": settings.app_origin + "/invite#token=" + token,
            "delivery": "manual",
            "workspace_name": workspace.name,
        }

    def list(self, principal: Principal) -> dict:
        owner_lock(self.session, principal)
        rows = self.session.scalars(
            select(Invitation)
            .where(Invitation.workspace_id == principal.scope)
            .order_by(Invitation.created_at.desc(), Invitation.id)
            .limit(50)
        ).all()
        return {"invitations": [self.summary(row) for row in rows]}

    def revoke(self, principal: Principal, invitation_id: str) -> dict:
        owner_lock(self.session, principal)
        row = self.session.scalar(
            select(Invitation)
            .where(Invitation.id == invitation_id, Invitation.workspace_id == principal.scope)
            .with_for_update()
        )
        if not row:
            raise ServiceError(status_code=404, error="Invitation not found", where="client")
        if row.consumed_at:
            raise ServiceError(
                status_code=409, error="Accepted membership must be managed separately", where="client"
            )
        row.revoked_at = now()
        audit(self.session, principal, "invitation.revoked", row.id)
        return self.summary(row)

    def valid(self, token: str) -> tuple[Invitation, Workspace]:
        row = self.session.scalar(select(Invitation).where(Invitation.token_hash == digest(token)))
        if not row:
            raise ServiceError(
                status_code=400, error="This invitation is unavailable; request a new link", where="client"
            )
        try:
            workspace = owner_lock(
                self.session,
                Principal(row.issued_by, row.workspace_id, "owner", auth_version=row.issuer_auth_version),
            )
        except ServiceError as exc:
            raise ServiceError(
                status_code=400, error="This invitation is unavailable; request a new link", where="client"
            ) from exc
        row = self.session.scalar(
            select(Invitation)
            .where(Invitation.id == row.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not row or row.revoked_at or row.consumed_at or aware(row.expires_at) <= now():
            raise ServiceError(
                status_code=400, error="This invitation is unavailable; request a new link", where="client"
            )
        return row, workspace

    def inspect(self, token: str) -> dict:
        row, workspace = self.valid(token)
        user = self.session.scalar(select(User).where(User.email == row.email))
        return {
            "workspace_name": workspace.name,
            "email": row.email,
            "role": row.role,
            "expires_at": aware(row.expires_at).isoformat(),
            "requires_sign_in": bool(user),
        }

    def accept(self, payload: InvitationAcceptInput, principal: Principal | None) -> dict:
        initial = self.session.scalar(
            select(Invitation).where(Invitation.token_hash == digest(payload.token))
        )
        target = self.session.scalar(select(User).where(User.email == payload.email.casefold()))
        if initial:
            ids = {initial.issued_by, *([target.id] if target else [])}
            self.session.scalars(
                select(User)
                .where(User.id.in_(ids))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).all()
        row, workspace = self.valid(payload.token)
        if payload.email.casefold() != row.email:
            raise ServiceError(
                status_code=403, error="Use the email address on your invitation", where="client"
            )
        user = self.session.scalar(select(User).where(User.email == row.email))
        created = user is None
        if user:
            if (
                not user_is_active(user)
                or user.is_visitor
                or not principal
                or principal.user_id != user.id
                or not principal.session_hash
            ):
                raise ServiceError(
                    status_code=403, error="Sign in to the account named on this invitation", where="client"
                )
            if payload.password is not None:
                raise ServiceError(
                    status_code=400,
                    error="An invitation cannot change an existing account password",
                    where="client",
                )
            browser = self.session.scalar(
                select(AuthSession)
                .where(AuthSession.token_hash == principal.session_hash)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                not browser
                or browser.user_id != user.id
                or browser.auth_version != user.auth_version
                or aware(browser.expires_at) <= now()
            ):
                raise ServiceError(
                    status_code=403, error="Sign in again before accepting this invitation", where="client"
                )
        else:
            if principal or not payload.name or not payload.password:
                raise ServiceError(
                    status_code=400,
                    error="Sign out and choose your name and password to accept this invitation",
                    where="client",
                )
            user = User(email=row.email, name=payload.name, password_hash=hasher.hash(payload.password))
            self.session.add(user)
            self.session.flush()
        if self.session.get(Membership, (workspace.id, user.id)):
            raise ServiceError(
                status_code=409,
                error="You are already a member; existing permissions were preserved",
                where="client",
            )
        self.session.add(Membership(workspace_id=workspace.id, user_id=user.id, role=row.role))
        row.consumed_at, row.consumed_by = now(), user.id
        audit(
            self.session,
            Principal(user.id, workspace.id, row.role),
            "invitation.accepted",
            row.id,
            {"role": row.role},
        )
        return {
            "ok": True,
            "workspace_id": workspace.id,
            "role": row.role,
            "account_created": created,
            "sign_in_required": created,
        }


class RecoveryService:
    def __init__(self, session: Session):
        self.session = session

    def issue_for_operator(self, email: str) -> str:
        user = self.session.scalar(
            select(User).where(User.email == email.casefold().strip()).with_for_update()
        )
        if not user_is_active(user) or user is None or user.is_visitor:
            raise ServiceError(status_code=400, error="A private active account is required", where="client")
        self.session.execute(delete(PasswordRecovery).where(PasswordRecovery.user_id == user.id))
        token = secrets.token_urlsafe(32)
        self.session.add(
            PasswordRecovery(
                token_hash=digest(token),
                user_id=user.id,
                auth_version=user.auth_version,
                expires_at=now() + timedelta(minutes=settings.recovery_minutes),
            )
        )
        self.session.flush()
        return settings.app_origin + "/recover#token=" + token

    def reset(self, payload: RecoveryInput) -> dict:
        row = self.session.get(PasswordRecovery, digest(payload.token))
        if not row:
            raise ServiceError(status_code=400, error="Recovery link is invalid or expired", where="client")
        user = self.session.scalar(
            select(User)
            .where(User.id == row.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self.session.scalar(
            select(PasswordRecovery)
            .where(PasswordRecovery.token_hash == digest(payload.token))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not row
            or not user_is_active(user)
            or user is None
            or user.is_visitor
            or user.email != payload.email.casefold()
            or row.consumed_at
            or aware(row.expires_at) <= now()
            or row.auth_version != user.auth_version
        ):
            raise ServiceError(status_code=400, error="Recovery link is invalid or expired", where="client")
        user.password_hash, user.auth_version = hasher.hash(payload.password), user.auth_version + 1
        row.consumed_at = now()
        user_id, authority_version = user.id, user.auth_version
        self.session.commit()
        # Authority is durably revoked before cleanup can wait for child/job locks.
        self.session.execute(
            delete(PasswordRecovery).where(
                PasswordRecovery.user_id == user_id,
                PasswordRecovery.auth_version < authority_version,
                PasswordRecovery.consumed_at.is_(None),
            )
        )
        old_sessions = select(AuthSession.token_hash).where(
            AuthSession.user_id == user_id, AuthSession.auth_version < authority_version
        )
        for model in (OAuthState, IntegrationOAuthState):
            self.session.execute(
                delete(model).where(model.user_id == user_id, model.session_hash.in_(old_sessions))
            )
        for model in (ApiToken, AuthSession):
            self.session.execute(
                delete(model).where(model.user_id == user_id, model.auth_version < authority_version)
            )
        cancel_actor_jobs(self.session, user_id, "account_recovery", before_version=authority_version)
        return {"ok": True, "sign_in_required": True, "sessions_revoked": True}


def cancel_actor_jobs(
    session: Session, user_id: str, reason: str, *, before_version: int | None = None
) -> None:
    from ..worker import settle_exhausted_delivery

    query = select(Job).where(Job.actor_id == user_id, Job.state == "queued")
    if before_version is not None:
        query = query.where(Job.actor_auth_version < before_version)
    jobs = session.scalars(query.order_by(Job.id).with_for_update()).all()
    for job in jobs:
        job.state, job.error_code, job.lease_until = "cancelled", reason, None
        settle_exhausted_delivery(session, job, reason="Account authority was revoked before delivery")
