"""Owner-bound Slack installation and verified public-channel destinations."""

import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

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
    SlackAccount,
    SlackDestination,
    User,
    now,
    uid,
)
from .provider_credentials import seal, unseal
from .schemas import SlackDestinationInput
from .services.common import audit
from .services.errors import ServiceError
from .settings import settings

SCOPES = {"chat:write", "channels:read", "channels:history", "commands"}
BASE = "https://slack.com/api/"
ID_PATTERN = r"^[A-Z][A-Z0-9]{7,63}$"


def provider_id(value, prefixes) -> str:
    if not isinstance(value, str) or not re.fullmatch("[" + prefixes + r"][A-Z0-9]{7,63}", value):
        raise ValueError("Invalid Slack identity")
    return value


class SlackToken(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    access_token: str = Field(min_length=1, max_length=16000)
    token_type: str
    scope: str = Field(max_length=2000)
    bot_user_id: str = Field(pattern=ID_PATTERN)
    app_id: str = Field(pattern=ID_PATTERN)
    team: dict
    authed_user: dict
    refresh_token: str | None = Field(default=None, min_length=1, max_length=16000)
    expires_in: int | None = Field(default=None, ge=1, le=86400)


def connection_query(principal):
    return select(ProviderConnection).where(
        ProviderConnection.user_id == principal.user_id, ProviderConnection.provider == "slack"
    )


def binding_query(principal):
    return (
        select(ProviderDestination)
        .join(ProviderConnection)
        .where(
            ProviderDestination.user_id == principal.user_id,
            ProviderDestination.workspace_id == principal.scope,
            ProviderConnection.provider == "slack",
        )
    )


def connection_status(session: Session, principal: Principal) -> dict:
    private = is_private_scope(session, principal)
    binding = session.scalar(binding_query(principal))
    row = session.scalar(connection_query(principal)) if binding else None
    account = session.get(SlackAccount, row.id) if row else None
    channel = session.get(SlackDestination, binding.id) if binding else None
    reasons = []
    if not settings.slack_configured:
        reasons.append("needs_configuration")
    if settings.public_demo_mode or not private:
        reasons.append("demo_mode")
    if principal.role != "owner":
        reasons.append("owner_required")
    if not row or not account:
        reasons.append("not_connected")
    elif row.state != "connected":
        reasons.append("reauthorization_required")
    elif not SCOPES.issubset(set(row.scopes)):
        reasons.append("missing_scopes")
    if not channel:
        reasons.append("unverified_destination")
    ready = not reasons
    from .slack_actions import ROLES, SlackActions, enabled

    actions = SlackActions(session).link_status(principal)
    linked = any(installation["linked"] for installation in actions["installations"])
    action_reasons = []
    if not enabled():
        action_reasons.append("interactions_disabled")
    if principal.role not in ROLES:
        action_reasons.append("member_role_required")
    if not actions["installations"]:
        action_reasons.append("not_connected")
    if not linked:
        action_reasons.append("identity_unconfirmed")
    action_ready = not action_reasons
    return {
        "configured": settings.slack_configured and private,
        "can_manage": principal.role == "owner" and not settings.public_demo_mode and private,
        "state": row.state if row else "disconnected",
        "version": binding.version if binding else None,
        "account": {"team_id": account.team_id, "team_name": account.team_name} if account else None,
        "destination": {"channel_id": channel.channel_id, "channel_name": channel.channel_name}
        if channel
        else None,
        "can_create": ready,
        "can_update": ready,
        "can_reconcile": ready,
        "can_link": actions["can_link"],
        "can_capture_meeting": action_ready,
        "can_change_my_plan": action_ready,
        "delivery_reasons": reasons,
        "interaction_reasons": action_reasons,
    }


class SlackAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    @staticmethod
    def owner_authority(session, principal):
        require_private_scope(session, principal)
        user = session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
        member = session.scalar(
            select(Membership)
            .where(Membership.user_id == principal.user_id, Membership.workspace_id == principal.scope)
            .with_for_update()
        )
        if not user or not user.active or not member:
            raise ServiceError(status_code=403, error="Slack account authority is unavailable", where="slack")
        require_role(Principal(principal.user_id, principal.scope, member.role), {"owner"})

    def authority(self, session, principal):
        self.owner_authority(session, principal)
        if settings.public_demo_mode:
            raise ServiceError(
                status_code=403, error="Slack delivery is disabled in demo mode", where="slack"
            )
        if not settings.slack_configured:
            raise ServiceError(
                status_code=503, error="Slack requires private application configuration", where="slack"
            )

    def begin(self, session, principal):
        self.authority(session, principal)
        browser = session.get(AuthSession, principal.session_hash) if principal.session_hash else None
        if not browser or browser.user_id != principal.user_id or aware(browser.expires_at) <= now():
            raise ServiceError(
                status_code=403, error="Connect Slack from a signed-in browser", where="client"
            )
        session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == principal.user_id, IntegrationOAuthState.provider == "slack"
            )
        )
        state = secrets.token_urlsafe(32)
        session.add(
            IntegrationOAuthState(
                state_hash=digest(state),
                user_id=principal.user_id,
                workspace_id=principal.scope,
                provider="slack",
                session_hash=principal.session_hash,
                expires_at=now() + timedelta(minutes=10),
            )
        )
        return {
            "url": "https://slack.com/oauth/v2/authorize?"
            + urlencode(
                {
                    "client_id": settings.slack_client_id,
                    "scope": ",".join(sorted(SCOPES)),
                    "state": state,
                    "redirect_uri": settings.slack_redirect_uri,
                }
            )
        }

    async def request(self, method, endpoint, *, token=None, form=None, params=None):
        try:
            async with httpx.AsyncClient(
                timeout=10, transport=self.transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.request(
                    method,
                    BASE + endpoint,
                    headers={"Authorization": "Bearer " + token} if token else {},
                    data=form,
                    params=params,
                )
            if response.status_code == 429:
                raise ServiceError(
                    status_code=429,
                    error="Slack request limit reached; wait before trying again",
                    where="slack",
                )
            if response.status_code != 200 or len(response.content) > 1_000_000:
                raise ValueError("Invalid response")
            body = response.json()
            if not isinstance(body, dict) or body.get("ok") is not True:
                code = body.get("error") if isinstance(body, dict) else None
                if code in {
                    "invalid_auth",
                    "token_revoked",
                    "account_inactive",
                    "not_authed",
                    "invalid_code",
                    "bad_client_secret",
                }:
                    raise ServiceError(
                        status_code=403, error="Slack authorization is unavailable; reconnect", where="slack"
                    )
                if code in {
                    "missing_scope",
                    "not_in_channel",
                    "channel_not_found",
                    "is_archived",
                    "no_permission",
                }:
                    raise ServiceError(
                        status_code=422, error="Slack scope or channel access is unavailable", where="slack"
                    )
                raise ValueError("Unknown response")
            return body
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError(
                status_code=502, error="Slack did not return a valid response", where="slack"
            ) from exc

    async def complete(self, session, principal, state, code, denied=False):
        session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
        stored = session.scalar(
            select(IntegrationOAuthState)
            .where(IntegrationOAuthState.state_hash == digest(state))
            .with_for_update()
        )
        if (
            not stored
            or stored.provider != "slack"
            or stored.user_id != principal.user_id
            or stored.session_hash != principal.session_hash
            or aware(stored.expires_at) <= now()
        ):
            raise ServiceError(
                status_code=400, error="Slack connection request is invalid or expired", where="slack"
            )
        member = session.get(Membership, (stored.workspace_id, principal.user_id))
        scoped = Principal(
            principal.user_id, stored.workspace_id, member.role if member else None, principal.session_hash
        )
        session.delete(stored)
        try:
            self.authority(session, scoped)
            if denied or not code:
                session.commit()
                return scoped.scope
            raw = await self.request(
                "POST",
                "oauth.v2.access",
                form={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret.get_secret_value(),
                    "code": code,
                    "redirect_uri": settings.slack_redirect_uri,
                },
            )
            token = SlackToken.model_validate(raw)
            team_id = provider_id(token.team.get("id"), "T")
            user_id = provider_id(token.authed_user.get("id"), "UW")
            team_name = token.team.get("name")

            if (
                token.token_type != "bot"
                or not SCOPES.issubset(set(token.scope.split(",")))
                or any(not isinstance(v, str) or not re.fullmatch(ID_PATTERN, v) for v in (team_id, user_id))
                or not isinstance(team_name, str)
                or not 1 <= len(team_name) <= 200
            ):
                raise ValueError("Invalid installation")
            if bool(token.refresh_token) != bool(token.expires_in):
                raise ValueError("Invalid token lifetime")
            verified = await self.request("POST", "auth.test", token=token.access_token)
            bot_id = verified.get("bot_id")
            if (
                verified.get("team_id") != team_id
                or verified.get("user_id") != token.bot_user_id
                or not isinstance(bot_id, str)
                or not re.fullmatch(ID_PATTERN, bot_id)
            ):
                raise ValueError("Invalid bot identity")
            row = session.scalar(connection_query(scoped).with_for_update())
            collision = session.scalar(
                select(SlackAccount).where(
                    SlackAccount.app_id == token.app_id, SlackAccount.team_id == team_id
                )
            )
            if collision and (not row or collision.connection_id != row.id):
                raise ServiceError(
                    status_code=409,
                    error="This Slack installation is already managed by another M2O account",
                    where="slack",
                )
            if not row:
                row = ProviderConnection(id=uid(), user_id=principal.user_id, provider="slack")
                session.add(row)
            row.state, row.scopes, row.updated_at = "connected", sorted(token.scope.split(",")), now()
            row.expires_at = now() + timedelta(seconds=token.expires_in) if token.expires_in else None
            row.encrypted_credentials = seal(
                row,
                {
                    "access_token": token.access_token,
                    **({"refresh_token": token.refresh_token} if token.refresh_token else {}),
                },
            )
            session.flush()
            account = session.get(SlackAccount, row.id)
            if not account:
                account = SlackAccount(connection_id=row.id)
                session.add(account)
            else:
                account.version += 1
            account.app_id, account.team_id, account.team_name = token.app_id, team_id, team_name
            account.bot_user_id, account.bot_id, account.installed_user_id = (
                token.bot_user_id,
                bot_id,
                user_id,
            )
            for binding in session.scalars(
                select(ProviderDestination).where(ProviderDestination.connection_id == row.id)
            ):
                channel = session.get(SlackDestination, binding.id)
                if channel:
                    session.delete(channel)
                binding.version += 1
            if not session.scalar(binding_query(scoped)):
                session.add(
                    ProviderDestination(
                        connection_id=row.id, user_id=principal.user_id, workspace_id=scoped.scope
                    )
                )
            audit(session, scoped, "slack.connected", row.id)
            session.commit()
            return scoped.scope
        except (ValidationError, ValueError, TypeError) as exc:
            session.rollback()
            session.execute(
                delete(IntegrationOAuthState).where(IntegrationOAuthState.state_hash == digest(state))
            )
            session.commit()
            raise ServiceError(
                status_code=502, error="Slack installation response could not be verified", where="slack"
            ) from exc
        except ServiceError:
            session.commit()
            raise

    async def access(self, session, principal):
        self.authority(session, principal)
        row = session.scalar(connection_query(principal).with_for_update())
        binding = session.scalar(binding_query(principal).with_for_update(of=ProviderDestination))
        account = session.get(SlackAccount, row.id) if row else None
        if not row or not binding or not account or row.state != "connected":
            raise ServiceError(status_code=409, error="Connect Slack first", where="slack")
        if not SCOPES.issubset(set(row.scopes)):
            raise ServiceError(
                status_code=403, error="Slack required scopes are missing; reconnect", where="slack"
            )
        credentials = unseal(row)
        if row.expires_at and aware(row.expires_at) <= now() + timedelta(seconds=60):
            try:
                raw = await self.request(
                    "POST",
                    "oauth.v2.access",
                    form={
                        "grant_type": "refresh_token",
                        "client_id": settings.slack_client_id,
                        "client_secret": settings.slack_client_secret.get_secret_value(),
                        "refresh_token": credentials.get("refresh_token", ""),
                    },
                )
                access, refresh, expiry = (
                    raw.get("access_token"),
                    raw.get("refresh_token"),
                    raw.get("expires_in"),
                )
                if (
                    not isinstance(access, str)
                    or not 1 <= len(access) <= 16000
                    or not isinstance(refresh, str)
                    or not 1 <= len(refresh) <= 16000
                    or type(expiry) is not int
                    or not 1 <= expiry <= 86400
                    or (raw.get("scope") and not SCOPES.issubset(set(raw["scope"].split(","))))
                ):
                    raise ServiceError(
                        status_code=403,
                        error="Slack renewable credentials are unavailable; reconnect",
                        where="slack",
                    )
                row.encrypted_credentials = seal(row, {"access_token": access, "refresh_token": refresh})
                row.expires_at, row.updated_at = now() + timedelta(seconds=expiry), now()
                session.commit()
            except ServiceError as exc:
                if exc.status_code == 403:
                    row.state, row.encrypted_credentials = "reauthorization_required", ""
                    session.commit()
                raise
            self.authority(session, principal)
            row = session.scalar(connection_query(principal).with_for_update())
            binding = session.scalar(binding_query(principal).with_for_update(of=ProviderDestination))
            account = session.get(SlackAccount, row.id) if row else None
            if not row or not binding or not account or row.state != "connected":
                raise ServiceError(status_code=409, error="Slack was disconnected; reconnect", where="slack")
            credentials = unseal(row)
        return row, binding, account, credentials["access_token"]

    async def channel(self, token, channel_id):
        body = await self.request("GET", "conversations.info", token=token, params={"channel": channel_id})
        channel = body.get("channel")
        if (
            not isinstance(channel, dict)
            or channel.get("id") != channel_id
            or not isinstance(channel.get("name"), str)
            or not 1 <= len(channel["name"]) <= 200
        ):
            raise ServiceError(status_code=502, error="Slack channel could not be verified", where="slack")
        if (
            channel.get("is_private") is not False
            or channel.get("is_member") is not True
            or channel.get("is_archived") is not False
            or any(
                channel.get(key) is True
                for key in ("is_shared", "is_ext_shared", "is_org_shared", "is_im", "is_mpim")
            )
        ):
            raise ServiceError(
                status_code=422,
                error="Select an active public channel containing the M2O bot; shared and private channels are not supported",
                where="slack",
            )
        return channel

    async def choose(self, session, principal, payload: SlackDestinationInput):
        _, binding, _, token = await self.access(session, principal)
        if binding.version != payload.expected_version:
            raise ServiceError(status_code=409, error="Slack destination changed; reload", where="client")
        channel = await self.channel(token, payload.channel_id)
        detail = session.get(SlackDestination, binding.id)
        if not detail:
            detail = SlackDestination(destination_id=binding.id)
            session.add(detail)
        detail.channel_id, detail.channel_name, detail.verified_at = channel["id"], channel["name"], now()
        binding.version += 1
        session.flush()
        audit(session, principal, "slack.destination_selected", binding.id)
        return connection_status(session, principal)

    def disconnect(self, session, principal):
        self.owner_authority(session, principal)
        row = session.scalar(connection_query(principal).with_for_update())
        binding = session.scalar(binding_query(principal))
        session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == principal.user_id,
                IntegrationOAuthState.workspace_id == principal.scope,
                IntegrationOAuthState.provider == "slack",
            )
        )
        if row and binding:
            session.delete(binding)
            session.flush()
            if not session.scalar(
                select(ProviderDestination.id).where(ProviderDestination.connection_id == row.id)
            ):
                session.delete(row)
            audit(session, principal, "slack.disconnected", binding.id)
        return {"ok": True}
