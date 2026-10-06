"""Read-only reviewed outcomes; scheduling and personal execution remain distinct."""

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..access_policy import workspace_access
from ..auth import Principal
from ..models import Meeting, Participant, PlanEntry, TranscriptRevision, WorkItem
from .common import meeting_access
from .errors import ServiceError
from .planning import PlanningService


class CalendarService:
    def __init__(self, session: Session, principal: Principal):
        self.session, self.principal = session, principal

    def list(
        self,
        start: date,
        end: date,
        *,
        meeting_id: str | None = None,
        include_unscheduled: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        workspace_access(self.session, self.principal)
        if end < start or (end - start).days > 92 or not 1 <= limit <= 200 or not 0 <= offset <= 10000:
            raise ServiceError(
                status_code=422,
                error="Use an ordered date range of at most 93 days and bounded pagination",
                where="client",
            )
        if meeting_id:
            meeting_access(self.session, self.principal, meeting_id)
        scheduled = WorkItem.due_date.between(start.isoformat(), end.isoformat())
        query = (
            select(WorkItem, Meeting, TranscriptRevision.number, Participant, PlanEntry)
            .join(Meeting, Meeting.id == WorkItem.meeting_id)
            .join(TranscriptRevision, TranscriptRevision.id == WorkItem.revision_id)
            .outerjoin(
                Participant,
                and_(Participant.id == WorkItem.owner_id, Participant.workspace_id == WorkItem.workspace_id),
            )
            .outerjoin(
                PlanEntry, and_(PlanEntry.item_id == WorkItem.id, PlanEntry.user_id == self.principal.user_id)
            )
            .where(
                *PlanningService(self.session, self.principal).visible(),
                WorkItem.status == "approved",
                TranscriptRevision.number == Meeting.current_revision,
                or_(scheduled, WorkItem.due_date.is_(None)) if include_unscheduled else scheduled,
            )
        )
        if meeting_id:
            query = query.where(Meeting.slug == meeting_id)
        rows = self.session.execute(
            query.order_by(WorkItem.due_date.asc().nulls_last(), Meeting.id, WorkItem.id)
            .offset(offset)
            .limit(limit + 1)
        ).all()
        entries = []
        for item, meeting, revision, person, plan in rows[:limit]:
            confirmed = person is not None and person.confirmed_by is not None
            entries.append(
                {
                    **PlanningService.source(item, meeting),
                    "meeting_version": meeting.version,
                    "revision_number": revision,
                    "scheduled": item.due_date is not None,
                    "owner_name": person.name if confirmed else "Unassigned",
                    "owner_confirmed": confirmed,
                    "personal_plan": {
                        "id": plan.id,
                        "state": plan.state,
                        "planned_on": plan.planned_on,
                        "version": plan.version,
                        "reviewed_version": plan.reviewed_version,
                        "stale": plan.reviewed_version != item.version,
                    }
                    if plan
                    else None,
                }
            )
        return {"entries": entries, "next_offset": offset + limit if len(rows) > limit else None}
