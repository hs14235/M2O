import asyncio

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.models import Meeting, Participant, TranscriptChunk, WorkItem, WorkItemEvidence
from app.schemas import IndexInput, ItemPatch, ParticipantInput
from app.services.common import current_revision
from app.services.errors import ServiceError
from app.services.extraction import ExtractionService
from app.services.meetings import MeetingService
from app.services.retrieval import RetrievalService
from app.services.review import ReviewService
from app.worker import run_once


def indexed(
    session, seeded, text="Alex: Action: I will ship the API by Friday.\nMorgan: Decision: Keep evidence."
):
    result = MeetingService(session, seeded["principal"]).index(
        IndexInput(meeting_id="weekly", title="Weekly", transcript=text)
    )
    session.commit()
    assert asyncio.run(run_once())
    session.expire_all()
    return result


def extracted(session, seeded):
    indexed(session, seeded)
    service = MeetingService(session, seeded["principal"])
    service.enqueue_extraction("weekly")
    session.commit()
    assert asyncio.run(run_once())
    session.expire_all()
    return service.get("weekly")


def test_outcome_list_batches_evidence_in_two_queries(engine, session, seeded):
    details = extracted(session, seeded)
    meeting = session.scalar(select(Meeting).where(Meeting.slug == "weekly"))
    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        outcomes = ReviewService(session, seeded["principal"]).list_items(
            meeting, details["tasks"][0]["revision_id"]
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 2
    assert len(outcomes) == 2 and all(outcome["evidence"] for outcome in outcomes)


def test_reindex_is_revision_safe_and_preserves_reviews(session, seeded):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    review = ReviewService(session, seeded["principal"])
    edited = review.patch(
        "weekly", item["id"], ItemPatch(expected_version=item["version"], title="Human edited task")
    )
    session.commit()
    service = MeetingService(session, seeded["principal"])
    service.index(
        IndexInput(
            meeting_id="weekly",
            title="Renamed",
            transcript=details["raw_text"],
            expected_version=details["version"],
        )
    )
    session.commit()
    same = service.get("weekly")
    assert same["current_revision"] == 1
    assert next(task for task in same["tasks"] if task["id"] == item["id"])["title"] == "Human edited task"
    service.index(
        IndexInput(
            meeting_id="weekly",
            transcript="Action: Taylor to validate finance controls.",
            expected_version=same["version"],
        )
    )
    session.commit()
    latest = service.get("weekly")
    assert latest["current_revision"] == 2 and latest["tasks"] == []
    assert session.get(WorkItem, item["id"]).title == edited["title"]
    with pytest.raises(ServiceError, match="earlier transcript"):
        review.patch("weekly", item["id"], ItemPatch(expected_version=edited["version"], title="Stale"))


def test_reextract_keeps_human_edits(session, seeded):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, title="Edited by reviewer")
    )
    session.commit()
    MeetingService(session, seeded["principal"]).enqueue_extraction("weekly")
    session.commit()
    asyncio.run(run_once())
    session.expire_all()
    tasks = MeetingService(session, seeded["principal"]).get("weekly")["tasks"]
    assert len(tasks) == len(details["tasks"])
    assert next(task for task in tasks if task["id"] == item["id"])["title"] == "Edited by reviewer"


def test_vectors_survive_new_sessions_and_match_workspace(session, seeded, engine):
    indexed(session, seeded)
    hits = RetrievalService(session, seeded["principal"]).search("weekly", "ship API", 1)["results"]
    assert "API" in hits[0]["text"]
    from sqlalchemy.orm import Session

    with Session(engine) as restarted:
        assert (
            RetrievalService(restarted, seeded["principal"]).search("weekly", "ship API", 1)["results"][0][
                "id"
            ]
            == hits[0]["id"]
        )


def test_ambiguous_participant_requires_confirmation(session, seeded):
    review = ReviewService(session, seeded["principal"])
    for role in ("Engineer", "HR lead"):
        review.add_participant(ParticipantInput(name="Alex", role=role))
    session.commit()
    details = extracted(session, seeded)
    mention = next(row for row in details["mentions"] if row["name"] == "Alex")
    assert len(mention["candidates"]) == 2 and not mention["confirmed"]
    action = next(row for row in details["tasks"] if row["kind"] == "action")
    assert action["owner_id"] is None
    person = review.participants()[0]
    assert review.confirm_mention("weekly", mention["id"], person["id"])["drafts_assigned"] == 1
    session.commit()
    assert session.get(WorkItem, action["id"]).owner_id == person["id"]


def test_optimistic_review_and_approval_reset(session, seeded):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    review = ReviewService(session, seeded["principal"])
    approved = review.patch("weekly", item["id"], ItemPatch(expected_version=1, status="approved"))
    session.commit()
    with pytest.raises(ServiceError, match="changed"):
        review.patch("weekly", item["id"], ItemPatch(expected_version=1, title="Lost update"))
    edited = review.patch(
        "weekly", item["id"], ItemPatch(expected_version=approved["version"], title="Changed scope")
    )
    session.commit()
    assert edited["status"] == "draft" and edited["version"] == 3
    assert len(review.history("weekly", item["id"])) == 3


def test_database_rejects_confidence_cross_revision_evidence_and_owner(session, seeded):
    details = extracted(session, seeded)
    item = session.get(WorkItem, details["tasks"][0]["id"])
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            item.confidence = 2
            session.flush()
    other = Participant(
        workspace_id=seeded["isolated"].id, name="Other", role="", aliases=[], confirmed_by=seeded["other"].id
    )
    session.add(other)
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            item.owner_id = other.id
            session.flush()
    meeting = session.scalar(select(Meeting).where(Meeting.slug == "weekly"))
    MeetingService(session, seeded["principal"]).index(
        IndexInput(meeting_id="weekly", transcript="Action: Replace.", expected_version=meeting.version)
    )
    session.flush()
    newer = current_revision(session, meeting)
    chunk = session.scalar(select(TranscriptChunk).where(TranscriptChunk.revision_id == newer.id))
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(WorkItemEvidence(item_id=item.id, revision_id=item.revision_id, chunk_id=chunk.id))
            session.flush()


def test_late_extraction_cannot_overwrite_new_transcript(session, seeded):
    indexed(session, seeded)
    meeting = session.scalar(select(Meeting).where(Meeting.slug == "weekly"))
    old_revision = current_revision(session, meeting).id
    result = asyncio.run(ExtractionService(session).generate(old_revision))
    MeetingService(session, seeded["principal"]).index(
        IndexInput(
            meeting_id="weekly", transcript="Decision: Replace source.", expected_version=meeting.version
        )
    )
    session.flush()
    with pytest.raises(ServiceError, match="changed during extraction"):
        ExtractionService(session).persist(meeting, old_revision, result)


def test_archive_preserves_history_and_blocks_access(session, seeded):
    details = extracted(session, seeded)
    service = MeetingService(session, seeded["principal"])
    assert service.delete("weekly")["archived"]
    session.commit()
    assert session.get(WorkItem, details["tasks"][0]["id"])
    with pytest.raises(ServiceError):
        service.get("weekly")
