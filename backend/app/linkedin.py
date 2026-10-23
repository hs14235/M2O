"""Consenting-user OIDC connection. This is not a directory or name-search API."""

import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import delete, select

from .access_policy import require_private_account
from .auth import aware, digest
from .models import LinkedInProfile, OAuthState, User, now
from .services.errors import ServiceError
from .settings import settings

AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
JWKS_URL = "https://www.linkedin.com/oauth/openid/jwks"
# The issuer LinkedIn signs ID tokens with, from its discovery document
# (https://www.linkedin.com/oauth/.well-known/openid-configuration).
ISSUER = "https://www.linkedin.com/oauth"
log = logging.getLogger("meeting.linkedin")


def verify_id_token(id_token: str, key: dict, nonce: str) -> dict:
    """Signed claims for this app. A nonce, when LinkedIn returns one, must match ours:
    it is optional in the code flow (OIDC Core 3.1.3.7) and LinkedIn does not list it
    among its claims; the session-bound state already protects the callback."""
    claims = jwt.decode(
        id_token,
        jwt.PyJWK.from_dict(key).key,
        algorithms=["RS256"],
        audience=settings.linkedin_client_id,
        issuer=ISSUER,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        leeway=30,
    )
    if "nonce" in claims and (
        not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], nonce)
    ):
        raise ValueError("Nonce mismatch")
    return claims


def log_unverified(flow: str, exc: Exception) -> None:
    """Which check failed, for the operator: an error type and LinkedIn's status only."""
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    log.warning(
        "linkedin_consent_unverified", extra={"error_code": f"{flow}:{type(exc).__name__}", "status": status}
    )


class LinkedInAdapter:
    def __init__(self, transport=None):
        self.transport = transport

    def begin(self, session, principal):
        session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
        require_private_account(session, principal)
        if not settings.linkedin_configured:
            raise ServiceError(
                status_code=503,
                error="Configure an approved LinkedIn OIDC application first",
                where="linkedin",
            )
        if not principal.session_hash:
            raise ServiceError(
                status_code=403, error="Connect LinkedIn from a signed-in browser session", where="client"
            )
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session.execute(delete(OAuthState).where(OAuthState.user_id == principal.user_id))
        session.add(
            OAuthState(
                state_hash=digest(state),
                user_id=principal.user_id,
                session_hash=principal.session_hash,
                nonce=nonce,
                expires_at=now() + timedelta(minutes=10),
            )
        )
        return {
            "url": AUTHORIZATION_URL
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": settings.linkedin_client_id,
                    "redirect_uri": settings.linkedin_profile_redirect_uri,
                    "scope": settings.linkedin_scopes,
                    "state": state,
                    "nonce": nonce,
                }
            )
        }

    async def complete(self, session, principal, state, code: str | None, denied: bool = False):
        session.scalar(
            select(User)
            .where(User.id == principal.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        require_private_account(session, principal)
        stored = session.scalar(
            select(OAuthState).where(OAuthState.state_hash == digest(state)).with_for_update()
        )
        if (
            not stored
            or stored.user_id != principal.user_id
            or stored.session_hash != principal.session_hash
            or aware(stored.expires_at) <= now()
        ):
            raise ServiceError(
                status_code=400, error="LinkedIn state is invalid or expired", where="linkedin"
            )
        nonce = stored.nonce
        session.delete(stored)
        if denied or not code:
            session.commit()
            return {"connected": False}
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False, transport=self.transport) as client:
                response = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": settings.linkedin_profile_redirect_uri,
                        "client_id": settings.linkedin_client_id,
                        "client_secret": settings.linkedin_client_secret.get_secret_value(),
                    },
                )
                response.raise_for_status()
                token = response.json()
                keys_response = await client.get(JWKS_URL)
                keys_response.raise_for_status()
                header = jwt.get_unverified_header(token["id_token"])
                if header.get("alg") != "RS256":
                    raise ValueError("Unexpected signing algorithm")
                key = next(key for key in keys_response.json()["keys"] if key.get("kid") == header.get("kid"))
                claims = verify_id_token(token["id_token"], key, nonce)
                info_response = await client.get(
                    USERINFO_URL, headers={"Authorization": f"Bearer {token['access_token']}"}
                )
                info_response.raise_for_status()
                info = info_response.json()
                if info.get("sub") != claims["sub"]:
                    raise ValueError("Subject mismatch")
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, StopIteration, TypeError) as exc:
            log_unverified("profile", exc)
            session.commit()  # Consume a verified challenge even when exchange fails.
            raise ServiceError(
                status_code=502,
                error="LinkedIn connection could not be verified; try connecting again",
                where="linkedin",
            ) from exc
        # Never store access/refresh/ID tokens, email, or arbitrary provider fields.
        require_private_account(session, principal)
        profile = {
            field: str(info[field])[:250]
            for field in ("name", "given_name", "family_name")
            if info.get(field)
        }
        row = session.get(LinkedInProfile, principal.user_id)
        if row and row.subject != claims["sub"]:
            session.commit()
            raise ServiceError(
                status_code=409,
                error="Disconnect the current LinkedIn account before linking another",
                where="linkedin",
            )
        if not row:
            row = LinkedInProfile(
                user_id=principal.user_id,
                subject=claims["sub"],
                profile=profile,
                scopes=settings.linkedin_scopes.split(),
            )
            session.add(row)
        else:
            row.profile, row.scopes, row.fetched_at = profile, settings.linkedin_scopes.split(), now()
        return {
            "connected": True,
            "profile": profile,
            "provenance": "linkedin_oidc_self",
            "identity_verified": False,
        }

    def disconnect(self, session, principal):
        session.scalar(select(User).where(User.id == principal.user_id).with_for_update())
        require_private_account(session, principal)
        session.execute(delete(LinkedInProfile).where(LinkedInProfile.user_id == principal.user_id))
        session.execute(delete(OAuthState).where(OAuthState.user_id == principal.user_id))
        return {"ok": True}
