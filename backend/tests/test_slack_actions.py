import asyncio
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier, Event
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_meeting_lifecycle import extracted
from test_slack import APP, TEAM, USER, connected, transport
from test_slack import slack as slack

from app.auth import Principal, digest
from app.models import (
    AuditEvent,
    AuthSession,
    Meeting,
    Membership,
    PlanEntry,
    ProviderConnection,
    SlackAccount,
    SlackIdentity,
    SlackInteractionContext,
    User,
    WorkItem,
    now,
)
from app.schemas import ItemPatch, PlanInput, PlanPatch
from app.services.errors import ServiceError
from app.services.planning import PlanningService
from app.services.review import ReviewService
from app.settings import settings
from app.slack import SlackAdapter, connection_status
from app.slack_actions import SlackActions, verify_request


def signed(body, timestamp=None):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    signature = (
        "v0="
        + hmac.new(
            b"synthetic-signing-secret", b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }


def command(text):
    return {
        "api_app_id": APP,
        "team_id": TEAM,
        "user_id": USER,
        "command": "/m2o",
        "text": text,
        "trigger_id": "synthetic-trigger",
        "response_url": "https://untrusted.example.test/must-not-be-requested",
    }


def submit(view, values, *, user=USER):
    return {
        "type": "view_submission",
        "api_app_id": APP,
        "team": {"id": TEAM},
        "user": {"id": user},
        "view": {**view, "state": {"values": {key: {"value": value} for key, value in values.items()}}},
    }


def receive(actions, payload, *, interactive=False, timestamp=None):
    raw = urlencode({"payload": json.dumps(payload)} if interactive else payload).encode()
    headers = signed(raw, timestamp)
    request_hash = verify_request(raw, [headers["X-Slack-Request-Timestamp"]], [headers["X-Slack-Signature"]])
    return asyncio.run(actions.receive(raw, request_hash, interactive=interactive))


@pytest.fixture
def actions(session, slack, monkeypatch):
    monkeypatch.setattr(settings, "slack_interactions_enabled", True)
    monkeypatch.setattr(settings, "slack_app_id", APP)
    monkeypatch.setattr(settings, "slack_signing_secret", SecretStr("synthetic-signing-secret"))
    connected(session, slack, [])
    opened = []

    def respond(request):
        assert request.url == "https://slack.com/api/views.open"
        assert request.headers["authorization"] == "Bearer synthetic-access"
        opened.append(json.loads(request.content)["view"])
        return httpx.Response(200, json={"ok": True, "view": {"id": "synthetic-view"}})

    service = SlackActions(session, httpx.MockTransport(respond))
    connection = session.scalar(select(ProviderConnection))
    challenge = service.begin_link(slack, connection.id)
    session.commit()
    response = receive(service, command(challenge["command"].removeprefix("/m2o ")))
    assert "No account link is active" in response["text"]
    assert session.scalar(select(SlackIdentity)) is None
    service.confirm_link(slack, challenge["challenge_id"], USER)
    session.commit()
    return service, opened, connection


def approved(session, seeded):
    item = extracted(session, seeded)["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    session.commit()
    return session.get(WorkItem, item["id"])


def plan_values(item, state="done"):
    return {
        "item": {"selected_option": {"value": item.id}},
        "state": {"selected_option": {"value": state}},
        "day": {"selected_date": date.today().isoformat()},
        "priority": {"selected_option": {"value": "2"}},
    }


def test_raw_signature_window_header_duplicates_and_gate(actions, monkeypatch):
    raw = urlencode(command("help")).encode()
    headers = signed(raw)
    signature, timestamp = headers["X-Slack-Signature"], headers["X-Slack-Request-Timestamp"]
    assert len(verify_request(raw, [timestamp], [signature])) == 64
    for body, times, signatures in [
        (raw + b"x", [timestamp], [signature]),
        (raw, [timestamp, timestamp], [signature]),
        (raw, [timestamp], [signature, signature]),
        (raw, [str(int(timestamp) - 301)], [signature]),
    ]:
        with pytest.raises(ServiceError):
            verify_request(body, times, signatures)
    with pytest.raises(ServiceError) as error:
        verify_request(b"a" * 65537, [timestamp], [signature])
    assert error.value.status_code == 413
    monkeypatch.setattr(settings, "public_demo_mode", True)
    with pytest.raises(ServiceError) as error:
        verify_request(raw, [timestamp], [signature])
    assert error.value.status_code == 503


def test_link_requires_original_browser_confirmation_and_correct_member(session, slack, actions):
    service, _, connection = actions
    challenge = service.begin_link(slack, connection.id)
    session.commit()
    with pytest.raises(ServiceError, match="submitted"):
        service.confirm_link(slack, challenge["challenge_id"], USER)
    session.rollback()
    receive(service, command(challenge["command"].removeprefix("/m2o ")))
    with pytest.raises(ServiceError, match="member"):
        service.confirm_link(slack, challenge["challenge_id"], "U00000002")
    session.rollback()
    browser = digest("another-browser")
    session.add(
        AuthSession(
            token_hash=browser,
            user_id=slack.user_id,
            csrf_hash=digest("other-csrf"),
            expires_at=now() + timedelta(minutes=5),
        )
    )
    session.commit()
    different = Principal(slack.user_id, slack.scope, "owner", browser)
    with pytest.raises(ServiceError, match="expired"):
        service.confirm_link(different, challenge["challenge_id"], USER)
    session.rollback()
    status = service.confirm_link(slack, challenge["challenge_id"], USER)
    assert status["installations"][0]["linked"]
    assert "synthetic-access" not in json.dumps(status)
    session.commit()
    with pytest.raises(ServiceError):
        service.confirm_link(slack, challenge["challenge_id"], USER)


def test_capture_shortcut_and_command_create_restricted_meeting_once(session, actions):
    service, opened, _ = actions
    receive(service, command("meeting"))
    assert len(opened) == 1
    payload = submit(
        opened[0],
        {
            "title": {"value": "Synthetic onboarding"},
            "transcript": {"value": "Alex: Action: Prepare the checklist."},
            "occurred": {"selected_date": "2026-10-04"},
            "timezone": {"value": "America/New_York"},
        },
    )
    assert receive(service, payload, interactive=True) == {}
    assert receive(service, payload, interactive=True, timestamp=int(time.time()) + 1) == {}
    meetings = session.scalars(select(Meeting)).all()
    assert len(meetings) == 1 and meetings[0].visibility == "restricted"
    assert meetings[0].timezone == "America/New_York"
    shortcut = {
        "type": "message_action",
        "team": {"id": TEAM},
        "user": {"id": USER},
        "callback_id": "m2o_capture_message",
        "trigger_id": "new-trigger",
        "message": {"text": "Synthetic notes"},
    }
    assert receive(service, shortcut, interactive=True) == {}
    assert opened[-1]["blocks"][2]["element"]["initial_value"] == "Synthetic notes"


def test_personal_completion_is_separate_and_duplicate_submission_is_safe(session, seeded, actions):
    service, opened, _ = actions
    item = approved(session, seeded)
    session.add(Membership(workspace_id=seeded["workspace"].id, user_id=seeded["other"].id, role="editor"))
    session.commit()
    other = Principal(seeded["other"].id, seeded["workspace"].id, "editor")
    PlanningService(session, other).add(
        "weekly", item.id, PlanInput(expected_item_version=item.version, planned_on=date.today())
    )
    session.commit()
    receive(service, command("plan"))
    payload = submit(opened[-1], plan_values(item))
    assert receive(service, payload, interactive=True) == {}
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    assert receive(service, payload, interactive=True, timestamp=int(time.time()) + 1) == {}
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before
    entries = session.scalars(select(PlanEntry)).all()
    assert {entry.user_id: entry.state for entry in entries} == {
        seeded["user"].id: "done",
        seeded["other"].id: "planned",
    }
    assert session.get(WorkItem, item.id).status == "approved"


@pytest.mark.parametrize(
    "failure", ["source", "plan", "role", "member", "expired", "reconnect", "disabled", "wrong_user"]
)
def test_forms_fail_closed_on_stale_authority_and_versions(session, seeded, actions, failure):
    service, opened, _ = actions
    item = approved(session, seeded)
    principal = seeded["principal"]
    entry = PlanningService(session, principal).add(
        "weekly", item.id, PlanInput(expected_item_version=item.version, planned_on=date.today())
    )
    session.commit()
    receive(service, command("plan"))
    if failure == "source":
        item.version += 1
    elif failure == "plan":
        PlanningService(session, principal).patch(
            "weekly",
            item.id,
            PlanPatch(
                expected_item_version=item.version,
                expected_version=entry["version"],
                planned_on=date.today(),
                state="blocked",
            ),
        )
    elif failure == "role":
        session.get(Membership, (principal.scope, principal.user_id)).role = "viewer"
    elif failure == "member":
        session.delete(session.get(Membership, (principal.scope, principal.user_id)))
    elif failure == "expired":
        session.scalar(select(SlackInteractionContext)).expires_at = now() - timedelta(seconds=1)
    elif failure == "reconnect":
        session.scalar(select(SlackAccount)).version += 1
    elif failure == "disabled":
        seeded["user"].active = False
    session.commit()
    try:
        result = receive(
            service,
            submit(opened[-1], plan_values(item), user="U00000002" if failure == "wrong_user" else USER),
            interactive=True,
        )
    except ServiceError as error:
        assert failure in {"role", "member", "disabled"} and error.status_code == 403
    else:
        assert result["response_action"] == "errors"
    current = session.scalar(select(PlanEntry).where(PlanEntry.user_id == principal.user_id))
    assert current.state != "done"


def test_modal_validation_and_outbound_timeout_do_not_accept_changes(session, actions):
    service, opened, _ = actions
    receive(service, command("meeting"))
    result = receive(
        service,
        submit(
            opened[-1],
            {
                "title": {"value": "Synthetic"},
                "transcript": {"value": "x" * 3001},
                "occurred": {"selected_date": "2026-10-04"},
                "timezone": {"value": "UTC"},
            },
        ),
        interactive=True,
    )
    assert result["response_action"] == "errors" and session.scalar(select(Meeting)) is None

    def timeout(request):
        raise httpx.ReadTimeout("synthetic", request=request)

    service.transport = httpx.MockTransport(timeout)
    result = receive(service, command("meeting"), timestamp=int(time.time()) + 1)
    assert "could not be opened" in result["text"]


def test_http_signature_content_limits_and_warm_acknowledgement(client, actions):
    raw = urlencode(command("help")).encode()
    started = time.perf_counter()
    result = client.post("/api/integrations/slack/commands", content=raw, headers=signed(raw))
    assert result.status_code == 200 and "Use /m2o" in result.json()["text"]
    assert time.perf_counter() - started < 3
    assert (
        client.post("/api/integrations/slack/commands", content=raw + b"x", headers=signed(raw)).status_code
        == 401
    )
    assert (
        client.post(
            "/api/integrations/slack/commands",
            content=raw,
            headers={**signed(raw), "Content-Type": "application/json"},
        ).status_code
        == 415
    )
    assert (
        client.post("/api/integrations/slack/commands", content=b"x" * 65537, headers=signed(raw)).status_code
        == 413
    )
    invalid = urlencode({"payload": "{"}).encode()
    assert (
        client.post(
            "/api/integrations/slack/interactions", content=invalid, headers=signed(invalid)
        ).status_code
        == 422
    )
    wrong = urlencode({**command("help"), "team_id": "T00000002"}).encode()
    assert (
        client.post("/api/integrations/slack/commands", content=wrong, headers=signed(wrong)).status_code
        == 403
    )


def test_browser_link_endpoints_require_session_csrf(client, seeded, actions):
    service, _, connection = actions
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.test", "password": "synthetic-test-password"},
        headers={"Origin": settings.app_origin},
    )
    root = "/api/workspaces/" + seeded["workspace"].id + "/integrations/slack"
    assert client.post(root + "/link", json={"connection_id": connection.id}).status_code == 403
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": login.json()["csrf_token"]}
    response = client.post(root + "/link", json={"connection_id": connection.id}, headers=headers)
    assert response.status_code == 200
    challenge = response.json()
    receive(service, command(challenge["command"].removeprefix("/m2o ")))
    response = client.get(root + "/link/" + challenge["challenge_id"])
    assert response.json()["slack_user_id"] == USER
    response = client.post(
        root + "/link/confirm",
        json={"challenge_id": challenge["challenge_id"], "slack_user_id": USER},
        headers=headers,
    )
    assert response.status_code == 200 and response.json()["installations"][0]["linked"]
    assert client.delete(root + "/link/" + connection.id, headers=headers).status_code == 200


def test_member_mapping_has_no_publisher_authority_and_cannot_replace_other_user(
    session, seeded, slack, actions
):
    service, _, connection = actions
    session.add(Membership(user_id=seeded["other"].id, workspace_id=slack.scope, role="editor"))
    browser = digest("synthetic-editor-browser")
    session.add(
        AuthSession(
            token_hash=browser,
            user_id=seeded["other"].id,
            csrf_hash=digest("editor-csrf"),
            expires_at=now() + timedelta(minutes=5),
        )
    )
    session.commit()
    editor = Principal(seeded["other"].id, slack.scope, "editor", browser)
    challenge = service.begin_link(editor, connection.id)
    session.commit()
    receive(service, {**command(challenge["command"].removeprefix("/m2o ")), "user_id": "U00000002"})
    service.confirm_link(editor, challenge["challenge_id"], "U00000002")
    session.commit()
    status = connection_status(session, editor)
    assert status["can_capture_meeting"] and status["can_change_my_plan"]
    assert not status["can_create"] and not status["can_manage"]
    replacement = service.begin_link(editor, connection.id)
    session.commit()
    receive(service, command(replacement["command"].removeprefix("/m2o ")))
    with pytest.raises(ServiceError, match="another M2O user"):
        service.confirm_link(editor, replacement["challenge_id"], USER)
    session.rollback()
    session.scalar(select(SlackAccount)).version += 1
    session.commit()
    assert not connection_status(session, editor)["can_capture_meeting"]
    service.unlink(editor, connection.id)
    session.commit()
    assert not service.link_status(editor)["installations"][0]["linked"]


def test_concurrent_signed_submission_applies_once(engine, session, seeded, actions):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL replay and row-lock behavior")
    service, opened, _ = actions
    item = approved(session, seeded)
    receive(service, command("plan"))
    raw = urlencode({"payload": json.dumps(submit(opened[-1], plan_values(item)))}).encode()
    headers = signed(raw)
    request_hash = verify_request(raw, [headers["X-Slack-Request-Timestamp"]], [headers["X-Slack-Signature"]])
    session.rollback()
    barrier = Barrier(2)

    def process():
        with Session(engine, expire_on_commit=False) as independent:
            barrier.wait(timeout=5)
            return asyncio.run(SlackActions(independent).receive(raw, request_hash, interactive=True))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: process(), range(2)))
    assert results == [{}, {}]
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(PlanEntry)) == 1
    assert session.scalar(select(PlanEntry)).state == "done"


def test_oauth_reconnect_and_signed_identity_share_owner_lock_order(engine, session, slack, actions):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL reconnect and action lock ordering")
    adapter = SlackAdapter(transport([]))
    state = parse_qs(urlsplit(adapter.begin(session, slack)["url"]).query)["state"][0]
    identity_id = session.scalar(select(SlackIdentity.id))
    tag = "m2o_action_" + identity_id.replace("-", "")
    session.commit()
    action_ready, owner_locked, action_attempted = Event(), Event(), Event()

    def action():
        with Session(engine, expire_on_commit=False) as db:
            db.execute(text("SELECT set_config('application_name', :tag, false)"), {"tag": tag})
            db.execute(text("SET LOCAL lock_timeout = '2500ms'"))
            action_ready.set()
            assert owner_locked.wait(5)
            action_attempted.set()
            with pytest.raises(ServiceError, match="current Slack identity"):
                SlackActions(db).principal(db.get(SlackIdentity, identity_id))

    def reconnect():
        assert action_ready.wait(5)
        with Session(engine, expire_on_commit=False) as db:
            db.scalar(select(User).where(User.id == slack.user_id).with_for_update())
            owner_locked.set()
            assert action_attempted.wait(5)
            deadline, blocked = time.monotonic() + 2, False
            while time.monotonic() < deadline:
                db.execute(text("SELECT pg_stat_clear_snapshot()"))
                blocked = bool(
                    db.scalar(
                        text(
                            "SELECT cardinality(pg_blocking_pids(pid)) > 0 FROM pg_stat_activity WHERE application_name = :tag"
                        ),
                        {"tag": tag},
                    )
                )
                if blocked:
                    break
                time.sleep(0.01)
            assert blocked, "The action must wait on the owner's user row while reconnection owns it"
            assert asyncio.run(adapter.complete(db, slack, state, "synthetic-code")) == slack.scope

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(action), pool.submit(reconnect)]
        for future in futures:
            future.result(timeout=10)
    session.expire_all()
    assert session.scalar(select(SlackAccount)).version == 2
