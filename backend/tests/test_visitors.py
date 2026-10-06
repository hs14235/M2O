import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import digest
from app.main import app
from app.models import (
    ApiToken,
    AuthSession,
    Job,
    Meeting,
    Membership,
    User,
    VisitorUsage,
    Workspace,
    now,
)
from app.services.demo import DemoService
from app.services.errors import ServiceError
from app.settings import settings
from app.worker import authorized, run_once


def start(client):
    response = client.post("/api/demo/start", headers={"Origin": settings.app_origin})
    assert response.status_code == 201, response.json()
    data = response.json()
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": data["csrf_token"]}
    workspaces = client.get("/api/workspaces").json()
    return data, headers, {workspace["department"]: workspace for workspace in workspaces}


def load(client, headers, workspace, fixture="engineering"):
    root = "/api/workspaces/" + workspace["id"]
    response = client.post(root + "/demo/load", json={"fixture_id": fixture}, headers=headers)
    assert response.status_code == 202, response.json()
    return root, response.json()


def test_visitors_have_distinct_authority_and_no_private_workspace_access(client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "github_allowed_repos", "operator/private-repository")
    monkeypatch.setattr(settings, "ollama_model", "private-model")
    first, headers, spaces = start(client)
    assert len(spaces) == 3
    assert all(space["is_demo"] and space["expires_at"] for space in spaces.values())
    root, response = load(client, headers, spaces["engineering"])
    with TestClient(app) as second:
        other, _, other_spaces = start(second)
        assert first["id"] != other["id"]
        assert {space["id"] for space in spaces.values()}.isdisjoint(
            {space["id"] for space in other_spaces.values()}
        )
        assert second.get(root + "/meetings/" + response["meeting_id"]).status_code == 404
        assert client.get("/api/workspaces/" + other_spaces["hr"]["id"] + "/meetings").status_code == 404
    assert client.get("/api/workspaces/" + seeded["workspace"].id + "/meetings").status_code == 404
    me = client.get("/api/me").json()
    assert me["is_visitor"] and me["capabilities"]["demo_mode"]
    assert me["capabilities"]["allowed_repos"] == []
    assert me["capabilities"]["ollama_model"] is None
    assert me["capabilities"]["embedding_provider"] == "hash"


def test_demo_start_requires_origin_and_never_replaces_signed_in_session(client):
    assert client.post("/api/demo/start").status_code == 403
    data, _, _ = start(client)
    assert client.post("/api/demo/start", headers={"Origin": settings.app_origin}).status_code == 409
    assert client.get("/api/me").json()["id"] == data["id"]


def test_fixture_loading_is_scoped_idempotent_and_custom_text_is_denied(client, session, monkeypatch):
    monkeypatch.setattr(settings, "public_demo_mode", False)
    user, headers, spaces = start(client)
    root, result = load(client, headers, spaces["engineering"])
    assert client.post(root + "/demo/load", json={"fixture_id": "hr"}, headers=headers).status_code == 404
    assert client.post(root + "/demo/load", json={"fixture_id": "engineering"}).status_code == 403
    repeated = client.post(root + "/demo/load", json={"fixture_id": "engineering"}, headers=headers)
    assert repeated.status_code == 202 and repeated.json()["job_id"] is None
    assert (
        client.post(
            root + "/index", json={"meeting_id": "real", "transcript": "Action: Real input"}, headers=headers
        ).status_code
        == 403
    )
    upload = client.post(
        root + "/upload",
        data={"meeting_id": "upload"},
        files={"file": ("meeting.txt", b"Action: Real input", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 403
    usage = session.get(VisitorUsage, user["id"])
    assert usage.jobs == 1
    assert (
        session.scalar(
            select(func.count())
            .select_from(Meeting)
            .where(Meeting.workspace_id == spaces["engineering"]["id"])
        )
        == 1
    )
    assert result["synthetic"]


def test_visitor_cannot_escape_through_workspace_or_member_admin(client, seeded):
    _, headers, spaces = start(client)
    root = "/api/workspaces/" + spaces["hr"]["id"]
    assert client.post("/api/workspaces", json={"name": "Escape"}, headers=headers).status_code == 403
    assert (
        client.post(
            root + "/members",
            json={
                "email": "person@example.test",
                "name": "Synthetic",
                "password": "synthetic-long-password",
                "role": "owner",
            },
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            root + "/members/" + seeded["user"].id, json={"role": "owner"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            root + "/participants", json={"name": "Custom person", "role": "New"}, headers=headers
        ).status_code
        == 403
    )


def test_visitor_token_and_password_access_are_denied(client, session, seeded, monkeypatch):
    data, _, spaces = start(client)
    session.add(
        ApiToken(
            token_hash=digest("synthetic-forged-visitor-token"),
            user_id=data["id"],
            workspace_id=spaces["engineering"]["id"],
            expires_at=now() + timedelta(days=1),
        )
    )
    session.commit()
    assert (
        client.get("/api/me", headers={"Authorization": "Bearer synthetic-forged-visitor-token"}).status_code
        == 401
    )
    # Even an accidental grant to a private workspace cannot change visitor scope.
    session.add(Membership(user_id=data["id"], workspace_id=seeded["workspace"].id, role="owner"))
    session.commit()
    assert client.get("/api/workspaces/" + seeded["workspace"].id + "/meetings").status_code == 404
    user = session.get(User, data["id"])
    user.password_hash = seeded["user"].password_hash
    session.commit()
    assert (
        client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "synthetic-test-password"},
            headers={"Origin": settings.app_origin},
        ).status_code
        == 401
    )


def test_visitor_expiry_invalidates_sessions_and_queued_jobs(client, session):
    data, headers, spaces = start(client)
    root, result = load(client, headers, spaces["engineering"])
    user = session.get(User, data["id"])
    user.visitor_expires_at = now() - timedelta(seconds=1)
    session.commit()
    assert client.get("/api/me").status_code == 401
    assert client.get(root + "/meetings").status_code == 401
    assert asyncio.run(run_once())
    session.expire_all()
    assert session.get(Job, result["job_id"]).state == "failed"
    assert (
        session.get(AuthSession, digest(client.cookies.get("mtt_session"))).expires_at
        > now().replace(tzinfo=None)
        if session.get(AuthSession, digest(client.cookies.get("mtt_session"))).expires_at.tzinfo is None
        else True
    )


def test_workspace_expiry_invalidates_work_and_removes_it_from_directory(client, session):
    _, headers, spaces = start(client)
    root, result = load(client, headers, spaces["engineering"])
    session.get(Workspace, spaces["engineering"]["id"]).demo_expires_at = now() - timedelta(seconds=1)
    session.commit()
    assert client.get(root + "/meetings").status_code == 404
    assert len(client.get("/api/workspaces").json()) == 2
    assert asyncio.run(run_once())
    session.expire_all()
    assert session.get(Job, result["job_id"]).state == "failed"


def test_mutation_and_job_budgets_are_bounded(client, session, monkeypatch):
    data, headers, spaces = start(client)
    root, result = load(client, headers, spaces["engineering"])
    usage = session.get(VisitorUsage, data["id"])
    usage.mutations = settings.visitor_mutation_limit
    session.commit()
    assert (
        client.post(root + "/meetings/" + result["meeting_id"] + "/extract", headers=headers).status_code
        == 429
    )
    usage.mutations = 0
    usage.jobs = settings.visitor_job_limit
    session.commit()
    assert (
        client.post(root + "/meetings/" + result["meeting_id"] + "/extract", headers=headers).status_code
        == 429
    )
    assert client.get(root + "/meetings/" + result["meeting_id"]).status_code == 200


def test_capacity_and_feature_gate_are_enforced(session, monkeypatch):
    monkeypatch.setattr(settings, "visitor_active_limit", 1)
    DemoService(session).start()
    session.commit()
    with pytest.raises(ServiceError) as full:
        DemoService(session).start()
    assert full.value.status_code == 429
    session.rollback()
    monkeypatch.setattr(settings, "visitor_demo_enabled", False)
    with pytest.raises(ServiceError) as disabled:
        DemoService(session).start()
    assert disabled.value.status_code == 403


def test_demo_workers_use_hash_and_rules_with_private_ai_configured(client, session, monkeypatch):
    _, headers, spaces = start(client)
    root, result = load(client, headers, spaces["engineering"])
    monkeypatch.setattr(settings, "embed_provider", "sentence-transformers")
    monkeypatch.setattr(settings, "ollama_model", "synthetic-private-model")

    async def forbidden_model(*args):
        raise AssertionError("Visitor work must not run model inference")

    monkeypatch.setattr("app.services.extraction.extract_tasks_ollama", forbidden_model)
    assert asyncio.run(run_once())
    extraction = client.post(root + "/meetings/" + result["meeting_id"] + "/extract", headers=headers)
    assert extraction.status_code == 202
    assert asyncio.run(run_once())
    session.expire_all()
    meeting = client.get(root + "/meetings/" + result["meeting_id"]).json()
    assert meeting["index_status"] == "ready" and meeting["embedding_provider"] == "hash"
    assert meeting["tasks"]
    job = session.get(Job, extraction.json()["job_id"])
    assert job.state == "completed" and job.result["mode"] == "rules"
    assert "synthetic_demo_rules" in job.result["coverage"]["warnings"]


def test_no_outcomes_is_a_useful_completed_demo_result(client, session):
    _, headers, spaces = start(client)
    root, result = load(client, headers, spaces["finance"], "no-outcomes")
    assert asyncio.run(run_once())
    extract = client.post(root + "/meetings/" + result["meeting_id"] + "/extract", headers=headers)
    assert extract.status_code == 202 and asyncio.run(run_once())
    assert client.get(root + "/meetings/" + result["meeting_id"]).json()["tasks"] == []
    assert session.get(Job, extract.json()["job_id"]).result["created"] == 0


def test_provider_jobs_are_denied_independently_of_global_demo_flag(client, session, monkeypatch):
    data, headers, spaces = start(client)
    _, result = load(client, headers, spaces["engineering"])
    monkeypatch.setattr(settings, "public_demo_mode", False)
    meeting = session.scalar(select(Meeting).where(Meeting.workspace_id == spaces["engineering"]["id"]))
    for kind in ("publish", "jira_publish", "slack_publish", "linkedin_publish"):
        job = Job(
            kind=kind,
            workspace_id=meeting.workspace_id,
            actor_id=data["id"],
            meeting_id=meeting.id,
            payload={},
        )
        with pytest.raises(ServiceError) as forbidden:
            authorized(session, job)
        assert forbidden.value.status_code == 403


def test_concurrent_admission_never_exceeds_capacity(engine, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("Admission row locks require PostgreSQL")
    monkeypatch.setattr(settings, "visitor_active_limit", 1)

    def attempt(_):
        with Session(engine) as session:
            try:
                DemoService(session).start()
                session.commit()
                return "admitted"
            except ServiceError as exc:
                session.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results, key=str) == [429, "admitted"]
