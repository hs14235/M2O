import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_publication import enable, proposal

from app.auth import Principal
from app.github import GitHubAdapter
from app.models import Job, Meeting, PublicationProposal, now
from app.schemas import PreviewInput
from app.services.errors import ServiceError
from app.services.issues import IssueService
from app.worker import run_once


def test_global_allowlist_does_not_enable_an_unbound_workspace(session, seeded, monkeypatch):
    enable(monkeypatch)
    state = IssueService(session, seeded["principal"]).destination_status()
    assert state["configured"] and state["destination"] is None and not state["can_publish"]


def test_owner_binding_is_versioned_and_audited(session, seeded, monkeypatch):
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    first = service.bind("synthetic/demo", 0)
    session.commit()
    assert first["destination"]["version"] == 1 and first["can_publish"]
    with pytest.raises(ServiceError, match="Destination changed"):
        service.bind("synthetic/demo", 0)
    second = service.bind("synthetic/demo", 1)
    session.commit()
    assert second["destination"]["id"] == first["destination"]["id"]
    assert second["destination"]["version"] == 2


@pytest.mark.parametrize("role", ["viewer", "editor", "reviewer"])
def test_binding_requires_workspace_owner(session, seeded, monkeypatch, role):
    enable(monkeypatch)
    principal = Principal(seeded["user"].id, seeded["workspace"].id, role)
    with pytest.raises(ServiceError):
        IssueService(session, principal).bind("synthetic/demo", 0)


def test_binding_rejects_demo_invalid_version_and_operator_denied_repository(session, seeded, monkeypatch):
    service = IssueService(session, seeded["principal"])
    with pytest.raises(ServiceError, match="Demo"):
        service.bind("synthetic/demo", 0)
    enable(monkeypatch)
    with pytest.raises(ServiceError, match="version"):
        service.bind("synthetic/demo", True)
    with pytest.raises(ServiceError, match="operator"):
        service.bind("other/repository", 0)


def test_old_unbound_preview_is_readable_but_not_publishable(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    stored = session.get(PublicationProposal, preview["id"])
    stored.destination_id, stored.destination_version = None, None
    session.commit()
    enable(monkeypatch)
    with pytest.raises(ServiceError, match="unbound"):
        IssueService(session, seeded["principal"]).approve(preview["id"], preview["payload_hash"])
    assert stored.payloads == preview["would_create"]


def test_binding_change_invalidates_approval_and_worker_without_provider_request(
    session, seeded, monkeypatch
):
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    approved = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    service.bind("synthetic/demo", 1)
    session.commit()
    with pytest.raises(ServiceError, match="destination changed"):
        service.approve(preview["id"], preview["payload_hash"])
    session.rollback()
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json=[])

    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    assert session.get(Job, approved["job_id"]).state == "failed"
    assert calls == []


def test_binding_constrains_preview_repository(session, seeded, monkeypatch):
    _, item = proposal(session, seeded)
    with pytest.raises(ServiceError, match="workspace's selected"):
        IssueService(session, seeded["principal"]).preview(
            "weekly", PreviewInput(repo="other/repo", task_ids=[item["id"]])
        )


def test_stored_payload_tampering_invalidates_approval(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    stored = session.get(PublicationProposal, preview["id"])
    stored.payloads = [{**stored.payloads[0], "body": "Changed after preview"}]
    session.commit()
    enable(monkeypatch)
    with pytest.raises(ServiceError, match="integrity"):
        IssueService(session, seeded["principal"]).approve(preview["id"], preview["payload_hash"])


def test_expected_source_destination_and_disclosure_are_enforced(session, seeded, monkeypatch):
    preview, item = proposal(session, seeded)
    service = IssueService(session, seeded["principal"])
    with pytest.raises(ServiceError, match="Outcome changed"):
        service.preview(
            "weekly",
            PreviewInput(repo="synthetic/demo", task_ids=[item["id"]], expected_versions={item["id"]: 1}),
        )
    with pytest.raises(ServiceError, match="Destination changed"):
        service.preview(
            "weekly",
            PreviewInput(repo="synthetic/demo", task_ids=[item["id"]], expected_destination_version=2),
        )
    meeting = session.get(Meeting, session.get(PublicationProposal, preview["id"]).meeting_id)
    meeting.visibility = "restricted"
    session.commit()
    with pytest.raises(ServiceError, match="disclosure"):
        service.preview("weekly", PreviewInput(repo="synthetic/demo", task_ids=[item["id"]]))
    enable(monkeypatch)
    with pytest.raises(ServiceError, match="disclosure"):
        service.approve(preview["id"], preview["payload_hash"])
    confirmed = service.preview(
        "weekly",
        PreviewInput(
            repo="synthetic/demo",
            task_ids=[item["id"]],
            expected_versions={item["id"]: 2},
            expected_destination_version=1,
            external_disclosure_confirmed=True,
        ),
    )
    assert service.approve(confirmed["id"], confirmed["payload_hash"])["state"] == "queued"


def test_http_destination_receipt_and_scope_contract(client, session, seeded, auth, monkeypatch):
    preview, item = proposal(session, seeded)
    enable(monkeypatch)
    root = f"/api/workspaces/{seeded['workspace'].id}"
    assert client.get(root + "/integrations/github", headers=auth).json()["can_publish"]
    assert (
        client.post(
            root + "/integrations/github/destination",
            headers=auth,
            json={"repo": "synthetic/demo", "expected_version": True},
        ).status_code
        == 422
    )
    approval = client.post(
        root + f"/proposals/{preview['id']}/approve",
        headers=auth,
        json={"payload_hash": preview["payload_hash"]},
    )
    assert approval.status_code == 202
    operation_id = approval.json()["operation_id"]
    receipt = client.get(root + f"/operations/{operation_id}", headers=auth)
    assert receipt.status_code == 200 and receipt.json()["results"][0]["item_id"] == item["id"]
    assert client.get(root + "/meetings/weekly/deliveries/github", headers=auth).json() == [receipt.json()]
    assert client.get(root + f"/operations/{operation_id}").status_code == 401


def test_receipt_history_survives_reload_and_preserves_unattempted_results(session, seeded, monkeypatch):
    preview, item = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    approved = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    session.expire_all()
    receipt = service.operation(approved["operation_id"])
    assert receipt["results"] == [
        {
            "status": "not_attempted",
            "item_id": item["id"],
            "version": 2,
            "revision_id": session.get(PublicationProposal, preview["id"]).snapshots[0]["revision_id"],
        }
    ]
    assert service.history("weekly") == [receipt]
    isolated = Principal(seeded["other"].id, seeded["isolated"].id, "owner")
    with pytest.raises(ServiceError, match="not found"):
        IssueService(session, isolated).operation(approved["operation_id"])
    meeting = session.get(Meeting, session.get(PublicationProposal, preview["id"]).meeting_id)
    meeting.visibility = "restricted"
    session.commit()
    hidden = Principal(seeded["other"].id, seeded["workspace"].id, "viewer")
    with pytest.raises(ServiceError, match="not found"):
        IssueService(session, hidden).operation(approved["operation_id"])


def test_concurrent_distinct_previews_enqueue_one_delivery(engine, session, seeded, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent approval requires PostgreSQL row locks")
    preview, item = proposal(session, seeded)
    enable(monkeypatch)
    second = IssueService(session, seeded["principal"]).preview(
        "weekly", PreviewInput(repo="synthetic/demo", task_ids=[item["id"]])
    )
    session.commit()
    barrier = Barrier(2)

    def approve(value):
        with Session(engine, expire_on_commit=False) as separate:
            barrier.wait(timeout=10)
            result = IssueService(separate, seeded["principal"]).approve(value["id"], value["payload_hash"])
            separate.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, [preview, second]))
    assert results[0]["job_id"] == results[1]["job_id"]
    assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == "publish")) == 1


def test_visitor_hides_operator_destination_and_blocks_saved_publication(session, seeded, monkeypatch):
    preview, item = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    approved = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    seeded["user"].is_visitor, seeded["user"].visitor_expires_at = True, now() + timedelta(hours=1)
    seeded["workspace"].is_demo, seeded["workspace"].demo_expires_at = True, now() + timedelta(hours=1)
    session.commit()
    assert service.destination_status() == {
        "configured": False,
        "destination": None,
        "can_manage": False,
        "can_publish": False,
    }
    with pytest.raises(ServiceError, match="private workspace"):
        service.bind("synthetic/demo", 1)
    with pytest.raises(ServiceError, match="private workspace"):
        service.approve(preview["id"], preview["payload_hash"])
    session.rollback()
    local_preview = service.preview("weekly", PreviewInput(repo="synthetic/demo", task_ids=[item["id"]]))
    session.commit()
    assert local_preview["destination"] is None
    calls = []
    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(lambda request: calls.append(request)))))
    session.expire_all()
    assert calls == [] and session.get(Job, approved["job_id"]).state == "failed"
