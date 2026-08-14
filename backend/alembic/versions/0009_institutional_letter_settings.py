"""Institutional letter settings.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_profiles", sa.Column(
        "department", sa.String(200), nullable=False, server_default=""
    ))
    op.add_column("organization_profiles", sa.Column(
        "qr_verification_url", sa.String(1000), nullable=False, server_default=""
    ))
    op.add_column("organization_profiles", sa.Column(
        "barcode_text", sa.String(200), nullable=False, server_default=""
    ))


def downgrade() -> None:
    op.drop_column("organization_profiles", "barcode_text")
    op.drop_column("organization_profiles", "qr_verification_url")
    op.drop_column("organization_profiles", "department")
