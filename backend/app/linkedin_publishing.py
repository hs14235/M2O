"""Member-owned text-post protocol, separate from token-discarding OIDC context."""

import re
import secrets
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from .linkedin import JWKS_URL, TOKEN_URL, USERINFO_URL
from .models import now
from .services.errors import ServiceError
from .settings import settings

INTROSPECTION_URL = "https://www.linkedin.com/oauth/v2/introspectToken"
POSTS_URL = "https://api.linkedin.com/rest/posts"
PUBLISHING_SCOPES = {"openid", "profile", "w_member_social"}


class UncertainLinkedInWrite(Exception):
    pass


class LinkedInPublishingAdapter:
    def __init__(self, transport=None):
        self.transport = transport

    async def exchange(self, code: str, nonce: str) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=15, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                response = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": settings.linkedin_publishing_redirect_uri,
                        "client_id": settings.linkedin_client_id,
                        "client_secret": settings.linkedin_client_secret.get_secret_value(),
                    },
                )
                response.raise_for_status()
                token = response.json()
                access_token, ttl = token["access_token"], token["expires_in"]
                if (
                    not isinstance(access_token, str)
                    or not access_token
                    or len(access_token) > 8192
                    or type(ttl) is not int
                    or ttl <= 0
                ):
                    raise ValueError("Invalid token response")
                keys_response = await client.get(JWKS_URL)
                keys_response.raise_for_status()
                header = jwt.get_unverified_header(token["id_token"])
                if header.get("alg") != "RS256":
                    raise ValueError("Unexpected signing algorithm")
                key = next(key for key in keys_response.json()["keys"] if key.get("kid") == header.get("kid"))
                claims = jwt.decode(
                    token["id_token"],
                    jwt.PyJWK.from_dict(key).key,
                    algorithms=["RS256"],
                    audience=settings.linkedin_client_id,
                    issuer="https://www.linkedin.com",
                    options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
                    leeway=30,
                )
                if not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], nonce):
                    raise ValueError("Nonce mismatch")
                info_response = await client.get(
                    USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
                )
                info_response.raise_for_status()
                info = info_response.json()
                subject = claims["sub"]
                if (
                    not isinstance(subject, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", subject)
                    or info.get("sub") != subject
                ):
                    raise ValueError("Subject mismatch")
                grant_response = await client.post(
                    INTROSPECTION_URL,
                    data={
                        "client_id": settings.linkedin_client_id,
                        "client_secret": settings.linkedin_client_secret.get_secret_value(),
                        "token": access_token,
                    },
                )
                grant_response.raise_for_status()
                grant = grant_response.json()
                if (
                    grant.get("active") is not True
                    or grant.get("client_id") != settings.linkedin_client_id
                    or not isinstance(grant.get("scope"), str)
                ):
                    raise ValueError("Unverified publishing grant")
                scopes = set(grant["scope"].replace(",", " ").split())
                expiry = grant.get("expires_at")
                if not PUBLISHING_SCOPES.issubset(scopes) or type(expiry) is not int:
                    raise ValueError("Missing publishing permission or expiry")
                expires_at = min(now() + timedelta(seconds=ttl), datetime.fromtimestamp(expiry, UTC))
                if expires_at <= now():
                    raise ValueError("Expired grant")
        except (
            httpx.HTTPError,
            jwt.PyJWTError,
            ValueError,
            KeyError,
            StopIteration,
            TypeError,
            OverflowError,
            AttributeError,
        ) as exc:
            raise ServiceError(
                status_code=502,
                error="LinkedIn publishing consent could not be verified; reconnect",
                where="linkedin",
            ) from exc
        return {
            "access_token": access_token,
            "author": "urn:li:person:" + subject,
            "scopes": sorted(scopes),
            "expires_at": expires_at,
        }

    @staticmethod
    def payload(author: str, text: str) -> dict:
        if not re.fullmatch(r"urn:li:person:[A-Za-z0-9_-]{1,200}", author):
            raise ServiceError(status_code=422, error="Invalid LinkedIn author", where="client")
        if not isinstance(text, str) or not text.strip() or len(text) > 3000:
            raise ServiceError(
                status_code=422, error="LinkedIn post text must contain 1 to 3000 characters", where="client"
            )
        return {
            "author": author,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

    async def publish(self, access_token: str, payload: dict, api_version: str) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=15, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                response = await client.post(
                    POSTS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "LinkedIn-Version": api_version,
                        "X-Restli-Protocol-Version": "2.0.0",
                    },
                    json=payload,
                )
                if response.status_code in {400, 401, 403, 404, 409, 422, 429}:
                    raise ServiceError(
                        status_code=502,
                        error="LinkedIn rejected the post; inspect permissions or content",
                        where="linkedin",
                        extra={"provider_status": response.status_code},
                    )
                if response.status_code != 201:
                    raise UncertainLinkedInWrite("LinkedIn did not confirm the write")
                post_id = response.headers.get("x-restli-id", "")
                if not re.fullmatch(r"urn:li:(?:share|ugcPost):[0-9]{1,30}", post_id):
                    raise UncertainLinkedInWrite("LinkedIn did not return a verified post identifier")
                return {"status": "created", "post_id": post_id}
        except httpx.TransportError as exc:
            raise UncertainLinkedInWrite("LinkedIn did not confirm the write") from exc
