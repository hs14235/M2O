"""Add scoped Slack delivery and explicit GitHub binding without replacing existing records."""

import sqlalchemy as sa
from alembic import op

revision = "20261003_05"
down_revision = "20261003_04"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "provider_connections", "expires_at", existing_type=sa.DateTime(timezone=True), nullable=True
    )
    op.create_table(
        "github_destinations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False, unique=True),
        sa.Column("repo", sa.String(180), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configured_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_github_destination_version"),
    )
    op.add_column("publication_proposals", sa.Column("destination_id", sa.String(36)))
    op.add_column("publication_proposals", sa.Column("destination_version", sa.Integer()))
    op.create_foreign_key(
        "fk_publication_destination",
        "publication_proposals",
        "github_destinations",
        ["destination_id"],
        ["id"],
    )
    op.create_table(
        "slack_accounts",
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("team_id", sa.String(64), nullable=False),
        sa.Column("team_name", sa.String(200), nullable=False),
        sa.Column("bot_user_id", sa.String(64), nullable=False),
        sa.Column("bot_id", sa.String(64), nullable=False),
        sa.Column("installed_user_id", sa.String(64), nullable=False),
        sa.UniqueConstraint("app_id", "team_id", name="uq_slack_installation"),
    )
    op.create_table(
        "slack_destinations",
        sa.Column(
            "destination_id",
            sa.String(36),
            sa.ForeignKey("provider_destinations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("channel_name", sa.String(200), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "slack_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("destination", sa.JSON(), nullable=False),
        sa.Column("snapshots", sa.JSON(), nullable=False),
        sa.Column("target", sa.JSON()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        sa.CheckConstraint("action IN ('create','update')", name="ck_slack_action"),
    )
    op.create_index("ix_slack_proposals_workspace_id", "slack_proposals", ["workspace_id"])
    op.create_table(
        "slack_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "proposal_id", sa.String(36), sa.ForeignKey("slack_proposals.id"), nullable=False, unique=True
        ),
        sa.Column("delivery_key", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued','sending','completed','failed','uncertain')", name="ck_slack_operation_state"
        ),
    )
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind", "jobs", "kind IN ('index','extract','publish','jira_publish','slack_publish')"
    )


def downgrade():
    raise RuntimeError(
        "Retain delivery and destination history; use a reviewed forward migration or backup recovery"
    )
