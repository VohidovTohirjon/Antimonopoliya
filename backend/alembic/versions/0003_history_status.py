"""AI tarixida muvaffaqiyat, fallback va xatoni ajratish.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_history",
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
    )
    op.alter_column("ai_history", "status", server_default=None)
    op.create_index("ix_ai_history_status", "ai_history", ["status"])


def downgrade():
    op.drop_index("ix_ai_history_status", table_name="ai_history")
    op.drop_column("ai_history", "status")
