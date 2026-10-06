import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_meeting_lifecycle import extracted

from app.auth import Principal
from app.jira_delivery import JiraDeliveryAdapter, document
from app.models import JiraOperation, Job, Membership, ProviderConnection, ProviderDestination, now
from app.provider_credentials import seal
from app.schemas import ItemPatch, JiraPreviewInput
from app.services.errors import ServiceError
from app.services.jira_delivery import JiraDeliveryService
from app.services.review import ReviewService
from app.settings import settings
from app.worker import claim, execute, run_once

SITE = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def delivery(session, seeded, monkeypatch):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "jira_client_id", "synthetic-id")
    monkeypatch.setattr(settings, "jira_client_secret", SecretStr("synthetic-secret"))
    monkeypatch.setattr(
        settings, "provider_encryption_key", SecretStr(base64.urlsafe_b64encode(b"a" * 32).decode())
    )
    row = ProviderConnection(
        user_id=seeded["user"].id,
        provider="jira",
        state="connected",
        scopes=["read:jira-work", "write:jira-work"],
        expires_at=now() + timedelta(hours=1),
        encrypted_credentials="",
    )
    session.add(row)
    session.flush()
    row.encrypted_credentials = seal(
        row, {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}
    )
    binding = ProviderDestination(
        connection_id=row.id,
        user_id=seeded["user"].id,
        workspace_id=seeded["workspace"].id,
        resource_id=SITE,
        resource_name="Synthetic",
        resource_url="https://synthetic.atlassian.net",
        project_key="M2O",
        project_name="Synthetic project",
        version=2,
    )
    session.add(binding)
    session.commit()
    return item, binding


def transport(calls, *, mode="ok", changed=False, required=False):
    def respond(request):
        calls.append(request)
        assert request.url.host == "api.atlassian.com"
        path = request.url.path
        if path.endswith("/issuetypes"):
            return httpx.Response(
                200, json={"issueTypes": [{"id": "10001", "name": "Task", "subtask": False}], "total": 1}
            )
        fields = [
            {
                "fieldId": "summary",
                "name": "Summary",
                "required": True,
                "schema": {"type": "string"},
                "operations": ["set"],
            },
            {
                "fieldId": "description",
                "name": "Description",
                "required": False,
                "schema": {"type": "string"},
                "operations": ["set"],
            },
            {
                "fieldId": "customfield_10",
                "name": "Department",
                "required": required,
                "schema": {"type": "option"},
                "allowedValues": [{"id": "11", "value": "Engineering"}],
                "operations": ["set"],
            },
        ]
        if path.endswith("/issuetypes/10001"):
            return httpx.Response(200, json={"fields": fields, "total": len(fields)})
        if path.endswith("/editmeta"):
            return httpx.Response(200, json={"fields": {f["fieldId"]: f for f in fields}})
        if path.endswith("/properties/m2o.delivery"):
            post = next((r for r in calls if r.method in {"POST", "PUT"}), None)
            marker = json.loads(post.content)["properties"][0]["value"] if post else {"marker": "wrong"}
            return httpx.Response(200, json={"value": marker})
        if request.method == "GET" and path.endswith("/issue/M2O-12"):
            return httpx.Response(
                200,
                json={
                    "key": "M2O-12",
                    "fields": {
                        "project": {"key": "M2O"},
                        "issuetype": {"id": "10001"},
                        "updated": "changed" if changed else "original",
                        "summary": "Prior title",
                        "status": {"name": "Open"},
                    },
                },
            )
        if request.method == "GET" and path.endswith("/issue/M2O-999"):
            return httpx.Response(404, json={"errorMessages": ["Not found"]})
        if request.method in {"POST", "PUT"}:
            if mode == "timeout":
                raise httpx.ReadTimeout("synthetic timeout", request=request)
            if mode == "rejected":
                return httpx.Response(400, json={"errors": {"private": "must never leak"}})
            if mode == "server_error":
                return httpx.Response(503)
            if request.method == "PUT":
                return httpx.Response(204)
            return httpx.Response(
                201, json={"key": "M2O-12", "id": "12", "self": "https://untrusted.invalid"}
            )
        raise AssertionError(str(request.url))

    return httpx.MockTransport(respond)


def preview(session, seeded, delivery, calls, **kwargs):
    item, _ = delivery
    adapter = JiraDeliveryAdapter(transport(calls))
    service = JiraDeliveryService(session, seeded["principal"], adapter)
    proposal = asyncio.run(
        service.preview(
            "weekly",
            JiraPreviewInput(
                item_id=item["id"],
                expected_item_version=2,
                expected_destination_version=2,
                issue_type_id="10001",
                **kwargs,
            ),
        )
    )
    session.commit()
    return service, proposal


def test_exact_create_payload_idempotent_approval_and_receipt(session, seeded, delivery):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls, fields={"customfield_10": "11"})
    assert proposal["payload"]["fields"]["description"]["type"] == "doc"
    assert proposal["payload"]["fields"]["customfield_10"] == {"id": "11"}
    first = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    second = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    assert first["job_id"] == second["job_id"]
    assert asyncio.run(run_once(service.adapter))
    session.expire_all()
    operation = session.get(JiraOperation, first["operation_id"])
    assert operation.state == "completed"
    assert operation.result == {
        "status": "created",
        "issue_key": "M2O-12",
        "url": "https://synthetic.atlassian.net/browse/M2O-12",
    }
    writes = [r for r in calls if r.method == "POST"]
    assert len(writes) == 1 and json.loads(writes[0].content) == proposal["payload"]
    assert not asyncio.run(run_once(service.adapter))


@pytest.mark.parametrize("change", ["item", "destination", "hash", "expired", "demo", "role", "disconnect"])
def test_stale_or_unauthorized_approval_never_enqueues(session, seeded, delivery, monkeypatch, change):
    service, proposal = preview(session, seeded, delivery, [])
    item, binding = delivery
    if change == "item":
        ReviewService(session, seeded["principal"]).patch(
            "weekly", item["id"], ItemPatch(expected_version=2, title="Changed")
        )
    elif change == "destination":
        binding.version += 1
    elif change == "expired":
        service.proposal(proposal["id"]).expires_at = now() - timedelta(seconds=1)
    elif change == "demo":
        monkeypatch.setattr(settings, "public_demo_mode", True)
    elif change == "role":
        session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "editor"
    elif change == "disconnect":
        session.delete(binding)
    session.commit()
    with pytest.raises(ServiceError):
        asyncio.run(
            service.approve(proposal["id"], "0" * 64 if change == "hash" else proposal["payload_hash"])
        )
    assert session.scalar(select(Job).where(Job.kind == "jira_publish")) is None


@pytest.mark.parametrize("mode", ["timeout", "server_error", "rejected"])
def test_uncertain_writes_not_repeated_and_reconcile_requires_marker(session, seeded, delivery, mode):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls)
    queued = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    adapter = JiraDeliveryAdapter(transport(calls, mode=mode))
    assert asyncio.run(run_once(adapter))
    session.expire_all()
    operation = session.get(JiraOperation, queued["operation_id"])
    assert operation.state == ("failed" if mode == "rejected" else "uncertain")
    assert "private" not in json.dumps(operation.result)
    repeated = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    assert repeated["operation_id"] == queued["operation_id"]
    assert not asyncio.run(run_once(adapter))
    assert len([r for r in calls if r.method == "POST"]) == 1
    if mode != "rejected":
        service.adapter = adapter
        with pytest.raises(ServiceError):
            asyncio.run(service.reconcile(operation.id, "M2O-999"))
        session.rollback()
        result = asyncio.run(service.reconcile(operation.id, "M2O-12"))
        session.commit()
        assert result["state"] == "completed" and result["result"]["status"] == "reconciled"
        assert len([r for r in calls if r.method == "POST"]) == 1


def test_update_uses_exact_put_and_checks_remote_changes(session, seeded, delivery):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls, action="update", issue_key="M2O-12")
    queued = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    assert asyncio.run(run_once(service.adapter))
    session.expire_all()
    operation = session.get(JiraOperation, queued["operation_id"])
    assert operation.result["status"] == "updated"
    put = [r for r in calls if r.method == "PUT"]
    assert len(put) == 1 and json.loads(put[0].content) == proposal["payload"]
    assert "project" not in proposal["payload"]["fields"]


def test_changed_remote_issue_is_not_overwritten(session, seeded, delivery):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls, action="update", issue_key="M2O-12")
    queued = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    assert asyncio.run(run_once(JiraDeliveryAdapter(transport(calls, changed=True))))
    session.expire_all()
    assert session.get(JiraOperation, queued["operation_id"]).state == "failed"
    assert not [r for r in calls if r.method in {"PUT", "POST"}]


def test_recovered_lease_does_not_repeat_intent(session, seeded, delivery):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls)
    queued = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    record = claim()
    record["recovered"] = True
    result = asyncio.run(execute(record, service.adapter))
    assert result["state"] == "uncertain"
    assert not [r for r in calls if r.method == "POST"]
    session.expire_all()
    assert session.get(JiraOperation, queued["operation_id"]).state == "uncertain"


def test_required_fields_unknown_values_and_raw_html_are_safe(session, seeded, delivery):
    item, _ = delivery
    calls = []
    service = JiraDeliveryService(
        session, seeded["principal"], JiraDeliveryAdapter(transport(calls, required=True))
    )
    data = dict(
        item_id=item["id"], expected_item_version=2, expected_destination_version=2, issue_type_id="10001"
    )
    for values in ({}, {"customfield_10": "unknown"}, {"status": "Done"}, {"summary": "Override"}):
        with pytest.raises(ServiceError):
            asyncio.run(service.preview("weekly", JiraPreviewInput(**data, fields=values)))
        session.rollback()
    assert (
        document("<script>alert(1)</script>")["content"][0]["content"][0]["text"]
        == "<script>alert(1)</script>"
    )


def test_api_validation_workspace_isolation_and_demo_block(
    client, session, seeded, delivery, auth, monkeypatch
):
    root = f"/api/workspaces/{seeded['workspace'].id}"
    monkeypatch.setattr(settings, "public_demo_mode", True)
    assert client.get(root + "/integrations/jira/metadata", headers=auth).status_code == 403
    assert (
        client.get(
            root + "/integrations/jira/metadata?issue_key=https://evil.invalid", headers=auth
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/workspaces/{seeded['isolated'].id}/meetings/weekly/jira/deliveries", headers=auth
        ).status_code
        == 404
    )
    other = JiraDeliveryService(session, Principal(seeded["other"].id, seeded["isolated"].id, "owner"))
    with pytest.raises(ServiceError, match="not found"):
        other.receipt("00000000-0000-0000-0000-000000000099")


def test_rejected_retry_is_explicit_and_uncertain_retry_is_blocked(session, seeded, delivery):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls)
    queued = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    assert asyncio.run(run_once(JiraDeliveryAdapter(transport(calls, mode="rejected"))))
    service, fresh = preview(session, seeded, delivery, calls)
    retry = asyncio.run(service.approve(fresh["id"], fresh["payload_hash"], retry_rejected=True))
    session.commit()
    assert retry["operation_id"] == queued["operation_id"] and retry["job_id"] != queued["job_id"]
    assert asyncio.run(run_once(JiraDeliveryAdapter(transport(calls, mode="timeout"))))
    session.expire_all()
    with pytest.raises(ServiceError, match="uncertain"):
        asyncio.run(service.approve(fresh["id"], fresh["payload_hash"], retry_rejected=True))
    assert len([r for r in calls if r.method == "POST"]) == 2


def test_http_session_csrf_preview_approval_job_and_receipt(client, session, seeded, delivery, monkeypatch):
    from app.models import WorkItem

    calls = []
    adapter = JiraDeliveryAdapter(transport(calls))
    monkeypatch.setattr("app.services.jira_delivery.JiraDeliveryAdapter", lambda: adapter)
    root = f"/api/workspaces/{seeded['workspace'].id}"
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "owner@example.test", "password": "synthetic-test-password"},
            headers={"Origin": settings.app_origin},
        ).status_code
        == 200
    )
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": client.cookies["mtt_csrf"]}
    item, _ = delivery
    body = dict(
        item_id=item["id"], expected_item_version=2, expected_destination_version=2, issue_type_id="10001"
    )
    assert client.post(root + "/meetings/weekly/jira/preview", json=body).status_code == 403
    response = client.post(root + "/meetings/weekly/jira/preview", json=body, headers=headers)
    assert response.status_code == 200
    proposal = response.json()
    response = client.post(
        root + "/jira/proposals/" + proposal["id"] + "/approve",
        json={"payload_hash": proposal["payload_hash"]},
        headers=headers,
    )
    assert response.status_code == 202
    queued = response.json()
    assert asyncio.run(run_once(adapter))
    assert client.get(root + "/jobs/" + queued["job_id"]).json()["result"]["state"] == "completed"
    receipt = client.get(root + "/jira/operations/" + queued["operation_id"]).json()
    assert (
        receipt["result"]["issue_key"] == "M2O-12" and receipt["proposal"]["payload"] == proposal["payload"]
    )
    assert (
        client.get(root + "/meetings/weekly/jira/deliveries").json()[0]["operation_id"]
        == queued["operation_id"]
    )
    session.expire_all()
    assert session.get(WorkItem, item["id"]).status == "approved"


def test_worker_rechecks_revoked_owner_before_write(session, seeded, delivery):
    calls = []
    service, proposal = preview(session, seeded, delivery, calls)
    queued = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "editor"
    session.commit()
    assert asyncio.run(run_once(service.adapter))
    session.expire_all()
    assert session.get(JiraOperation, queued["operation_id"]).state == "failed"
    assert not [r for r in calls if r.method in {"POST", "PUT"}]


def test_metadata_pagination_and_invalid_contracts_fail_closed():
    from app.jira_delivery import field_contract

    calls = []

    def respond(request):
        start = int(request.url.params["startAt"])
        calls.append(start)
        return httpx.Response(200, json={"issueTypes": [{"id": str(start + 1), "name": "Task"}], "total": 2})

    adapter = JiraDeliveryAdapter(httpx.MockTransport(respond))
    types = asyncio.run(adapter.types("synthetic", {"resource_id": SITE, "project_key": "M2O"}))
    assert [t["id"] for t in types] == ["1", "2"] and calls == [0, 1]
    for raw in (
        {"fieldId": "bad/path"},
        {"fieldId": "summary", "operations": None},
        {"fieldId": "summary", "schema": {"type": []}},
    ):
        with pytest.raises(ServiceError):
            field_contract(raw)


def test_concurrent_approvals_enqueue_once_on_postgres(engine, session, seeded, delivery):
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent approval locking requires PostgreSQL")
    service, proposal = preview(session, seeded, delivery, [])
    barrier = Barrier(2)
    principal = seeded["principal"]

    def approve():
        with Session(engine, expire_on_commit=False) as local:
            barrier.wait(timeout=10)
            result = asyncio.run(
                JiraDeliveryService(local, principal, service.adapter).approve(
                    proposal["id"], proposal["payload_hash"]
                )
            )
            local.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(approve) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert results[0]["job_id"] == results[1]["job_id"]
    session.expire_all()
    assert len(session.scalars(select(Job).where(Job.kind == "jira_publish")).all()) == 1
