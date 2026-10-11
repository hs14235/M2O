"""Print one local read-only operational snapshot; no uploads or periodic probes."""

import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.services.diagnostics import operational_snapshot


def main() -> int:
    # A fresh session keeps this report from flushing pending ORM changes. On
    # PostgreSQL the transaction is also database-enforced read-only; SQLite has
    # no equivalent, so there the guarantee rests on the snapshot issuing only reads.
    try:
        with Session(get_engine()) as session:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SET TRANSACTION READ ONLY"))
            report = operational_snapshot(session)
    except (SQLAlchemyError, RuntimeError):
        print(json.dumps({"error_code": "diagnostics_unavailable"}))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
