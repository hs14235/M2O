import asyncio
import json
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text
from test_hosted_runtime import demo_config

from app import database, worker
from app.schema_compatibility import require_schema, supported_revisions
from app.schemas import IndexInput
from app.services.errors import ServiceError
from app.services.meetings import MeetingService
from app.settings import Settings, settings
from app.worker_health import WorkerPulse, worker_available
from scripts import migrate
from scripts.serve_demo import PRIVATE_CREDENTIAL_KEYS, demo_environment, supervise


@pytest.mark.parametrize("key", PRIVATE_CREDENTIAL_KEYS)
@pytest.mark.parametrize("lowercase", [False, True])
def test_every_private_credential_family_is_rejected_without_echo(key, lowercase):
    secret = "synthetic-private-canary"
    with pytest.raises(ValueError) as failure:
        demo_environment({**demo_config(), key.lower() if lowercase else key: secret})
    assert secret not in str(failure.value)


def test_credential_inventory_covers_all_settings_secret_fields():
    required = {
        name.upper()
        for name, field in Settings.model_fields.items()
        if field.annotation is SecretStr and name != "database_url"
    }
    assert required <= set(PRIVATE_CREDENTIAL_KEYS)


def test_demo_overrides_dotenv_and_requires_an_explicit_policy():
    environment = demo_environment(demo_config())
    assert all(environment[key] == "" for key in PRIVATE_CREDENTIAL_KEYS)
    assert environment["OLLAMA_MODEL"] == "" and environment["EMBED_PROVIDER"] == "hash"
    assert environment["SLACK_INTERACTIONS_ENABLED"] == environment["LINKEDIN_PUBLISHING_ENABLED"] == "false"
    for extra in (
        {"CLIENT_IDENTITY_MODE": ""},
        {"CLIENT_IDENTITY_MODE": "direct"},
        {"CLIENT_IDENTITY_MODE": "trusted_proxy"},
        {"WORKER_HEARTBEAT_FILE": "/not-owned"},
        {"client_identity_mode": "trusted_proxy"},
    ):
        with pytest.raises(ValueError):
            demo_environment({**demo_config(), **extra})
    environment = demo_environment(
        {
            **demo_config(),
            "CLIENT_IDENTITY_MODE": "trusted_proxy",
            "CLIENT_IP_HEADER": "cf-connecting-ip",
            "TRUSTED_PROXY_CIDRS": "192.0.2.10/32",
        }
    )
    assert environment["TRUSTED_PROXY_CIDRS"] == "192.0.2.10/32"


@pytest.mark.parametrize("revision", ["20261004_10", "unknown_revision", None])
def test_ready_and_startup_reject_incompatible_schema_without_echo(client, engine, revision):
    from app.main import app

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
        if revision is not None:
            connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})
    response = client.get("/readyz")
    assert response.status_code == 503 and response.json()["code"] == "schema_incompatible"
    assert revision is None or revision not in response.text
    assert client.get("/healthz").status_code == 200
    with pytest.raises(ServiceError) as failure, TestClient(app):
        pass
    assert failure.value.status_code == 503


def test_readiness_worker_freshness_and_deadline_do_not_leak_path(client, monkeypatch, tmp_path):
    path = tmp_path / "private-worker-health.json"
    monkeypatch.setattr(settings, "worker_heartbeat_file", str(path))
    response = client.get("/readyz")
    assert response.status_code == 503 and response.json()["code"] == "worker_unavailable"
    assert str(path) not in response.text
    pulse = WorkerPulse(str(path))
    pulse.idle()
    assert client.get("/readyz").status_code == 200
    path.write_text(json.dumps({"seen_at": time.monotonic(), "started_at": time.monotonic() - 601}))
    assert client.get("/readyz").status_code == 503
    pulse.idle()
    assert client.get("/readyz").status_code == 200


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        {"seen_at": float("nan"), "started_at": None},
        {"seen_at": 110, "started_at": None},
        {"seen_at": 40, "started_at": None},
        {"seen_at": 99, "started_at": True},
        {"seen_at": 99, "started_at": 101},
        {"seen_at": 99, "started_at": -600},
    ],
)
def test_malformed_stale_future_or_overlong_job_signals_fail_closed(tmp_path, value):
    path = tmp_path / "health.json"
    path.write_text(json.dumps(value))
    assert not worker_available(str(path), 45, 600, at=100)
    path.write_text("x" * 513)
    assert not worker_available(str(path), 45, 600, at=100)


def test_real_job_signals_busy_then_idle_without_source_data(session, seeded, tmp_path, monkeypatch):
    path = tmp_path / "health.json"
    MeetingService(session, seeded["principal"]).index(
        IndexInput(
            meeting_id="phase8-worker", transcript="Action: Keep this synthetic content out of diagnostics."
        )
    )
    session.commit()
    actual_execute = worker.execute
    observed = []

    async def inspect_busy(record, adapter=None, linkedin_adapter=None):
        observed.append(json.loads(path.read_text())["started_at"])
        return await actual_execute(record, adapter, linkedin_adapter)

    monkeypatch.setattr(worker, "execute", inspect_busy)
    assert asyncio.run(worker.run_once(runtime=WorkerPulse(str(path))))
    assert observed and observed[0] is not None
    value = json.loads(path.read_text())
    assert set(value) == {"seen_at", "started_at"} and value["started_at"] is None
    assert "synthetic" not in path.read_text()
    assert worker_available(str(path), 45, 600)


def test_supervisor_stops_children_on_missing_signal(monkeypatch, tmp_path, capsys):
    actual_popen, children = subprocess.Popen, []

    def start(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", start)
    import os

    env = {
        **os.environ,
        "WORKER_HEARTBEAT_FILE": str(tmp_path / "missing.json"),
        "WORKER_HEARTBEAT_TIMEOUT": "1",
        "WORKER_JOB_DEADLINE": "60",
    }
    assert supervise([[sys.executable, "-c", "import time; time.sleep(60)"]], env) == 1
    assert all(child.poll() is not None for child in children)
    assert str(tmp_path) not in capsys.readouterr().err


def test_single_pool_connection_migrates_and_releases_lock(engine, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("Actual advisory lock, transactional DDL and pool regression")
    schema = "mtt_phase8_" + uuid4().hex
    assert schema.startswith("mtt_phase8_") and len(schema) == len("mtt_phase8_") + 32
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    single = create_engine(
        engine.url,
        hide_parameters=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        connect_args={"options": "-csearch_path=" + schema},
    )
    monkeypatch.setattr(database, "get_engine", lambda: single)
    monkeypatch.setattr(migrate, "get_engine", lambda: single)
    try:
        migrate.main()
        migrate.main()
        with single.connect() as connection:
            assert require_schema(connection) in supported_revisions()
            assert "jobs" in inspect(connection).get_table_names()
        with engine.connect() as independent:
            assert independent.execute(text("SELECT pg_try_advisory_lock(674198234)")).scalar_one()
            independent.execute(text("SELECT pg_advisory_unlock(674198234)"))
    finally:
        single.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_http_cooldown_and_logs_use_server_expiry_and_route_templates(client, monkeypatch, seeded):
    from app.main import log

    records = []
    monkeypatch.setattr(log, "info", lambda event, **kwargs: records.append(kwargs["extra"]))
    origin = {"Origin": settings.app_origin}
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/recovery/request", headers=origin, json={"email": "absent@example.test"}
            ).status_code
            == 202
        )
    response = client.post(
        "/api/auth/recovery/request", headers=origin, json={"email": "absent@example.test"}
    )
    assert response.status_code == 429 and response.json()["code"] == "rate_limited"
    assert 1 <= int(response.headers["Retry-After"]) <= 300
    assert response.json()["retry_after"] == int(response.headers["Retry-After"])
    assert client.get("/api/workspaces/" + seeded["workspace"].id + "/meetings").status_code == 401
    assert records[-1]["path"] == "/api/workspaces/{workspace_id}/meetings"
    assert seeded["workspace"].id not in json.dumps(records)
    client.get("/unmatched-synthetic-canary")
    assert records[-1]["path"] == "unmatched"


def test_failed_migration_rolls_back_and_unlocks_independent_session(engine, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("Transactional migration failure and session lock release")
    monkeypatch.setattr(migrate, "get_engine", lambda: engine)
    with engine.connect() as owner:
        # Capture the actual runner connection through the supplied Alembic contract.
        runner_pid = []

        def fail(config, target):
            connection = config.attributes["connection"]
            runner_pid.append(connection.execute(text("SELECT pg_backend_pid()")).scalar_one())
            connection.execute(text("CREATE TABLE phase8_rollback_probe (id INTEGER)"))
            raise RuntimeError("Synthetic migration failure")

        monkeypatch.setattr(migrate.command, "upgrade", fail)
        with pytest.raises(RuntimeError, match="Synthetic migration failure"):
            migrate.main()
        assert owner.execute(text("SELECT pg_backend_pid()")).scalar_one() != runner_pid[0]
        assert "phase8_rollback_probe" not in inspect(owner).get_table_names()
        assert owner.execute(text("SELECT pg_try_advisory_lock(674198234)")).scalar_one()
        owner.execute(text("SELECT pg_advisory_unlock(674198234)"))


def test_contended_migration_lock_times_out_without_releasing_other_owner(engine, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("Actual competing advisory-lock sessions")
    monkeypatch.setattr(migrate, "get_engine", lambda: engine)
    monkeypatch.setattr(settings, "migration_lock_timeout", 1)
    with engine.connect() as owner:
        owner.execute(text("SELECT pg_advisory_lock(674198234)"))
        owner.commit()
        try:
            with pytest.raises(ServiceError, match="Migration lock is temporarily unavailable"):
                migrate.main()
            # The first owner still holds exactly its lock.
            assert owner.execute(text("SELECT pg_advisory_unlock(674198234)")).scalar_one()
        finally:
            owner.execute(text("SELECT pg_advisory_unlock_all()"))


def test_expired_frozen_job_settles_before_purge_without_manual_requeue(session, seeded):
    from datetime import timedelta

    from app.models import Job, Workspace, now
    from app.schemas import WorkspaceErasureInput
    from app.services.privacy import PrivacyService

    result = MeetingService(session, seeded["principal"]).index(
        IndexInput(meeting_id="phase8-erasure", transcript="Action: Synthetic work awaiting recovery.")
    )
    session.commit()
    job = session.get(Job, result["job_id"])
    job.state, job.lease_token, job.lease_until = (
        "running",
        "expired-phase8-lease",
        now() - timedelta(seconds=1),
    )
    session.commit()
    pending = PrivacyService(session).erase_workspace(
        seeded["principal"],
        WorkspaceErasureInput(
            password="synthetic-test-password", confirmation_name=seeded["workspace"].name, expected_version=1
        ),
    )
    session.commit()
    assert pending["state"] == "pending_erasure"
    assert asyncio.run(worker.run_once())
    session.expire_all()
    assert session.get(Job, result["job_id"]).state == "failed"
    erased = PrivacyService(session).purge_workspace(seeded["workspace"].id)
    session.commit()
    assert erased["state"] == "erased"
    assert session.get(Workspace, seeded["workspace"].id).erased_at is not None
