import asyncio
import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.auth import Principal
from app.models import (
    AuditEvent,
    DeliveryTombstone,
    Job,
    LinkedInDraft,
    LinkedInOperation,
    LinkedInProfile,
    LinkedInProposal,
    Meeting,
    Membership,
    PlanEntry,
    ProviderConnection,
    ProviderDestination,
    TranscriptChunk,
    TranscriptRevision,
    User,
    WorkItem,
    Workspace,
    now,
)
from app.schemas import IndexInput, WorkspaceErasureInput
from app.services.errors import ServiceError
from app.services.meetings import MeetingService
from app.services.privacy import PrivacyService
from app.settings import settings
from app.worker import run_once

PASSWORD = "synthetic-test-password"
PRIVATE_TEXT = "Action: Review the synthetic private lifecycle document."


def login(client):
    result = client.post(
        "/api/auth/login",
        json={"email": "owner@example.test", "password": PASSWORD},
        headers={"Origin": settings.app_origin},
    )
    assert result.status_code == 200
    return {"Origin": settings.app_origin, "X-CSRF-Token": result.json()["csrf_token"]}


def indexed(session, seeded):
    service = MeetingService(session, seeded["principal"])
    service.index(IndexInput(meeting_id="private-lifecycle", transcript=PRIVATE_TEXT, title="Lifecycle test"))
    session.commit()
    assert asyncio.run(run_once())
    service.enqueue_extraction("private-lifecycle")
    session.commit()
    assert asyncio.run(run_once())
    session.expire_all()
    meeting = session.scalar(select(Meeting).where(Meeting.workspace_id == seeded["workspace"].id))
    item = session.scalar(select(WorkItem).where(WorkItem.meeting_id == meeting.id))
    session.add(
        PlanEntry(
            user_id=seeded["user"].id,
            item_id=item.id,
            planned_on=now().date().isoformat(),
            reviewed_version=item.version,
        )
    )
    session.commit()
    return meeting, item


def delivery_records(session, seeded, meeting):
    connection = ProviderConnection(
        user_id=seeded["user"].id,
        provider="linkedin",
        encrypted_credentials="synthetic-private-ciphertext",
        scopes=["w_member_social"],
        expires_at=now() + timedelta(hours=1),
    )
    session.add(connection)
    session.flush()
    session.add(
        ProviderDestination(
            connection_id=connection.id, user_id=seeded["user"].id, workspace_id=seeded["workspace"].id
        )
    )
    draft = LinkedInDraft(
        workspace_id=meeting.workspace_id,
        meeting_id=meeting.id,
        actor_id=seeded["user"].id,
        kind="post",
        text=PRIVATE_TEXT,
        snapshots=[{"private": PRIVATE_TEXT}],
    )
    session.add(draft)
    session.flush()
    proposal = LinkedInProposal(
        workspace_id=meeting.workspace_id,
        meeting_id=meeting.id,
        actor_id=seeded["user"].id,
        draft_id=draft.id,
        draft_version=1,
        connection_id=connection.id,
        connection_updated_at=connection.updated_at,
        author="urn:li:person:synthetic",
        payload={"commentary": PRIVATE_TEXT},
        payload_hash="a" * 64,
        snapshots=[{"private": PRIVATE_TEXT}],
        expires_at=now() + timedelta(hours=1),
    )
    session.add(proposal)
    session.flush()
    operation = LinkedInOperation(
        proposal_id=proposal.id,
        delivery_key="b" * 64,
        state="uncertain",
        result={"status": "uncertain", "error": PRIVATE_TEXT},
    )
    session.add(operation)
    session.commit()
    return connection, draft, operation


def test_scoped_exports_are_no_store_and_do_not_contain_credentials(client, session, seeded, auth):
    meeting, _ = indexed(session, seeded)
    delivery_records(session, seeded, meeting)
    headers = login(client)
    root = "/api/workspaces/" + seeded["workspace"].id
    exported = client.get(root + "/privacy/export")
    assert exported.status_code == 200 and exported.headers["cache-control"] == "no-store"
    assert exported.json()["meetings"][0]["revisions"][0]["raw_text"] == PRIVATE_TEXT
    account = client.get("/api/privacy/account/export")
    assert account.status_code == 200 and account.headers["cache-control"] == "no-store"
    assert "password_hash" not in account.text and "ciphertext" not in account.text
    assert len(account.json()["personal_plan"]) == 1
    assert exported.json()["meetings"][0]["revisions"][0]["outcomes"][0]["review_history"]
    assert exported.json()["delivery_receipts"][0]["state"] == "uncertain"
    assert "private lifecycle document" not in json.dumps(exported.json()["delivery_receipts"])
    assert exported.json()["audit"]
    assert client.get("/api/privacy/account/export", headers=auth).status_code == 403
    assert client.get("/api/workspaces/" + seeded["isolated"].id + "/privacy/export").status_code == 404
    assert headers["X-CSRF-Token"]


def test_workspace_erasure_requires_password_name_version_and_owner(client, session, seeded):
    indexed(session, seeded)
    headers = login(client)
    root = "/api/workspaces/" + seeded["workspace"].id
    status = client.get(root + "/privacy").json()
    body = {"password": PASSWORD, "confirmation_name": status["name"], "expected_version": status["version"]}
    assert (
        client.post(root + "/privacy/erase", json={**body, "password": "wrong"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            root + "/privacy/erase", json={**body, "confirmation_name": "wrong"}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            root + "/privacy/erase", json={**body, "expected_version": 9}, headers=headers
        ).status_code
        == 409
    )
    assert session.scalar(select(func.count()).select_from(Meeting)) == 1
    session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "editor"
    session.commit()
    assert client.post(root + "/privacy/erase", json=body, headers=headers).status_code == 403


def test_erasure_removes_all_local_content_but_retains_minimal_uncertain_delivery(session, seeded):
    meeting, _ = indexed(session, seeded)
    connection, draft, operation = delivery_records(session, seeded, meeting)
    workspace_id, operation_id, connection_id = seeded["workspace"].id, operation.id, connection.id
    result = PrivacyService(session).erase_workspace(
        seeded["principal"],
        WorkspaceErasureInput(
            password=PASSWORD, confirmation_name=seeded["workspace"].name, expected_version=1
        ),
    )
    assert result["state"] == "erased" and not result["remote_content_erased"]
    session.commit()
    for model in (
        Meeting,
        TranscriptRevision,
        TranscriptChunk,
        WorkItem,
        PlanEntry,
        Job,
        AuditEvent,
        LinkedInDraft,
        LinkedInProposal,
        LinkedInOperation,
    ):
        assert session.scalar(select(func.count()).select_from(model)) == 0
    tombstone = session.scalar(select(DeliveryTombstone))
    assert tombstone.operation_id == operation_id and tombstone.state == "uncertain"
    assert PRIVATE_TEXT not in json.dumps(tombstone.receipt)
    assert tombstone.payload_hash == "a" * 64 and tombstone.delivery_key == "b" * 64
    retained = session.get(ProviderConnection, connection_id)
    assert retained.encrypted_credentials == "" and retained.state == "reauthorization_required"
    assert session.get(Workspace, workspace_id).erased_at
    assert session.get(User, seeded["user"].id).active
    assert session.get(Workspace, seeded["isolated"].id).erased_at is None


def test_erasure_freezes_scope_and_can_resume_after_running_job_settles(client, session, seeded):
    service = MeetingService(session, seeded["principal"])
    result = service.index(IndexInput(meeting_id="in-flight", transcript=PRIVATE_TEXT))
    session.commit()
    job = session.get(Job, result["job_id"])
    job.state, job.lease_token, job.lease_until = (
        "running",
        "synthetic-worker-lease",
        now() + timedelta(seconds=90),
    )
    session.commit()
    headers = login(client)
    root = "/api/workspaces/" + seeded["workspace"].id
    body = {"password": PASSWORD, "confirmation_name": seeded["workspace"].name, "expected_version": 1}
    pending = client.post(root + "/privacy/erase", json=body, headers=headers)
    assert pending.status_code == 202 and pending.json()["retry_required"]
    assert client.get(root + "/meetings").status_code == 404
    status = client.get(root + "/privacy")
    assert status.status_code == 200 and status.json()["state"] == "pending_erasure"
    session.expire_all()
    session.get(Job, result["job_id"]).state = "failed"
    session.commit()
    completed = client.post(
        root + "/privacy/erase", json={**body, "expected_version": status.json()["version"]}, headers=headers
    )
    assert completed.status_code == 200 and completed.json()["state"] == "erased"
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_workspace_scoped_token_cannot_target_another_owned_workspace(session, seeded):
    session.add(Membership(user_id=seeded["user"].id, workspace_id=seeded["isolated"].id, role="owner"))
    session.commit()
    scoped = Principal(
        seeded["user"].id, seeded["isolated"].id, "owner", token_workspace_id=seeded["workspace"].id
    )
    with pytest.raises(ServiceError) as denied:
        PrivacyService(session).erase_workspace(
            scoped,
            WorkspaceErasureInput(
                password=PASSWORD, confirmation_name=seeded["isolated"].name, expected_version=1
            ),
        )
    assert denied.value.status_code == 404
    assert seeded["isolated"].erasure_requested_at is None


def test_account_erasure_preserves_last_owner_and_shared_collaborative_data(client, session, seeded):
    meeting, _ = indexed(session, seeded)
    connection, draft, operation = delivery_records(session, seeded, meeting)
    session.add(
        LinkedInProfile(
            user_id=seeded["user"].id,
            subject="synthetic-member",
            profile={"name": "Synthetic Owner"},
            scopes=["openid", "profile"],
        )
    )
    session.commit()
    headers = login(client)
    body = {"password": PASSWORD, "confirmation": "DELETE MY ACCOUNT"}
    assert client.post("/api/privacy/account/erase", json=body, headers=headers).status_code == 409
    session.add(Membership(user_id=seeded["other"].id, workspace_id=seeded["workspace"].id, role="owner"))
    session.commit()
    erased = client.post("/api/privacy/account/erase", json=body, headers=headers)
    assert erased.status_code == 200 and erased.json()["collaborative_content_retained"]
    assert client.get("/api/me").status_code == 401
    session.expire_all()
    user = session.get(User, seeded["user"].id)
    assert not user.active and user.name == "Deleted account" and user.email.endswith("@deleted.invalid")
    assert session.get(Meeting, meeting.id) is not None
    assert session.get(Membership, (seeded["workspace"].id, seeded["other"].id)).role == "owner"
    assert session.get(Membership, (seeded["workspace"].id, user.id)) is None
    assert session.get(LinkedInProfile, user.id) is None
    assert session.get(ProviderConnection, connection.id).encrypted_credentials == ""
    assert session.get(LinkedInDraft, draft.id).text == "[erased]"
    assert session.get(LinkedInProposal, operation.proposal_id).payload == {}
    assert session.scalar(select(func.count()).select_from(PlanEntry)) == 0


def test_erasure_keeps_a_grant_used_by_another_workspace(session, seeded):
    meeting, _ = indexed(session, seeded)
    connection, _, _ = delivery_records(session, seeded, meeting)
    other_workspace = Workspace(name="Another private workspace", department="finance")
    session.add(other_workspace)
    session.flush()
    session.add(Membership(workspace_id=other_workspace.id, user_id=seeded["user"].id, role="owner"))
    session.flush()
    session.add(
        ProviderDestination(
            connection_id=connection.id, user_id=seeded["user"].id, workspace_id=other_workspace.id
        )
    )
    session.commit()
    PrivacyService(session).erase_workspace(
        seeded["principal"],
        WorkspaceErasureInput(
            password=PASSWORD, confirmation_name=seeded["workspace"].name, expected_version=1
        ),
    )
    session.commit()
    session.expire_all()
    assert (
        session.get(ProviderConnection, connection.id).encrypted_credentials == "synthetic-private-ciphertext"
    )
    assert session.get(Membership, (other_workspace.id, seeded["user"].id)) is not None


def test_review_service_rejects_cached_role_after_demotion(session, seeded):
    from app.schemas import ItemPatch
    from app.services.review import ReviewService

    meeting, item = indexed(session, seeded)
    session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "viewer"
    session.commit()
    with pytest.raises(ServiceError) as denied:
        ReviewService(session, seeded["principal"]).patch(
            meeting.slug, item.id, ItemPatch(expected_version=item.version, status="approved")
        )
    assert denied.value.status_code == 403
    session.refresh(item)
    assert item.status == "draft"


def test_inactive_owner_does_not_satisfy_last_active_owner_guard(client, session, seeded):
    session.add(Membership(workspace_id=seeded["workspace"].id, user_id=seeded["other"].id, role="owner"))
    seeded["other"].active = False
    session.commit()
    headers = login(client)
    root = "/api/workspaces/" + seeded["workspace"].id
    assert (
        client.patch(
            root + "/members/" + seeded["user"].id, json={"role": "editor"}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/privacy/account/erase",
            json={"password": PASSWORD, "confirmation": "DELETE MY ACCOUNT"},
            headers=headers,
        ).status_code
        == 409
    )
