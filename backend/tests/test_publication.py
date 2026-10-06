import asyncio
from datetime import timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from test_meeting_lifecycle import extracted

from app.github import GitHubAdapter
from app.models import GitHubDestination, Job, PublicationOperation, WorkItem, now
from app.schemas import ItemPatch, PreviewInput
from app.services.errors import ServiceError
from app.services.issues import IssueService
from app.services.review import ReviewService
from app.settings import settings
from app.worker import run_once


def proposal(session, seeded):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    session.add(
        GitHubDestination(
            workspace_id=seeded["workspace"].id,
            repo="synthetic/demo",
            version=1,
            configured_by=seeded["user"].id,
        )
    )
    session.flush()
    result = IssueService(session, seeded["principal"]).preview(
        "weekly", PreviewInput(repo="synthetic/demo", task_ids=[item["id"]])
    )
    session.commit()
    return result, item


def enable(monkeypatch):
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "github_allowed_repos", "synthetic/demo")
    monkeypatch.setattr(settings, "github_token", SecretStr("synthetic-github-token"))


def test_preview_exact_payload_stale_hash_and_edit_rejection(session, seeded, monkeypatch):
    preview, item = proposal(session, seeded)
    assert "Source chunk" not in preview["would_create"][0]["body"]
    assert "<!-- meeting-to-tasks:" in preview["would_create"][0]["body"]
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    with pytest.raises(ServiceError, match="hash"):
        service.approve(preview["id"], "0" * 64)
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=2, title="Changed after preview")
    )
    session.commit()
    with pytest.raises(ServiceError, match="stale"):
        service.approve(preview["id"], preview["payload_hash"])


def test_publication_idempotency_and_exact_request(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    first = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    second = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    assert second["job_id"] == first["job_id"]
    posted = []

    def respond(request):
        if request.method == "GET":
            assert request.url.params["state"] == "all"
            return httpx.Response(200, json=[])
        import json

        posted.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={
                "number": 12,
                "html_url": "https://github.com/synthetic/demo/issues/12",
                "title": posted[-1]["title"],
                "body": posted[-1]["body"],
                "labels": [{"name": name} for name in posted[-1]["labels"]],
                "assignees": [],
            },
        )

    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    operation = session.get(PublicationOperation, first["operation_id"])
    assert operation.state == "completed" and operation.results[0]["status"] == "created"
    assert posted == preview["would_create"]
    assert not asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    assert len(posted) == 1


def test_closed_issue_marker_prevents_duplicate(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    approved = IssueService(session, seeded["principal"]).approve(preview["id"], preview["payload_hash"])
    session.commit()

    def respond(request):
        assert request.method == "GET"
        return httpx.Response(
            200,
            json=[
                {
                    "title": preview["would_create"][0]["title"],
                    "body": preview["would_create"][0]["body"],
                    "labels": [{"name": name} for name in preview["would_create"][0]["labels"]],
                    "assignees": [],
                    "state": "closed",
                    "number": 9,
                    "html_url": "https://github.com/synthetic/demo/issues/9",
                }
            ],
        )

    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    assert session.get(PublicationOperation, approved["operation_id"]).results[0]["status"] == "existing"


def test_timeout_is_uncertain_and_never_reposted(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    approved = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    calls = []

    def respond(request):
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        raise httpx.ReadTimeout("Synthetic timeout")

    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    assert session.get(PublicationOperation, approved["operation_id"]).state == "uncertain"
    assert service.approve(preview["id"], preview["payload_hash"])["operation_id"] == approved["operation_id"]
    session.commit()
    assert not asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    assert calls.count("POST") == 1

    def reconcile_response(request):
        calls.append(request.method)
        assert request.method == "GET"
        return httpx.Response(
            200,
            json=[
                {
                    "title": preview["would_create"][0]["title"],
                    "body": preview["would_create"][0]["body"],
                    "labels": [{"name": name} for name in preview["would_create"][0]["labels"]],
                    "assignees": [],
                    "state": "closed",
                    "number": 42,
                    "html_url": "https://github.com/synthetic/demo/issues/42",
                }
            ],
        )

    result = asyncio.run(
        service.reconcile(approved["operation_id"], GitHubAdapter(httpx.MockTransport(reconcile_response)))
    )
    session.commit()
    assert result["state"] == "completed"
    assert result["results"][0]["status"] == "existing"
    assert calls.count("POST") == 1


def test_expired_publish_lease_reconciles_without_resending(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    approved = IssueService(session, seeded["principal"]).approve(preview["id"], preview["payload_hash"])
    session.commit()
    job = session.get(Job, approved["job_id"])
    job.state, job.lease_until, job.attempts = "running", now() - timedelta(seconds=10), 1
    session.commit()

    def respond(request):
        assert request.method == "GET"
        return httpx.Response(200, json=[])

    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    assert session.get(PublicationOperation, approved["operation_id"]).state == "uncertain"


@pytest.mark.parametrize("effect", ["created", "existing"])
def test_content_conflict_preserves_resource_and_stops_remaining_batch(session, seeded, monkeypatch, effect):
    first, item = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    other = session.scalar(select(WorkItem).where(WorkItem.id != item["id"]))
    ReviewService(session, seeded["principal"]).patch(
        "weekly", other.id, ItemPatch(expected_version=other.version, status="approved")
    )
    preview = service.preview("weekly", PreviewInput(repo="synthetic/demo", task_ids=[item["id"], other.id]))
    session.commit()
    approved = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    payload = preview["would_create"][0]
    remote = {
        "number": 12,
        "html_url": "https://github.com/synthetic/demo/issues/12",
        "title": "Externally changed title",
        "body": payload["body"],
        "labels": [{"name": name} for name in payload["labels"]],
        "assignees": [],
    }
    calls = []

    def respond(request):
        calls.append(request.method)
        return (
            httpx.Response(200, json=[remote] if effect == "existing" else [])
            if request.method == "GET"
            else httpx.Response(201, json=remote)
        )

    asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    session.expire_all()
    receipt = service.operation(approved["operation_id"])
    assert receipt["state"] == "failed" and receipt["can_reconcile"]
    assert receipt["results"][0]["status"] == "conflict"
    assert receipt["results"][0]["provider_effect"] == effect
    assert receipt["results"][0]["number"] == 12 and receipt["results"][1]["status"] == "not_attempted"
    assert calls.count("POST") == (1 if effect == "created" else 0)
    service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    assert not asyncio.run(run_once(GitHubAdapter(httpx.MockTransport(respond))))
    assert calls.count("POST") == (1 if effect == "created" else 0)


def test_conflict_read_reconciliation_requires_exact_content_and_never_writes(session, seeded, monkeypatch):
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    service = IssueService(session, seeded["principal"])
    approved = service.approve(preview["id"], preview["payload_hash"])
    session.commit()
    payload = preview["would_create"][0]
    remote = {
        "number": 12,
        "html_url": "https://github.com/synthetic/demo/issues/12",
        "title": "Externally changed title",
        "body": payload["body"],
        "labels": [{"name": name} for name in payload["labels"]],
        "assignees": [],
    }
    calls = []

    def respond(request):
        calls.append(request.method)
        assert request.method == "GET"
        return httpx.Response(200, json=[remote])

    adapter = GitHubAdapter(httpx.MockTransport(respond))
    asyncio.run(run_once(adapter))
    session.expire_all()
    unresolved = asyncio.run(service.reconcile(approved["operation_id"], adapter))
    session.commit()
    assert unresolved["state"] == "failed" and unresolved["results"][0]["status"] == "conflict"
    remote["title"] = payload["title"]
    resolved = asyncio.run(service.reconcile(approved["operation_id"], adapter))
    session.commit()
    assert resolved["state"] == "completed" and resolved["results"][0]["status"] == "existing"
    assert calls == ["GET", "GET", "GET"]
