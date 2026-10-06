"""Isolated synthetic visitors with independent authority, expiry and bounded usage."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_09"
down_revision = "20261004_08"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_visitor", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("visitor_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("users", "is_visitor", server_default=None)
    op.create_check_constraint(
        "ck_visitor_expiry", "users", "NOT is_visitor OR visitor_expires_at IS NOT NULL"
    )
    op.create_index("ix_user_visitor_expiry", "users", ["is_visitor", "visitor_expires_at"])
    op.add_column("workspaces", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("workspaces", sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("workspaces", "is_demo", server_default=None)
    op.create_check_constraint(
        "ck_demo_workspace_expiry", "workspaces", "NOT is_demo OR demo_expires_at IS NOT NULL"
    )
    op.create_table(
        "demo_admission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.CheckConstraint("id = 1", name="ck_demo_admission_singleton"),
    )
    op.bulk_insert(sa.table("demo_admission", sa.column("id", sa.Integer())), [{"id": 1}])
    op.create_table(
        "visitor_usage",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mutations", sa.Integer(), nullable=False),
        sa.Column("jobs", sa.Integer(), nullable=False),
        sa.CheckConstraint("mutations >= 0 AND jobs >= 0", name="ck_visitor_usage_nonnegative"),
    )


def downgrade():
    raise RuntimeError(
        "Preserve visitor authority and history; use a reviewed forward migration or backup recovery"
    )
