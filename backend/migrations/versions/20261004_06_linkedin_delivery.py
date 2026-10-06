"""Preserve existing credentials and reviews while adding explicit LinkedIn drafts and consent."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_06"
down_revision = "20261003_05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("integration_oauth_states", sa.Column("nonce", sa.String(100)))
    op.create_table(
        "linkedin_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshots", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        sa.CheckConstraint("kind IN ('post','outreach')", name="ck_linkedin_draft_kind"),
        sa.CheckConstraint("version >= 1", name="ck_linkedin_draft_version"),
    )
    op.create_index("ix_linkedin_drafts_workspace_id", "linkedin_drafts", ["workspace_id"])
    op.create_table(
        "linkedin_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("linkedin_drafts.id"), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("provider_connections.id"), nullable=False),
        sa.Column("connection_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author", sa.String(250), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("snapshots", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        sa.CheckConstraint("draft_version >= 1", name="ck_linkedin_proposal_draft_version"),
    )
    op.create_index("ix_linkedin_proposals_workspace_id", "linkedin_proposals", ["workspace_id"])
    op.create_table(
        "linkedin_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "proposal_id", sa.String(36), sa.ForeignKey("linkedin_proposals.id"), nullable=False, unique=True
        ),
        sa.Column("delivery_key", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued','sending','completed','failed','uncertain')",
            name="ck_linkedin_operation_state",
        ),
    )


def downgrade():
    raise RuntimeError(
        "Retain draft, consent and publication history; use a reviewed forward migration or backup recovery"
    )
