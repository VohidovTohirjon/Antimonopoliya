"""Extended official letterhead profile.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, length in (
        ("organization_name_secondary", 300),
        ("parent_organization", 300),
        ("tax_id", 40),
        ("letterhead_text", 1000),
        ("footer_text", 500),
    ):
        op.add_column("organization_profiles", sa.Column(
            name, sa.String(length), nullable=False, server_default=""
        ))


def downgrade() -> None:
    for name in (
        "footer_text", "letterhead_text", "tax_id",
        "parent_organization", "organization_name_secondary",
    ):
        op.drop_column("organization_profiles", name)
