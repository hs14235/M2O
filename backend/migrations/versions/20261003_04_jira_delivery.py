"""Persist exact Jira proposals, delivery intents and receipts without altering existing data."""

import sqlalchemy as sa
from alembic import op

revision = "20261003_04"
down_revision = "20261003_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jira_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("destination", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        sa.CheckConstraint("action IN ('create','update')", name="ck_jira_action"),
    )
    op.create_index("ix_jira_proposals_workspace_id", "jira_proposals", ["workspace_id"])
    op.create_table(
        "jira_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "proposal_id", sa.String(36), sa.ForeignKey("jira_proposals.id"), nullable=False, unique=True
        ),
        sa.Column("delivery_key", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued','sending','completed','failed','uncertain')", name="ck_jira_operation_state"
        ),
    )
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint("ck_job_kind", "jobs", "kind IN ('index','extract','publish','jira_publish')")


def downgrade():
    raise RuntimeError("Delivery history must be retained; use reviewed forward migration or backup recovery")
