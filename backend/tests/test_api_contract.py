import asyncio
from datetime import timedelta

import pytest

from app.auth import Principal, digest, hasher
from app.models import ApiToken, Membership, User, now
from app.schemas import IndexInput
from app.services.meetings import MeetingService
from app.worker import run_once


def root(seeded):
    return "/api/workspaces/" + seeded["workspace"].id


def test_authentication_and_workspace_isolation(client, seeded, auth):
    assert client.get(root(seeded) + "/meetings").status_code == 401
    assert client.get(root(seeded) + "/meetings", headers=auth).status_code == 200
    assert (
        client.get("/api/workspaces/" + seeded["isolated"].id + "/meetings", headers=auth).status_code == 404
    )
    assert len(client.get("/api/workspaces", headers=auth).json()) == 1


def test_summary_aggregation_respects_restricted_access(client, session, seeded, auth):
    session.add(Membership(user_id=seeded["other"].id, workspace_id=seeded["workspace"].id, role="editor"))
    session.commit()
    service = MeetingService(session, seeded["principal"])
    service.index(IndexInput(meeting_id="public", transcript="Action: Review public synthetic controls."))
    other = Principal(seeded["other"].id, seeded["workspace"].id, "editor")
    private = MeetingService(session, other)
    private.index(
        IndexInput(
            meeting_id="private",
            visibility="restricted",
            transcript="Action: Review restricted controls.\nBlocker: Restricted access pending.",
        )
    )
    session.commit()
    while asyncio.run(run_once()):
        pass
    service.enqueue_extraction("public")
    private.enqueue_extraction("private")
    session.commit()
    while asyncio.run(run_once()):
        pass
    session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "viewer"
    session.commit()
    response = client.get(root(seeded) + "/summary", headers=auth)
    assert response.status_code == 200
    assert response.json()["counts"] == {"action": 1, "decision": 0, "blocker": 0, "follow_up": 0, "risk": 0}
    assert response.json()["review_pending"] == 1
    assert client.get(root(seeded) + "/meetings/private", headers=auth).status_code == 404


def test_session_login_csrf_and_logout(client, seeded):
    headers = {"Origin": "http://localhost:5173"}
    response = client.post(
        "/api/auth/login",
        headers=headers,
        json={"email": seeded["user"].email, "password": "synthetic-test-password"},
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers.get_list("set-cookie")[0]
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/workspaces", json={"name": "No CSRF"}).status_code == 403
    valid = {**headers, "X-CSRF-Token": response.json()["csrf_token"]}
    assert (
        client.post(
            "/api/workspaces",
            headers={**valid, "Origin": "https://evil.example"},
            json={"name": "Wrong origin"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/workspaces", headers=valid, json={"name": "New workspace", "department": "finance"}
        ).status_code
        == 201
    )
    assert client.post("/api/auth/logout", headers=valid).status_code == 200
    assert client.get("/api/me").status_code == 401


def test_login_throttles_failed_passwords(client):
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login",
                headers={"Origin": "http://localhost:5173"},
                json={"email": "absent@example.test", "password": "bad"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "http://localhost:5173"},
            json={"email": "absent@example.test", "password": "bad"},
        ).status_code
        == 429
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"meeting_id": "../bad", "transcript": "Action: test"},
        {"meeting_id": "valid", "transcript": "", "title": "Empty"},
        {"meeting_id": "valid", "transcript": "Action: test", "extra": True},
        {"meeting_id": "valid", "transcript": "Action: test", "timezone": "Invalid/Zone"},
    ],
)
def test_index_strict_validation(client, seeded, auth, payload):
    response = client.post(root(seeded) + "/index", headers=auth, json=payload)
    assert response.status_code == 422
    assert "traceback" not in response.text.lower() and "input" not in response.text


def test_complete_rest_journey(client, seeded, auth):
    response = client.post(
        root(seeded) + "/index",
        headers=auth,
        json={
            "meeting_id": "api-demo",
            "title": "Synthetic demo",
            "transcript": "Alex: Action: I will review the API by Friday.\nDecision: Keep review history.",
        },
    )
    assert response.status_code == 202
    assert asyncio.run(run_once())
    extract = client.post(root(seeded) + "/meetings/api-demo/extract", headers=auth)
    assert extract.status_code == 202
    assert asyncio.run(run_once())
    job = client.get(root(seeded) + "/jobs/" + extract.json()["job_id"], headers=auth).json()
    assert job["state"] == "completed" and job["result"]["coverage"]["full_transcript"]
    meeting = client.get(root(seeded) + "/meetings/api-demo", headers=auth).json()
    assert len(meeting["tasks"]) == 2
    item = meeting["tasks"][0]
    assert (
        client.patch(
            root(seeded) + "/meetings/api-demo/outcomes/" + item["id"],
            headers=auth,
            json={"expected_version": 1, "status": "approved"},
        ).status_code
        == 200
    )
    preview = client.post(
        root(seeded) + "/meetings/api-demo/preview",
        headers=auth,
        json={"repo": "synthetic/demo", "task_ids": [item["id"]]},
    )
    assert preview.status_code == 200 and "meeting-to-tasks:" in preview.json()["would_create"][0]["body"]
    assert (
        client.post(
            root(seeded) + "/proposals/" + preview.json()["id"] + "/approve",
            headers=auth,
            json={"payload_hash": preview.json()["payload_hash"]},
        ).status_code
        == 403
    )
    assert client.get(root(seeded) + "/summary", headers=auth).json()["counts"]["action"] == 1


def test_upload_bounds_and_validation(client, seeded, auth):
    for name, content, status in (
        ("bad.pdf", b"x", 400),
        ("bad.txt", b"\xff", 400),
        ("big.txt", b"x" * 1000001, 413),
    ):
        response = client.post(
            root(seeded) + "/upload",
            headers=auth,
            data={"meeting_id": "upload"},
            files={"file": (name, content)},
        )
        assert response.status_code == status
    response = client.post(
        root(seeded) + "/upload",
        headers=auth,
        data={"meeting_id": "../bad"},
        files={"file": ("good.txt", b"Action: test")},
    )
    assert response.status_code == 422


def test_viewer_cannot_write_and_cannot_read_restricted_meeting(client, session, seeded, auth):
    assert (
        client.post(
            root(seeded) + "/index",
            headers=auth,
            json={
                "meeting_id": "private",
                "transcript": "Action: Synthetic HR check",
                "visibility": "restricted",
            },
        ).status_code
        == 202
    )
    viewer = User(
        email="viewer@example.test", name="Viewer", password_hash=hasher.hash("synthetic-test-password")
    )
    session.add(viewer)
    session.flush()
    session.add(Membership(user_id=viewer.id, workspace_id=seeded["workspace"].id, role="viewer"))
    session.add(
        ApiToken(
            token_hash=digest("viewer-token"),
            user_id=viewer.id,
            workspace_id=seeded["workspace"].id,
            expires_at=now() + timedelta(days=1),
        )
    )
    session.commit()
    viewer_auth = {"Authorization": "Bearer viewer-token"}
    assert client.get(root(seeded) + "/meetings/private", headers=viewer_auth).status_code == 404
    assert client.get(root(seeded) + "/meetings", headers=viewer_auth).json()["meetings"] == []
    assert (
        client.post(
            root(seeded) + "/index",
            headers=viewer_auth,
            json={"meeting_id": "bad", "transcript": "Action: No"},
        ).status_code
        == 403
    )
    assert client.get(root(seeded) + "/members", headers=viewer_auth).status_code == 403


def test_last_owner_and_cross_scope_token(client, seeded, auth):
    assert (
        client.patch(
            root(seeded) + "/members/" + seeded["user"].id, headers=auth, json={"role": "viewer"}
        ).status_code
        == 409
    )
    assert client.post("/api/workspaces", headers=auth, json={"name": "Outside scope"}).status_code == 403


def test_safe_database_error(client, seeded, auth, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.services.meetings import MeetingService

    def broken(*args, **kwargs):
        raise OperationalError("private sql", {"secret": "do-not-leak"}, Exception("sensitive-stack"))

    monkeypatch.setattr(MeetingService, "list", broken)
    response = client.get(root(seeded) + "/meetings", headers=auth)
    assert response.status_code == 503
    assert "do-not-leak" not in response.text and "sensitive-stack" not in response.text
    assert response.headers["X-Request-ID"]
