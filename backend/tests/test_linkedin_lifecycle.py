"""Real provider-service records crossing local account/workspace privacy boundaries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select
from test_linkedin_publishing import configured as configured
from test_linkedin_publishing import connected, preview
from test_linkedin_publishing import transport as publishing_transport

from app.auth import Principal, digest
from app.linkedin_publishing import LinkedInPublishingAdapter
from app.models import (
    AuthSession,
    DeliveryTombstone,
    IntegrationOAuthState,
    LinkedInOperation,
    LinkedInProposal,
    Membership,
    ProviderConnection,
    ProviderDestination,
    User,
    Workspace,
    now,
)
from app.schemas import LinkedInPreviewInput, WorkspaceErasureInput
from app.services.errors import ServiceError
from app.services.linkedin_drafts import LinkedInDraftService
from app.services.linkedin_publishing import LinkedInPublishingService
from app.services.privacy import PrivacyService
from app.worker import run_once

PASSWORD = "synthetic-test-password"


def test_workspace_erasure_revokes_actual_unshared_publishing_grant(session, seeded, configured):
    value, _, _ = preview(session, seeded, configured)
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    connection_id = service.connection().id
    # Use actual consent/storage paths; no artificial destination is inserted.
    result = PrivacyService(session).erase_workspace(
        configured,
        WorkspaceErasureInput(
            password=PASSWORD,
            confirmation_name=seeded["workspace"].name,
            expected_version=seeded["workspace"].version,
        ),
    )
    session.commit()
    session.expire_all()
    assert result["state"] == "erased" and not result["remote_content_erased"]
    receipt = session.scalar(
        select(DeliveryTombstone).where(DeliveryTombstone.operation_id == approved["operation_id"])
    )
    assert receipt is not None and receipt.payload_hash == value["payload_hash"]
    retained = session.get(ProviderConnection, connection_id)
    grant_retained = bool(retained.encrypted_credentials)
    assert not grant_retained, "Erased workspace retained its sole publishing grant"
    assert retained.state == "reauthorization_required"


def test_erasing_one_workspace_preserves_real_grant_used_in_another(session, seeded, configured):
    value, _, _ = preview(session, seeded, configured)
    origin = LinkedInPublishingService(session, configured)
    connection_id = origin.connection().id
    session.add(Membership(user_id=configured.user_id, workspace_id=seeded["isolated"].id, role="owner"))
    session.commit()
    other = Principal(
        configured.user_id, seeded["isolated"].id, "owner", session_hash=configured.session_hash
    )
    other_service = LinkedInPublishingService(session, other)
    assert not other_service.status()["can_publish"]
    other_service.access()
    session.commit()
    assert other_service.status()["can_publish"]
    result = PrivacyService(session).erase_workspace(
        configured,
        WorkspaceErasureInput(
            password=PASSWORD,
            confirmation_name=seeded["workspace"].name,
            expected_version=seeded["workspace"].version,
        ),
    )
    session.commit()
    session.expire_all()
    assert result["state"] == "erased"
    retained = session.get(ProviderConnection, connection_id)
    grant_retained = bool(retained.encrypted_credentials)
    assert grant_retained and retained.state == "connected"
    associations = session.scalars(
        select(ProviderDestination).where(ProviderDestination.connection_id == connection_id)
    ).all()
    assert [row.workspace_id for row in associations] == [other.workspace_id]
    assert other_service.status()["can_publish"]


def test_purge_before_other_workspace_use_cannot_restore_cached_credentials(
    engine, session, seeded, configured
):
    from sqlalchemy.orm import Session

    preview(session, seeded, configured)
    session.add(Membership(user_id=configured.user_id, workspace_id=seeded["isolated"].id, role="owner"))
    session.commit()
    other = Principal(configured.user_id, seeded["isolated"].id, "owner")
    service = LinkedInPublishingService(session, other)
    cached = service.connection()
    assert cached.state == "connected" and not service.status()["can_publish"]
    name, version = seeded["workspace"].name, seeded["workspace"].version
    session.commit()
    with Session(engine, expire_on_commit=False) as separate:
        PrivacyService(separate).erase_workspace(
            configured,
            WorkspaceErasureInput(password=PASSWORD, confirmation_name=name, expected_version=version),
        )
        separate.commit()
    assert cached.state == "connected"
    with pytest.raises(ServiceError, match="Reconnect"):
        service.access()
    assert service.association(cached) is None
    assert cached.state == "reauthorization_required"


def test_account_erasure_marks_redacted_draft_stale_for_other_publisher(session, seeded, configured):
    _, local, _ = preview(session, seeded, configured)
    other = seeded["other"]
    session.add(Membership(user_id=other.id, workspace_id=configured.workspace_id, role="owner"))
    browser_hash = digest("synthetic-other-publishing-browser")
    session.add(
        AuthSession(
            token_hash=browser_hash,
            user_id=other.id,
            csrf_hash=digest("csrf"),
            expires_at=now() + timedelta(hours=1),
        )
    )
    session.commit()
    result = PrivacyService(session).erase_account(configured, PASSWORD)
    session.commit()
    session.expire_all()
    assert result["state"] == "deactivated_and_anonymized"
    publisher = Principal(other.id, configured.workspace_id, "owner", session_hash=browser_hash)
    connected(session, publisher)
    values = LinkedInDraftService(session, publisher).list("weekly")
    erased = next(row for row in values if row["id"] == local["id"])
    assert erased["text"] == "[erased]" and erased["sources"] == []
    assert erased["source_stale"], "An erased draft cannot provide approved source evidence"
    with pytest.raises(ServiceError, match="current post draft"):
        LinkedInPublishingService(session, publisher).preview(
            "weekly",
            LinkedInPreviewInput(
                draft_id=erased["id"], expected_draft_version=erased["version"], disclosure_confirmed=True
            ),
        )


@pytest.mark.parametrize("effect", ["created", "uncertain"])
def test_account_erasure_waits_for_inflight_post_and_preserves_receipt(
    engine, session, seeded, configured, effect
):
    if engine.dialect.name != "postgresql":
        pytest.skip("Provider write/erasure concurrency requires PostgreSQL row locks")
    value, _, _ = preview(session, seeded, configured)
    session.add(Membership(user_id=seeded["other"].id, workspace_id=configured.workspace_id, role="owner"))
    service = LinkedInPublishingService(session, configured)
    approved = service.approve(value["id"], value["payload_hash"])
    session.commit()
    connection_id = service.connection().id
    session.rollback()
    posting, release, erase_started, erase_finished = Event(), Event(), Event(), Event()
    calls = []

    async def respond(request):
        calls.append(request.method)
        assert request.method == "POST" and request.url.path == "/rest/posts"
        posting.set()
        assert await asyncio.to_thread(release.wait, 10)
        if effect == "uncertain":
            raise httpx.ReadTimeout("Synthetic post response lost")
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:12345"})

    adapter = LinkedInPublishingAdapter(httpx.MockTransport(respond))

    def deliver():
        return asyncio.run(run_once(linkedin_adapter=adapter))

    def erase():
        from sqlalchemy.orm import Session

        with Session(engine, expire_on_commit=False) as separate:
            erase_started.set()
            result = PrivacyService(separate).erase_account(configured, PASSWORD)
            separate.commit()
            erase_finished.set()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        delivery = pool.submit(deliver)
        assert posting.wait(timeout=10)
        erasure = pool.submit(erase)
        try:
            assert erase_started.wait(timeout=10)
            assert not erase_finished.wait(timeout=0.2)
        finally:
            release.set()
        assert delivery.result(timeout=15)
        assert erasure.result(timeout=15)["state"] == "deactivated_and_anonymized"
    session.expire_all()
    operation = session.get(LinkedInOperation, approved["operation_id"])
    assert operation.state == ("completed" if effect == "created" else "uncertain")
    assert operation.result["status"] == effect
    if effect == "created":
        assert operation.result["post_id"] == "urn:li:share:12345"
    proposal = session.get(LinkedInProposal, value["id"])
    assert proposal.payload == {} and proposal.author == "" and proposal.approved_at is None
    grant_retained = bool(session.get(ProviderConnection, connection_id).encrypted_credentials)
    assert not grant_retained and not session.get(User, configured.user_id).active
    assert not asyncio.run(run_once(linkedin_adapter=adapter))
    assert calls == ["POST"]


def test_workspace_freeze_during_callback_does_not_restore_a_grant(engine, session, seeded, configured):
    if engine.dialect.name != "postgresql":
        pytest.skip("Callback/workspace erasure concurrency requires PostgreSQL row locks")
    from sqlalchemy.orm import Session

    session.add(Membership(user_id=seeded["other"].id, workspace_id=configured.workspace_id, role="owner"))
    begin = LinkedInPublishingService(session, configured).begin()
    session.commit()
    state = parse_qs(urlsplit(begin["url"]).query)["state"][0]
    nonce = session.get(IntegrationOAuthState, digest(state)).nonce
    name, version = seeded["workspace"].name, seeded["workspace"].version
    other = Principal(seeded["other"].id, configured.workspace_id, "owner")
    session.rollback()
    exchanging, release = Event(), Event()

    class PausedExchange(LinkedInPublishingAdapter):
        async def exchange(self, code, nonce):
            exchanging.set()
            assert await asyncio.to_thread(release.wait, 10)
            return await super().exchange(code, nonce)

    def callback():
        with Session(engine, expire_on_commit=False) as separate:
            try:
                asyncio.run(
                    LinkedInPublishingService(
                        separate, configured, PausedExchange(publishing_transport(nonce))
                    ).complete(state, "synthetic-code")
                )
                separate.commit()
                return 200
            except ServiceError as exc:
                separate.rollback()
                return exc.status_code

    def erase():
        with Session(engine, expire_on_commit=False) as separate:
            result = PrivacyService(separate).erase_workspace(
                other,
                WorkspaceErasureInput(password=PASSWORD, confirmation_name=name, expected_version=version),
            )
            separate.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(callback)
        assert exchanging.wait(timeout=10)
        erasure = pool.submit(erase)
        try:
            deadline, frozen = monotonic() + 5, False
            while monotonic() < deadline:
                with Session(engine) as observer:
                    frozen = (
                        observer.scalar(
                            select(Workspace.erasure_requested_at).where(
                                Workspace.id == configured.workspace_id
                            )
                        )
                        is not None
                    )
                if frozen:
                    break
                Event().wait(0.02)
            assert frozen, "Workspace authority must be frozen before awaiting callback cleanup"
        finally:
            release.set()
        assert pending.result(timeout=15) == 404
        assert erasure.result(timeout=15)["state"] == "erased"
    session.expire_all()
    assert (
        session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.user_id == configured.user_id, ProviderConnection.provider == "linkedin"
            )
        )
        is None
    )
    assert session.get(IntegrationOAuthState, digest(state)) is None
