"""Apply forward migrations under a PostgreSQL advisory lock."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database import check_database, get_engine


def main():
    check_database()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with get_engine().connect() as lock:
        if lock.dialect.name == "postgresql":
            lock.execute(text("SELECT pg_advisory_lock(674198234)"))
        try:
            command.upgrade(config, "head")
            print("Schema is at the current migration.")
        finally:
            if lock.dialect.name == "postgresql":
                lock.execute(text("SELECT pg_advisory_unlock(674198234)"))


if __name__ == "__main__":
    main()
