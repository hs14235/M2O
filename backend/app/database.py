from contextlib import contextmanager
from functools import lru_cache
from time import sleep
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .services.errors import ServiceError
from .settings import settings


def must_get[Record](session: Session, model: type[Record], identifier: Any) -> Record:
    row = session.get(model, identifier)
    if row is None:
        raise ServiceError(status_code=409, error="A required record is no longer available")
    return row


@lru_cache(maxsize=1)
def get_engine():
    url = settings.database_url.get_secret_value()
    if not url:
        raise RuntimeError("DATABASE_URL must be configured; run the local setup script")
    sqlite = url.startswith("sqlite")
    if sqlite and settings.app_environment != "test":
        raise RuntimeError("SQLite is supported only for isolated tests; configure PostgreSQL")
    options: dict[str, Any] = {"pool_pre_ping": True, "hide_parameters": True}
    if sqlite:
        options["connect_args"] = {"check_same_thread": False}
    else:
        options.update(pool_size=settings.db_pool_size, max_overflow=0, pool_timeout=settings.db_pool_timeout)
        options["connect_args"] = {"connect_timeout": 5}
    engine = create_engine(url, **options)
    if sqlite:

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


@contextmanager
def session_scope():
    with Session(get_engine(), expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_session():
    with session_scope() as session:
        yield session


def check_database(attempts: int = 3) -> None:
    for attempt in range(attempts):
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError:
            if attempt + 1 == attempts:
                raise
            sleep(0.25 * 2**attempt)
