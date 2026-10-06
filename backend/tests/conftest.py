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


@pytest.fixture
def engine(tmp_path, monkeypatch, request):
    postgres = request.config.getoption("--postgres")
    if postgres:
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
    else:
        engine = create_engine(
            "sqlite:///" + (tmp_path / "test.db").as_posix(), connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "get_engine", lambda: engine)
    monkeypatch.setattr(settings, "app_environment", "test")
    monkeypatch.setattr(settings, "embed_provider", "hash")
    monkeypatch.setattr(settings, "ollama_model", "")
    monkeypatch.setattr(settings, "public_demo_mode", True)
    monkeypatch.setattr(settings, "github_token", SecretStr(""))
    yield engine
    engine.dispose()
    if postgres:
        with base.begin() as connection:
            # Only the randomly named schema created by this fixture is removed.
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


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
