from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from ..access_policy import account, consume_visitor_usage
from ..auth import Principal, require_role
from ..chunking import CHUNKING_VERSION, to_chunk_records
from ..models import (
    Job,
    Meeting,
    MeetingImport,
    Participant,
    ParticipantMention,
    TranscriptChunk,
    TranscriptRevision,
    now,
)
from ..schemas import IndexInput
from ..settings import settings
from .common import audit, current_revision, meeting_access
from .errors import ServiceError


class MeetingService:
    def __init__(self, session: Session, principal: Principal):
        self.session, self.principal = session, principal

    def validate_upload_filename(self, filename: str | None) -> str:
        extension = Path(filename or "").suffix.lower()
        if extension not in {".txt", ".md"}:
            raise ServiceError(status_code=400, error="Upload a UTF-8 .txt or .md transcript", where="client")
        return extension

    def decode_upload_text(self, filename: str | None, raw_bytes: bytes) -> str:
        self.validate_upload_filename(filename)
        if len(raw_bytes) > settings.max_upload_bytes:
            raise ServiceError(status_code=413, error="Transcript exceeds the upload limit", where="client")
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ServiceError(
                status_code=400, error="Transcript must be UTF-8 text", where="client"
            ) from exc
        if not text.strip() or "\x00" in text:
            raise ServiceError(status_code=400, error="Transcript must contain readable text", where="client")
        return text

    def index_meeting_text(self, meeting_id: str, title: str, raw_text: str, **options) -> dict:
        return self.index(IndexInput(meeting_id=meeting_id, title=title, transcript=raw_text, **options))

    def index(self, payload: IndexInput, *, trusted_demo_fixture: bool = False) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        if account(self.session, self.principal).is_visitor and not trusted_demo_fixture:
            raise ServiceError(
                status_code=403,
                error="Demo explorers can load approved synthetic examples; private transcripts require an invitation",
                where="client",
            )
        text = payload.transcript
        if len(text.encode("utf-8")) > settings.max_upload_bytes:
            raise ServiceError(status_code=413, error="Transcript exceeds the upload limit", where="client")
        if not text.strip() or "\x00" in text:
            raise ServiceError(status_code=400, error="Transcript must contain readable text", where="client")
        records = to_chunk_records(text)
        if len(records) > settings.max_chunks:
            raise ServiceError(status_code=413, error="Transcript contains too many chunks", where="client")
        session, principal = self.session, self.principal
        existing = session.scalar(
            select(Meeting)
            .where(Meeting.workspace_id == principal.workspace_id, Meeting.slug == payload.meeting_id)
            .with_for_update()
        )
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        if existing:
            meeting = meeting_access(session, principal, payload.meeting_id, lock=True)
            if payload.expected_version != meeting.version:
                raise ServiceError(
                    status_code=409,
                    error="Meeting changed; reload before replacing its transcript",
                    where="client",
                )
            previous = current_revision(session, meeting)
            if previous.content_hash == content_hash:
                meeting.title = payload.title or meeting.title
                meeting.version += 1
                meeting.updated_at = now()
                audit(session, principal, "meeting.metadata_updated", meeting.id)
                return {
                    "ok": True,
                    "meeting_id": meeting.slug,
                    "chunks_indexed": len(records),
                    "reindexed": False,
                    "version": meeting.version,
                    "job_id": None,
                }
            meeting.current_revision += 1
            meeting.version += 1
            meeting.title = payload.title or meeting.title
            meeting.updated_at = now()
        else:
            meeting = Meeting(
                workspace_id=principal.workspace_id,
                slug=payload.meeting_id,
                title=payload.title or payload.meeting_id,
                visibility=payload.visibility,
                created_by=principal.user_id,
                occurred_on=payload.occurred_on.isoformat() if payload.occurred_on else None,
                timezone=payload.timezone,
            )
            session.add(meeting)
            session.flush()
        revision = TranscriptRevision(
            meeting_id=meeting.id,
            number=meeting.current_revision,
            raw_text=text,
            content_hash=content_hash,
            chunking_version=CHUNKING_VERSION,
        )
        session.add(revision)
        session.flush()
        for record in records:
            session.add(
                TranscriptChunk(
                    revision_id=revision.id,
                    chunk_index=record["i"],
                    text=record["text"],
                    speaker=record["speaker"],
                    timestamp=record["timestamp"],
                    start_line=record["start_line"],
                )
            )
        for name in sorted({record["speaker"] for record in records if record["speaker"]}):
            session.add(
                ParticipantMention(
                    workspace_id=principal.workspace_id,
                    meeting_id=meeting.id,
                    revision_id=revision.id,
                    name=name,
                )
            )
        job = Job(
            workspace_id=principal.workspace_id,
            meeting_id=meeting.id,
            actor_id=principal.user_id,
            kind="index",
            payload={"revision_id": revision.id},
        )
        session.add(job)
        session.flush()
        audit(
            session,
            principal,
            "meeting.transcript_indexed",
            meeting.id,
            {"revision": revision.number, "chunk_count": len(records)},
        )
        return {
            "ok": True,
            "meeting_id": meeting.slug,
            "chunks_indexed": len(records),
            "reindexed": existing is not None,
            "version": meeting.version,
            "job_id": job.id,
        }

    def list(self, offset: int = 0, limit: int = 25, q: str | None = None) -> dict:
        principal = self.principal
        query = select(Meeting).where(
            Meeting.workspace_id == principal.workspace_id, Meeting.archived_at.is_(None)
        )
        if q and q.strip():
            literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(
                or_(
                    Meeting.title.ilike("%" + literal + "%", escape="\\"),
                    Meeting.slug.ilike("%" + literal + "%", escape="\\"),
                )
            )
        if principal.role not in {"owner", "reviewer"}:
            query = query.where(
                or_(Meeting.visibility == "workspace", Meeting.created_by == principal.user_id)
            )
        rows = self.session.scalars(
            query.order_by(Meeting.updated_at.desc(), Meeting.id).offset(offset).limit(limit + 1)
        ).all()
        return {
            "meetings": [self.summary(row) for row in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None,
        }

    @staticmethod
    def summary(meeting: Meeting) -> dict:
        return {
            "id": meeting.slug,
            "record_id": meeting.id,
            "title": meeting.title,
            "visibility": meeting.visibility,
            "version": meeting.version,
            "current_revision": meeting.current_revision,
            "created_at": meeting.created_at.isoformat(),
            "updated_at": meeting.updated_at.isoformat(),
            "occurred_on": meeting.occurred_on,
            "timezone": meeting.timezone,
        }

    def get(self, meeting_id: str) -> dict:
        from .review import ReviewService

        meeting = meeting_access(self.session, self.principal, meeting_id)
        revision = current_revision(self.session, meeting)
        chunks = self.session.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.revision_id == revision.id)
            .order_by(TranscriptChunk.chunk_index)
        ).all()
        mentions = self.session.scalars(
            select(ParticipantMention).where(ParticipantMention.revision_id == revision.id)
        ).all()
        directory = self.session.scalars(
            select(Participant).where(Participant.workspace_id == self.principal.workspace_id)
        ).all()

        def candidates(name):
            return [
                {"id": person.id, "name": person.name, "role": person.role}
                for person in directory
                if name.casefold() in {value.casefold() for value in [person.name, *person.aliases]}
            ]

        revisions = self.session.scalars(
            select(TranscriptRevision)
            .where(TranscriptRevision.meeting_id == meeting.id)
            .order_by(TranscriptRevision.number.desc())
        ).all()
        imported = self.session.scalar(select(MeetingImport).where(MeetingImport.meeting_id == meeting.id))
        return {
            **self.summary(meeting),
            "import_source": {
                **imported.source,
                "revision_id": imported.revision_id,
                "current": imported.revision_id == revision.id,
            }
            if imported
            else None,
            "revision_id": revision.id,
            "raw_text": revision.raw_text,
            "index_status": revision.index_status,
            "embedding_provider": revision.embed_provider,
            "chunks": [
                {
                    "id": chunk.id,
                    "i": chunk.chunk_index,
                    "text": chunk.text,
                    "speaker": chunk.speaker,
                    "timestamp": chunk.timestamp,
                    "start_line": chunk.start_line,
                }
                for chunk in chunks
            ],
            "chunk_count": len(chunks),
            "tasks": ReviewService(self.session, self.principal).list_items(meeting),
            "mentions": [
                {
                    "id": mention.id,
                    "name": mention.name,
                    "participant_id": mention.participant_id,
                    "confirmed": bool(mention.confirmed_by),
                    "candidates": candidates(mention.name),
                }
                for mention in mentions
            ],
            "revisions": [
                {"number": item.number, "id": item.id, "created_at": item.created_at.isoformat()}
                for item in revisions
            ],
        }

    def rename(self, meeting_id: str, title: str, expected_version: int) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id)
        result = self.session.execute(
            update(Meeting)
            .where(Meeting.id == meeting.id, Meeting.version == expected_version)
            .values(title=title, version=expected_version + 1, updated_at=now())
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ServiceError(status_code=409, error="Meeting changed; reload before saving", where="client")
        audit(self.session, self.principal, "meeting.renamed", meeting.id)
        self.session.expire(meeting)
        return self.summary(meeting)

    def delete(self, meeting_id: str) -> dict:
        require_role(self.principal, {"owner", "reviewer"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        meeting.archived_at = now()
        self.session.execute(
            update(Job).where(Job.meeting_id == meeting.id, Job.state == "queued").values(state="cancelled")
        )
        audit(self.session, self.principal, "meeting.archived", meeting.id)
        return {"ok": True, "deleted": meeting_id, "archived": True}

    def enqueue_extraction(self, meeting_id: str) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        # Visitor request budgets are acquired before meeting locks.
        user = account(self.session, self.principal)
        if user.is_visitor:
            from ..models import VisitorUsage

            self.session.scalar(select(VisitorUsage).where(VisitorUsage.user_id == user.id).with_for_update())
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        revision = current_revision(self.session, meeting)
        pending = self.session.scalar(
            select(Job).where(
                Job.meeting_id == meeting.id,
                Job.kind == "extract",
                Job.state.in_(["queued", "running"]),
                Job.payload["revision_id"].as_string() == revision.id,
            )
        )
        if pending:
            return {"job_id": pending.id, "state": pending.state}
        consume_visitor_usage(self.session, self.principal, jobs=True)
        job = Job(
            workspace_id=self.principal.workspace_id,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            kind="extract",
            payload={"revision_id": revision.id},
        )
        self.session.add(job)
        self.session.flush()
        audit(self.session, self.principal, "extraction.requested", meeting.id)
        return {"job_id": job.id, "state": job.state}
