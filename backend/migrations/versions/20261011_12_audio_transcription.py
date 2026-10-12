"""Temporary uploaded audio and the transcribe job kind for local speech-to-text."""

import sqlalchemy as sa
from alembic import op

revision = "20261011_12"
down_revision = "20261005_11"
branch_labels = None
depends_on = None

PREVIOUS_KINDS = "'index','extract','publish','jira_publish','slack_publish','linkedin_publish'"


def upgrade():
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint("ck_job_kind", "jobs", f"kind IN ({PREVIOUS_KINDS},'transcribe')")
    op.create_table(
        "audio_uploads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("extension", sa.String(8), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_audio_uploads_workspace_id", "audio_uploads", ["workspace_id"])
    op.create_index("ix_audio_uploads_expires_at", "audio_uploads", ["expires_at"])


def downgrade():
    # Refuse to drop queued transcribe jobs silently; settle or delete them first.
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM jobs WHERE kind = 'transcribe'")):
        raise RuntimeError("Transcribe jobs exist; resolve them before downgrading")
    op.drop_index("ix_audio_uploads_expires_at", table_name="audio_uploads")
    op.drop_index("ix_audio_uploads_workspace_id", table_name="audio_uploads")
    op.drop_table("audio_uploads")
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint("ck_job_kind", "jobs", f"kind IN ({PREVIOUS_KINDS})")
