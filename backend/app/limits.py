from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import aware, digest
from .database import session_scope
from .models import RateBucket, now
from .services.errors import ServiceError


def consume(key: str, maximum=10, seconds=300, *, session: Session | None = None):
    hashed = digest(key)
    if session is not None:
        # Keep visitor mutation and endpoint budgets in one transaction. A second
        # SQLite writer would wait on this request's own already-written budget.
        insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        session.execute(
            insert(RateBucket)
            .values(key=hashed, count=0, expires_at=now() + timedelta(seconds=seconds))
            .on_conflict_do_nothing()
        )
        row = session.scalar(
            select(RateBucket)
            .where(RateBucket.key == hashed)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert row is not None
        if aware(row.expires_at) <= now():
            row.count, row.expires_at = 0, now() + timedelta(seconds=seconds)
        if row.count >= maximum:
            raise ServiceError(status_code=429, error="Too many requests; try again later", where="client")
        row.count += 1
        return
    # A first-request collision is retried only before the rate-limit mutation.
    for attempt in range(2):
        try:
            with session_scope() as session:
                row = session.scalar(select(RateBucket).where(RateBucket.key == hashed).with_for_update())
                if not row:
                    row = RateBucket(key=hashed, count=0, expires_at=now() + timedelta(seconds=seconds))
                    session.add(row)
                    session.flush()
                if aware(row.expires_at) <= now():
                    row.count, row.expires_at = 0, now() + timedelta(seconds=seconds)
                blocked = row.count >= maximum
                row.count += 0 if blocked else 1
            if blocked:
                raise ServiceError(
                    status_code=429, error="Too many requests; try again later", where="client"
                )
            return
        except IntegrityError:
            if attempt:
                raise
