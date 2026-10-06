"""Personal Atlassian grants with explicit, authorized workspace destinations."""

import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .access_policy import is_private_scope, require_private_scope
from .auth import Principal, aware, digest, require_role
from .models import (
    AuthSession,
    IntegrationOAuthState,
    Membership,
    ProviderConnection,
    ProviderDestination,
    User,
    now,
    uid,
)
from .provider_credentials import seal, unseal
from .schemas import JiraDestinationInput
from .services.common import audit
from .services.errors import ServiceError
from .settings import settings

TOKEN_URL = "https://auth.atlassian.com/oauth/token"
RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
SCOPES = {"read:jira-work", "write:jira-work"}


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str = Field(min_length=1, max_length=16000)
    refresh_token: str = Field(min_length=1, max_length=16000)
    expires_in: int = Field(strict=True, ge=1, le=86400)
    scope: str = Field(default="", max_length=2000)


class ResourceResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=250)
    scopes: list[str] = Field(max_length=100)


def connection_query(principal: Principal):
    return select(ProviderConnection).where(
        ProviderConnection.user_id == principal.user_id, ProviderConnection.provider == "jira"
    )


def binding_query(principal: Principal):
    return (
        select(ProviderDestination)
        .join(ProviderConnection, ProviderConnection.id == ProviderDestination.connection_id)
        .where(
            ProviderDestination.workspace_id == principal.scope,
            ProviderDestination.user_id == principal.user_id,
            ProviderConnection.provider == "jira",
        )
    )


def connection_status(session: Session, principal: Principal) -> dict:
    private = is_private_scope(session, principal)
    binding = session.scalar(binding_query(principal))
    row = session.scalar(connection_query(principal)) if binding else None
    return {
        "configured": settings.jira_configured and private,
        "can_manage": principal.role == "owner" and not settings.public_demo_mode and private,
        "state": row.state if row else "disconnected",
        "version": binding.version if binding else None,
        "destination": {
            "resource_id": binding.resource_id,
            "name": binding.resource_name,
            "url": binding.resource_url,
            "project_key": binding.project_key,
            "project_name": binding.project_name,
        }
        if binding and binding.resource_id
        else None,
    }


class JiraAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    def owner_authority(self, session: Session, principal: Principal) -> None:
        require_private_scope(session, principal)
        require_role(principal, {"owner"})
        user = session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
        member = session.scalar(
            select(Membership)
            .where(Membership.user_id == principal.user_id, Membership.workspace_id == principal.scope)
            .with_for_update()
        )
        if not user or not user.active or not member or member.role != "owner":
            raise ServiceError(status_code=403, error="Workspace owner access is required", where="client")

    def authority(self, session: Session, principal: Principal) -> None:
        self.owner_authority(session, principal)
        if settings.public_demo_mode:
            raise ServiceError(
                status_code=403, error="Provider connections are disabled in demo mode", where="client"
            )
        if not settings.jira_configured:
            raise ServiceError(
                status_code=503, error="The operator must configure the Jira application first", where="jira"
            )

    def begin(self, session: Session, principal: Principal) -> dict:
        self.authority(session, principal)
        browser = session.get(AuthSession, principal.session_hash) if principal.session_hash else None
        if not browser or browser.user_id != principal.user_id or aware(browser.expires_at) <= now():
            raise ServiceError(status_code=403, error="Connect Jira from a signed-in browser", where="client")
        session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == principal.user_id, IntegrationOAuthState.provider == "jira"
            )
        )
        state = secrets.token_urlsafe(32)
        session.add(
            IntegrationOAuthState(
                state_hash=digest(state),
                user_id=principal.user_id,
                workspace_id=principal.scope,
                provider="jira",
                session_hash=principal.session_hash,
                expires_at=now() + timedelta(minutes=10),
            )
        )
        return {
            "url": "https://auth.atlassian.com/authorize?"
            + urlencode(
                {
                    "audience": "api.atlassian.com",
                    "client_id": settings.jira_client_id,
                    "scope": "offline_access read:jira-work write:jira-work",
                    "redirect_uri": settings.jira_redirect_uri,
                    "state": state,
                    "response_type": "code",
                    "prompt": "consent",
                }
            )
        }

    async def request(self, method: str, url: str, *, token: str | None = None, payload: dict | None = None):
        try:
            async with httpx.AsyncClient(
                timeout=15, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                response = await client.request(
                    method, url, json=payload, headers={"Authorization": "Bearer " + token} if token else {}
                )
            if response.status_code == 429:
                raise ServiceError(
                    status_code=429, error="Jira is rate limiting requests; try again later", where="jira"
                )
            if response.status_code in {401, 403}:
                raise ServiceError(
                    status_code=403,
                    error="Jira access was denied; reconnect or check permissions",
                    where="jira",
                )
            if response.status_code in {400, 404}:
                raise ServiceError(
                    status_code=422,
                    error="Jira could not accept the request or locate the resource",
                    where="jira",
                )
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Response too large")
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError(
                status_code=502, error="Jira did not return a valid response; try again", where="jira"
            ) from exc

    async def exchange(self, grant: dict) -> TokenResponse:
        payload = await self.request(
            "POST",
            TOKEN_URL,
            payload={
                **grant,
                "client_id": settings.jira_client_id,
                "client_secret": settings.jira_client_secret.get_secret_value(),
            },
        )
        try:
            return TokenResponse.model_validate(payload)
        except ValidationError as exc:
            raise ServiceError(
                status_code=502, error="Jira did not return a renewable credential", where="jira"
            ) from exc

    async def complete(
        self, session: Session, principal: Principal, state: str, code: str | None, denied: bool = False
    ) -> str:
        # Lock account before state to serialize connect/disconnect across workspaces.
        session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
        stored = session.scalar(
            select(IntegrationOAuthState)
            .where(IntegrationOAuthState.state_hash == digest(state))
            .with_for_update()
        )
        if (
            not stored
            or stored.provider != "jira"
            or stored.user_id != principal.user_id
            or stored.session_hash != principal.session_hash
            or aware(stored.expires_at) <= now()
        ):
            raise ServiceError(
                status_code=400, error="Jira connection request is invalid or expired", where="jira"
            )
        workspace = stored.workspace_id
        member = session.get(Membership, (workspace, principal.user_id))
        scoped = Principal(
            principal.user_id, workspace, member.role if member else None, principal.session_hash
        )
        session.delete(stored)
        try:
            self.authority(session, scoped)
            if denied or not code:
                session.commit()
                return workspace
            token = await self.exchange(
                {"grant_type": "authorization_code", "code": code, "redirect_uri": settings.jira_redirect_uri}
            )
            if not SCOPES.issubset(set(token.scope.split())):
                raise ServiceError(
                    status_code=403,
                    error="Jira did not grant the required read and write permissions",
                    where="jira",
                )
        except ServiceError:
            # A validated callback is consumed even if its exchange is rejected.
            session.commit()
            raise
        try:
            row = session.scalar(connection_query(scoped).with_for_update())
            if not row:
                row = ProviderConnection(id=uid(), user_id=principal.user_id, provider="jira")
                session.add(row)
            row.state, row.scopes, row.expires_at, row.updated_at = (
                "connected",
                token.scope.split(),
                now() + timedelta(seconds=token.expires_in),
                now(),
            )
            row.encrypted_credentials = seal(
                row, {"access_token": token.access_token, "refresh_token": token.refresh_token}
            )
            session.flush()
            for existing in session.scalars(
                select(ProviderDestination).where(ProviderDestination.connection_id == row.id)
            ):
                existing.resource_id = existing.resource_name = existing.resource_url = None
                existing.project_key = existing.project_name = None
                existing.version += 1
            binding = session.scalar(binding_query(scoped))
            if not binding:
                session.add(
                    ProviderDestination(
                        connection_id=row.id, user_id=principal.user_id, workspace_id=workspace
                    )
                )
            audit(session, scoped, "jira.connected", row.id)
            session.commit()
            return workspace
        except ServiceError:
            session.rollback()
            session.execute(
                delete(IntegrationOAuthState).where(IntegrationOAuthState.state_hash == digest(state))
            )
            session.commit()
            raise

    async def access(
        self, session: Session, principal: Principal
    ) -> tuple[ProviderConnection, ProviderDestination, str]:
        self.authority(session, principal)
        row = session.scalar(connection_query(principal).with_for_update())
        binding = session.scalar(binding_query(principal).with_for_update(of=ProviderDestination))
        if not row or not binding or row.state != "connected":
            raise ServiceError(
                status_code=409, error="Connect Jira before choosing a destination", where="jira"
            )
        credentials = unseal(row)
        if row.expires_at is None:
            raise ServiceError(
                status_code=409, error="Jira credential expiry is unavailable; reconnect", where="jira"
            )
        if aware(row.expires_at) <= now() + timedelta(seconds=60):
            try:
                token = await self.exchange(
                    {"grant_type": "refresh_token", "refresh_token": credentials["refresh_token"]}
                )
            except ServiceError as exc:
                if exc.status_code in {403, 422}:
                    row.state = "reauthorization_required"
                    row.encrypted_credentials = ""
                    audit(session, principal, "jira.authorization_lost", row.id)
                    session.commit()
                raise
            if token.scope and not SCOPES.issubset(set(token.scope.split())):
                row.state, row.encrypted_credentials = "reauthorization_required", ""
                session.commit()
                raise ServiceError(status_code=403, error="Jira permissions changed; reconnect", where="jira")
            credentials = {"access_token": token.access_token, "refresh_token": token.refresh_token}
            row.encrypted_credentials, row.expires_at, row.updated_at = (
                seal(row, credentials),
                now() + timedelta(seconds=token.expires_in),
                now(),
            )
            # Persist rotating credentials before subsequent calls can fail.
            session.commit()
            self.authority(session, principal)
            row = session.scalar(connection_query(principal).with_for_update())
            binding = session.scalar(binding_query(principal).with_for_update(of=ProviderDestination))
            if not row or not binding or row.state != "connected":
                raise ServiceError(status_code=409, error="Jira was disconnected; reconnect", where="jira")
            credentials = unseal(row)
        return row, binding, credentials["access_token"]

    async def resources(self, token: str) -> list[dict]:
        payload = await self.request("GET", RESOURCES_URL, token=token)
        try:
            if not isinstance(payload, list) or len(payload) > 100:
                raise ValueError("Invalid site list")
            result = []
            for item in payload:
                resource = ResourceResponse.model_validate(item)
                parsed = urlsplit(resource.url)
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or not parsed.hostname.endswith(".atlassian.net")
                    or parsed.username
                    or parsed.password
                    or parsed.port
                    or parsed.query
                    or parsed.fragment
                    or parsed.path not in {"", "/"}
                ):
                    raise ValueError("Unexpected site origin")
                if SCOPES.issubset(resource.scopes):
                    result.append(
                        {"id": str(resource.id), "name": resource.name, "url": resource.url.rstrip("/")}
                    )
            return result
        except (ValidationError, ValueError, TypeError) as exc:
            raise ServiceError(
                status_code=502, error="Jira returned an invalid site list", where="jira"
            ) from exc

    async def sites(self, session: Session, principal: Principal) -> list[dict]:
        _, _, token = await self.access(session, principal)
        return await self.resources(token)

    async def choose(self, session: Session, principal: Principal, payload: JiraDestinationInput) -> dict:
        _, binding, token = await self.access(session, principal)
        if binding.version != payload.expected_version:
            raise ServiceError(
                status_code=409, error="Jira destination changed; reload before saving", where="client"
            )
        resource = next((r for r in await self.resources(token) if r["id"] == payload.resource_id), None)
        if not resource:
            raise ServiceError(
                status_code=403, error="The selected Jira site is not authorized", where="jira"
            )
        project = await self.request(
            "GET",
            f"https://api.atlassian.com/ex/jira/{payload.resource_id}/rest/api/3/project/{payload.project_key}",
            token=token,
        )
        if (
            not isinstance(project, dict)
            or project.get("key") != payload.project_key
            or not isinstance(project.get("name"), str)
            or not 1 <= len(project["name"]) <= 200
        ):
            raise ServiceError(
                status_code=502, error="Jira project details could not be verified", where="jira"
            )
        binding.resource_id, binding.resource_name, binding.resource_url = (
            resource["id"],
            resource["name"],
            resource["url"],
        )
        binding.project_key, binding.project_name, binding.version = (
            payload.project_key,
            project["name"],
            binding.version + 1,
        )
        audit(
            session, principal, "jira.destination_selected", binding.id, {"project_key": binding.project_key}
        )
        session.flush()
        return connection_status(session, principal)

    def disconnect(self, session: Session, principal: Principal) -> dict:
        # Disconnect remains available when configuration is missing or demo mode changed.
        self.owner_authority(session, principal)
        row = session.scalar(connection_query(principal).with_for_update())
        binding = session.scalar(binding_query(principal))
        session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == principal.user_id,
                IntegrationOAuthState.workspace_id == principal.scope,
                IntegrationOAuthState.provider == "jira",
            )
        )
        if binding and row:
            session.delete(binding)
            session.flush()
            if not session.scalar(
                select(ProviderDestination.id).where(ProviderDestination.connection_id == row.id)
            ):
                session.delete(row)
            audit(session, principal, "jira.disconnected", binding.id)
        return {"ok": True}
