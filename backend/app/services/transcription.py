"""Queue uploaded meeting audio for local transcription into a new meeting."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access_policy import account
from ..auth import Principal, require_role
from ..models import AudioUpload, Job, Meeting, now
from ..schemas import IndexInput
from ..settings import settings
from .common import audit
from .errors import ServiceError

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".webm", ".flac", ".mp4"}
# Pending audio is removed by the worker once transcribed; this only bounds orphans.
AUDIO_RETENTION = timedelta(hours=24)


class TranscriptionService:
    def __init__(self, session: Session, principal: Principal):
        self.session, self.principal = session, principal

    def queue(self, filename: str | None, raw: bytes, details: IndexInput) -> dict:
        if not settings.transcription_enabled:
            raise ServiceError(
                status_code=404,
                error="Audio transcription is not enabled on this installation",
                where="client",
            )
        require_role(self.principal, {"owner", "reviewer", "editor"})
        if account(self.session, self.principal).is_visitor:
            raise ServiceError(
                status_code=403, error="Audio transcription requires a private workspace", where="client"
            )
        extension = Path(filename or "").suffix.lower()
        if extension not in AUDIO_EXTENSIONS:
            raise ServiceError(
                status_code=400,
                error="Upload audio as " + ", ".join(sorted(AUDIO_EXTENSIONS)),
                where="client",
            )
        if len(raw) > settings.transcription_max_bytes:
            raise ServiceError(status_code=413, error="Audio exceeds the upload limit", where="client")
        if not raw:
            raise ServiceError(status_code=400, error="The audio file is empty", where="client")
        # Audio always creates a new meeting; replacing a transcript needs its current version,
        # which a long-running job cannot hold safely.
        if self.session.scalar(
            select(Meeting.id).where(
                Meeting.workspace_id == self.principal.workspace_id, Meeting.slug == details.meeting_id
            )
        ):
            raise ServiceError(
                status_code=409,
                error="A meeting with this identifier exists; audio creates a new meeting",
                where="client",
            )
        audio = AudioUpload(
            workspace_id=self.principal.workspace_id,
            user_id=self.principal.user_id,
            extension=extension,
            byte_size=len(raw),
            content=raw,
            expires_at=now() + AUDIO_RETENTION,
        )
        self.session.add(audio)
        self.session.flush()
        job = Job(
            workspace_id=self.principal.workspace_id,
            meeting_id=None,
            actor_id=self.principal.user_id,
            kind="transcribe",
            payload={
                "audio_id": audio.id,
                "meeting_id": details.meeting_id,
                "title": details.title,
                "visibility": details.visibility,
                "occurred_on": details.occurred_on.isoformat() if details.occurred_on else None,
                "timezone": details.timezone,
            },
        )
        self.session.add(job)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "meeting.audio_queued",
            job.id,
            {"byte_size": len(raw), "extension": extension},
        )
        return {"ok": True, "job_id": job.id, "meeting_id": details.meeting_id}
