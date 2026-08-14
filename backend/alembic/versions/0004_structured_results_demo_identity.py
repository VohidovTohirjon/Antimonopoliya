"""Structured AI results and stable demo identities.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("demo_key", sa.String(120), nullable=True))
    op.create_index("ix_documents_demo_key", "documents", ["demo_key"], unique=True)
    op.add_column("ai_history", sa.Column("structured_data", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("ai_history", "structured_data")
    op.drop_index("ix_documents_demo_key", table_name="documents")
    op.drop_column("documents", "demo_key")
