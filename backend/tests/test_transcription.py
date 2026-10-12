"""Local audio transcription: queueing rules, worker flow and audio lifecycle.

The real faster-whisper model is replaced with a stub, so these tests never
download a model or need requirements-ai.txt.
"""

import asyncio
import importlib.util
import os
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import transcription as speech
from app.models import AudioUpload, AuditEvent, Job, Meeting, Membership, TranscriptRevision, now
from app.schemas import IndexInput
from app.services.errors import ServiceError
from app.services.retention import RetentionService
from app.services.transcription import TranscriptionService
from app.settings import settings
from app.worker import run_once
from scripts.serve_demo import demo_environment

SPOKEN = "Alex: Action: Prepare the synthetic onboarding checklist.\nSam: Decision: Ship on Friday."


def details(meeting_id="audio-meeting"):
    return IndexInput(meeting_id=meeting_id, title="Recorded sync", transcript="pending transcription")


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "transcription_enabled", True)


@pytest.fixture
def stub_transcriber(monkeypatch):
    calls = []

    def transcribe(audio, *, model_name, compute_type, max_seconds):
        calls.append({"bytes": audio, "model": model_name, "compute": compute_type, "max": max_seconds})
        return speech.Transcript(text=SPOKEN, duration_seconds=42.4, language="en")

    monkeypatch.setattr(speech, "transcribe", transcribe)
    return calls


def queue(session, seeded, filename="sync.mp3", raw=b"synthetic-audio", meeting_id="audio-meeting"):
    result = TranscriptionService(session, seeded["principal"]).queue(filename, raw, details(meeting_id))
    session.commit()
    return result


def test_transcription_is_disabled_by_default(session, seeded):
    with pytest.raises(ServiceError) as disabled:
        queue(session, seeded)
    assert disabled.value.status_code == 404
    assert session.scalar(select(func.count()).select_from(AudioUpload)) == 0


@pytest.mark.parametrize(
    "filename,size,status",
    [("notes.txt", 15, 400), ("sync.mp3", 0, 400), ("sync.mp3", 1_000_001, 413)],
    ids=["wrong-type", "empty", "oversized"],
)
def test_queue_rejects_wrong_type_empty_and_oversized_audio(
    session, seeded, enabled, monkeypatch, filename, size, status
):
    monkeypatch.setattr(settings, "transcription_max_bytes", 1_000_000)
    with pytest.raises(ServiceError) as rejected:
        queue(session, seeded, filename=filename, raw=b"x" * size)
    assert rejected.value.status_code == status
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_queue_refuses_an_existing_meeting_identifier(session, seeded, enabled):
    session.add(
        Meeting(
            workspace_id=seeded["workspace"].id, slug="taken", title="Taken", created_by=seeded["user"].id
        )
    )
    session.commit()
    with pytest.raises(ServiceError) as taken:
        queue(session, seeded, meeting_id="taken")
    assert taken.value.status_code == 409


def test_worker_transcribes_into_a_new_meeting_and_deletes_the_audio(
    session, seeded, enabled, stub_transcriber
):
    queued = queue(session, seeded)
    assert asyncio.run(run_once())
    session.expire_all()
    job = session.get(Job, queued["job_id"])
    assert job.state == "completed", job.error_code
    assert job.result["meeting_id"] == "audio-meeting" and job.result["duration_seconds"] == 42
    assert stub_transcriber[0]["bytes"] == b"synthetic-audio"
    assert stub_transcriber[0]["model"] == "small" and stub_transcriber[0]["compute"] == "int8"
    meeting = session.scalar(select(Meeting).where(Meeting.slug == "audio-meeting"))
    assert meeting is not None and meeting.title == "Recorded sync"
    # The transcript enters the normal path: a revision plus a queued index job.
    index_job = session.get(Job, job.result["index_job_id"])
    assert index_job.kind == "index" and index_job.state == "queued"
    assert session.scalar(select(func.count()).select_from(AudioUpload)) == 0
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "meeting.audio_transcribed"))


def test_failed_transcription_fails_the_job_and_still_deletes_the_audio(
    session, seeded, enabled, monkeypatch
):
    def too_long(audio, **options):
        raise ServiceError(status_code=413, error="Audio is longer than the 60-minute limit", where="client")

    monkeypatch.setattr(speech, "transcribe", too_long)
    queued = queue(session, seeded)
    assert asyncio.run(run_once())
    session.expire_all()
    job = session.get(Job, queued["job_id"])
    assert job.state == "failed" and job.error_code == "service_413"
    assert session.scalar(select(func.count()).select_from(AudioUpload)) == 0
    assert session.scalar(select(func.count()).select_from(Meeting)) == 0


def test_revoked_membership_removes_pending_audio_and_the_job_cannot_run(
    session, seeded, enabled, stub_transcriber
):
    queued = queue(session, seeded)
    session.delete(session.get(Membership, (seeded["workspace"].id, seeded["user"].id)))
    session.commit()
    # The membership foreign key cascades: pending audio disappears with the access.
    assert session.scalar(select(func.count()).select_from(AudioUpload)) == 0
    assert asyncio.run(run_once())
    session.expire_all()
    assert session.get(Job, queued["job_id"]).state == "failed"
    assert stub_transcriber == []


def test_retention_removes_orphaned_audio_after_expiry(session, seeded, enabled):
    queue(session, seeded)
    session.execute(AudioUpload.__table__.update().values(expires_at=now() - timedelta(seconds=1)))
    session.commit()
    report = RetentionService(session).run(limit=10, apply=True)
    assert report["temporary_records"]["audio_uploads"]["removed"] == 1
    assert session.scalar(select(func.count()).select_from(AudioUpload)) == 0


def test_hosted_demo_always_disables_transcription():
    env = demo_environment(
        {
            "PUBLIC_DEMO_MODE": "true",
            "DATABASE_URL": "postgresql://synthetic:synthetic@localhost/demo",
            "APP_ORIGIN": "https://demo.example.test",
            "CLIENT_IDENTITY_MODE": "shared",
            "transcription_enabled": "true",
        }
    )
    assert env["TRANSCRIPTION_ENABLED"] == "false"
    assert "transcription_enabled" not in env


def test_upload_endpoint_queues_audio_through_http(client, session, seeded, enabled):
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.test", "password": "synthetic-test-password"},
        headers={"Origin": settings.app_origin},
    )
    assert login.status_code == 200
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": login.json()["csrf_token"]}
    response = client.post(
        "/api/workspaces/" + seeded["workspace"].id + "/transcribe",
        files={"file": ("sync.mp3", b"synthetic-audio", "audio/mpeg")},
        data={"meeting_id": "audio-api", "title": "API sync", "visibility": "restricted"},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    assert response.json()["meeting_id"] == "audio-api"
    job = session.get(Job, response.json()["job_id"])
    assert job.kind == "transcribe" and job.payload["visibility"] == "restricted"
    invalid = client.post(
        "/api/workspaces/" + seeded["workspace"].id + "/transcribe",
        files={"file": ("sync.mp3", b"synthetic-audio", "audio/mpeg")},
        data={"meeting_id": "not a valid id!"},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_word_error_rate_counts_substitutions_deletions_and_insertions():
    from scripts.evaluate_transcription import word_error_rate, words

    reference = words("Alex will prepare the checklist.")
    assert word_error_rate(reference, words("alex will prepare the checklist")) == 0
    assert word_error_rate(reference, words("Alex will review the checklist")) == 1 / 5
    assert word_error_rate(reference, words("Alex prepare the checklist")) == 1 / 5
    assert word_error_rate(reference, words("Alex will prepare the new checklist")) == 1 / 5


def test_me_reports_audio_capability_only_when_enabled(client, seeded, monkeypatch):
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.test", "password": "synthetic-test-password"},
        headers={"Origin": settings.app_origin},
    )
    assert login.status_code == 200
    assert client.get("/api/me").json()["capabilities"]["can_transcribe_audio"] is False
    monkeypatch.setattr(settings, "transcription_enabled", True)
    assert client.get("/api/me").json()["capabilities"]["can_transcribe_audio"] is True


REAL_AUDIO = os.environ.get("M2O_REAL_TRANSCRIPTION_AUDIO")


@pytest.mark.skipif(
    not REAL_AUDIO or importlib.util.find_spec("faster_whisper") is None,
    reason="Opt-in: set M2O_REAL_TRANSCRIPTION_AUDIO and install requirements-ai.txt",
)
def test_real_model_transcribes_through_the_queue_into_a_meeting(session, seeded, enabled, monkeypatch):
    # Uses the real faster-whisper model end to end; never runs in CI.
    monkeypatch.setattr(
        settings, "transcription_model", os.environ.get("M2O_REAL_TRANSCRIPTION_MODEL", "small")
    )
    audio = Path(REAL_AUDIO or "")
    queued = queue(session, seeded, filename=audio.name, raw=audio.read_bytes(), meeting_id="real-audio")
    assert asyncio.run(run_once())
    session.expire_all()
    job = session.get(Job, queued["job_id"])
    assert job.state == "completed", job.error_code
    meeting = session.scalar(select(Meeting).where(Meeting.slug == "real-audio"))
    revision_text = session.scalar(
        select(TranscriptRevision.raw_text).where(TranscriptRevision.meeting_id == meeting.id)
    )
    print(f"\n[real model] {job.result} :: {revision_text[:120]!r}")
    assert len(revision_text.split()) > 10
    assert session.scalar(select(func.count()).select_from(AudioUpload)) == 0
