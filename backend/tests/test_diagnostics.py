import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.models import DeliveryTombstone, Job, RateBucket, Workspace, now
from app.services.diagnostics import EFFECT_STATES, JOB_KINDS, JOB_STATES, operational_snapshot
from scripts import diagnostics


def test_snapshot_is_read_only_and_has_bounded_labels_without_payloads(session, seeded):
    canary = "PRIVATE_DIAG_CANARY@example.test"  # fits varchar(36) columns
    workspace = seeded["workspace"]
    workspace.name = canary
    workspace.erasure_requested_at = now()
    job = Job(
        workspace_id=workspace.id,
        actor_id=seeded["user"].id,
        kind="extract",
        state="queued",
        created_at=now() - timedelta(minutes=3),
        payload={"transcript": canary, "token": canary},
        result={"provider_payload": canary},
    )
    session.add_all(
        [
            job,
            Job(
                workspace_id=workspace.id,
                actor_id=seeded["user"].id,
                kind="index",
                state="running",
                lease_until=now() - timedelta(seconds=1),
                payload={},
            ),
            RateBucket(key=canary, count=30, expires_at=now() - timedelta(seconds=1)),
            DeliveryTombstone(
                workspace_id=workspace.id,
                provider="github",
                operation_id=canary,
                delivery_key="a" * 64,
                payload_hash="b" * 64,
                state="uncertain",
                receipt={"resources": [canary]},
                retained_until=now(),
            ),
        ]
    )
    session.commit()
    report = operational_snapshot(session)
    serialized = json.dumps(report)
    assert canary not in serialized and workspace.id not in serialized and job.id not in serialized
    assert set(report["jobs"]) == set(JOB_KINDS)
    assert all(set(states) == set(JOB_STATES) for states in report["jobs"].values())
    assert all(set(states) == set(EFFECT_STATES) for states in report["delivery_effects"].values())
    assert report["jobs"]["extract"]["queued"] == 1
    assert report["oldest_queued_seconds"]["extract"] >= 180
    assert report["expired_running_leases"] == 1
    assert report["pending_erasure_workspaces"] == 1 and report["unresolved_tombstones"] == 1
    assert report["expired_temporary_records"]["rate_buckets"] == 1
    assert session.scalar(select(func.count()).select_from(Job)) == 2
    assert session.get(Workspace, workspace.id).name == canary


def test_snapshot_does_not_autoflush_pending_changes(session, seeded):
    session.add(
        Job(workspace_id=seeded["workspace"].id, actor_id=seeded["user"].id, kind="index", payload={})
    )
    assert operational_snapshot(session)["jobs"]["index"]["queued"] == 0
    assert session.new
    session.rollback()


def test_postgres_report_runs_in_read_only_transaction_and_includes_storage(session, engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL storage and read-only transaction")
    session.execute(text("SET TRANSACTION READ ONLY"))
    report = operational_snapshot(session)
    assert session.scalar(text("SHOW transaction_read_only")) == "on"
    assert report["storage"]["database_bytes"] > 0
    assert report["storage"]["relation_bytes"]["jobs"] > 0


def test_diagnostics_cli_hides_database_exception_contents(monkeypatch, capsys):
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("SECRET_SQL_CANARY", {}, RuntimeError("SECRET_DSN_CANARY"))

    monkeypatch.setattr(diagnostics, "get_engine", unavailable)
    assert diagnostics.main() == 1
    assert json.loads(capsys.readouterr().out) == {"error_code": "diagnostics_unavailable"}
