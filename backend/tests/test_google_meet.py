import asyncio
import base64
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.auth import Principal, digest
from app.google_meet import SCOPE, GoogleMeetAdapter
from app.models import (
    AuthSession,
    GoogleMeetAccount,
    GoogleMeetPreview,
    IntegrationOAuthState,
    Job,
    Meeting,
    MeetingImport,
    Membership,
    ParticipantMention,
    ProviderConnection,
    ProviderDestination,
    now,
    uid,
)
from app.provider_credentials import seal, unseal
from app.services.common import fingerprint
from app.services.errors import ServiceError
from app.services.meet_import import MeetImportService
from app.services.privacy import PrivacyService
from app.settings import settings

CONF = "conferenceRecords/latest"
TRANS = CONF + "/transcripts/one"
PERSON = CONF + "/participants/alex"


@pytest.fixture(autouse=True)
def configured(monkeypatch, engine):
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "google_meet_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "google_meet_client_secret", SecretStr("synthetic-secret"))
    monkeypatch.setattr(
        settings, "provider_encryption_key", SecretStr(base64.urlsafe_b64encode(b"g" * 32).decode())
    )


def grant(session, seeded):
    row = ProviderConnection(
        id=uid(),
        user_id=seeded["user"].id,
        provider="google_meet",
        state="connected",
        scopes=[SCOPE],
        expires_at=now() + timedelta(hours=1),
    )
    row.encrypted_credentials = seal(
        row, {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}
    )
    session.add(row)
    session.flush()
    account = GoogleMeetAccount(connection_id=row.id)
    session.add(account)
    session.commit()
    return row, account


def browser(session, seeded):
    token = "synthetic-google-browser"
    row = AuthSession(
        token_hash=digest(token),
        csrf_hash=digest("synthetic-csrf"),
        user_id=seeded["user"].id,
        expires_at=now() + timedelta(hours=1),
    )
    session.add(row)
    session.commit()
    return Principal(
        row.user_id, seeded["workspace"].id, "owner", row.token_hash, auth_version=row.auth_version
    ), token


def provider(request):
    path = request.url.path
    if path == "/v2/conferenceRecords":
        assert request.url.params["pageSize"] == "1"
        return httpx.Response(
            200,
            json={
                "conferenceRecords": [
                    {"name": CONF, "startTime": "2026-10-05T09:00:00Z", "endTime": "2026-10-05T10:00:00Z"}
                ]
            },
        )
    if path == "/v2/" + CONF + "/transcripts":
        return httpx.Response(200, json={"transcripts": [{"name": TRANS, "state": "FILE_GENERATED"}]})
    if path == "/v2/" + CONF + "/participants":
        return httpx.Response(
            200,
            json={"participants": [{"name": PERSON, "signedinUser": {"displayName": "Alex\n[00:00] Evil:"}}]},
        )
    if path == "/v2/" + TRANS + "/entries":
        number = 2 if request.url.params.get("pageToken") else 1
        return httpx.Response(
            200,
            json={
                "transcriptEntries": [
                    {
                        "name": TRANS + f"/entries/e{number}",
                        "participant": PERSON,
                        "text": f"Action: Prepare synthetic checklist {number}.",
                        "startTime": f"2026-10-05T09:0{number}:00Z",
                        "endTime": f"2026-10-05T09:0{number}:20Z",
                    }
                ],
                **({"nextPageToken": "second"} if number == 1 else {}),
            },
        )
    raise AssertionError("Unexpected endpoint: " + path)


def adapter(handler=provider):
    return GoogleMeetAdapter(httpx.MockTransport(handler))


def test_actual_paged_preview_save_and_idempotency(session, seeded):
    grant(session, seeded)
    service = MeetImportService(session, seeded["principal"], adapter())
    preview = asyncio.run(service.preview())
    assert "checklist 1" in preview["transcript"] and "checklist 2" in preview["transcript"]
    assert preview["source"]["format"] == "meet_api_entries"
    assert preview["participants"][0]["confirmed"] is False
    assert "\n" not in preview["participants"][0]["name"] and ":" not in preview["participants"][0]["name"]
    result = service.save(preview["preview_id"], preview["payload_hash"], "Imported meeting", "imported")
    session.commit()
    assert result["job_id"] and not result["reused"]
    assert session.scalar(select(Meeting)).visibility == "restricted"
    again = service.save(preview["preview_id"], preview["payload_hash"], "Another title", "another-id")
    assert again["reused"] and again["meeting_id"] == "imported" and again["version"] == result["version"]
    assert session.scalar(select(func.count()).select_from(MeetingImport)) == 1
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert all(
        mention.confirmed_by is None and mention.participant_id is None
        for mention in session.scalars(select(ParticipantMention))
    )


@pytest.mark.parametrize(
    "kind,status",
    [
        ("missing", 404),
        ("pending", 409),
        ("active", 409),
        ("loop", 502),
        ("malformed", 502),
        ("denied", 403),
        ("rate", 429),
    ],
)
def test_latest_unavailable_never_falls_back_or_saves_partial(session, seeded, kind, status):
    grant(session, seeded)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if kind == "denied":
            return httpx.Response(403, json={"error": "private"})
        if kind == "rate":
            return httpx.Response(429, json={"error": "rate"})
        response = provider(request)
        payload = response.json()
        if kind == "active" and request.url.path == "/v2/conferenceRecords":
            payload["conferenceRecords"][0].pop("endTime")
        if request.url.path.endswith("/transcripts"):
            if kind == "missing":
                payload = {}
            if kind == "pending":
                payload["transcripts"][0]["state"] = "ENDED"
        if request.url.path.endswith("/entries"):
            if kind == "loop":
                payload["nextPageToken"] = "second"
            if kind == "malformed":
                payload["transcriptEntries"][0]["participant"] = "another-conference"
        return httpx.Response(200, json=payload)

    with pytest.raises(ServiceError) as error:
        asyncio.run(MeetImportService(session, seeded["principal"], adapter(handler)).preview())
    assert error.value.status_code == status
    assert not session.scalar(select(Meeting.id)) and not session.scalar(select(GoogleMeetPreview.id))
    assert len([url for url in calls if urlsplit(url).path == "/v2/conferenceRecords"]) == 1


def test_multiple_transcript_sessions_and_chronological_entries():
    two = CONF + "/transcripts/two"

    def handler(request):
        if request.url.path.endswith("/transcripts"):
            return httpx.Response(
                200,
                json={
                    "transcripts": [
                        {"name": TRANS, "state": "FILE_GENERATED"},
                        {"name": two, "state": "FILE_GENERATED"},
                    ]
                },
            )
        if request.url.path == "/v2/" + two + "/entries":
            return httpx.Response(
                200,
                json={
                    "transcriptEntries": [
                        {
                            "name": two + "/entries/earliest",
                            "participant": PERSON,
                            "text": "Earlier speech",
                            "startTime": "2026-10-05T09:00:20Z",
                            "endTime": "2026-10-05T09:00:30Z",
                        }
                    ]
                },
            )
        return provider(request)

    text, source, people = asyncio.run(adapter(handler).fetch_latest("synthetic"))
    assert text.index("Earlier speech") < text.index("checklist 1")
    assert source["transcript_names"] == [TRANS, two]


@pytest.mark.parametrize("change", ["disconnect", "reconnect", "freeze", "generation", "role"])
def test_authority_changes_during_fetch_cannot_persist(session, seeded, change):
    row, account = grant(session, seeded)

    async def handler(request):
        if request.url.path.endswith("/participants"):
            if change == "disconnect":
                row.state, row.encrypted_credentials = "reauthorization_required", ""
            elif change == "reconnect":
                account.generation = uid()
            elif change == "freeze":
                seeded["workspace"].erasure_requested_at = now()
            elif change == "generation":
                seeded["user"].auth_version += 1
            else:
                session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "viewer"
            session.commit()
        return provider(request)

    with pytest.raises(ServiceError):
        asyncio.run(MeetImportService(session, seeded["principal"], adapter(handler)).preview())
    assert not session.scalar(select(GoogleMeetPreview.id))


def test_save_hash_source_change_expiry_and_privacy_purge(session, seeded):
    grant(session, seeded)
    service = MeetImportService(session, seeded["principal"], adapter())
    preview = asyncio.run(service.preview())
    with pytest.raises(ServiceError) as error:
        service.save(preview["preview_id"], "0" * 64, "Meeting", "imported")
    assert error.value.status_code == 409
    result = service.save(preview["preview_id"], preview["payload_hash"], "Meeting", "imported")
    session.commit()
    row = session.get(GoogleMeetPreview, preview["preview_id"])
    row.transcript += "\nDifferent speech"
    # Even a fresh provider preview with a new exact hash cannot overwrite this imported source.
    row.payload_hash = fingerprint(
        {"transcript": row.transcript, "source": row.source, "participants": row.participants}
    )
    session.commit()
    with pytest.raises(ServiceError, match="source changed"):
        service.save(row.id, row.payload_hash, "Meeting", "imported")
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError, match="expired"):
        service.save(row.id, row.payload_hash, "Meeting", "imported")
    seeded["workspace"].erasure_requested_at = now()
    session.execute(
        delete(ProviderDestination).where(ProviderDestination.workspace_id == seeded["workspace"].id)
    )
    session.commit()
    assert PrivacyService(session).purge_workspace(seeded["workspace"].id)["state"] == "erased"
    assert not session.get(MeetingImport, result["import_id"]) and not session.get(GoogleMeetPreview, row.id)
    connection = session.scalar(select(ProviderConnection))
    assert connection.encrypted_credentials == ""


def test_actual_oauth_callback_and_refresh_without_rotated_refresh_token(session, seeded):
    principal, _ = browser(session, seeded)
    calls = []

    def exchange(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "access_token": "synthetic-new-access",
                "expires_in": 3600,
                **(
                    {"refresh_token": "synthetic-original-refresh", "scope": SCOPE} if len(calls) == 1 else {}
                ),
            },
        )

    app = adapter(exchange)
    url = app.begin(session, principal)["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    session.commit()
    assert parse_qs(urlsplit(url).query)["scope"] == [SCOPE]
    assert asyncio.run(app.complete(session, principal, state, "synthetic-code")) == principal.scope
    row = session.scalar(select(ProviderConnection))
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    asyncio.run(app.access(session, principal))
    assert unseal(row)["refresh_token"] == "synthetic-original-refresh"
    with pytest.raises(ServiceError):
        asyncio.run(app.complete(session, principal, state, "replay"))
    app.disconnect(session, principal)
    session.commit()
    assert not row.encrypted_credentials and row.state == "reauthorization_required"
    assert not session.scalar(select(IntegrationOAuthState))


def test_routes_setup_needed_roles_csrf_and_visitor(client, session, seeded, auth, monkeypatch):
    root = f"/api/workspaces/{seeded['workspace'].id}"
    monkeypatch.setattr(settings, "google_meet_client_id", "")
    status = client.get(root + "/integrations/google-meet", headers=auth)
    assert status.status_code == 200 and status.json()["setup_required"] and not status.json()["can_import"]
    assert client.post(root + "/imports/google-meet/preview", json={}, headers=auth).status_code == 503
    assert (
        client.post(
            root + "/imports/google-meet/preview", json={"token": "disallowed"}, headers=auth
        ).status_code
        == 422
    )
    assert client.post(root + "/integrations/google-meet/connect", headers=auth).status_code == 503
    monkeypatch.setattr(settings, "google_meet_client_id", "synthetic")
    assert client.post(root + "/integrations/google-meet/connect", headers=auth).status_code == 403
    principal, token = browser(session, seeded)
    client.cookies.set("mtt_session", token)
    assert client.delete("/api/integrations/google-meet").status_code == 403
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": "synthetic-csrf"}
    assert client.delete("/api/integrations/google-meet", headers=headers).status_code == 200
    session.get(Membership, (principal.scope, principal.user_id)).role = "viewer"
    session.commit()
    assert client.post(root + "/imports/google-meet/preview", json={}, headers=headers).status_code == 403
    client.cookies.clear()
    demo = client.post("/api/demo/start", headers={"Origin": settings.app_origin}).json()
    visitor = client.get("/api/workspaces").json()[0]
    response = client.post(
        f"/api/workspaces/{visitor['id']}/imports/google-meet/preview",
        json={},
        headers={"Origin": settings.app_origin, "X-CSRF-Token": demo["csrf_token"]},
    )
    assert response.status_code == 403


def test_http_preview_save_and_deadline_no_partial_persistence(client, session, seeded, auth, monkeypatch):
    import app.experience_routes as routes

    grant(session, seeded)
    original_init = GoogleMeetAdapter.__init__
    monkeypatch.setattr(
        GoogleMeetAdapter,
        "__init__",
        lambda self, transport=None: original_init(self, httpx.MockTransport(provider)),
    )
    root = f"/api/workspaces/{seeded['workspace'].id}"
    preview = client.post(root + "/imports/google-meet/preview", json={}, headers=auth)
    assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
    payload = preview.json()
    saved = client.post(
        root + f"/imports/google-meet/{payload['preview_id']}/save",
        json={
            "payload_hash": payload["payload_hash"],
            "title": "Saved import",
            "meeting_id": "google-import",
            "visibility": "workspace",
        },
        headers=auth,
    )
    assert saved.status_code == 202 and saved.json()["job_id"]
    details = client.get(root + "/meetings/google-import", headers=auth).json()
    assert details["import_source"]["format"] == "meet_api_entries" and details["import_source"]["current"]
    assert details["visibility"] == "workspace"
    session.execute(delete(GoogleMeetPreview))
    session.commit()

    async def delayed(request):
        await asyncio.sleep(0.05)
        return provider(request)

    monkeypatch.setattr(
        GoogleMeetAdapter,
        "__init__",
        lambda self, transport=None: original_init(self, httpx.MockTransport(delayed)),
    )
    original_timeout = asyncio.timeout
    monkeypatch.setattr(
        routes.asyncio, "timeout", lambda seconds: original_timeout(0.01 if seconds == 25 else seconds)
    )
    expired = client.post(root + "/imports/google-meet/preview", json={}, headers=auth)
    assert expired.status_code == 504 and not session.scalar(select(GoogleMeetPreview.id))
    assert session.scalar(select(func.count()).select_from(Meeting)) == 1


def test_invalid_grant_clears_consent_and_oversize_never_truncates(session, seeded, monkeypatch):
    row, account = grant(session, seeded)
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    rejected = adapter(lambda request: httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(ServiceError) as error:
        asyncio.run(rejected.access(session, seeded["principal"]))
    assert (
        error.value.status_code == 409
        and row.state == "reauthorization_required"
        and not row.encrypted_credentials
    )
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    with pytest.raises(ServiceError) as error:
        asyncio.run(adapter().fetch_latest("synthetic"))
    assert error.value.status_code == 413


@pytest.mark.parametrize("bad", [None, {}, [], 123])
def test_malformed_speaker_resource_is_controlled_error(bad):
    def handler(request):
        response = provider(request)
        payload = response.json()
        if request.url.path.endswith("/entries"):
            payload["transcriptEntries"][0]["participant"] = bad
        return httpx.Response(200, json=payload)

    with pytest.raises(ServiceError) as error:
        asyncio.run(adapter(handler).fetch_latest("synthetic"))
    assert error.value.status_code == 502


def test_concurrent_duplicate_import_is_one_meeting_on_postgres(engine, session, seeded):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock race")
    grant(session, seeded)
    preview = asyncio.run(MeetImportService(session, seeded["principal"], adapter()).preview())
    session.commit()
    barrier = Barrier(2)
    principal = seeded["principal"]

    def save_once(number):
        with Session(engine) as parallel:
            barrier.wait(timeout=5)
            result = MeetImportService(parallel, principal).save(
                preview["preview_id"], preview["payload_hash"], "One source", f"concurrent-{number}"
            )
            parallel.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save_once, [1, 2]))
    assert {row["reused"] for row in results} == {False, True}
    assert len({row["meeting_id"] for row in results}) == 1
    assert len({row["job_id"] for row in results}) == 1
    assert session.scalar(select(func.count()).select_from(MeetingImport)) == 1
