"""Independent HTTP acceptance checks for the integrated visitor boundary."""

import asyncio
import json
from datetime import date, timedelta
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Job, Membership, User, Workspace, now
from app.services.lifecycle import RecoveryService
from app.settings import settings
from app.worker import run_once


def start(browser):
    response = browser.post("/api/demo/start", headers={"Origin": settings.app_origin})
    assert response.status_code == 201, response.text
    identity = response.json()
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": identity["csrf_token"]}
    workspaces = browser.get("/api/workspaces").json()
    assert {row["department"] for row in workspaces} == {"engineering", "hr", "finance"}
    assert all(row["is_demo"] and row["expires_at"] for row in workspaces)
    return identity, headers, workspaces


def test_two_visitors_are_isolated_from_each_other_and_private_accounts(engine, seeded, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    with TestClient(app) as first, TestClient(app) as second:
        first_user, first_headers, first_spaces = start(first)
        second_user, second_headers, second_spaces = start(second)
        assert first_user["id"] != second_user["id"]
        assert not {row["id"] for row in first_spaces} & {row["id"] for row in second_spaces}
        first_scope = "/api/workspaces/" + first_spaces[0]["id"]
        second_scope = "/api/workspaces/" + second_spaces[0]["id"]
        loaded = first.post(
            first_scope + "/demo/load",
            json={"fixture_id": first_spaces[0]["department"]},
            headers=first_headers,
        )
        assert loaded.status_code == 202, loaded.text
        assert second.get(first_scope + "/meetings").status_code == 404
        assert first.get(second_scope + "/participants").status_code == 404
        assert first.get("/api/workspaces/" + seeded["workspace"].id + "/meetings").status_code == 404
        assert (
            second.post(
                first_scope + "/demo/load", json={"fixture_id": "hr"}, headers=second_headers
            ).status_code
            == 404
        )


def test_visitor_cannot_upload_real_text_or_create_private_workspaces(engine, seeded, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "public_demo_mode", False)
    monkeypatch.setattr(settings, "github_allowed_repos", "operator/private-repository")
    with TestClient(app) as browser:
        _, headers, spaces = start(browser)
        scope = "/api/workspaces/" + spaces[0]["id"]
        identity = browser.get("/api/me")
        assert identity.headers["cache-control"] == "no-store"
        capabilities = identity.json()["capabilities"]
        assert capabilities["demo_mode"] is True
        assert capabilities["allowed_repos"] == []
        assert capabilities["can_upload_transcript"] is False
        assert (
            browser.post(
                scope + "/index",
                json={
                    "meeting_id": "private-input",
                    "title": "Unauthorized text",
                    "transcript": "Synthetic adversarial input outside the approved fixtures.",
                },
                headers=headers,
            ).status_code
            == 403
        )
        assert (
            browser.post(
                "/api/workspaces",
                json={"name": "Unauthorized workspace", "department": "engineering"},
                headers=headers,
            ).status_code
            == 403
        )


def test_expired_visitor_session_and_queued_job_lose_authority(engine, seeded, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    with TestClient(app) as browser:
        identity, headers, spaces = start(browser)
        scope = "/api/workspaces/" + spaces[0]["id"]
        loaded = browser.post(
            scope + "/demo/load", json={"fixture_id": spaces[0]["department"]}, headers=headers
        )
        assert loaded.status_code == 202, loaded.text
        job_id = loaded.json()["job_id"]
        with Session(engine) as session:
            visitor = session.get(User, identity["id"])
            visitor.visitor_expires_at = now() - timedelta(seconds=1)
            session.commit()
        assert browser.get("/api/me").status_code == 401
        assert browser.get(scope + "/meetings").status_code == 401
        asyncio.run(run_once())
        with Session(engine) as session:
            job = session.scalar(select(Job).where(Job.id == job_id))
            assert job.state == "failed"
            assert job.result is None


def test_demo_review_plan_and_exact_export_work_without_provider_access(engine, seeded, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    with TestClient(app) as browser:
        _, headers, spaces = start(browser)
        workspace = next(row for row in spaces if row["department"] == "engineering")
        scope = "/api/workspaces/" + workspace["id"]
        loaded = browser.post(scope + "/demo/load", json={"fixture_id": "engineering"}, headers=headers)
        assert loaded.status_code == 202, loaded.text
        meeting_path = scope + "/meetings/" + loaded.json()["meeting_id"]
        asyncio.run(run_once())
        assert browser.post(meeting_path + "/extract", headers=headers).status_code == 202
        asyncio.run(run_once())
        meeting = browser.get(meeting_path).json()
        action = next(item for item in meeting["tasks"] if item["kind"] == "action")
        item_path = meeting_path + "/outcomes/" + action["id"]
        approval = browser.patch(
            item_path, json={"expected_version": action["version"], "status": "approved"}, headers=headers
        )
        assert approval.status_code == 200, approval.text
        version = approval.json()["version"]
        plan_input = {"expected_item_version": version, "planned_on": date.today().isoformat(), "priority": 1}
        planned = browser.post(item_path + "/plan", json=plan_input, headers=headers)
        assert planned.status_code == 201, planned.text
        completed = browser.patch(
            item_path + "/plan",
            json={**plan_input, "expected_version": planned.json()["version"], "state": "done"},
            headers=headers,
        )
        assert completed.status_code == 200, completed.text
        current = next(
            item for item in browser.get(meeting_path).json()["tasks"] if item["id"] == action["id"]
        )
        assert current["status"] == "approved" and current["version"] == version
        payload = {"format": "json", "expected_revision": 1, "versions": {action["id"]: version}}
        exported = browser.post(meeting_path + "/export", json=payload, headers=headers)
        assert exported.status_code == 200, exported.text
        bundle = json.loads(exported.json()["content"])
        assert bundle["outcomes"][0]["status"] == "approved"
        stale = browser.post(
            meeting_path + "/export",
            json={**payload, "versions": {action["id"]: version - 1}},
            headers=headers,
        )
        assert stale.status_code == 409


def test_scoped_token_cannot_inspect_or_erase_another_owned_workspace(client, session, seeded, auth):
    other = Workspace(name="Another owned private workspace", department="finance")
    session.add(other)
    session.flush()
    session.add(Membership(workspace_id=other.id, user_id=seeded["user"].id, role="owner"))
    session.commit()
    scope = "/api/workspaces/" + other.id
    assert client.get(scope + "/privacy", headers=auth).status_code == 404
    response = client.post(
        scope + "/privacy/erase",
        json={
            "confirmation_name": other.name,
            "expected_version": other.version,
            "password": "synthetic-test-password",
        },
        headers=auth,
    )
    assert response.status_code == 404
    session.refresh(other)
    assert other.erasure_requested_at is None and other.erased_at is None


def private_login(browser, email, password):
    response = browser.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": settings.app_origin},
    )
    assert response.status_code == 200, response.text
    return {"Origin": settings.app_origin, "X-CSRF-Token": response.json()["csrf_token"]}


def test_invited_private_user_recovers_exports_and_erases_without_affecting_owner(
    engine, session, seeded, monkeypatch
):
    monkeypatch.setattr(settings, "cookie_secure", False)
    scope = "/api/workspaces/" + seeded["workspace"].id
    email, password = "recipient@acceptance.example.test", "synthetic-invited-password"
    with TestClient(app) as owner, TestClient(app) as recipient, TestClient(app) as recovery:
        owner_headers = private_login(owner, seeded["user"].email, "synthetic-test-password")
        invitation = owner.post(
            scope + "/invitations", json={"email": email, "role": "editor"}, headers=owner_headers
        )
        assert invitation.status_code == 201
        token = urlsplit(invitation.json()["accept_url"]).fragment.removeprefix("token=")
        accepted = recipient.post(
            "/api/invitations/accept",
            json={"token": token, "email": email, "name": "Synthetic Recipient", "password": password},
            headers={"Origin": settings.app_origin},
        )
        assert accepted.status_code == 200 and accepted.json()["account_created"]
        assert recipient.get("/api/me").status_code == 401
        private_login(recipient, email, password)
        assert {row["id"] for row in recipient.get("/api/workspaces").json()} == {seeded["workspace"].id}
        exported = recipient.get("/api/privacy/account/export")
        assert exported.status_code == 200 and exported.headers["cache-control"] == "no-store"
        assert exported.json()["account"]["email"] == email
        assert "password_hash" not in exported.text and "encrypted_credentials" not in exported.text
        assert recipient.get(scope + "/privacy/export").status_code == 403
        link = RecoveryService(session).issue_for_operator(email)
        session.commit()
        recovery_token = urlsplit(link).fragment.removeprefix("token=")
        new_password = "synthetic-recovered-password"
        payload = {"token": recovery_token, "email": email, "password": new_password}
        reset = recovery.post(
            "/api/auth/recovery/reset", json=payload, headers={"Origin": settings.app_origin}
        )
        assert reset.status_code == 200 and reset.json()["sign_in_required"]
        assert recipient.get("/api/me").status_code == 401
        assert (
            recovery.post(
                "/api/auth/recovery/reset", json=payload, headers={"Origin": settings.app_origin}
            ).status_code
            == 400
        )
        new_headers = private_login(recipient, email, new_password)
        erased = recipient.post(
            "/api/privacy/account/erase",
            json={"password": new_password, "confirmation": "DELETE MY ACCOUNT"},
            headers=new_headers,
        )
        assert erased.status_code == 200 and erased.json()["state"] == "deactivated_and_anonymized"
        assert recipient.get("/api/me").status_code == 401
        assert owner.get(scope + "/members").status_code == 200
        assert owner.get("/api/me").status_code == 200


def test_private_workspace_export_and_erasure_preserve_other_workspace(client, session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    headers = private_login(client, seeded["user"].email, "synthetic-test-password")
    scope = "/api/workspaces/" + seeded["workspace"].id
    indexed = client.post(
        scope + "/index",
        json={
            "meeting_id": "private-acceptance",
            "title": "Synthetic private meeting",
            "transcript": "Action: Review the synthetic onboarding checklist.",
        },
        headers=headers,
    )
    assert indexed.status_code == 202
    asyncio.run(run_once())
    assert client.post(scope + "/meetings/private-acceptance/extract", headers=headers).status_code == 202
    asyncio.run(run_once())
    exported = client.get(scope + "/privacy/export")
    assert exported.status_code == 200 and exported.headers["cache-control"] == "no-store"
    assert (
        exported.json()["meetings"][0]["revisions"][0]["raw_text"]
        == "Action: Review the synthetic onboarding checklist."
    )
    status = client.get(scope + "/privacy").json()
    erased = client.post(
        scope + "/privacy/erase",
        json={
            "password": "synthetic-test-password",
            "confirmation_name": status["name"],
            "expected_version": status["version"],
        },
        headers=headers,
    )
    assert erased.status_code == 200 and erased.json()["state"] == "erased"
    assert erased.json()["remote_content_erased"] is False
    assert client.get(scope + "/meetings").status_code == 404
    session.expire_all()
    assert session.get(Workspace, seeded["isolated"].id).erased_at is None
    assert session.get(User, seeded["other"].id).active
