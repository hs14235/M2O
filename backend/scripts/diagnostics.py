"""Print one local read-only operational snapshot; no uploads or periodic probes."""

import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.services.diagnostics import operational_snapshot


def main() -> int:
    # A fresh session plus database-enforced read-only transaction prevents this
    # operator report from flushing pending ORM changes or writing during inspection.
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
