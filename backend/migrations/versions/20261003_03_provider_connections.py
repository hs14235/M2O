"""Add encrypted account grants and workspace-bound provider destinations."""

import sqlalchemy as sa
from alembic import op

revision = "20261003_03"
down_revision = "20261003_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_provider_account"),
        sa.UniqueConstraint("id", "user_id", name="uq_provider_owner"),
        sa.CheckConstraint("provider IN ('jira','slack','github','linkedin')", name="ck_provider_name"),
        sa.CheckConstraint("state IN ('connected','reauthorization_required')", name="ck_provider_state"),
    )
    op.create_table(
        "provider_destinations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("resource_id", sa.String(36)),
        sa.Column("resource_name", sa.String(200)),
        sa.Column("resource_url", sa.String(250)),
        sa.Column("project_key", sa.String(40)),
        sa.Column("project_name", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["provider_connections.id", "provider_connections.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("workspace_id", "connection_id", name="uq_provider_workspace"),
        sa.CheckConstraint("version >= 1", name="ck_destination_version"),
    )
    op.create_index("ix_provider_destinations_workspace_id", "provider_destinations", ["workspace_id"])
    op.create_table(
        "integration_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column(
            "session_hash",
            sa.String(64),
            sa.ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("provider IN ('jira','slack','github','linkedin')", name="ck_oauth_provider"),
    )
    op.create_index("ix_integration_oauth_states_expires_at", "integration_oauth_states", ["expires_at"])


def downgrade():
    raise RuntimeError("Provider grants contain user data; use reviewed forward migration or backup recovery")
