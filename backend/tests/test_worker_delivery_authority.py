import asyncio

import pytest
from sqlalchemy.orm import Session
from test_publication import enable, proposal

from app.models import Job, Membership, PublicationOperation
from app.services.issues import IssueService
from app.worker import run_once


def test_revocation_during_marker_read_is_rechecked_before_create(engine, session, seeded, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL authority change during provider read")
    preview, _ = proposal(session, seeded)
    enable(monkeypatch)
    approval = IssueService(session, seeded["principal"]).approve(preview["id"], preview["payload_hash"])
    session.commit()
    calls = []

    class RevokingAdapter:
        async def find_marker(self, repo, marker, expected_payload=None):
            calls.append("read")
            with Session(engine) as other:
                other.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "viewer"
                other.commit()
            return None

        async def create(self, repo, payload):
            calls.append("write")
            raise AssertionError("Revoked authority must never reach the provider write")

    assert asyncio.run(run_once(RevokingAdapter()))
    session.expire_all()
    job = session.get(Job, approval["job_id"])
    receipt = session.get(PublicationOperation, approval["operation_id"])
    assert calls == ["read"] and job.state == "failed"
    assert job.error_code == "service_403" and receipt.state == "uncertain"
