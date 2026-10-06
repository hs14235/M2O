"""Invitation acceptance, operator recovery and explicit privacy lifecycle records."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_10"
down_revision = "20261004_09"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("users", "auth_version", server_default=None)
    op.create_check_constraint("ck_user_auth_version", "users", "auth_version >= 1")
    for table, field in (
        ("auth_sessions", "auth_version"),
        ("api_tokens", "auth_version"),
        ("jobs", "actor_auth_version"),
        ("slack_identities", "auth_version"),
    ):
        op.add_column(table, sa.Column(field, sa.Integer(), nullable=False, server_default="1"))
        op.alter_column(table, field, server_default=None)
    op.add_column("workspaces", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("workspaces", "version", server_default=None)
    op.add_column("workspaces", sa.Column("erasure_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workspaces", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_workspace_version", "workspaces", "version >= 1")
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("issued_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issuer_auth_version", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('owner','reviewer','editor','viewer')", name="ck_invitation_role"),
    )
    op.create_index("ix_invitation_workspace", "invitations", ["workspace_id", "created_at"])
    op.create_table(
        "password_recoveries",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_recoveries_user_id", "password_recoveries", ["user_id"])
    op.create_index("ix_password_recoveries_expires_at", "password_recoveries", ["expires_at"])
    op.create_table(
        "delivery_tombstones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("delivery_key", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("retained_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "operation_id", name="uq_tombstone_operation"),
        sa.CheckConstraint("provider IN ('github','jira','slack','linkedin')", name="ck_tombstone_provider"),
    )
    op.create_index("ix_delivery_tombstones_workspace_id", "delivery_tombstones", ["workspace_id"])
    op.create_index("ix_delivery_tombstones_retained_until", "delivery_tombstones", ["retained_until"])


def downgrade():
    raise RuntimeError(
        "Preserve account revocation and privacy history; use a reviewed forward migration or backup recovery"
    )
