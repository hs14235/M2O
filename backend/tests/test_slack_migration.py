import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, inspect, select, text
from test_jira import connected
from test_jira import jira as jira

from app.auth import aware
from app.models import Base, ProviderConnection, now
from app.services.errors import ServiceError


def test_jira_null_expiry_requires_reconnect_without_provider_call(session, jira):
    calls = []
    adapter, _ = connected(session, jira, calls)
    row = session.scalar(select(ProviderConnection))
    row.expires_at = None
    session.commit()
    before = len(calls)
    with pytest.raises(ServiceError, match="expiry"):
        asyncio.run(adapter.access(session, jira))
    assert len(calls) == before


def test_upgrade_preserves_jira_token_expiry_and_existing_proposals(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("Forward migration requires PostgreSQL")
    schema = "mtt_migration_" + uuid4().hex
    identifier, workspace, meeting, proposal, connection_id = [str(uuid4()) for _ in range(5)]
    expiry = now() + timedelta(hours=1)
    with engine.connect() as connection:
        original = connection.execute(text("SHOW search_path")).scalar_one()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        try:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "20261003_04")
            legacy = MetaData()
            legacy.reflect(bind=connection)
            tables = legacy.tables
            connection.execute(
                tables["users"]
                .insert()
                .values(
                    id=identifier,
                    email="migration@example.test",
                    name="Synthetic Migration",
                    password_hash="synthetic-hash",
                    active=True,
                    created_at=now(),
                )
            )
            connection.execute(
                tables["workspaces"]
                .insert()
                .values(id=workspace, name="Synthetic Migration", department="engineering", created_at=now())
            )
            connection.execute(
                tables["meetings"]
                .insert()
                .values(
                    id=meeting,
                    workspace_id=workspace,
                    slug="migration",
                    title="Synthetic",
                    created_by=identifier,
                    current_revision=1,
                    version=1,
                    visibility="workspace",
                    timezone="UTC",
                    created_at=now(),
                    updated_at=now(),
                )
            )
            connection.execute(
                tables["provider_connections"]
                .insert()
                .values(
                    id=connection_id,
                    user_id=identifier,
                    provider="jira",
                    state="connected",
                    encrypted_credentials="synthetic-ciphertext",
                    scopes=["read:jira-work", "write:jira-work"],
                    expires_at=expiry,
                    updated_at=now(),
                )
            )
            connection.execute(
                tables["publication_proposals"]
                .insert()
                .values(
                    id=proposal,
                    workspace_id=workspace,
                    meeting_id=meeting,
                    repo="synthetic/example",
                    payload_hash="a" * 64,
                    payloads=[],
                    snapshots=[],
                    expires_at=expiry,
                    created_at=now(),
                )
            )
            connection.commit()
            command.upgrade(config, "head")
            tables = Base.metadata.tables
            result = connection.execute(
                select(
                    tables["provider_connections"].c.expires_at,
                    tables["provider_connections"].c.encrypted_credentials,
                ).where(tables["provider_connections"].c.id == connection_id)
            ).one()
            assert (
                aware(result.expires_at) == expiry and result.encrypted_credentials == "synthetic-ciphertext"
            )
            old = connection.execute(
                select(
                    tables["publication_proposals"].c.destination_id,
                    tables["publication_proposals"].c.destination_version,
                ).where(tables["publication_proposals"].c.id == proposal)
            ).one()
            assert old.destination_id is None and old.destination_version is None
            assert next(
                col
                for col in inspect(connection).get_columns("provider_connections")
                if col["name"] == "expires_at"
            )["nullable"]
            connection.commit()
            command.check(config)
        finally:
            connection.rollback()
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.execute(text("SELECT set_config('search_path', :path, false)"), {"path": original})
            connection.commit()
