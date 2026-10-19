import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app import database
from app.auth import Principal, digest, hasher
from app.models import ApiToken, Base, Membership, User, Workspace, now
from app.settings import settings


def pytest_addoption(parser):
    parser.addoption(
        "--postgres",
        action="store_true",
        help="Run against an isolated schema in configured local PostgreSQL",
    )


@pytest.fixture(autouse=True)
def offline_models(monkeypatch):
    # Unit/integration tests must stay deterministic even when local AI is enabled.
    # Provider tests explicitly configure their controlled transport afterward.
    monkeypatch.setattr(settings, "ollama_model", "")


def migrated_schema():
    base = create_engine(settings.database_url.get_secret_value(), hide_parameters=True)
    schema = "mtt_test_" + uuid.uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url.get_secret_value(),
        hide_parameters=True,
        connect_args={"options": "-csearch_path=" + schema},
    )
    with engine.begin() as connection:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return base, schema, engine


def drop_schemas(base, engine, *schemas):
    engine.dispose()
    with base.begin() as connection:
        # Only the randomly named schemas created by these fixtures are removed.
        for schema in schemas:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    base.dispose()


@pytest.fixture(scope="session")
def shared_postgres(request):
    # Migrating once per run and emptying every table after each test keeps tests
    # isolated without running all migrations per test (docs/study/05-test-database-isolation.md).
    if not request.config.getoption("--postgres"):
        yield None
        return
    base, schema, engine = migrated_schema()
    seed = schema + "_seed"
    with engine.begin() as connection:
        tables = (
            connection.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
                    "AND tablename <> 'alembic_version' ORDER BY tablename"
                )
            )
            .scalars()
            .all()
        )
        # Rows that migrations insert (such as the demo admission counter) are restored
        # after each truncate; alembic_version is never emptied, the schema guard reads it.
        seeded = [
            table
            for table in tables
            if connection.execute(text(f'SELECT EXISTS (SELECT 1 FROM "{table}")')).scalar_one()
        ]
        connection.execute(text(f'CREATE SCHEMA "{seed}"'))
        for table in seeded:
            connection.execute(text(f'CREATE TABLE "{seed}"."{table}" AS TABLE "{table}"'))
    truncate = "TRUNCATE " + ", ".join(f'"{table}"' for table in tables) + " RESTART IDENTITY CASCADE"

    def reset():
        with engine.begin() as connection:
            # A test that leaks an open transaction fails here instead of hanging the run.
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text(truncate))
            for table in seeded:
                connection.execute(text(f'INSERT INTO "{table}" SELECT * FROM "{seed}"."{table}"'))

    yield engine, reset
    drop_schemas(base, engine, schema, seed)


@pytest.fixture
def engine(tmp_path, monkeypatch, request, shared_postgres):
    postgres = request.config.getoption("--postgres")
    fresh = postgres and request.node.get_closest_marker("fresh_schema") is not None
    if fresh:
        base, schema, engine = migrated_schema()
    elif postgres:
        engine, reset = shared_postgres
    else:
        engine = create_engine(
            "sqlite:///" + (tmp_path / "test.db").as_posix(), connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        # SQLite fixtures model a migrated release, but do not claim migration
        # or row-lock evidence. PostgreSQL above executes the actual migrations.
        from app.schema_compatibility import supported_revisions

        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
            for revision in supported_revisions():
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                    {"revision": revision},
                )
    monkeypatch.setattr(database, "get_engine", lambda: engine)
    monkeypatch.setattr(settings, "app_environment", "test")
    monkeypatch.setattr(settings, "embed_provider", "hash")
    monkeypatch.setattr(settings, "ollama_model", "")
    monkeypatch.setattr(settings, "public_demo_mode", True)
    monkeypatch.setattr(settings, "github_token", SecretStr(""))
    yield engine
    if fresh:
        drop_schemas(base, engine, schema)
    elif postgres:
        reset()
    else:
        engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def seeded(session):
    user = User(
        email="owner@example.test",
        name="Synthetic Owner",
        password_hash=hasher.hash("synthetic-test-password"),
    )
    other = User(
        email="other@example.test", name="Other Owner", password_hash=hasher.hash("synthetic-test-password")
    )
    session.add_all([user, other])
    workspace = Workspace(name="Synthetic engineering", department="engineering")
    isolated = Workspace(name="Isolated HR", department="hr")
    session.add_all([workspace, isolated])
    session.flush()
    session.add_all(
        [
            Membership(user_id=user.id, workspace_id=workspace.id, role="owner"),
            Membership(user_id=other.id, workspace_id=isolated.id, role="owner"),
        ]
    )
    token = "synthetic-scoped-api-token"
    session.add(
        ApiToken(
            token_hash=digest(token),
            user_id=user.id,
            workspace_id=workspace.id,
            expires_at=now() + timedelta(days=1),
        )
    )
    session.commit()
    return {
        "user": user,
        "workspace": workspace,
        "other": other,
        "isolated": isolated,
        "token": token,
        "principal": Principal(user.id, workspace.id, "owner"),
    }


@pytest.fixture
def client(engine, seeded):
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth(seeded):
    return {"Authorization": "Bearer " + seeded["token"]}
