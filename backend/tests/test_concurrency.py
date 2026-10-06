from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.orm import Session
from test_meeting_lifecycle import extracted

from app.models import WorkItem
from app.schemas import IndexInput, ItemPatch
from app.services.errors import ServiceError
from app.services.meetings import MeetingService
from app.services.review import ReviewService
from app.worker import claim


def test_two_postgres_workers_claim_distinct_jobs(engine, session, seeded):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock behavior requires the --postgres suite")
    service = MeetingService(session, seeded["principal"])
    for slug in ("first", "second"):
        service.index(IndexInput(meeting_id=slug, transcript="Action: Review synthetic controls."))
    session.commit()
    barrier = Barrier(2)

    def concurrent_claim(_):
        barrier.wait(timeout=10)
        return claim()

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(concurrent_claim, range(2)))
    assert all(record is not None for record in claims)
    assert len({record["id"] for record in claims}) == 2
    assert claim() is None


def test_two_postgres_reviews_cannot_overwrite_same_version(engine, session, seeded):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock behavior requires the --postgres suite")
    item = extracted(session, seeded)["tasks"][0]
    barrier = Barrier(2)

    def concurrent_review(number):
        with Session(engine, expire_on_commit=False) as transaction:
            barrier.wait(timeout=10)
            try:
                result = ReviewService(transaction, seeded["principal"]).patch(
                    "weekly",
                    item["id"],
                    ItemPatch(expected_version=1, title=f"Synthetic reviewer {number}"),
                )
                transaction.commit()
                return result["version"]
            except ServiceError as exc:
                transaction.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(concurrent_review, range(2)))
    assert sorted(results) == [2, 409]
    session.expire_all()
    assert session.get(WorkItem, item["id"]).version == 2
