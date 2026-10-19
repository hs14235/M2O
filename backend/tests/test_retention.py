import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import (
    ApiToken,
    AuditEvent,
    AuthSession,
    DeliveryTombstone,
    Invitation,
    Job,
    Membership,
    OAuthState,
    RateBucket,
    User,
    Workspace,
    now,
)
from app.schemas import InvitationInput
from app.services.demo import DemoService
from app.services.errors import ServiceError
from app.services.lifecycle import InvitationService
from app.services.retention import RetentionService
from app.worker import run_once


def expired_visitor(session):
    user, _, _ = DemoService(session).start()
    session.commit()
    workspace = session.scalar(
        select(Workspace)
        .join(Membership)
        .where(Membership.user_id == user.id, Workspace.department == "engineering")
    )
    loaded = DemoService(session).load(Principal(user.id, workspace.id, "owner"), "engineering")
    user.visitor_expires_at = now() - timedelta(seconds=1)
    session.commit()
    return user.id, workspace.id, loaded["job_id"]


def test_retention_preview_does_not_mutate_and_apply_removes_only_expired_visitor(session, seeded):
    user_id, workspace_id, _ = expired_visitor(session)
    before = session.scalar(select(func.count()).select_from(User))
    preview = RetentionService(session).run(limit=1)
    assert preview["expired_visitors"] == 1 and not preview["applied"]
    assert session.scalar(select(func.count()).select_from(User)) == before
    applied = RetentionService(session).run(limit=1, apply=True)
    assert applied["removed_visitors"] == 1
    assert session.get(User, user_id) is None
    assert session.get(Workspace, workspace_id).erased_at is not None
    assert session.get(User, seeded["user"].id).active
    assert session.get(Workspace, seeded["workspace"].id).erased_at is None


def test_retention_preserves_unresolved_uncertainty_until_explicit_operator_decision(session, seeded):
    unknown = DeliveryTombstone(
        workspace_id=seeded["workspace"].id,
        provider="github",
        operation_id="synthetic-unknown-operation",
        delivery_key="a" * 64,
        payload_hash="b" * 64,
        state="uncertain",
        receipt={"resources": [{"status": "uncertain"}]},
        retained_until=now() - timedelta(days=1),
    )
    known = DeliveryTombstone(
        workspace_id=seeded["workspace"].id,
        provider="slack",
        operation_id="synthetic-known-operation",
        delivery_key="c" * 64,
        payload_hash="d" * 64,
        state="completed",
        receipt={"resources": [{"status": "created", "message_ts": "synthetic"}]},
        retained_until=now() - timedelta(days=1),
    )
    session.add_all([unknown, known])
    session.commit()
    unknown_id, known_id = unknown.id, known.id
    result = RetentionService(session).run(apply=True)
    assert result["removed_tombstones"] == 1
    assert session.get(DeliveryTombstone, unknown_id) is not None
    assert session.get(DeliveryTombstone, known_id) is None
    RetentionService(session).resolve_tombstone(unknown_id, "accepted_unknown")
    assert unknown.state == "uncertain"
    RetentionService(session).resolve_tombstone(unknown_id, "accepted_unknown", apply=True)
    session.commit()
    assert unknown.state == "resolved" and unknown.receipt["resolution"]["status"] == "accepted_unknown"
    assert RetentionService(session).run(apply=True)["removed_tombstones"] == 0
    unknown.retained_until = now() - timedelta(seconds=1)
    session.commit()
    assert RetentionService(session).run(apply=True)["removed_tombstones"] == 1


def test_retention_keeps_running_visitor_data_frozen_until_worker_settles(session, seeded):
    user_id, workspace_id, job_id = expired_visitor(session)
    job = session.get(Job, job_id)
    job.state, job.lease_token = "running", "synthetic-retention-lease"
    session.commit()
    result = RetentionService(session).run(apply=True)
    assert result["pending_visitors"] == 1 and result["removed_visitors"] == 0
    assert session.get(User, user_id) is not None
    assert session.get(Workspace, workspace_id).erasure_requested_at is not None
    session.get(Job, job_id).state = "failed"
    session.commit()
    assert RetentionService(session).run(apply=True)["removed_visitors"] == 1


def test_retention_does_not_modify_protected_cross_workspace_relationship(session, seeded):
    user_id, _, _ = expired_visitor(session)
    session.add(Membership(user_id=user_id, workspace_id=seeded["workspace"].id, role="viewer"))
    session.commit()
    result = RetentionService(session).run(apply=True)
    assert result["protected_visitors"] == 1 and result["removed_visitors"] == 0
    assert session.get(Membership, (seeded["workspace"].id, user_id)) is not None
    assert session.get(Workspace, seeded["workspace"].id).erasure_requested_at is None


def test_retention_batch_validation(session):
    import pytest

    for limit in (0, 101):
        with pytest.raises(ValueError):
            RetentionService(session).run(limit=limit)


def test_retention_previews_all_temporary_classes_and_bounds_cleanup(session, seeded):
    user = seeded["user"]
    past, future = now() - timedelta(seconds=1), now() + timedelta(hours=1)
    for position in range(2):
        session.add(RateBucket(key=f"expired-{position}", count=30, expires_at=past))
    session.add_all(
        [
            AuthSession(
                token_hash="expired-session", csrf_hash="synthetic", user_id=user.id, expires_at=past
            ),
            AuthSession(token_hash="live-session", csrf_hash="synthetic", user_id=user.id, expires_at=future),
            ApiToken(
                token_hash="expired-api",
                user_id=user.id,
                workspace_id=seeded["workspace"].id,
                expires_at=past,
            ),
            Invitation(
                workspace_id=seeded["workspace"].id,
                issued_by=user.id,
                issuer_auth_version=1,
                email="synthetic@example.test",
                role="viewer",
                token_hash="expired-invite",
                expires_at=past,
            ),
        ]
    )
    session.flush()
    session.add(
        OAuthState(
            state_hash="expired-oauth",
            user_id=user.id,
            session_hash="live-session",
            nonce="synthetic",
            expires_at=past,
        )
    )
    session.commit()
    preview = RetentionService(session).run(limit=1)
    assert preview["limit_scope"] == "per_record_class"
    for name in ("rate_buckets", "api_tokens", "auth_sessions", "invitations", "oauth_states"):
        assert preview["temporary_records"][name] == {"eligible": 1, "removed": 0}
    assert session.get(OAuthState, "expired-oauth") is not None
    applied = RetentionService(session).run(limit=1, apply=True)
    for name in ("rate_buckets", "api_tokens", "auth_sessions", "invitations", "oauth_states"):
        assert applied["temporary_records"][name]["removed"] == 1
    assert session.get(AuthSession, "live-session") is not None
    assert session.get(ApiToken, "expired-api") is None
    assert session.scalar(select(func.count()).select_from(RateBucket)) == 1


def test_purged_expired_invitation_reports_not_found_and_keeps_audit_history(session, seeded):
    invitations = InvitationService(session)
    issued = invitations.issue(seeded["principal"], InvitationInput(email="expiring@example.test"))
    session.get(Invitation, issued["id"]).expires_at = now() - timedelta(seconds=1)
    session.commit()
    applied = RetentionService(session).run(limit=10, apply=True)
    assert applied["temporary_records"]["invitations"]["removed"] == 1
    # A stale owner tab revoking the purged link gets a clear not-found, never a false success.
    with pytest.raises(ServiceError) as missing:
        invitations.revoke(seeded["principal"], issued["id"])
    assert missing.value.status_code == 404
    actions = session.scalars(select(AuditEvent.action).where(AuditEvent.target_id == issued["id"])).all()
    assert actions == ["invitation.issued"]


def test_retention_rechecks_a_concurrently_renewed_rate_bucket(engine, session):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrent cleanup/renewal")
    session.add(RateBucket(key="renewed-bucket", count=30, expires_at=now() - timedelta(seconds=1)))
    session.commit()
    renewed = False

    def renew_before_delete(connection, cursor, statement, parameters, context, executemany):
        nonlocal renewed
        if not renewed and statement.startswith("DELETE FROM rate_buckets"):
            renewed = True
            with Session(engine) as concurrent:
                concurrent.execute(
                    update(RateBucket)
                    .where(RateBucket.key == "renewed-bucket")
                    .values(count=1, expires_at=now() + timedelta(hours=1))
                )
                concurrent.commit()

    event.listen(engine, "before_cursor_execute", renew_before_delete)
    try:
        report = RetentionService(session).run(limit=1, apply=True)
    finally:
        event.remove(engine, "before_cursor_execute", renew_before_delete)
    session.expire_all()
    assert renewed and report["temporary_records"]["rate_buckets"] == {"eligible": 1, "removed": 0}
    assert session.get(RateBucket, "renewed-bucket").count == 1


def test_expired_crashed_visitor_job_recovers_then_erasure_finishes(session, seeded):
    user_id, workspace_id, job_id = expired_visitor(session)
    job = session.get(Job, job_id)
    job.state, job.lease_token, job.lease_until = "running", "crashed-worker", now() - timedelta(seconds=1)
    session.commit()
    assert RetentionService(session).run(apply=True)["pending_visitors"] == 1
    assert asyncio.run(run_once())
    session.expire_all()
    assert session.get(Job, job_id).state == "failed"
    assert session.get(Job, job_id).error_code == "service_403"
    assert RetentionService(session).run(apply=True)["removed_visitors"] == 1
    assert session.get(User, user_id) is None and session.get(Workspace, workspace_id).erased_at is not None


@pytest.mark.parametrize("attempts", [1, 3])
def test_frozen_crashed_delivery_keeps_uncertainty_without_provider_replay(
    session, seeded, monkeypatch, attempts
):
    from test_publication import enable, proposal

    from app.models import PublicationOperation
    from app.services.issues import IssueService
    from app.services.privacy import PrivacyService

    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    approved = IssueService(session, seeded["principal"]).approve(preview["id"], preview["payload_hash"])
    job = session.get(Job, approved["job_id"])
    job.state, job.lease_token, job.lease_until, job.attempts = (
        "running",
        "crashed-delivery",
        now() - timedelta(seconds=1),
        attempts,
    )
    operation = session.get(PublicationOperation, approved["operation_id"])
    operation.state, operation.results = "sending", [{"status": "uncertain"}]
    workspace = seeded["workspace"]
    workspace.erasure_requested_at = now()
    session.commit()
    calls = []

    class ForbiddenProvider:
        async def find_marker(self, *args):
            calls.append("read")
            raise AssertionError("Frozen workspace must not call a provider")

        async def create(self, *args):
            calls.append("write")
            raise AssertionError("Crash recovery must not replay a write")

    assert PrivacyService(session).purge_workspace(workspace.id)["state"] == "pending_erasure"
    session.commit()
    assert asyncio.run(run_once(ForbiddenProvider())) == (attempts < 3)
    session.expire_all()
    assert calls == [] and session.get(Job, job.id).state == "failed"
    assert session.get(PublicationOperation, operation.id).state == "uncertain"
    assert PrivacyService(session).purge_workspace(workspace.id)["state"] == "erased"
    session.commit()
    tombstone = session.scalar(
        select(DeliveryTombstone).where(DeliveryTombstone.operation_id == operation.id)
    )
    assert tombstone.state == "uncertain"
    assert RetentionService(session).run(apply=True)["removed_tombstones"] == 0


def test_worker_maintenance_purges_expired_visitors_only_when_enabled_and_due(session, seeded):
    from app.worker import Maintenance

    user_id, _, _ = expired_visitor(session)
    kept, _, _ = DemoService(session).start()
    session.commit()
    assert asyncio.run(Maintenance(0).run_if_due()) is None  # Off by default outside the hosted demo.
    session.expire_all()
    assert session.get(User, user_id) is not None
    maintenance = Maintenance(600)
    assert asyncio.run(maintenance.run_if_due())["removed_visitors"] == 1
    session.expire_all()
    assert session.get(User, user_id) is None and session.get(User, kept.id) is not None
    assert asyncio.run(maintenance.run_if_due()) is None  # Not due again within the interval.


def test_demo_admission_recovers_after_maintenance_purges_expired_visitors(session, monkeypatch):
    from app.settings import settings
    from app.worker import Maintenance

    monkeypatch.setattr(settings, "visitor_retained_limit", 1)
    first, _, _ = DemoService(session).start()
    session.commit()
    with pytest.raises(ServiceError) as full:
        DemoService(session).start()
    assert full.value.status_code == 429
    session.rollback()
    session.get(User, first.id).visitor_expires_at = now() - timedelta(seconds=1)
    session.commit()
    assert asyncio.run(Maintenance(600).run_if_due())["removed_visitors"] == 1
    session.expire_all()
    DemoService(session).start()  # Expired visitors no longer hold the retained budget.
    session.commit()


def test_maintenance_failure_is_logged_without_stopping_the_worker(engine, monkeypatch):
    from app import worker

    records = []

    class Broken:
        def __init__(self, session):
            pass

        def run(self, **kwargs):
            raise RuntimeError("synthetic private detail")

    monkeypatch.setattr(worker, "RetentionService", Broken)
    monkeypatch.setattr(worker.log, "error", lambda event, **kwargs: records.append((event, kwargs["extra"])))
    assert asyncio.run(worker.Maintenance(600).run_if_due()) is None
    assert records == [("retention_maintenance_failed", {"error_code": "RuntimeError"})]


def test_new_visitor_rings_the_wake_file_but_other_users_do_not(session, monkeypatch, tmp_path):
    from app.settings import settings

    wake = tmp_path / "wake"
    monkeypatch.setattr(settings, "worker_wake_file", str(wake))
    session.add(User(email="member@example.test", name="Member", password_hash="not-a-login"))
    session.commit()
    assert not wake.exists()
    DemoService(session).start()
    session.commit()
    assert wake.exists()
