import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_meeting_lifecycle import extracted
from test_slack import APP, BOT, CHANNEL, USER, connected, transport
from test_slack import slack as slack

from app.models import Job, Meeting, Membership, SlackOperation, WorkItem, now
from app.schemas import ItemPatch, SlackDestinationInput, SlackPreviewInput
from app.services.errors import ServiceError
from app.services.review import ReviewService
from app.services.slack_delivery import SlackDeliveryService
from app.settings import settings
from app.slack_delivery import SlackDeliveryAdapter
from app.worker import claim, execute, run_once


@pytest.fixture
def delivery(session, seeded, slack):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    adapter, _ = connected(session, slack, [])
    asyncio.run(adapter.choose(session, slack, SlackDestinationInput(channel_id=CHANNEL, expected_version=1)))
    session.commit()
    return item


def provider(calls, remote, *, mode="ok"):
    base = transport(calls)

    def respond(request):
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint in {"chat.postMessage", "chat.update"}:
            calls.append(request)
            body = json.loads(request.content)
            ts = body.get("ts", "1791000000.000001")
            if mode not in {"rejected", "server", "unknown", "malformed"}:
                remote[ts] = {**body, "ts": ts, "user": USER, "bot_id": BOT, "app_id": APP}
            if mode == "timeout":
                raise httpx.ReadTimeout("Synthetic timeout")
            if mode == "rejected":
                return httpx.Response(
                    200, json={"ok": False, "error": "not_in_channel", "secret": "must-not-leak"}
                )
            if mode == "unknown":
                return httpx.Response(200, json={"ok": False, "error": "internal_error"})
            if mode == "server":
                return httpx.Response(503)
            if mode == "malformed":
                return httpx.Response(200, json={"ok": True, "channel": "CWRONG"})
            return httpx.Response(200, json={"ok": True, "channel": CHANNEL, "ts": ts})
        if endpoint == "conversations.history":
            calls.append(request)
            ts = request.url.params["oldest"]
            return httpx.Response(200, json={"ok": True, "messages": [remote[ts]] if ts in remote else []})
        return base.handle_request(request)

    return SlackDeliveryAdapter(httpx.MockTransport(respond))


def preview(session, slack, delivery, adapter, **options):
    service = SlackDeliveryService(session, slack, adapter)
    data = SlackPreviewInput(
        expected_revision=1, versions={delivery["id"]: 2}, expected_destination_version=2, **options
    )
    result = asyncio.run(service.preview("weekly", data))
    session.commit()
    return service, result


def approved(session, slack, delivery, adapter):
    service, proposal = preview(session, slack, delivery, adapter)
    result = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    return service, proposal, result


def writes(calls):
    return [r for r in calls if r.url.path.endswith(("chat.postMessage", "chat.update"))]


def test_exact_create_receipt_and_idempotent_approval(session, slack, delivery):
    calls, remote = [], {}
    adapter = provider(calls, remote)
    service, proposal, approval = approved(session, slack, delivery, adapter)
    assert proposal["payload"]["unfurl_links"] is False
    assert "Source line" not in proposal["payload"]["text"]
    again = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    assert again == approval
    assert asyncio.run(run_once(adapter))
    session.expire_all()
    operation, stored = service.receipt(approval["operation_id"])
    assert operation.state == "completed" and operation.result["status"] == "created"
    assert len(writes(calls)) == 1
    assert json.loads(writes(calls)[0].content) == proposal["payload"]
    receipt = service.receipt_payload(operation, stored)
    assert not receipt["can_reconcile"] and not receipt["can_retry_rejected"]
    assert service.history("weekly")[0]["operation_id"] == operation.id
    assert session.get(WorkItem, delivery["id"]).status == "approved"


@pytest.mark.parametrize("mode", ["timeout", "server", "unknown", "malformed"])
def test_uncertain_write_cannot_resend(session, slack, delivery, mode):
    calls, remote = [], {}
    adapter = provider(calls, remote, mode=mode)
    service, proposal, approval = approved(session, slack, delivery, adapter)
    assert asyncio.run(run_once(adapter))
    session.expire_all()
    operation, _ = service.receipt(approval["operation_id"])
    assert operation.state == "uncertain"
    assert len(writes(calls)) == 1
    with pytest.raises(ServiceError, match="cannot be retried"):
        asyncio.run(service.approve(proposal["id"], proposal["payload_hash"], retry_rejected=True))
    session.rollback()
    if mode == "timeout":
        result = asyncio.run(service.reconcile(operation.id, "1791000000.000001"))
        session.commit()
        assert result["state"] == "completed" and result["result"]["status"] == "existing"
    assert len(writes(calls)) == 1


def test_known_rejection_requires_explicit_retry(session, slack, delivery):
    calls, remote = [], {}
    service, proposal, approval = approved(session, slack, delivery, provider(calls, remote, mode="rejected"))
    asyncio.run(run_once(service.adapter))
    session.expire_all()
    receipt = service.receipt_payload(*service.receipt(approval["operation_id"]))
    assert receipt["state"] == "failed" and receipt["can_retry_rejected"]
    assert "must-not-leak" not in json.dumps(receipt)
    assert (
        asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))["job_id"] == approval["job_id"]
    )
    retry = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"], retry_rejected=True))
    session.commit()
    assert retry["job_id"] != approval["job_id"]
    asyncio.run(run_once(provider(calls, remote)))
    assert len(writes(calls)) == 2


def test_update_existing_bot_receipt_checks_remote_changes(session, slack, delivery):
    calls, remote = [], {}
    adapter = provider(calls, remote)
    service, _, approval = approved(session, slack, delivery, adapter)
    asyncio.run(run_once(adapter))
    session.expire_all()
    service, proposal = preview(
        session, slack, delivery, adapter, action="update", target_operation_id=approval["operation_id"]
    )
    update = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    asyncio.run(run_once(adapter))
    session.expire_all()
    assert service.receipt(update["operation_id"])[0].result["status"] == "updated"
    assert writes(calls)[-1].method == "POST" and writes(calls)[-1].url.path.endswith("chat.update")


def test_changed_remote_update_is_rejected_before_write(session, slack, delivery):
    calls, remote = [], {}
    adapter = provider(calls, remote)
    service, _, approval = approved(session, slack, delivery, adapter)
    asyncio.run(run_once(adapter))
    session.expire_all()
    service, proposal = preview(
        session, slack, delivery, adapter, action="update", target_operation_id=approval["operation_id"]
    )
    update = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    remote["1791000000.000001"]["text"] = "Remote edit"
    asyncio.run(run_once(adapter))
    session.expire_all()
    assert service.receipt(update["operation_id"])[0].state == "failed"
    assert len(writes(calls)) == 1


@pytest.mark.parametrize("change", ["item", "expiry", "hash", "demo", "role"])
def test_stale_or_unauthorized_approval_has_no_write(session, seeded, slack, delivery, monkeypatch, change):
    calls = []
    service, proposal = preview(session, slack, delivery, provider(calls, {}))
    if change == "item":
        session.get(WorkItem, delivery["id"]).version += 1
    elif change == "expiry":
        service.proposal(proposal["id"]).expires_at = now() - timedelta(seconds=1)
    elif change == "demo":
        monkeypatch.setattr(settings, "public_demo_mode", True)
    elif change == "role":
        session.get(Membership, (slack.scope, slack.user_id)).role = "viewer"
    session.commit()
    with pytest.raises(ServiceError):
        asyncio.run(
            service.approve(proposal["id"], "a" * 64 if change == "hash" else proposal["payload_hash"])
        )
    assert not writes(calls)


def test_restricted_disclosure_evidence_limits_and_lease_recovery(session, slack, delivery):
    calls, remote = [], {}
    adapter = provider(calls, remote)
    session.scalar(select(Meeting).where(Meeting.slug == "weekly")).visibility = "restricted"
    session.commit()
    with pytest.raises(ServiceError, match="restricted"):
        preview(session, slack, delivery, adapter)
    session.rollback()
    service, proposal = preview(
        session, slack, delivery, adapter, confirm_restricted_share=True, include_evidence=True
    )
    assert "Source line" in proposal["payload"]["text"]
    approval = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    session.commit()
    record = claim()
    result = asyncio.run(execute({**record, "recovered": True}, adapter))
    assert result["state"] == "uncertain" and not writes(calls)
    session.expire_all()
    assert session.get(SlackOperation, approval["operation_id"]).state == "uncertain"


def test_workspace_api_receipt_and_runtime_validation(
    client, seeded, session, slack, delivery, monkeypatch, auth
):
    adapter = provider([], {})
    monkeypatch.setattr(
        "app.slack_routes.SlackDeliveryService",
        lambda db, principal: SlackDeliveryService(db, principal, adapter),
    )
    root = "/api/workspaces/" + slack.scope
    body = {"expected_revision": 1, "versions": {delivery["id"]: 2}, "expected_destination_version": 2}
    response = client.post(root + "/meetings/weekly/slack/preview", headers=auth, json=body)
    assert response.status_code == 200
    proposal = response.json()
    approval = client.post(
        root + "/slack/proposals/" + proposal["id"] + "/approve",
        headers=auth,
        json={"payload_hash": proposal["payload_hash"]},
    )
    assert approval.status_code == 202
    assert (
        client.get(root + "/slack/operations/" + approval.json()["operation_id"], headers=auth).status_code
        == 200
    )
    assert (
        client.post(
            root + "/meetings/weekly/slack/preview", headers=auth, json={**body, "expected_revision": True}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/workspaces/"
            + seeded["isolated"].id
            + "/slack/operations/"
            + approval.json()["operation_id"],
            headers=auth,
        ).status_code
        == 404
    )


def test_postgres_concurrent_approvals_share_one_operation(engine, seeded, session, slack, delivery):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock behavior")
    service, proposal = preview(session, slack, delivery, provider([], {}))
    barrier = Barrier(2)

    def approve_once(_):
        with Session(engine, expire_on_commit=False) as db:
            barrier.wait()
            result = asyncio.run(
                SlackDeliveryService(db, slack, provider([], {})).approve(
                    proposal["id"], proposal["payload_hash"]
                )
            )
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve_once, range(2)))
    assert results[0]["operation_id"] == results[1]["operation_id"]
    assert len(session.scalars(select(Job).where(Job.kind == "slack_publish")).all()) == 1


@pytest.mark.parametrize("state", ["sending", "queued", "completed"])
def test_worker_attempt_limit_preserves_durable_receipt(session, slack, delivery, state):
    calls = []
    service, proposal = preview(session, slack, delivery, provider(calls, {}))
    approval = asyncio.run(service.approve(proposal["id"], proposal["payload_hash"]))
    operation = session.get(SlackOperation, approval["operation_id"])
    operation.state = state
    operation.result = (
        {"status": "uncertain"}
        if state == "sending"
        else {"status": "created", "message_ts": "1760000000.000001"}
        if state == "completed"
        else None
    )
    job = session.get(Job, approval["job_id"])
    job.attempts, job.state, job.lease_until = 3, "running", now() - timedelta(seconds=1)
    session.commit()
    assert claim() is None
    session.expire_all()
    operation = session.get(SlackOperation, operation.id)
    job = session.get(Job, job.id)
    assert operation.state == (
        "uncertain" if state == "sending" else "failed" if state == "queued" else "completed"
    )
    assert job.state == ("completed" if state == "completed" else "failed")
    assert job.result["state"] == operation.state and not writes(calls)
