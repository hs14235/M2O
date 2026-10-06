import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .access_policy import aware, consume_visitor_usage, user_is_active, workspace_access
from .database import get_session
from .models import ApiToken, AuthSession, Membership, User, now
from .schemas import RecordId
from .services.errors import ServiceError
from .settings import settings

hasher = PasswordHasher()
_dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str | None = None
    role: str | None = None
    session_hash: str | None = None
    token_workspace_id: str | None = None
    auth_version: int | None = None

    @property
    def scope(self) -> str:
        if self.workspace_id is None:
            raise ServiceError(status_code=403, error="A workspace scope is required", where="client")
        return self.workspace_id


def authenticate(request: Request, session: Session = Depends(get_session, scope="function")) -> Principal:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = session.get(ApiToken, digest(authorization[7:]))
        if token and aware(token.expires_at) > now():
            user = session.get(User, token.user_id)
            if (
                user_is_active(user)
                and user is not None
                and not user.is_visitor
                and token.auth_version == user.auth_version
            ):
                assert user is not None
                return Principal(
                    user.id, token_workspace_id=token.workspace_id, auth_version=user.auth_version
                )
    else:
        token = request.cookies.get("mtt_session", "")
        auth_session = session.get(AuthSession, digest(token)) if token else None
        if auth_session and aware(auth_session.expires_at) > now():
            user = session.get(User, auth_session.user_id)
            if user_is_active(user) and user is not None and auth_session.auth_version == user.auth_version:
                assert user is not None
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    csrf = request.headers.get("X-CSRF-Token", "")
                    if not csrf or not secrets.compare_digest(digest(csrf), auth_session.csrf_hash):
                        raise ServiceError(status_code=403, error="CSRF verification failed", where="client")
                    if request.headers.get("Origin") != settings.app_origin:
                        raise ServiceError(
                            status_code=403, error="Request origin is not allowed", where="client"
                        )
                    if request.url.path != "/api/auth/logout":
                        consume_visitor_usage(session, Principal(user.id))
                return Principal(
                    user.id, session_hash=auth_session.token_hash, auth_version=user.auth_version
                )
    raise ServiceError(status_code=401, error="Sign in to continue", where="client")


def workspace_principal(
    workspace_id: RecordId,
    principal: Principal = Depends(authenticate),
    session: Session = Depends(get_session, scope="function"),
) -> Principal:
    if principal.token_workspace_id and principal.token_workspace_id != workspace_id:
        raise ServiceError(status_code=404, error="Workspace not found", where="client")
    _, _, member = workspace_access(
        session,
        Principal(
            principal.user_id,
            workspace_id,
            token_workspace_id=principal.token_workspace_id,
            auth_version=principal.auth_version,
        ),
    )
    return Principal(
        principal.user_id,
        workspace_id,
        member.role,
        principal.session_hash,
        principal.token_workspace_id,
        principal.auth_version,
    )


def require_role(principal: Principal, roles: set[str]) -> None:
    if principal.role not in roles:
        raise ServiceError(
            status_code=403, error="Your workspace role does not allow this operation", where="client"
        )


def create_session(session: Session, email: str, password: str):
    user = session.scalar(
        select(User)
        .where(User.email == email.casefold().strip())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    try:
        valid = hasher.verify(user.password_hash if user else _dummy_hash, password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not user_is_active(user) or user is None or user.is_visitor or not valid:
        raise ServiceError(status_code=401, error="Email or password is incorrect", where="client")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=digest(token),
            user_id=user.id,
            csrf_hash=digest(csrf),
            expires_at=now() + timedelta(hours=settings.session_hours),
        )
    )
    session.flush()
    return user, token, csrf


def mcp_principal(session: Session) -> Principal:
    value = settings.mcp_api_token.get_secret_value()
    token = session.get(ApiToken, digest(value)) if value else None
    if token is None or aware(token.expires_at) <= now():
        raise ServiceError(
            status_code=401, error="Configure a valid workspace-scoped MCP_API_TOKEN", where="client"
        )
    user = session.get(User, token.user_id)
    member = session.get(Membership, (token.workspace_id, token.user_id))
    if (
        not user_is_active(user)
        or user is None
        or user.is_visitor
        or not member
        or token.auth_version != user.auth_version
    ):
        raise ServiceError(status_code=401, error="MCP access is no longer authorized", where="client")
    assert user is not None
    principal = Principal(
        user.id,
        token.workspace_id,
        member.role,
        token_workspace_id=token.workspace_id,
        auth_version=user.auth_version,
    )
    workspace_access(session, principal)
    return principal
