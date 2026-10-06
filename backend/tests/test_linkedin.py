import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Principal, digest
from app.linkedin import LinkedInAdapter
from app.models import AuthSession, LinkedInProfile, OAuthState, User, now
from app.services.errors import ServiceError
from app.settings import settings


@pytest.fixture
def connection(session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "linkedin_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "linkedin_client_secret", SecretStr("synthetic-secret"))
    monkeypatch.setattr(
        settings, "linkedin_redirect_uri", "http://localhost:5173/api/integrations/linkedin/callback"
    )
    monkeypatch.setattr(settings, "linkedin_scopes", "openid profile")
    session.add(
        AuthSession(
            token_hash=digest("browser-session"),
            user_id=seeded["user"].id,
            csrf_hash=digest("csrf"),
            expires_at=now() + timedelta(hours=1),
        )
    )
    session.commit()
    principal = Principal(seeded["user"].id, session_hash=digest("browser-session"))
    result = LinkedInAdapter().begin(session, principal)
    session.commit()
    state = parse_qs(urlsplit(result["url"]).query)["state"][0]
    stored = session.get(OAuthState, digest(state))
    return principal, state, stored.nonce


def provider(nonce, overrides=None, info_subject="synthetic-subject"):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()

    def encode(number):
        return (
            base64.urlsafe_b64encode(number.to_bytes((number.bit_length() + 7) // 8, "big"))
            .rstrip(b"=")
            .decode()
        )

    jwk = {
        "kty": "RSA",
        "kid": "synthetic-key",
        "use": "sig",
        "alg": "RS256",
        "n": encode(numbers.n),
        "e": encode(numbers.e),
    }
    claims = {
        "iss": "https://www.linkedin.com",
        "aud": "synthetic-client",
        "sub": "synthetic-subject",
        "exp": now() + timedelta(minutes=10),
        "iat": now(),
        "nonce": nonce,
    }
    claims.update(overrides or {})
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "synthetic-key"})

    def respond(request):
        if request.url.path.endswith("accessToken"):
            assert request.method == "POST"
            return httpx.Response(200, json={"access_token": "synthetic-access-token", "id_token": token})
        if request.url.path.endswith("jwks"):
            return httpx.Response(200, json={"keys": [jwk]})
        return httpx.Response(
            200, json={"sub": info_subject, "name": "Synthetic Person", "email": "not-stored@example.test"}
        )

    return httpx.MockTransport(respond)


def test_configurable_connection_stores_minimum_profile_and_consumes_state(session, seeded, connection):
    principal, state, nonce = connection
    result = asyncio.run(
        LinkedInAdapter(provider(nonce)).complete(session, principal, state, "synthetic-code")
    )
    session.commit()
    assert result["profile"] == {"name": "Synthetic Person"}
    assert result["identity_verified"] is False
    profile = session.get(LinkedInProfile, seeded["user"].id)
    assert "email" not in profile.profile and profile.scopes == ["openid", "profile"]
    assert session.get(OAuthState, digest(state)) is None
    with pytest.raises(ServiceError, match="state"):
        asyncio.run(LinkedInAdapter(provider(nonce)).complete(session, principal, state, "replayed-code"))


def test_concurrent_callbacks_consume_oauth_state_once(engine, connection):
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent OAuth consumption requires PostgreSQL row locks")
    principal, state, nonce = connection
    barrier, calls = Barrier(2), []
    transport = provider(nonce)

    def respond(request):
        calls.append(request.method)
        return transport.handle_request(request)

    def complete(_):
        with Session(engine, expire_on_commit=False) as transaction:
            barrier.wait(timeout=10)
            try:
                result = asyncio.run(
                    LinkedInAdapter(httpx.MockTransport(respond)).complete(
                        transaction, principal, state, "synthetic-code"
                    )
                )
                transaction.commit()
                return result["connected"]
            except ServiceError as exc:
                transaction.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(complete, range(2)))
    assert sorted(results) == [True, 400]
    assert calls.count("POST") == 1


@pytest.mark.parametrize("action", ["disconnect", "erase"])
def test_pending_profile_exchange_cannot_restore_after_disconnect_or_erasure(
    engine, session, connection, action
):
    if engine.dialect.name != "postgresql":
        pytest.skip("Profile lifecycle concurrency requires PostgreSQL row locks")
    principal, state, nonce = connection
    original = provider(nonce)
    exchanging, release, mutation_started, mutation_finished = Event(), Event(), Event(), Event()

    async def respond(request):
        if request.url.path.endswith("accessToken"):
            exchanging.set()
            assert await asyncio.to_thread(release.wait, 10)
        return original.handle_request(request)

    def callback():
        with Session(engine, expire_on_commit=False) as separate:
            asyncio.run(
                LinkedInAdapter(httpx.MockTransport(respond)).complete(
                    separate, principal, state, "synthetic-code"
                )
            )
            separate.commit()

    def mutation():
        with Session(engine, expire_on_commit=False) as separate:
            mutation_started.set()
            if action == "disconnect":
                LinkedInAdapter().disconnect(separate, principal)
            else:
                user = separate.scalar(select(User).where(User.id == principal.user_id).with_for_update())
                user.active = False
                separate.execute(delete(LinkedInProfile).where(LinkedInProfile.user_id == principal.user_id))
                separate.execute(delete(OAuthState).where(OAuthState.user_id == principal.user_id))
            separate.commit()
            mutation_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        exchanging_callback = pool.submit(callback)
        assert exchanging.wait(timeout=10)
        removal = pool.submit(mutation)
        try:
            assert mutation_started.wait(timeout=10)
            assert not mutation_finished.wait(timeout=0.2)
        finally:
            release.set()
        exchanging_callback.result(timeout=15)
        removal.result(timeout=15)
    session.expire_all()
    assert session.get(LinkedInProfile, principal.user_id) is None
    assert session.get(OAuthState, digest(state)) is None


def test_profile_visitor_guard_and_validated_cancellation(session, seeded, connection):
    principal, state, nonce = connection
    adapter = LinkedInAdapter(provider(nonce))
    with pytest.raises(ServiceError, match="state"):
        asyncio.run(adapter.complete(session, principal, "invalid", None, denied=True))
    session.rollback()
    assert session.get(OAuthState, digest(state)) is not None
    assert asyncio.run(adapter.complete(session, principal, state, None, denied=True)) == {"connected": False}
    assert session.get(OAuthState, digest(state)) is None
    seeded["user"].is_visitor, seeded["user"].visitor_expires_at = True, now() + timedelta(hours=1)
    seeded["workspace"].is_demo, seeded["workspace"].demo_expires_at = True, now() + timedelta(hours=1)
    session.commit()
    with pytest.raises(ServiceError, match="private account"):
        adapter.begin(session, principal)
    with pytest.raises(ServiceError, match="private account"):
        asyncio.run(adapter.complete(session, principal, "anything", "synthetic-code"))


@pytest.mark.parametrize(
    "override",
    [
        {"nonce": "wrong"},
        {"aud": "different-client"},
        {"iss": "https://evil.example"},
        {"exp": now() - timedelta(minutes=1)},
    ],
)
def test_signed_claims_require_nonce_audience_issuer_expiry(session, connection, override):
    principal, state, nonce = connection
    with pytest.raises(ServiceError, match="verified"):
        asyncio.run(
            LinkedInAdapter(provider(nonce, override)).complete(session, principal, state, "synthetic-code")
        )
    assert session.get(OAuthState, digest(state)) is None


def test_userinfo_subject_must_match_signed_token(session, connection):
    principal, state, nonce = connection
    with pytest.raises(ServiceError, match="verified"):
        asyncio.run(
            LinkedInAdapter(provider(nonce, info_subject="other-person")).complete(
                session, principal, state, "synthetic-code"
            )
        )


def test_oauth_state_is_bound_to_local_session(session, connection):
    principal, state, nonce = connection
    wrong = Principal(principal.user_id, session_hash=digest("different-session"))
    with pytest.raises(ServiceError, match="state"):
        asyncio.run(LinkedInAdapter(provider(nonce)).complete(session, wrong, state, "synthetic-code"))


def test_no_app_configuration_has_honest_capability(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "linkedin_client_id", "")
    assert client.get("/api/me", headers=auth).json()["capabilities"]["linkedin_configured"] is False
    assert client.post("/api/integrations/linkedin/connect", headers=auth).status_code == 503
