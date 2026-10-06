import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic, sleep
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import Principal, digest
from app.models import AuthSession, Invitation, Job, Membership, PasswordRecovery, User, now
from app.schemas import IndexInput, InvitationAcceptInput, InvitationInput, RecoveryInput
from app.services.errors import ServiceError
from app.services.lifecycle import InvitationService, RecoveryService
from app.services.meetings import MeetingService
from app.settings import settings
from app.worker import run_once

PASSWORD = "synthetic-test-password"
NEW_PASSWORD = "synthetic-new-test-password"


def token_from_link(link):
    parsed = urlsplit(link)
    assert not parsed.query and parsed.fragment.startswith("token=")
    return parsed.fragment.removeprefix("token=")


def login(client, email="owner@example.test", password=PASSWORD):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": settings.app_origin},
    )
    assert response.status_code == 200, response.json()
    return {"Origin": settings.app_origin, "X-CSRF-Token": response.json()["csrf_token"]}


def issue(session, seeded, email="invitee@example.test", role="editor"):
    result = InvitationService(session).issue(seeded["principal"], InvitationInput(email=email, role=role))
    session.commit()
    return result, token_from_link(result["accept_url"])


def test_new_recipient_accepts_role_and_chooses_own_password(client, session, seeded):
    headers = login(client)
    root = "/api/workspaces/" + seeded["workspace"].id
    result = client.post(
        root + "/invitations", json={"email": "invitee@example.test", "role": "reviewer"}, headers=headers
    )
    assert result.status_code == 201 and result.headers["cache-control"] == "no-store"
    token = token_from_link(result.json()["accept_url"])
    assert session.scalar(select(Invitation)).token_hash == digest(token)
    client.post("/api/auth/logout", headers=headers)
    inspect = client.post(
        "/api/invitations/inspect", json={"token": token}, headers={"Origin": settings.app_origin}
    )
    assert inspect.status_code == 200 and not inspect.json()["requires_sign_in"]
    accept = client.post(
        "/api/invitations/accept",
        json={
            "token": token,
            "email": "invitee@example.test",
            "name": "Synthetic Invitee",
            "password": NEW_PASSWORD,
        },
        headers={"Origin": settings.app_origin},
    )
    assert accept.status_code == 200 and accept.json()["sign_in_required"]
    assert client.get("/api/me").status_code == 401
    login(client, "invitee@example.test", NEW_PASSWORD)
    assert client.get("/api/workspaces").json()[0]["role"] == "reviewer"
    assert (
        client.post(
            "/api/invitations/accept",
            json={"token": token, "email": "invitee@example.test"},
            headers=login(client, "invitee@example.test", NEW_PASSWORD),
        ).status_code
        == 400
    )


def test_existing_recipient_requires_current_browser_and_password_is_preserved(client, session, seeded):
    result, token = issue(session, seeded, seeded["other"].email, "viewer")
    original_hash = seeded["other"].password_hash
    body = {"token": token, "email": seeded["other"].email}
    assert (
        client.post("/api/invitations/accept", json=body, headers={"Origin": settings.app_origin}).status_code
        == 403
    )
    wrong = login(client)
    assert client.post("/api/invitations/accept", json=body, headers=wrong).status_code == 403
    correct = login(client, seeded["other"].email)
    assert (
        client.post(
            "/api/invitations/accept", json={**body, "password": NEW_PASSWORD}, headers=correct
        ).status_code
        == 400
    )
    assert client.post("/api/invitations/accept", json=body, headers=correct).status_code == 200
    session.expire_all()
    assert session.get(User, seeded["other"].id).password_hash == original_hash
    assert session.get(Membership, (seeded["workspace"].id, seeded["other"].id)).role == "viewer"


@pytest.mark.parametrize("state", ["expired", "revoked", "issuer_demoted", "issuer_inactive"])
def test_invitation_rejects_expiry_revocation_or_issuer_authority_change(session, seeded, state):
    result, token = issue(session, seeded)
    row = session.get(Invitation, result["id"])
    if state == "expired":
        row.expires_at = now() - timedelta(seconds=1)
    if state == "revoked":
        row.revoked_at = now()
    if state == "issuer_demoted":
        session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "editor"
    if state == "issuer_inactive":
        seeded["user"].active = False
    session.commit()
    with pytest.raises(ServiceError) as rejected:
        InvitationService(session).accept(
            InvitationAcceptInput(
                token=token, email="invitee@example.test", name="Synthetic", password=NEW_PASSWORD
            ),
            None,
        )
    assert rejected.value.status_code == 400
    assert session.scalar(select(User).where(User.email == "invitee@example.test")) is None


def test_invitation_revoke_and_legacy_membership_bypass(client, session, seeded):
    headers = login(client)
    root = "/api/workspaces/" + seeded["workspace"].id
    issued = client.post(
        root + "/invitations", json={"email": "invitee@example.test"}, headers=headers
    ).json()
    assert "accept_url" not in client.get(root + "/invitations").json()["invitations"][0]
    assert client.delete(root + "/invitations/" + issued["id"], headers=headers).status_code == 200
    assert (
        client.post(
            root + "/members",
            json={
                "email": "bypass@example.test",
                "name": "Bypass",
                "password": NEW_PASSWORD,
                "role": "owner",
            },
            headers=headers,
        ).status_code
        == 409
    )
    assert session.scalar(select(User).where(User.email == "bypass@example.test")) is None


def test_recovery_revokes_sessions_tokens_and_prior_jobs_and_allows_new_authority(client, session, seeded):
    login(client)
    MeetingService(session, seeded["principal"]).index(
        IndexInput(meeting_id="reset-job", transcript="Action: Synthetic task")
    )
    link = RecoveryService(session).issue_for_operator(seeded["user"].email)
    session.commit()
    token = token_from_link(link)
    response = client.post(
        "/api/auth/recovery/reset",
        json={"token": token, "email": seeded["user"].email, "password": NEW_PASSWORD},
        headers={"Origin": settings.app_origin},
    )
    assert response.status_code == 200 and response.json()["sessions_revoked"]
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer " + seeded["token"]}).status_code == 401
    session.expire_all()
    assert session.scalar(select(Job).where(Job.actor_id == seeded["user"].id)).state == "cancelled"
    assert (
        client.post(
            "/api/auth/login",
            json={"email": seeded["user"].email, "password": PASSWORD},
            headers={"Origin": settings.app_origin},
        ).status_code
        == 401
    )
    login(client, seeded["user"].email, NEW_PASSWORD)
    principal = Principal(seeded["user"].id, seeded["workspace"].id, "owner")
    MeetingService(session, principal).index(
        IndexInput(meeting_id="new-job", transcript="Action: New synthetic task")
    )
    session.commit()
    assert asyncio.run(run_once())
    session.expire_all()
    assert session.scalar(select(Job).where(Job.state == "completed")).actor_auth_version == 2
    assert (
        client.post(
            "/api/auth/recovery/reset",
            json={"token": token, "email": seeded["user"].email, "password": PASSWORD},
            headers={"Origin": settings.app_origin},
        ).status_code
        == 400
    )


def test_recovery_neutral_response_wrong_identity_expiry_and_no_public_issuance(client, session, seeded):
    one = client.post(
        "/api/auth/recovery/request",
        json={"email": seeded["user"].email},
        headers={"Origin": settings.app_origin},
    )
    two = client.post(
        "/api/auth/recovery/request",
        json={"email": "missing@example.test"},
        headers={"Origin": settings.app_origin},
    )
    assert one.json() == two.json() and one.status_code == two.status_code == 202
    assert session.scalar(select(PasswordRecovery)) is None
    token = token_from_link(RecoveryService(session).issue_for_operator(seeded["user"].email))
    session.commit()
    with pytest.raises(ServiceError, match="invalid"):
        RecoveryService(session).reset(
            RecoveryInput(token=token, email="wrong@example.test", password=NEW_PASSWORD)
        )
    session.rollback()
    session.get(PasswordRecovery, digest(token)).expires_at = now() - timedelta(seconds=1)
    session.commit()
    with pytest.raises(ServiceError, match="expired"):
        RecoveryService(session).reset(
            RecoveryInput(token=token, email=seeded["user"].email, password=NEW_PASSWORD)
        )


def test_recovery_private_file_writer_never_prints_link(tmp_path, capsys):
    from scripts.issue_recovery import save_private_link

    link = "https://example.test/recover#token=" + "a" * 43
    path = save_private_link(tmp_path / ".runtime", link)
    assert path.read_text(encoding="utf-8").strip() == link
    assert capsys.readouterr().out == ""


def test_concurrent_invitation_acceptance_is_single_use(engine, session, seeded):
    if engine.dialect.name != "postgresql":
        pytest.skip("Row locks require PostgreSQL")
    _, token = issue(session, seeded)

    def attempt(_):
        with Session(engine) as candidate:
            try:
                value = InvitationService(candidate).accept(
                    InvitationAcceptInput(
                        token=token, email="invitee@example.test", name="Synthetic", password=NEW_PASSWORD
                    ),
                    None,
                )
                candidate.commit()
                return value["ok"]
            except ServiceError as exc:
                candidate.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results, key=str) == [400, True]
    session.expire_all()
    invitee = session.scalar(select(User).where(User.email == "invitee@example.test"))
    assert session.get(Membership, (seeded["workspace"].id, invitee.id)) is not None


def test_reset_while_existing_invitee_waits_invalidates_acceptance(engine, session, seeded):
    if engine.dialect.name != "postgresql":
        pytest.skip("Forced authority lock overlap requires PostgreSQL")
    _, token = issue(session, seeded, seeded["other"].email)
    browser_token = "synthetic-invite-browser"
    session.add(
        AuthSession(
            token_hash=digest(browser_token),
            user_id=seeded["other"].id,
            csrf_hash="a" * 64,
            expires_at=now() + timedelta(hours=1),
        )
    )
    recovery = token_from_link(RecoveryService(session).issue_for_operator(seeded["other"].email))
    session.commit()
    waiting = Event()
    accepting_pids = []
    principal = Principal(seeded["other"].id, session_hash=digest(browser_token), auth_version=1)
    with Session(engine) as resetting:
        resetting.scalar(select(User).where(User.id == seeded["other"].id).with_for_update())

        def accept():
            with Session(engine) as accepting:
                accepting.execute(text("SET LOCAL lock_timeout = '5000ms'"))
                accepting_pids.append(accepting.execute(text("SELECT pg_backend_pid()")).scalar_one())
                waiting.set()
                try:
                    InvitationService(accepting).accept(
                        InvitationAcceptInput(token=token, email=seeded["other"].email), principal
                    )
                    accepting.commit()
                    return "accepted"
                except ServiceError as exc:
                    accepting.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(accept)
            assert waiting.wait(2)
            deadline = monotonic() + 2
            while not resetting.execute(
                text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": accepting_pids[0]}
            ).scalar_one():
                assert monotonic() < deadline, "Acceptance did not block on the recipient authority row"
                sleep(0.02)
            RecoveryService(resetting).reset(
                RecoveryInput(token=recovery, email=seeded["other"].email, password=NEW_PASSWORD)
            )
            resetting.commit()
            assert future.result(timeout=8) == 403
    session.expire_all()
    assert session.get(Membership, (seeded["workspace"].id, seeded["other"].id)) is None


def test_reset_revokes_old_owner_invitations_but_allows_new_generation(session, seeded):
    _, old_token = issue(session, seeded)
    reset_token = token_from_link(RecoveryService(session).issue_for_operator(seeded["user"].email))
    session.commit()
    RecoveryService(session).reset(
        RecoveryInput(token=reset_token, email=seeded["user"].email, password=NEW_PASSWORD)
    )
    session.commit()
    with pytest.raises(ServiceError, match="unavailable"):
        InvitationService(session).inspect(old_token)
    session.rollback()
    new = InvitationService(session).issue(
        seeded["principal"], InvitationInput(email="new-recipient@example.test")
    )
    session.commit()
    assert (
        InvitationService(session).inspect(token_from_link(new["accept_url"]))["email"]
        == "new-recipient@example.test"
    )
