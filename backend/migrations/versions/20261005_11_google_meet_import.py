"""Read-only Meet consent, expiring previews and unique workspace import provenance."""

import sqlalchemy as sa
from alembic import op

revision = "20261005_11"
down_revision = "20261004_10"
branch_labels = None
depends_on = None


def upgrade():
    for table, constraint in (
        ("provider_connections", "ck_provider_name"),
        ("integration_oauth_states", "ck_oauth_provider"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(
            constraint, table, "provider IN ('jira','slack','github','linkedin','google_meet')"
        )
    op.create_table(
        "google_meet_accounts",
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("generation", sa.String(36), nullable=False),
    )
    op.create_table(
        "google_meet_previews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_google_meet_previews_workspace_id", "google_meet_previews", ["workspace_id"])
    op.create_index("ix_google_meet_previews_expires_at", "google_meet_previews", ["expires_at"])
    op.create_table(
        "meeting_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("meeting_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("provider_connections.id"), nullable=False),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("conference_record", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("transcript_revisions.id"), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        sa.UniqueConstraint("workspace_id", "conference_record", name="uq_meet_import_source"),
        sa.UniqueConstraint("meeting_id", name="uq_meet_import_meeting"),
    )
    op.create_index("ix_meeting_imports_workspace_id", "meeting_imports", ["workspace_id"])


def downgrade():
    raise RuntimeError(
        "Meet provenance may be in use; downgrade requires a reviewed backup and data transition"
    )
