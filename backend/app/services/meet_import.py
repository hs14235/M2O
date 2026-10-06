"""Explicit exact-preview save with transactional workspace/source deduplication."""

import hashlib
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..access_policy import aware
from ..auth import Principal
from ..google_meet import GoogleMeetAdapter, connection_query, fail
from ..limits import consume
from ..models import GoogleMeetAccount, GoogleMeetPreview, Job, Meeting, MeetingImport, User, now
from ..schemas import IndexInput
from .common import audit, current_revision, fingerprint, meeting_access
from .meetings import MeetingService


class MeetImportService:
    def __init__(self, session: Session, principal: Principal, adapter: GoogleMeetAdapter | None = None):
        self.session, self.principal = session, principal
        self.adapter = adapter or GoogleMeetAdapter()

    def current_connection(self, connection_id: str, generation: str, auth_version: int):
        self.adapter.authority(self.session, self.principal, lock=True)
        user = self.session.get(User, self.principal.user_id)
        row = self.session.scalar(
            connection_query(self.principal).with_for_update().execution_options(populate_existing=True)
        )
        account = self.session.get(GoogleMeetAccount, row.id, populate_existing=True) if row else None
        if (
            not user
            or user.auth_version != auth_version
            or not row
            or row.id != connection_id
            or row.state != "connected"
            or not account
            or account.generation != generation
        ):
            fail("Google consent or account authority changed; create a fresh preview", 409)
        return row

    async def preview(self) -> dict:
        self.adapter.authority(self.session, self.principal)
        user = self.session.get(User, self.principal.user_id)
        assert user is not None
        version = user.auth_version
        consume(
            "meet-import:" + self.principal.user_id + ":" + self.principal.scope,
            10,
            3600,
            session=self.session,
        )
        connection_id, generation, token = await self.adapter.access(self.session, self.principal)
        transcript, source, participants = await self.adapter.fetch_latest(token)
        self.current_connection(connection_id, generation, version)
        # Keep at most three actor previews, removing expired/unneeded private text.
        existing = self.session.scalars(
            select(GoogleMeetPreview)
            .where(GoogleMeetPreview.user_id == self.principal.user_id)
            .order_by(GoogleMeetPreview.expires_at.desc())
        ).all()
        for row in existing[2:]:
            self.session.delete(row)
        self.session.execute(
            delete(GoogleMeetPreview).where(
                GoogleMeetPreview.user_id == self.principal.user_id, GoogleMeetPreview.expires_at <= now()
            )
        )
        payload_hash = fingerprint({"transcript": transcript, "source": source, "participants": participants})
        preview = GoogleMeetPreview(
            workspace_id=self.principal.scope,
            user_id=self.principal.user_id,
            auth_version=version,
            connection_id=connection_id,
            generation=generation,
            transcript=transcript,
            source=source,
            participants=participants,
            payload_hash=payload_hash,
            expires_at=now() + timedelta(minutes=15),
        )
        self.session.add(preview)
        self.session.flush()
        audit(self.session, self.principal, "google_meet.previewed", preview.id)
        return {
            "preview_id": preview.id,
            "payload_hash": payload_hash,
            "transcript": transcript,
            "source": source,
            "participants": participants,
            "expires_at": preview.expires_at.isoformat(),
        }

    def save(
        self,
        preview_id: str,
        payload_hash: str,
        title: str,
        meeting_id: str,
        *,
        visibility: Literal["workspace", "restricted"] = "restricted",
    ) -> dict:
        self.adapter.authority(self.session, self.principal, lock=True)
        preview = self.session.scalar(
            select(GoogleMeetPreview)
            .where(
                GoogleMeetPreview.id == preview_id,
                GoogleMeetPreview.workspace_id == self.principal.scope,
                GoogleMeetPreview.user_id == self.principal.user_id,
            )
            .with_for_update()
        )
        if not preview:
            fail("Import preview was not found", 404)
        if aware(preview.expires_at) <= now() or preview.payload_hash != payload_hash:
            fail("Import preview expired or changed; create a fresh preview", 409)
        if (
            fingerprint(
                {
                    "transcript": preview.transcript,
                    "source": preview.source,
                    "participants": preview.participants,
                }
            )
            != preview.payload_hash
        ):
            fail("Stored import preview changed; create a fresh preview", 409)
        row = self.current_connection(preview.connection_id, preview.generation, preview.auth_version)
        source = self.session.scalar(
            select(MeetingImport)
            .where(
                MeetingImport.workspace_id == self.principal.scope,
                MeetingImport.conference_record == preview.source["conference_record"],
            )
            .with_for_update()
        )
        content_hash = hashlib.sha256(preview.transcript.encode()).hexdigest()
        if source:
            meeting = self.session.get(Meeting, source.meeting_id)
            if not meeting:
                fail("Imported meeting is unavailable", 409)
            meeting = meeting_access(self.session, self.principal, meeting.slug, lock=True)
            revision = current_revision(self.session, meeting)
            if (
                source.content_hash != content_hash
                or revision.id != source.revision_id
                or revision.content_hash != content_hash
            ):
                fail(
                    "This imported source changed; use the meeting's explicit transcript replacement and review flow",
                    409,
                )
            job = self.session.scalar(
                select(Job)
                .where(Job.meeting_id == meeting.id, Job.kind == "index")
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            return {
                "ok": True,
                "meeting_id": meeting.slug,
                "version": meeting.version,
                "job_id": job.id if job else None,
                "chunks_indexed": None,
                "reindexed": False,
                "import_id": source.id,
                "reused": True,
            }
        # Never turn a caller-selected existing meeting into an implicit replacement.
        if self.session.scalar(
            select(Meeting.id).where(Meeting.workspace_id == self.principal.scope, Meeting.slug == meeting_id)
        ):
            fail("That meeting identifier already exists; choose a new identifier", 409)
        result = MeetingService(self.session, self.principal).index(
            IndexInput(
                meeting_id=meeting_id,
                title=title,
                transcript=preview.transcript,
                visibility=visibility,
                occurred_on=datetime.fromisoformat(preview.source["start_time"]).date(),
            )
        )
        meeting = meeting_access(self.session, self.principal, meeting_id)
        revision = current_revision(self.session, meeting)
        source = MeetingImport(
            workspace_id=self.principal.scope,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            connection_id=row.id,
            generation=preview.generation,
            conference_record=preview.source["conference_record"],
            content_hash=content_hash,
            revision_id=revision.id,
            source=preview.source,
        )
        self.session.add(source)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "google_meet.imported",
            source.id,
            {"meeting_id": meeting.id, "revision": revision.number},
        )
        return {**result, "import_id": source.id, "reused": False}
