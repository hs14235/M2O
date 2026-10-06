import asyncio
import base64
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.auth import Principal, digest
from app.models import AuthSession, IntegrationOAuthState, ProviderConnection, SlackDestination, now
from app.provider_credentials import unseal
from app.schemas import SlackDestinationInput
from app.services.errors import ServiceError
from app.settings import settings
from app.slack import SCOPES, SlackAdapter, connection_status

CHANNEL = "C00000001"
TEAM = "T00000001"
USER = "U00000001"
BOT = "B00000001"
APP = "A00000001"


@pytest.fixture
def slack(session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "slack_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "slack_client_secret", SecretStr("synthetic-secret"))
    monkeypatch.setattr(
        settings, "provider_encryption_key", SecretStr(base64.urlsafe_b64encode(b"a" * 32).decode())
    )
    browser = digest("synthetic-slack-browser")
    session.add(
        AuthSession(
            token_hash=browser,
            user_id=seeded["user"].id,
            csrf_hash=digest("synthetic-csrf"),
            expires_at=now() + timedelta(hours=1),
        )
    )
    session.commit()
    return Principal(seeded["user"].id, seeded["workspace"].id, "owner", browser)


def transport(calls, *, failure=None, private=False, mismatch=False, rotating=False):
    def respond(request):
        calls.append(request)
        assert request.url.host == "slack.com"
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "oauth.v2.access":
            if failure:
                return httpx.Response(200, json={"ok": False, "error": failure, "token": "must-not-leak"})
            data = {
                "ok": True,
                "access_token": "synthetic-access",
                "token_type": "bot",
                "scope": ",".join(sorted(SCOPES)),
                "bot_user_id": USER,
                "app_id": APP,
                "team": {"id": TEAM, "name": "Synthetic Slack"},
                "authed_user": {"id": "U00000002"},
            }
            if rotating:
                data.update(refresh_token="synthetic-refresh", expires_in=43200)
            return httpx.Response(200, json=data)
        assert request.headers["authorization"] == "Bearer synthetic-access"
        if method == "auth.test":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "team_id": "T00000002" if mismatch else TEAM,
                    "user_id": USER,
                    "bot_id": BOT,
                },
            )
        if method == "conversations.info":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "channel": {
                        "id": CHANNEL,
                        "name": "m2o-demo",
                        "is_member": True,
                        "is_private": private,
                        "is_archived": False,
                        "is_shared": False,
                    },
                },
            )
        raise AssertionError(method)

    return httpx.MockTransport(respond)


def connected(session, slack, calls, **options):
    adapter = SlackAdapter(transport(calls, **options))
    state = parse_qs(urlsplit(adapter.begin(session, slack)["url"]).query)["state"][0]
    session.commit()
    asyncio.run(adapter.complete(session, slack, state, "synthetic-code"))
    return adapter, state


def test_connection_seals_non_expiring_token_and_verifies_channel(session, slack):
    calls = []
    adapter, state = connected(session, slack, calls)
    row = session.scalar(select(ProviderConnection))
    assert row.expires_at is None
    assert "synthetic-access" not in row.encrypted_credentials
    assert unseal(row)["access_token"] == "synthetic-access"
    assert session.get(IntegrationOAuthState, digest(state)) is None
    assert connection_status(session, slack)["destination"] is None
    result = asyncio.run(
        adapter.choose(session, slack, SlackDestinationInput(channel_id=CHANNEL, expected_version=1))
    )
    session.commit()
    assert result["can_create"] and result["version"] == 2
    assert result["destination"]["channel_id"] == CHANNEL
    assert not result["can_capture_meeting"]
    assert "synthetic-access" not in json.dumps(result)
    with pytest.raises(ServiceError, match="changed"):
        asyncio.run(
            adapter.choose(session, slack, SlackDestinationInput(channel_id=CHANNEL, expected_version=1))
        )
    session.rollback()
    adapter.disconnect(session, slack)
    session.commit()
    assert not session.scalar(select(SlackDestination))
    assert not session.scalar(select(ProviderConnection))


@pytest.mark.parametrize("option", ["private", "mismatch", "failure"])
def test_wrong_bot_private_channel_and_denied_exchange_fail_closed(session, slack, option):
    options = (
        {"private": True}
        if option == "private"
        else {"mismatch": True}
        if option == "mismatch"
        else {"failure": "invalid_code"}
    )
    if option == "private":
        adapter, _ = connected(session, slack, [], **options)
        with pytest.raises(ServiceError, match="public channel"):
            asyncio.run(
                adapter.choose(session, slack, SlackDestinationInput(channel_id=CHANNEL, expected_version=1))
            )
        assert not session.scalar(select(SlackDestination))
    else:
        with pytest.raises(ServiceError) as error:
            connected(session, slack, [], **options)
        assert "must-not-leak" not in str(error.value)
        assert not session.scalar(select(ProviderConnection))
        assert not session.scalar(select(IntegrationOAuthState))


def test_wrong_browser_expiry_and_demo_block_connect(session, slack, monkeypatch):
    adapter = SlackAdapter(transport([]))
    state = parse_qs(urlsplit(adapter.begin(session, slack)["url"]).query)["state"][0]
    session.commit()
    with pytest.raises(ServiceError, match="invalid"):
        asyncio.run(
            adapter.complete(
                session, Principal(slack.user_id, slack.workspace_id, "owner", digest("wrong")), state, "code"
            )
        )
    session.rollback()
    session.get(IntegrationOAuthState, digest(state)).expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError, match="expired"):
        asyncio.run(adapter.complete(session, slack, state, "code"))
    monkeypatch.setattr(settings, "public_demo_mode", True)
    with pytest.raises(ServiceError, match="demo"):
        adapter.begin(session, slack)


def test_rotating_tokens_persist_and_invalid_refresh_revokes(session, slack):
    adapter, _ = connected(session, slack, [], rotating=True)
    row = session.scalar(select(ProviderConnection))
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    asyncio.run(adapter.access(session, slack))
    session.rollback()
    session.refresh(row)
    assert (
        row.expires_at > now() - timedelta(minutes=1)
        if row.expires_at.tzinfo
        else row.expires_at > now().replace(tzinfo=None)
    )
    assert unseal(row)["refresh_token"] == "synthetic-refresh"
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError):
        asyncio.run(SlackAdapter(transport([], failure="token_revoked")).access(session, slack))
    assert row.state == "reauthorization_required" and row.encrypted_credentials == ""
