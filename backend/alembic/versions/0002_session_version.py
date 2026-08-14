"""Sessiyalarni bekor qilish uchun foydalanuvchi token versiyasi.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("users", "token_version", server_default=None)
    op.alter_column("documents", "is_confidential", server_default=sa.false())


def downgrade():
    op.alter_column("documents", "is_confidential", server_default=None)
    op.drop_column("users", "token_version")
