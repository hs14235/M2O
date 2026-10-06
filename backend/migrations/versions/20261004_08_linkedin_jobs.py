"""Allow reviewed LinkedIn jobs after the explicit publishing handler is implemented."""

from alembic import op

revision = "20261004_08"
down_revision = "20261004_07"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_job_kind", "jobs", type_="check")
    op.create_check_constraint(
        "ck_job_kind",
        "jobs",
        "kind IN ('index','extract','publish','jira_publish','slack_publish','linkedin_publish')",
    )


def downgrade():
    raise RuntimeError(
        "Preserve queued publication history; use a reviewed forward migration or backup recovery"
    )
