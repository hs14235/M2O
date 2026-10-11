"""Fail closed on a database revision outside this release's tested schema."""

from functools import lru_cache

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

from . import database
from .services.errors import ServiceError
from .settings import BACKEND_ROOT


@lru_cache(maxsize=1)
def supported_revisions() -> frozenset[str]:
    # No arbitrary environment override. Expand this policy only with tested
    # old/new binary + schema compatibility when a later release requires it.
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def require_schema(connection: Connection) -> str:
    current = frozenset(MigrationContext.configure(connection).get_current_heads())
    if not current or current != supported_revisions():
        raise ServiceError(
            status_code=503,
            error="Database schema is incompatible; apply the reviewed migrations",
            extra={"code": "schema_incompatible"},
        )
    return ",".join(sorted(current))


def check_schema() -> None:
    with database.get_engine().connect() as connection:
        require_schema(connection)
