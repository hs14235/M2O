"""Editable local drafts with reviewed source versions and no provider side effects."""

from sqlalchemy import select

from ..auth import require_role
from ..models import LinkedInDraft, WorkItem, now
from ..schemas import LinkedInDraftInput, LinkedInDraftPatch
from .common import audit, current_revision, meeting_access
from .errors import ServiceError


class LinkedInDraftService:
    def __init__(self, session, principal):
        self.session, self.principal = session, principal

    def sources(self, meeting, versions: dict) -> list[dict]:
        revision = current_revision(self.session, meeting)
        snapshots = []
        for item_id, version in versions.items():
            item = self.session.get(WorkItem, item_id)
            if (
                not item
                or item.meeting_id != meeting.id
                or item.revision_id != revision.id
                or item.version != version
                or item.status != "approved"
            ):
                raise ServiceError(
                    status_code=409,
                    error="Draft sources must be current approved outcome versions",
                    where="client",
                )
            snapshots.append(
                {"item_id": item.id, "version": item.version, "revision_id": revision.id, "title": item.title}
            )
        return snapshots

    def current(self, row, meeting) -> bool:
        if not row.snapshots:
            return False
        revision = current_revision(self.session, meeting)
        return all(
            (item := self.session.get(WorkItem, source["item_id"])) is not None
            and item.meeting_id == meeting.id
            and item.revision_id == revision.id
            and item.version == source["version"]
            and item.status == "approved"
            and source["revision_id"] == revision.id
            for source in row.snapshots
        )

    def serialize(self, row, meeting) -> dict:
        return {
            "id": row.id,
            "kind": row.kind,
            "text": row.text,
            "version": row.version,
            "sources": row.snapshots,
            "source_stale": not self.current(row, meeting),
            "actor_id": row.actor_id,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def list(self, meeting_id: str) -> list[dict]:
        meeting = meeting_access(self.session, self.principal, meeting_id)
        rows = self.session.scalars(
            select(LinkedInDraft)
            .where(
                LinkedInDraft.workspace_id == self.principal.workspace_id,
                LinkedInDraft.meeting_id == meeting.id,
            )
            .order_by(LinkedInDraft.updated_at.desc(), LinkedInDraft.id.desc())
            .limit(50)
        )
        return [self.serialize(row, meeting) for row in rows]

    def get(self, meeting_id: str, draft_id: str, *, lock=False):
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=lock)
        query = select(LinkedInDraft).where(
            LinkedInDraft.id == draft_id,
            LinkedInDraft.workspace_id == self.principal.workspace_id,
            LinkedInDraft.meeting_id == meeting.id,
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise ServiceError(status_code=404, error="LinkedIn draft not found", where="client")
        return row, meeting

    def create(self, meeting_id: str, payload: LinkedInDraftInput) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        if not payload.text.strip():
            raise ServiceError(status_code=422, error="Draft text cannot be blank", where="client")
        row = LinkedInDraft(
            workspace_id=self.principal.workspace_id,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            kind=payload.kind,
            text=payload.text,
            version=1,
            snapshots=self.sources(meeting, payload.versions),
        )
        self.session.add(row)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "linkedin.draft_created",
            row.id,
            {"kind": row.kind, "version": row.version},
        )
        return self.serialize(row, meeting)

    def update(self, meeting_id: str, draft_id: str, payload: LinkedInDraftPatch) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        row, meeting = self.get(meeting_id, draft_id, lock=True)
        if row.actor_id != self.principal.user_id and self.principal.role not in {"owner", "reviewer"}:
            raise ServiceError(
                status_code=403, error="Only the author or a reviewer may edit this draft", where="client"
            )
        if row.version != payload.expected_version:
            raise ServiceError(status_code=409, error="Draft changed; reload before editing", where="client")
        if not payload.text.strip():
            raise ServiceError(status_code=422, error="Draft text cannot be blank", where="client")
        row.snapshots = self.sources(meeting, payload.versions)
        row.text, row.kind, row.version, row.updated_at = payload.text, payload.kind, row.version + 1, now()
        audit(self.session, self.principal, "linkedin.draft_updated", row.id, {"version": row.version})
        return self.serialize(row, meeting)
