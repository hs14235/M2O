from collections.abc import Sequence
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from ..auth import Principal, require_role
from ..models import (
    Meeting,
    Participant,
    ParticipantMention,
    TranscriptChunk,
    WorkItem,
    WorkItemEvidence,
    WorkItemRevision,
    now,
)
from ..schemas import ItemPatch, ParticipantInput
from .common import audit, current_revision, meeting_access
from .errors import ServiceError


class ReviewService:
    def __init__(self, session: Session, principal: Principal):
        self.session, self.principal = session, principal

    def item_payload(self, item: WorkItem, chunks: Sequence[TranscriptChunk] | None = None) -> dict:
        if chunks is None:
            chunks = self.session.scalars(
                select(TranscriptChunk)
                .join(WorkItemEvidence, WorkItemEvidence.chunk_id == TranscriptChunk.id)
                .where(WorkItemEvidence.item_id == item.id)
                .order_by(TranscriptChunk.chunk_index)
            ).all()
        return {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "body": item.body,
            "labels": item.labels,
            "status": item.status,
            "owner_id": item.owner_id,
            "assignee_hint": item.assignee_hint,
            "due_hint": item.due_hint,
            "due_date": item.due_date,
            "confidence": item.confidence,
            "version": item.version,
            "revision_id": item.revision_id,
            "source_i": chunks[0].chunk_index if chunks else None,
            "evidence": [
                {
                    "id": chunk.id,
                    "i": chunk.chunk_index,
                    "text": chunk.text,
                    "speaker": chunk.speaker,
                    "start_line": chunk.start_line,
                }
                for chunk in chunks
            ],
        }

    def list_items(self, meeting: Meeting, revision_id: str | None = None) -> list[dict]:
        revision_id = revision_id or current_revision(self.session, meeting).id
        items = self.session.scalars(
            select(WorkItem)
            .where(WorkItem.meeting_id == meeting.id, WorkItem.revision_id == revision_id)
            .order_by(WorkItem.updated_at, WorkItem.id)
        ).all()
        if not items:
            return []
        evidence: dict[str, list[TranscriptChunk]] = {}
        rows = self.session.execute(
            select(WorkItemEvidence.item_id, TranscriptChunk)
            .join(TranscriptChunk, TranscriptChunk.id == WorkItemEvidence.chunk_id)
            .where(WorkItemEvidence.item_id.in_([item.id for item in items]))
            .order_by(TranscriptChunk.chunk_index)
        )
        for item_id, chunk in rows:
            evidence.setdefault(item_id, []).append(chunk)
        return [self.item_payload(item, evidence.get(item.id, [])) for item in items]

    def patch(self, meeting_id: str, item_id: str, payload: ItemPatch) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        item = self.session.scalar(
            select(WorkItem)
            .where(WorkItem.id == item_id, WorkItem.meeting_id == meeting.id)
            .with_for_update()
        )
        if item is None:
            raise ServiceError(status_code=404, error="Outcome not found", where="client")
        if item.revision_id != current_revision(self.session, meeting).id:
            raise ServiceError(
                status_code=409,
                error="This outcome belongs to an earlier transcript revision",
                where="client",
            )
        if item.version != payload.expected_version:
            raise ServiceError(status_code=409, error="Outcome changed; reload before saving", where="client")
        values = payload.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"})
        for field in {"title", "body", "labels", "kind", "status"} & values.keys():
            if values[field] is None:
                raise ServiceError(status_code=422, error=f"{field} cannot be null", where="client")
        if values.get("owner_id"):
            owner = self.session.get(Participant, values["owner_id"])
            if owner is None or owner.workspace_id != self.principal.workspace_id:
                raise ServiceError(
                    status_code=422, error="Owner must be a confirmed workspace participant", where="client"
                )
        if values.get("status") == "approved":
            require_role(self.principal, {"owner", "reviewer"})
        transitions = {
            "draft": {"draft", "approved", "dismissed"},
            "approved": {"approved", "draft", "done", "dismissed"},
            "done": {"done", "draft"},
            "dismissed": {"dismissed", "draft"},
        }
        next_status = values.get("status", item.status)
        if next_status not in transitions[item.status]:
            raise ServiceError(
                status_code=409, error="Review this outcome before completing or approving it", where="client"
            )
        content_fields = set(values) - {"status"}
        if content_fields and item.status in {"approved", "done"} and values.get("status") != "approved":
            values["status"] = "draft"
        values.update(version=payload.expected_version + 1, updated_at=now())
        result = self.session.execute(
            update(WorkItem)
            .where(WorkItem.id == item.id, WorkItem.version == payload.expected_version)
            .values(**values)
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ServiceError(status_code=409, error="Outcome changed; reload before saving", where="client")
        self.session.expire(item)
        snapshot = self.item_payload(item)
        self.session.add(
            WorkItemRevision(
                item_id=item.id, version=item.version, actor_id=self.principal.user_id, payload=snapshot
            )
        )
        audit(
            self.session,
            self.principal,
            "outcome.reviewed",
            item.id,
            {"version": item.version, "status": item.status},
        )
        self.session.flush()
        return snapshot

    def history(self, meeting_id: str, item_id: str) -> list[dict]:
        meeting = meeting_access(self.session, self.principal, meeting_id)
        item = self.session.scalar(
            select(WorkItem).where(WorkItem.id == item_id, WorkItem.meeting_id == meeting.id)
        )
        if item is None:
            raise ServiceError(status_code=404, error="Outcome not found", where="client")
        revisions = self.session.scalars(
            select(WorkItemRevision)
            .where(WorkItemRevision.item_id == item_id)
            .order_by(WorkItemRevision.version.desc())
        ).all()
        return [
            {
                "version": row.version,
                "actor_id": row.actor_id,
                "created_at": row.created_at.isoformat(),
                "payload": row.payload,
            }
            for row in revisions
        ]

    def participants(self) -> list[dict]:
        rows = self.session.scalars(
            select(Participant)
            .where(Participant.workspace_id == self.principal.workspace_id)
            .order_by(Participant.name)
        ).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "role": row.role,
                "aliases": row.aliases,
                "github_login": row.github_login,
                "linkedin_url": row.linkedin_url,
                "linked_user_id": row.linked_user_id,
                "confirmed_at": row.confirmed_at.isoformat(),
                "provenance": "workspace_directory",
            }
            for row in rows
        ]

    def add_participant(self, payload: ParticipantInput) -> dict:
        from ..access_policy import require_private_scope
        from ..models import Membership

        require_role(self.principal, {"owner", "reviewer", "editor"})
        require_private_scope(self.session, self.principal)
        if payload.linked_user_id and (
            payload.linked_user_id != self.principal.user_id
            or self.session.get(Membership, (self.principal.workspace_id, payload.linked_user_id)) is None
        ):
            raise ServiceError(
                status_code=403, error="Participants can only link their own account", where="client"
            )
        participant = Participant(
            workspace_id=self.principal.workspace_id,
            confirmed_by=self.principal.user_id,
            **payload.model_dump(),
        )
        self.session.add(participant)
        self.session.flush()
        audit(self.session, self.principal, "participant.confirmed", participant.id)
        return {"id": participant.id, "name": participant.name}

    def confirm_mention(self, meeting_id: str, mention_id: str, participant_id: str) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        mention = self.session.scalar(
            select(ParticipantMention).where(
                ParticipantMention.id == mention_id,
                ParticipantMention.meeting_id == meeting.id,
                ParticipantMention.revision_id == current_revision(self.session, meeting).id,
            )
        )
        participant = self.session.get(Participant, participant_id)
        if not mention or not participant or participant.workspace_id != self.principal.workspace_id:
            raise ServiceError(status_code=404, error="Participant or mention not found", where="client")
        mention.participant_id, mention.confirmed_by = participant_id, self.principal.user_id
        items = self.session.scalars(
            select(WorkItem).where(
                WorkItem.meeting_id == meeting.id,
                WorkItem.revision_id == mention.revision_id,
                WorkItem.status == "draft",
            )
        ).all()
        updated = 0
        for item in items:
            if (
                item.assignee_hint or ""
            ).casefold() == mention.name.casefold() and item.owner_id != participant_id:
                self.patch(
                    meeting_id, item.id, ItemPatch(expected_version=item.version, owner_id=participant_id)
                )
                updated += 1
        audit(
            self.session,
            self.principal,
            "participant.mention_resolved",
            mention.id,
            {"participant_id": participant_id, "drafts_assigned": updated},
        )
        return {"ok": True, "drafts_assigned": updated}
