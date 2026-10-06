"""Explicit Slack identity confirmation, one-use actions, and durable replay acknowledgements."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_07"
down_revision = "20261004_06"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("slack_accounts", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("slack_accounts", "version", server_default=None)
    op.create_check_constraint("ck_slack_account_version", "slack_accounts", "version >= 1")
    op.create_table(
        "slack_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("slack_accounts.connection_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slack_user_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("account_version", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("workspace_id", "connection_id", "slack_user_id", name="uq_slack_member_mapping"),
        sa.UniqueConstraint("workspace_id", "connection_id", "user_id", name="uq_slack_user_mapping"),
        sa.CheckConstraint("version >= 1 AND account_version >= 1", name="ck_slack_identity_version"),
    )
    op.create_table(
        "slack_link_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("slack_accounts.connection_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_version", sa.Integer(), nullable=False),
        sa.Column(
            "session_hash",
            sa.String(64),
            sa.ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("pending_slack_user_id", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_slack_link_challenges_expires_at", "slack_link_challenges", ["expires_at"])
    op.create_table(
        "slack_interaction_contexts",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "identity_id",
            sa.String(36),
            sa.ForeignKey("slack_identities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledgement", sa.JSON()),
        sa.CheckConstraint("kind IN ('capture','plan')", name="ck_slack_context_kind"),
    )
    op.create_index("ix_slack_interaction_contexts_expires_at", "slack_interaction_contexts", ["expires_at"])
    op.create_table(
        "slack_inbound_receipts",
        sa.Column("request_hash", sa.String(64), primary_key=True),
        sa.Column("acknowledgement", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slack_inbound_receipts_expires_at", "slack_inbound_receipts", ["expires_at"])


def downgrade():
    raise RuntimeError(
        "Preserve identity and replay history; use a reviewed forward migration or backup recovery"
    )
