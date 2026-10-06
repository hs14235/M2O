from datetime import date

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from ..auth import Principal, require_role
from ..models import Meeting, PlanEntry, TranscriptRevision, WorkItem, now
from ..schemas import PlanInput, PlanPatch
from .common import audit, current_revision, meeting_access
from .errors import ServiceError


class PlanningService:
    def __init__(self, session: Session, principal: Principal):
        self.session, self.principal = session, principal

    def visible(self):
        return (
            Meeting.workspace_id == self.principal.workspace_id,
            Meeting.archived_at.is_(None),
            or_(
                Meeting.visibility == "workspace",
                Meeting.created_by == self.principal.user_id,
                true() if self.principal.role in {"owner", "reviewer"} else Meeting.visibility == "workspace",
            ),
        )

    @staticmethod
    def source(item: WorkItem, meeting: Meeting) -> dict:
        return {
            "item_id": item.id,
            "meeting_id": meeting.slug,
            "meeting_title": meeting.title,
            "title": item.title,
            "kind": item.kind,
            "item_version": item.version,
            "review_status": item.status,
            "due_date": item.due_date,
            "due_hint": item.due_hint,
        }

    def payload(self, entry: PlanEntry, item: WorkItem, meeting: Meeting, revision_number: int) -> dict:
        return {
            **self.source(item, meeting),
            "id": entry.id,
            "planned_on": entry.planned_on,
            "state": entry.state,
            "priority": entry.priority,
            "version": entry.version,
            "reviewed_version": entry.reviewed_version,
            "can_reconfirm": item.status == "approved" and revision_number == meeting.current_revision,
            "stale": item.status != "approved"
            or item.version != entry.reviewed_version
            or revision_number != meeting.current_revision,
        }

    def list(self, day: date) -> dict:
        rows = self.session.execute(
            select(PlanEntry, WorkItem, Meeting, TranscriptRevision.number)
            .join(WorkItem, WorkItem.id == PlanEntry.item_id)
            .join(Meeting, Meeting.id == WorkItem.meeting_id)
            .join(TranscriptRevision, TranscriptRevision.id == WorkItem.revision_id)
            .where(
                PlanEntry.user_id == self.principal.user_id,
                PlanEntry.planned_on == day.isoformat(),
                *self.visible(),
            )
            .order_by(PlanEntry.priority, PlanEntry.updated_at, PlanEntry.id)
            .limit(201)
        ).all()
        candidates = self.session.execute(
            select(WorkItem, Meeting)
            .join(Meeting, Meeting.id == WorkItem.meeting_id)
            .join(TranscriptRevision, TranscriptRevision.id == WorkItem.revision_id)
            .where(
                *self.visible(),
                WorkItem.status == "approved",
                WorkItem.kind.in_(["action", "follow_up"]),
                TranscriptRevision.number == Meeting.current_revision,
                ~select(PlanEntry.id)
                .where(PlanEntry.user_id == self.principal.user_id, PlanEntry.item_id == WorkItem.id)
                .exists(),
            )
            .order_by(WorkItem.updated_at.desc(), WorkItem.id)
            .limit(101)
        ).all()
        return {
            "entries": [self.payload(*row) for row in rows[:200]],
            "candidates": [self.source(*row) for row in candidates[:100]],
            "entries_truncated": len(rows) > 200,
            "candidates_truncated": len(candidates) > 100,
        }

    def reviewed(self, meeting_id: str, item_id: str, version: int):
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        item = self.session.scalar(
            select(WorkItem)
            .where(WorkItem.id == item_id, WorkItem.meeting_id == meeting.id)
            .with_for_update()
        )
        if item is None:
            raise ServiceError(status_code=404, error="Outcome not found", where="client")
        revision = current_revision(self.session, meeting)
        if item.status != "approved" or item.version != version or item.revision_id != revision.id:
            raise ServiceError(
                status_code=409,
                error="Review the current approved outcome before planning it",
                where="client",
            )
        if item.kind not in {"action", "follow_up"}:
            raise ServiceError(
                status_code=422,
                error="Only actions and follow-ups can enter your execution plan",
                where="client",
            )
        return item, meeting, revision

    def add(self, meeting_id: str, item_id: str, payload: PlanInput) -> dict:
        item, meeting, revision = self.reviewed(meeting_id, item_id, payload.expected_item_version)
        existing = self.session.scalar(
            select(PlanEntry).where(PlanEntry.user_id == self.principal.user_id, PlanEntry.item_id == item.id)
        )
        if existing:
            raise ServiceError(
                status_code=409,
                error="This outcome is already in your plan; update its planned date instead",
                where="client",
            )
        entry = PlanEntry(
            user_id=self.principal.user_id,
            item_id=item.id,
            planned_on=payload.planned_on.isoformat(),
            priority=payload.priority,
            reviewed_version=item.version,
        )
        self.session.add(entry)
        self.session.flush()
        audit(self.session, self.principal, "plan.created", entry.id, {"item_id": item.id})
        return self.payload(entry, item, meeting, revision.number)

    def patch(self, meeting_id: str, item_id: str, payload: PlanPatch) -> dict:
        item, meeting, revision = self.reviewed(meeting_id, item_id, payload.expected_item_version)
        entry = self.session.scalar(
            select(PlanEntry)
            .where(PlanEntry.user_id == self.principal.user_id, PlanEntry.item_id == item.id)
            .with_for_update()
        )
        if entry is None:
            raise ServiceError(status_code=404, error="Plan entry not found", where="client")
        if entry.version != payload.expected_version:
            raise ServiceError(
                status_code=409, error="Your plan changed; reload before saving", where="client"
            )
        if entry.reviewed_version != item.version and payload.state != "planned":
            raise ServiceError(
                status_code=409,
                error="Reconfirm the changed outcome as planned before continuing work",
                where="client",
            )
        entry.state, entry.priority = payload.state, payload.priority
        entry.planned_on, entry.reviewed_version = payload.planned_on.isoformat(), item.version
        entry.version += 1
        entry.updated_at = now()
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "plan.updated",
            entry.id,
            {"state": entry.state, "version": entry.version},
        )
        return self.payload(entry, item, meeting, revision.number)

    def remove(self, meeting_id: str, item_id: str) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        entry = self.session.scalar(
            select(PlanEntry)
            .join(WorkItem, WorkItem.id == PlanEntry.item_id)
            .where(
                PlanEntry.user_id == self.principal.user_id,
                WorkItem.id == item_id,
                WorkItem.meeting_id == meeting.id,
            )
            .with_for_update()
        )
        if entry is None:
            raise ServiceError(status_code=404, error="Plan entry not found", where="client")
        audit(self.session, self.principal, "plan.removed", entry.id)
        self.session.delete(entry)
        return {"ok": True}
