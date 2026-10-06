import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access_policy import workspace_access
from ..auth import Principal
from ..models import AuditEvent, Meeting, TranscriptRevision
from .errors import ServiceError


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def audit(session: Session, principal: Principal, action: str, target: str, details=None) -> None:
    session.add(
        AuditEvent(
            workspace_id=principal.workspace_id,
            actor_id=principal.user_id,
            action=action,
            target_id=target,
            details=details or {},
        )
    )


def meeting_access(session: Session, principal: Principal, slug: str, *, lock=False) -> Meeting:
    workspace_access(session, principal)
    query = select(Meeting).where(
        Meeting.workspace_id == principal.workspace_id, Meeting.slug == slug, Meeting.archived_at.is_(None)
    )
    if lock:
        query = query.with_for_update()
    meeting = session.scalar(query)
    if meeting is None or (
        meeting.visibility == "restricted"
        and principal.role not in {"owner", "reviewer"}
        and meeting.created_by != principal.user_id
    ):
        raise ServiceError(status_code=404, error="Meeting not found", where="client")
    return meeting


def current_revision(session: Session, meeting: Meeting) -> TranscriptRevision:
    revision = session.scalar(
        select(TranscriptRevision).where(
            TranscriptRevision.meeting_id == meeting.id, TranscriptRevision.number == meeting.current_revision
        )
    )
    if revision is None:
        raise ServiceError(status_code=409, error="Transcript revision is unavailable", where="server")
    return revision
