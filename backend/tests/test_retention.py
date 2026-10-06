from datetime import timedelta

from sqlalchemy import func, select

from app.auth import Principal
from app.models import DeliveryTombstone, Job, Membership, User, Workspace, now
from app.services.demo import DemoService
from app.services.retention import RetentionService


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
