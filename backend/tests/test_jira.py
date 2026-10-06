import asyncio
import base64
import json
import runpy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, digest
from app.jira import JiraAdapter, connection_status
from app.models import (
    AuthSession,
    IntegrationOAuthState,
    Membership,
    ProviderConnection,
    ProviderDestination,
    now,
)
from app.provider_credentials import unseal
from app.schemas import JiraDestinationInput
from app.services.errors import ServiceError
from app.settings import Settings, settings

SITE = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def jira(session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "jira_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "jira_client_secret", SecretStr("synthetic-client-secret"))
    monkeypatch.setattr(
        settings, "provider_encryption_key", SecretStr(base64.urlsafe_b64encode(b"a" * 32).decode())
    )
    monkeypatch.setattr(settings, "public_demo_mode", False)
    browser = digest("synthetic-jira-browser")
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


def transport(
    calls,
    *,
    failure=None,
    scopes="read:jira-work write:jira-work",
    resource_url="https://synthetic.atlassian.net",
):
    def respond(request):
        calls.append(request)
        if request.url.path == "/oauth/token":
            if failure:
                return httpx.Response(failure, json={"error": "invalid_grant", "secret": "must-not-leak"})
            body = json.loads(request.content)
            refreshed = body["grant_type"] == "refresh_token"
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-access-new" if refreshed else "synthetic-access",
                    "refresh_token": "synthetic-refresh-new" if refreshed else "synthetic-refresh",
                    "scope": scopes,
                    "expires_in": 3600,
                },
            )
        assert request.headers["authorization"].startswith("Bearer synthetic-access")
        if request.url.path.endswith("accessible-resources"):
            return httpx.Response(
                200,
                json=[{"id": SITE, "name": "Synthetic Jira", "url": resource_url, "scopes": scopes.split()}],
            )
        assert request.url.host == "api.atlassian.com"
        assert request.url.path == f"/ex/jira/{SITE}/rest/api/3/project/M2O"
        return httpx.Response(200, json={"key": "M2O", "name": "Synthetic M2O Sandbox"})

    return httpx.MockTransport(respond)


def connected(session, jira, calls):
    adapter = JiraAdapter(transport(calls))
    url = adapter.begin(session, jira)["url"]
    session.commit()
    state = parse_qs(urlsplit(url).query)["state"][0]
    asyncio.run(adapter.complete(session, jira, state, "synthetic-code"))
    return adapter, state


def test_connection_seals_tokens_and_verifies_destination(session, seeded, jira):
    calls = []
    adapter, state = connected(session, jira, calls)
    row = session.scalar(select(ProviderConnection))
    assert (
        "synthetic-access" not in row.encrypted_credentials
        and "synthetic-refresh" not in row.encrypted_credentials
    )
    assert unseal(row)["access_token"] == "synthetic-access"
    assert session.get(IntegrationOAuthState, digest(state)) is None
    status = connection_status(session, jira)
    assert status["state"] == "connected" and status["destination"] is None
    assert "synthetic-access" not in json.dumps(status)
    sites = asyncio.run(adapter.sites(session, jira))
    assert sites[0]["id"] == SITE
    result = asyncio.run(
        adapter.choose(
            session, jira, JiraDestinationInput(resource_id=SITE, project_key="M2O", expected_version=1)
        )
    )
    session.commit()
    assert result["destination"]["project_key"] == "M2O" and result["version"] == 2
    assert all(request.method == "GET" for request in calls[1:])
    with pytest.raises(ServiceError, match="changed"):
        asyncio.run(
            adapter.choose(
                session, jira, JiraDestinationInput(resource_id=SITE, project_key="M2O", expected_version=1)
            )
        )
    session.rollback()
    with pytest.raises(ServiceError, match="invalid"):
        asyncio.run(adapter.complete(session, jira, state, "replayed"))


def test_state_wrong_browser_expiry_denial_and_failure(session, jira):
    adapter = JiraAdapter(transport([], failure=400))
    state = parse_qs(urlsplit(adapter.begin(session, jira)["url"]).query)["state"][0]
    session.commit()
    wrong = Principal(jira.user_id, jira.workspace_id, "owner", digest("other-browser"))
    with pytest.raises(ServiceError, match="invalid"):
        asyncio.run(adapter.complete(session, wrong, state, "code"))
    session.rollback()
    with pytest.raises(ServiceError) as error:
        asyncio.run(adapter.complete(session, jira, state, "code"))
    assert "must-not-leak" not in str(error.value)
    assert session.get(IntegrationOAuthState, digest(state)) is None
    state = parse_qs(urlsplit(adapter.begin(session, jira)["url"]).query)["state"][0]
    session.commit()
    assert asyncio.run(adapter.complete(session, jira, state, None, True)) == jira.workspace_id
    assert not session.scalar(select(ProviderConnection))
    state = parse_qs(urlsplit(adapter.begin(session, jira)["url"]).query)["state"][0]
    session.get(IntegrationOAuthState, digest(state)).expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError, match="expired"):
        asyncio.run(adapter.complete(session, jira, state, "code"))


def test_refresh_survives_subsequent_error_and_revocation_clears_credentials(session, jira):
    calls = []
    adapter, _ = connected(session, jira, calls)
    row = session.scalar(select(ProviderConnection))
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError, match="invalid site"):
        asyncio.run(JiraAdapter(transport(calls, resource_url="https://evil.example")).sites(session, jira))
    session.rollback()
    session.refresh(row)
    assert unseal(row)["refresh_token"] == "synthetic-refresh-new"
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError):
        asyncio.run(JiraAdapter(transport([], failure=400)).sites(session, jira))
    assert connection_status(session, jira)["state"] == "reauthorization_required"
    assert row.encrypted_credentials == ""


def test_authorization_demo_scope_and_credential_tampering(session, seeded, jira, monkeypatch):
    adapter, _ = connected(session, jira, [])
    isolated = Principal(jira.user_id, seeded["isolated"].id, "owner", jira.session_hash)
    with pytest.raises(ServiceError) as inaccessible:
        connection_status(session, isolated)
    assert inaccessible.value.status_code == 404
    with pytest.raises(ServiceError) as forbidden:
        asyncio.run(adapter.sites(session, isolated))
    assert forbidden.value.status_code == 404
    session.rollback()
    with pytest.raises(ServiceError):
        adapter.begin(session, Principal(jira.user_id, jira.workspace_id, "viewer", jira.session_hash))
    monkeypatch.setattr(settings, "public_demo_mode", True)
    with pytest.raises(ServiceError, match="demo"):
        adapter.begin(session, jira)
    monkeypatch.setattr(settings, "public_demo_mode", False)
    row = session.scalar(select(ProviderConnection))
    original_id = row.id
    row.id = "00000000-0000-0000-0000-000000000099"
    with pytest.raises(ServiceError, match="cannot be opened"):
        unseal(row)
    row.id = original_id
    monkeypatch.setattr(settings, "public_demo_mode", True)
    adapter.disconnect(session, jira)
    session.commit()
    assert not session.scalar(select(ProviderConnection))


def test_workspace_bindings_share_account_and_disconnect_independently(session, seeded, jira):
    adapter, _ = connected(session, jira, [])
    session.add(Membership(workspace_id=seeded["isolated"].id, user_id=jira.user_id, role="owner"))
    session.commit()
    second = Principal(jira.user_id, seeded["isolated"].id, "owner", jira.session_hash)
    connected(session, second, [])
    assert len(list(session.scalars(select(ProviderConnection)))) == 1
    assert len(list(session.scalars(select(ProviderDestination)))) == 2
    adapter.disconnect(session, jira)
    session.commit()
    assert connection_status(session, jira)["state"] == "disconnected"
    assert connection_status(session, second)["state"] == "connected"
    adapter.disconnect(session, second)
    session.commit()
    assert not session.scalar(select(ProviderConnection))


def test_unknown_site_and_missing_scopes_are_rejected(session, jira):
    adapter, _ = connected(session, jira, [])
    with pytest.raises(ServiceError, match="not authorized"):
        asyncio.run(
            adapter.choose(
                session,
                jira,
                JiraDestinationInput(
                    resource_id="00000000-0000-0000-0000-000000000002", project_key="M2O", expected_version=1
                ),
            )
        )
    session.rollback()
    state = parse_qs(urlsplit(adapter.begin(session, jira)["url"]).query)["state"][0]
    session.commit()
    with pytest.raises(ServiceError, match="permissions"):
        asyncio.run(
            JiraAdapter(transport([], scopes="read:jira-work")).complete(session, jira, state, "code")
        )
    assert session.get(IntegrationOAuthState, digest(state)) is None


def test_concurrent_callbacks_exchange_once(engine, session, jira):
    if engine.dialect.name != "postgresql":
        pytest.skip("OAuth locking requires PostgreSQL")
    calls = []
    adapter = JiraAdapter(transport(calls))
    state = parse_qs(urlsplit(adapter.begin(session, jira)["url"]).query)["state"][0]
    session.commit()
    barrier = Barrier(2)

    def complete(_):
        with Session(engine, expire_on_commit=False) as transaction:
            barrier.wait(timeout=10)
            try:
                asyncio.run(adapter.complete(transaction, jira, state, "code"))
                return 200
            except ServiceError as exc:
                transaction.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(complete, range(2))) == [200, 400]
    assert len(calls) == 1


def test_settings_reject_invalid_encryption_key():
    with pytest.raises(ValidationError, match="32 random bytes"):
        Settings(
            _env_file=None, provider_encryption_key=SecretStr(base64.urlsafe_b64encode(b"short").decode())
        )


def test_private_configuration_preserves_other_settings_and_existing_key(tmp_path):
    update = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "configure_jira.py"))[
        "update_configuration"
    ]
    path = tmp_path / ".env"
    path.write_text("DATABASE_URL=synthetic-private-db\nPUBLIC_DEMO_MODE=true\n")
    update(path, "synthetic-client", "synthetic-secret")
    first = path.read_text()
    key = next(line for line in first.splitlines() if line.startswith("PROVIDER_ENCRYPTION_KEY="))
    assert len(base64.urlsafe_b64decode(key.split("=", 1)[1])) == 32
    update(path, "other-client", "other-secret")
    assert key in path.read_text()
    assert "DATABASE_URL=synthetic-private-db" in path.read_text()
    assert "PUBLIC_DEMO_MODE=true" in path.read_text()
    assert not list(tmp_path.glob(".env.jira.*"))
    before = path.read_text()
    with pytest.raises(ValueError):
        update(path, "client\nINJECTED=1", "secret")
    assert path.read_text() == before


def test_concurrent_refresh_rotates_account_credential_once(engine, session, jira):
    if engine.dialect.name != "postgresql":
        pytest.skip("Refresh serialization requires PostgreSQL")
    connected(session, jira, [])
    row = session.scalar(select(ProviderConnection))
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    calls, barrier = [], Barrier(2)
    adapter = JiraAdapter(transport(calls))

    def sites(_):
        with Session(engine, expire_on_commit=False) as transaction:
            barrier.wait(timeout=10)
            result = asyncio.run(adapter.sites(transaction, jira))
            transaction.commit()
            return result[0]["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(sites, range(2))) == [SITE, SITE]
    assert sum(request.method == "POST" for request in calls) == 1
    session.refresh(row)
    assert unseal(row)["refresh_token"] == "synthetic-refresh-new"


def test_reconnect_invalidates_all_prior_destination_choices(session, jira):
    adapter, _ = connected(session, jira, [])
    asyncio.run(
        adapter.choose(
            session, jira, JiraDestinationInput(resource_id=SITE, project_key="M2O", expected_version=1)
        )
    )
    session.commit()
    connected(session, jira, [])
    assert connection_status(session, jira)["destination"] is None
    assert connection_status(session, jira)["version"] == 3


def test_membership_revocation_prevents_callback_exchange(session, jira):
    calls = []
    adapter = JiraAdapter(transport(calls))
    state = parse_qs(urlsplit(adapter.begin(session, jira)["url"]).query)["state"][0]
    session.commit()
    session.get(Membership, (jira.workspace_id, jira.user_id)).role = "viewer"
    session.commit()
    with pytest.raises(ServiceError):
        asyncio.run(adapter.complete(session, jira, state, "code"))
    assert not calls and not session.scalar(select(ProviderConnection))
    assert session.get(IntegrationOAuthState, digest(state)) is None


def test_browser_api_connection_returns_to_originating_workspace(client, seeded, jira, monkeypatch):
    monkeypatch.setattr("app.main.JiraAdapter", lambda: JiraAdapter(transport([])))
    response = client.post(
        "/api/auth/login",
        json={"email": seeded["user"].email, "password": "synthetic-test-password"},
        headers={"Origin": settings.app_origin},
    )
    assert response.status_code == 200
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": client.cookies["mtt_csrf"]}
    path = f"/api/workspaces/{jira.workspace_id}/integrations/jira"
    assert client.post(path + "/connect").status_code == 403
    response = client.post(path + "/connect", headers=headers)
    assert response.status_code == 200
    state = parse_qs(urlsplit(response.json()["url"]).query)["state"][0]
    callback = client.get(
        "/api/integrations/jira/callback",
        params={"state": state, "code": "synthetic-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert (
        callback.headers["location"] == settings.app_origin + f"/workspaces/{jira.workspace_id}/integrations"
    )
    assert client.get(path).json()["state"] == "connected"
    assert client.delete(path, headers=headers).status_code == 200
    assert client.get(path).json()["state"] == "disconnected"


def test_api_status_authorization_and_strict_destination(client, auth, seeded):
    path = f"/api/workspaces/{seeded['workspace'].id}/integrations/jira"
    assert client.get(path).status_code == 401
    response = client.get(path, headers=auth)
    assert response.status_code == 200 and response.json()["state"] == "disconnected"
    assert "encrypted_credentials" not in response.text
    assert (
        client.post(
            path + "/destination",
            headers=auth,
            json={"resource_id": SITE, "project_key": "../../evil", "expected_version": True},
        ).status_code
        == 422
    )
    isolated = f"/api/workspaces/{seeded['isolated'].id}/integrations/jira"
    assert client.get(isolated, headers=auth).status_code == 404
