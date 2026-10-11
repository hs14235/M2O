"""Apply forward migrations under a PostgreSQL advisory lock."""

import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database import check_database, get_engine
from app.services.errors import ServiceError
from app.settings import settings


def main():
    check_database()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with get_engine().connect() as lock:
        if lock.dialect.name == "postgresql":
            deadline = time.monotonic() + settings.migration_lock_timeout
            while True:
                acquired = lock.execute(text("SELECT pg_try_advisory_lock(674198234)")).scalar_one()
                # Session locks survive commit; don't leave an idle transaction
                # while waiting, or make Alembic borrow a second pool connection.
                lock.commit()
                if acquired:
                    break
                if time.monotonic() >= deadline:
                    raise ServiceError(status_code=503, error="Migration lock is temporarily unavailable")
                time.sleep(0.1)
        try:
            config.attributes["connection"] = lock
            command.upgrade(config, "head")
            lock.commit()
            print("Schema is at the current migration.")
        finally:
            if lock.dialect.name == "postgresql":
                if lock.in_transaction():
                    lock.rollback()
                lock.execute(text("SELECT pg_advisory_unlock(674198234)"))
                lock.commit()


if __name__ == "__main__":
    main()
