import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_linkedin import provider
from test_meeting_lifecycle import extracted

from app.auth import Principal, digest
from app.linkedin_publishing import LinkedInPublishingAdapter
from app.models import (
    AuthSession,
    IntegrationOAuthState,
    Job,
    LinkedInDraft,
    LinkedInOperation,
    LinkedInProfile,
    LinkedInProposal,
    ProviderConnection,
    WorkItem,
    now,
)
from app.provider_credentials import unseal
from app.schemas import ItemPatch, LinkedInDraftInput, LinkedInDraftPatch, LinkedInPreviewInput
from app.services.errors import ServiceError
from app.services.linkedin_drafts import LinkedInDraftService
from app.services.linkedin_publishing import LinkedInPublishingService
from app.services.review import ReviewService
from app.settings import settings
from app.worker import run_once


@pytest.fixture
def configured(session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "linkedin_publishing_enabled", True)
    monkeypatch.setattr(settings, "linkedin_client_id", "synthetic-client")
    monkeypatch.setattr(settings, "linkedin_client_secret", SecretStr("synthetic-secret"))
    monkeypatch.setattr(
        settings, "provider_encryption_key", SecretStr(base64.urlsafe_b64encode(b"s" * 32).decode())
    )
    session.add(
        AuthSession(
            token_hash=digest("publishing-browser"),
            user_id=seeded["user"].id,
            csrf_hash=digest("csrf"),
            expires_at=now() + timedelta(hours=1),
        )
    )
    session.commit()
    return Principal(
        seeded["user"].id, seeded["workspace"].id, "owner", session_hash=digest("publishing-browser")
    )


def transport(
    nonce,
    *,
    grant=None,
    claims=None,
    subject="synthetic-subject",
    post_status=201,
    post_id="urn:li:share:12345",
    calls=None,
):
    original = provider(nonce, overrides=claims, info_subject=subject)
    record = calls if calls is not None else []

    def respond(request):
        record.append((request.method, request.url.path))
        if request.url.path.endswith("accessToken"):
            response = original.handle_request(request)
            return httpx.Response(200, json={**response.json(), "expires_in": 3600})
        if request.url.path.endswith("introspectToken"):
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "client_id": "synthetic-client",
                    "scope": "openid,profile,w_member_social",
                    "expires_at": int((now() + timedelta(hours=1)).timestamp()),
                    **(grant or {}),
                },
            )
        if request.url.path == "/rest/posts":
            if post_status == "timeout":
                raise httpx.ReadTimeout("Synthetic timeout")
            return httpx.Response(post_status, headers={"x-restli-id": post_id})
        return original.handle_request(request)

    return httpx.MockTransport(respond)


def connected(session, principal, **options):
    service = LinkedInPublishingService(session, principal)
    result = service.begin()
    session.commit()
    state = parse_qs(urlsplit(result["url"]).query)["state"][0]
    row = session.get(IntegrationOAuthState, digest(state))
    adapter = LinkedInPublishingAdapter(transport(row.nonce, **options))
    result = asyncio.run(
        LinkedInPublishingService(session, principal, adapter).complete(state, "synthetic-code")
    )
    session.commit()
    return adapter, result


def draft(session, seeded, principal, kind="post"):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    result = LinkedInDraftService(session, principal).create(
        "weekly",
        LinkedInDraftInput(
            kind=kind, text="  A synthetic public process improvement.\n", versions={item["id"]: 2}
        ),
    )
    session.commit()
    return result, item


def preview(session, seeded, principal):
    adapter, _ = connected(session, principal)
    value, item = draft(session, seeded, principal)
    result = LinkedInPublishingService(session, principal, adapter).preview(
        "weekly",
        LinkedInPreviewInput(draft_id=value["id"], expected_draft_version=1, disclosure_confirmed=True),
    )
    session.commit()
    return result, value, item


def test_local_draft_exact_text_source_versions_stale_and_workspace_isolation(session, seeded):
    value, item = draft(session, seeded, seeded["principal"])
    assert value["text"].startswith("  ") and value["text"].endswith("\n")
    assert value["sources"][0]["version"] == 2 and not value["source_stale"]
    assert "Source chunk" not in value["text"]
    changed = LinkedInDraftService(session, seeded["principal"]).update(
        "weekly",
        value["id"],
        LinkedInDraftPatch(
            kind="outreach", text="Manual outreach draft", versions={item["id"]: 2}, expected_version=1
        ),
    )
    session.commit()
    assert changed["version"] == 2
    with pytest.raises(ServiceError, match="Draft changed"):
        LinkedInDraftService(session, seeded["principal"]).update(
            "weekly",
            value["id"],
            LinkedInDraftPatch(kind="post", text="Stale edit", versions={item["id"]: 2}, expected_version=1),
        )
    session.rollback()
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=2, title="Changed approved source")
    )
    session.commit()
    assert LinkedInDraftService(session, seeded["principal"]).list("weekly")[0]["source_stale"]
    other = Principal(seeded["other"].id, seeded["isolated"].id, "owner")
    with pytest.raises(ServiceError, match="not found"):
        LinkedInDraftService(session, other).get("weekly", value["id"])


@pytest.mark.parametrize("text", ["", "   ", "x" * 3001])
def test_draft_input_rejects_blank_and_oversized_text(text):
    with pytest.raises(ValidationError):
        LinkedInDraftInput(kind="post", text=text, versions={"00000000-0000-4000-8000-000000000001": 2})


def test_separate_consent_verifies_actual_grants_and_encrypts_without_profile_write(
    session, seeded, configured
):
    adapter, result = connected(session, configured)
    assert result == {"workspace_id": seeded["workspace"].id, "connected": True}
    row = session.scalar(select(ProviderConnection).where(ProviderConnection.provider == "linkedin"))
    assert "synthetic-access-token" not in row.encrypted_credentials
    assert unseal(row)["author"] == "urn:li:person:synthetic-subject"
    assert session.get(LinkedInProfile, seeded["user"].id) is None
    status = LinkedInPublishingService(session, configured).status()
    assert status["can_publish"] and not status["can_message"] and not status["can_reconcile"]
    assert "synthetic-access-token" not in json.dumps(status)


@pytest.mark.parametrize(
    "grant",
    [
        {"active": False},
        {"scope": "openid profile"},
        {"client_id": "other-app"},
        {"expires_at": 0},
        {"expires_at": None},
    ],
)
def test_missing_or_unverified_grant_never_stores_posting_credentials(session, configured, grant):
    with pytest.raises(ServiceError, match="consent could not"):
        connected(session, configured, grant=grant)
    session.rollback()
    assert session.scalar(select(ProviderConnection)) is None
    assert session.scalar(select(IntegrationOAuthState)) is None


@pytest.mark.parametrize(
    "claims",
    [
        {"nonce": "wrong"},
        {"aud": "wrong"},
        {"iss": "https://example.test"},
        {"exp": now() - timedelta(minutes=1)},
    ],
)
def test_publishing_signed_claims_require_session_nonce_audience_issuer_expiry(session, configured, claims):
    with pytest.raises(ServiceError, match="consent could not"):
        connected(session, configured, claims=claims)


def test_cancelled_consent_consumes_only_valid_state_and_does_not_call_provider(session, configured):
    service = LinkedInPublishingService(session, configured)
    result = service.begin()
    session.commit()
    state = parse_qs(urlsplit(result["url"]).query)["state"][0]
    calls = []
    service.adapter = LinkedInPublishingAdapter(httpx.MockTransport(lambda request: calls.append(request)))
    with pytest.raises(ServiceError, match="cancelled"):
        asyncio.run(service.complete(state, None, denied=True))
    assert session.get(IntegrationOAuthState, digest(state)) is None and calls == []
    with pytest.raises(ServiceError, match="state"):
        asyncio.run(service.complete(state, "replayed"))


def test_exact_preview_requires_public_disclosure_and_post_kind(session, seeded, configured):
    connected(session, configured)
    value, _ = draft(session, seeded, configured, kind="outreach")
    with pytest.raises(ServiceError, match="current post"):
        LinkedInPublishingService(session, configured).preview(
            "weekly",
            LinkedInPreviewInput(draft_id=value["id"], expected_draft_version=1, disclosure_confirmed=True),
        )
    session.rollback()
    row = session.get(LinkedInDraft, value["id"])
    row.kind = "post"
    session.commit()
    with pytest.raises(ServiceError, match="disclosed publicly"):
        LinkedInPublishingService(session, configured).preview(
            "weekly", LinkedInPreviewInput(draft_id=value["id"], expected_draft_version=1)
        )


def test_exact_public_post_and_duplicate_approval_receipt(session, seeded, configured):
    value, _, item = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    first = service.approve(value["id"], value["payload_hash"])
    session.commit()
    assert service.approve(value["id"], value["payload_hash"])["job_id"] == first["job_id"]
    session.commit()
    posted = []

    def respond(request):
        assert request.method == "POST" and request.url.path == "/rest/posts"
        assert request.headers["LinkedIn-Version"] == value["api_version"]
        posted.append(json.loads(request.content))
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:12345"})

    asyncio.run(run_once(linkedin_adapter=LinkedInPublishingAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    receipt = service.operation(first["operation_id"])
    assert posted == [value["payload"]] and receipt["state"] == "completed"
    assert receipt["result"] == {"status": "created", "post_id": "urn:li:share:12345"}
    assert service.history("weekly") == [receipt]
    assert session.get(WorkItem, item["id"]).status == "approved"


@pytest.mark.parametrize("status", ["timeout", 200, 302, 500, 503, 201])
def test_uncertain_post_is_not_requeued_or_resent(session, seeded, configured, status):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    calls = []
    adapter = LinkedInPublishingAdapter(
        transport(
            "unused",
            post_status=status,
            post_id="invalid" if status == 201 else "urn:li:share:12345",
            calls=calls,
        )
    )
    asyncio.run(run_once(linkedin_adapter=adapter))
    session.expire_all()
    assert service.operation(approved["operation_id"])["state"] == "uncertain"
    assert service.approve(value["id"], value["payload_hash"])["job_id"] == approved["job_id"]
    session.commit()
    assert not asyncio.run(run_once(linkedin_adapter=adapter))
    assert calls == [("POST", "/rest/posts")]


@pytest.mark.parametrize("expired", [False, True])
def test_visitor_or_expired_authority_cannot_reveal_or_use_saved_grant(session, seeded, configured, expired):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    seeded["user"].is_visitor = seeded["workspace"].is_demo = True
    expiry = now() + timedelta(hours=-1 if expired else 1)
    seeded["user"].visitor_expires_at = seeded["workspace"].demo_expires_at = expiry
    session.commit()
    if not expired:
        status = service.status()
        assert not status["configured"] and status["author"] is None and status["expires_at"] is None
        assert not status["can_connect"] and not status["can_publish"] and status["can_draft"]
    with pytest.raises(ServiceError, match="private workspace|session ended"):
        service.begin()
    session.rollback()
    calls = []
    asyncio.run(
        run_once(
            linkedin_adapter=LinkedInPublishingAdapter(
                httpx.MockTransport(lambda request: calls.append(request))
            )
        )
    )
    session.expire_all()
    assert calls == [] and session.get(Job, approved["job_id"]).state == "failed"


def test_revoked_or_changed_account_blocks_worker_without_send(session, seeded, configured):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    service.disconnect()
    session.commit()
    calls = []
    asyncio.run(
        run_once(
            linkedin_adapter=LinkedInPublishingAdapter(
                httpx.MockTransport(lambda request: calls.append(request))
            )
        )
    )
    session.expire_all()
    assert session.get(Job, approved["job_id"]).state == "failed" and calls == []
    assert service.operation(approved["operation_id"])["state"] == "failed"


def test_recovered_lease_is_uncertain_without_any_send(session, seeded, configured):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    job = session.get(Job, approved["job_id"])
    job.state, job.lease_until, job.attempts = "running", now() - timedelta(seconds=10), 1
    session.commit()
    calls = []
    asyncio.run(
        run_once(
            linkedin_adapter=LinkedInPublishingAdapter(
                httpx.MockTransport(lambda request: calls.append(request))
            )
        )
    )
    session.expire_all()
    assert service.operation(approved["operation_id"])["state"] == "uncertain" and calls == []


def test_callback_browser_binding_and_subject_must_match(session, seeded, configured):
    service = LinkedInPublishingService(session, configured)
    result = service.begin()
    session.commit()
    state = parse_qs(urlsplit(result["url"]).query)["state"][0]
    other_browser = Principal(
        configured.user_id, configured.workspace_id, "owner", session_hash=digest("another-browser")
    )
    with pytest.raises(ServiceError, match="state"):
        asyncio.run(LinkedInPublishingService(session, other_browser).complete(state, "synthetic-code"))
    session.rollback()
    assert session.get(IntegrationOAuthState, digest(state)) is not None
    with pytest.raises(ServiceError, match="consent could not"):
        connected(session, configured, subject="different-userinfo-subject")


def test_disconnect_deletes_ciphertext_and_reconnect_invalidates_old_preview(session, seeded, configured):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    service.disconnect()
    session.commit()
    connection = service.connection()
    assert connection.encrypted_credentials == ""
    connected(session, configured)
    with pytest.raises(ServiceError, match="stale"):
        service.approve(value["id"], value["payload_hash"])


@pytest.mark.parametrize("change", ["hash", "payload", "draft"])
def test_stale_or_tampered_preview_cannot_enqueue(session, seeded, configured, change):
    value, local, item = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    if change == "payload":
        row = session.get(LinkedInProposal, value["id"])
        row.payload = {**row.payload, "api_version": "202001"}
        session.commit()
    elif change == "draft":
        LinkedInDraftService(session, configured).update(
            "weekly",
            local["id"],
            LinkedInDraftPatch(
                kind="post", text="Changed exact text", versions={item["id"]: 2}, expected_version=1
            ),
        )
        session.commit()
    with pytest.raises(ServiceError, match="hash|stale"):
        service.approve(value["id"], "0" * 64 if change == "hash" else value["payload_hash"])
    session.rollback()
    assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == "linkedin_publish")) == 0


@pytest.mark.parametrize("status", [400, 401, 403, 409, 422, 429])
def test_known_provider_rejection_records_failure_and_revoked_grant(session, seeded, configured, status):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    calls = []
    adapter = LinkedInPublishingAdapter(transport("unused", post_status=status, calls=calls))
    asyncio.run(run_once(linkedin_adapter=adapter))
    session.expire_all()
    receipt = service.operation(approved["operation_id"])
    assert receipt["state"] == "failed" and receipt["result"]["status"] == "rejected"
    assert receipt["can_retry_rejected"] is False
    assert service.connection().state == ("reauthorization_required" if status in {401, 403} else "connected")
    assert calls == [("POST", "/rest/posts")]


def test_http_draft_preview_approval_receipt_history_and_isolation(client, auth, session, seeded, configured):
    _, item = draft(session, seeded, configured)
    connected(session, configured)
    root = "/api/workspaces/" + configured.workspace_id
    created = client.post(
        root + "/meetings/weekly/linkedin/drafts",
        headers=auth,
        json={"kind": "post", "text": "  Exact HTTP draft\n", "versions": {item["id"]: 2}},
    )
    assert created.status_code == 201
    value = created.json()
    assert value["text"] == "  Exact HTTP draft\n"
    changed = client.patch(
        root + "/meetings/weekly/linkedin/drafts/" + value["id"],
        headers=auth,
        json={
            "kind": "post",
            "text": "Reviewed HTTP draft",
            "versions": {item["id"]: 2},
            "expected_version": 1,
        },
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert len(client.get(root + "/meetings/weekly/linkedin/drafts", headers=auth).json()) == 2
    status = client.get(root + "/integrations/linkedin/publishing", headers=auth)
    assert status.status_code == 200 and status.json()["can_publish"]
    assert "access_token" not in status.text
    proposal = client.post(
        root + "/meetings/weekly/linkedin/preview",
        headers=auth,
        json={"draft_id": value["id"], "expected_draft_version": 2, "disclosure_confirmed": True},
    )
    assert proposal.status_code == 200
    proposal_value = proposal.json()
    approved = client.post(
        root + "/linkedin/proposals/" + proposal_value["id"] + "/approve",
        headers=auth,
        json={"payload_hash": proposal_value["payload_hash"]},
    )
    assert approved.status_code == 202
    receipt_path = root + "/linkedin/operations/" + approved.json()["operation_id"]
    receipt = client.get(receipt_path, headers=auth)
    assert receipt.status_code == 200 and receipt.json()["state"] == "queued"
    assert client.get(root + "/meetings/weekly/deliveries/linkedin", headers=auth).json() == [receipt.json()]
    assert client.get(receipt_path).status_code == 401
    assert (
        client.get(
            "/api/workspaces/"
            + seeded["isolated"].id
            + "/linkedin/operations/"
            + approved.json()["operation_id"],
            headers=auth,
        ).status_code
        == 404
    )


def test_unknown_expiration_and_demo_mode_cannot_publish(session, seeded, configured, monkeypatch):
    connected(session, configured)
    service = LinkedInPublishingService(session, configured)
    service.connection().expires_at = None
    session.commit()
    assert not service.status()["can_publish"]
    with pytest.raises(ServiceError, match="Reconnect"):
        service.access()
    session.rollback()
    monkeypatch.setattr(settings, "public_demo_mode", True)
    assert not service.status()["can_connect"]
    with pytest.raises(ServiceError, match="Demo mode"):
        service.begin()


def test_concurrent_distinct_previews_share_one_post_intent(engine, session, seeded, configured):
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent approval requires PostgreSQL row locks")
    first, local, _ = preview(session, seeded, configured)
    second = LinkedInPublishingService(session, configured).preview(
        "weekly",
        LinkedInPreviewInput(draft_id=local["id"], expected_draft_version=1, disclosure_confirmed=True),
    )
    session.commit()
    barrier = Barrier(2)

    def approve(value):
        with Session(engine, expire_on_commit=False) as separate:
            barrier.wait(timeout=10)
            result = LinkedInPublishingService(separate, configured).approve(
                value["id"], value["payload_hash"]
            )
            separate.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, [first, second]))
    assert results[0]["job_id"] == results[1]["job_id"]
    assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == "linkedin_publish")) == 1


def test_disconnect_serializes_with_pending_oauth_exchange(engine, session, configured):
    if engine.dialect.name != "postgresql":
        pytest.skip("OAuth/disconnect concurrency requires PostgreSQL row locks")
    service = LinkedInPublishingService(session, configured)
    result = service.begin()
    session.commit()
    state = parse_qs(urlsplit(result["url"]).query)["state"][0]
    nonce = session.get(IntegrationOAuthState, digest(state)).nonce
    session.rollback()
    exchanging, release, disconnect_started, disconnect_finished = Event(), Event(), Event(), Event()

    class PausedExchange(LinkedInPublishingAdapter):
        async def exchange(self, code, nonce):
            exchanging.set()
            assert await asyncio.to_thread(release.wait, 10)
            return await super().exchange(code, nonce)

    def complete():
        with Session(engine, expire_on_commit=False) as separate:
            asyncio.run(
                LinkedInPublishingService(separate, configured, PausedExchange(transport(nonce))).complete(
                    state, "synthetic-code"
                )
            )
            separate.commit()

    def disconnect():
        with Session(engine, expire_on_commit=False) as separate:
            disconnect_started.set()
            LinkedInPublishingService(separate, configured).disconnect()
            separate.commit()
            disconnect_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        callback = pool.submit(complete)
        assert exchanging.wait(timeout=10)
        revoked = pool.submit(disconnect)
        try:
            assert disconnect_started.wait(timeout=10)
            assert not disconnect_finished.wait(timeout=0.2)
        finally:
            release.set()
        callback.result(timeout=15)
        revoked.result(timeout=15)
    session.expire_all()
    connection = service.connection()
    assert connection.encrypted_credentials == "" and connection.state == "reauthorization_required"
    assert not service.status()["can_publish"]


def test_disconnect_after_write_intent_refreshes_cached_connection_without_post(
    engine, session, seeded, configured
):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    disconnected = []

    def revoke_after_intent(current):
        if current.bind is not engine or disconnected:
            return
        if any(
            isinstance(row, LinkedInOperation) and row.state == "sending"
            for row in current.identity_map.values()
        ):
            disconnected.append(True)
            with Session(engine, expire_on_commit=False) as separate:
                LinkedInPublishingService(separate, configured).disconnect()
                separate.commit()

    calls = []
    event.listen(Session, "after_commit", revoke_after_intent)
    try:
        asyncio.run(
            run_once(
                linkedin_adapter=LinkedInPublishingAdapter(
                    httpx.MockTransport(lambda request: calls.append(request))
                )
            )
        )
    finally:
        event.remove(Session, "after_commit", revoke_after_intent)
    session.expire_all()
    assert disconnected == [True] and calls == []
    assert session.get(Job, approved["job_id"]).state == "failed"
    assert service.operation(approved["operation_id"])["state"] == "uncertain"
