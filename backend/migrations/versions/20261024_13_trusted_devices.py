"""Trusted devices: browsers an account signed in from keep their own sign-in budget."""

import sqlalchemy as sa
from alembic import op

revision = "20261024_13"
down_revision = "20261011_12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trusted_devices",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_index("ix_trusted_devices_expires_at", "trusted_devices", ["expires_at"])


def downgrade():
    # Dropping only removes sign-in budgets; every browser simply signs in as untrusted.
    op.drop_index("ix_trusted_devices_expires_at", table_name="trusted_devices")
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
