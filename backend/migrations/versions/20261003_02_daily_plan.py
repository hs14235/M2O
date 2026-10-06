"""Add personal execution plans without changing existing review state."""

import sqlalchemy as sa
from alembic import op

revision = "20261003_02"
down_revision = "20261001_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plan_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "item_id", sa.String(36), sa.ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("planned_on", sa.String(10), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("reviewed_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "item_id", name="uq_plan_user_item"),
        sa.CheckConstraint("state IN ('planned','in_progress','blocked','done')", name="ck_plan_state"),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 3 AND version >= 1 AND reviewed_version >= 1", name="ck_plan_values"
        ),
    )
    op.create_index("ix_plan_day", "plan_entries", ["user_id", "planned_on"])


def downgrade():
    raise RuntimeError("Daily plans contain user data; use a reviewed forward migration or backup recovery")
