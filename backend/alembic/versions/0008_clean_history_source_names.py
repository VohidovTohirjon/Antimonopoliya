"""Normalize legacy source filenames stored in AI history JSON.

Revision ID: 0008
Revises: 0007
"""

from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        UPDATE ai_history h
        SET sources = (
          SELECT jsonb_agg(
            CASE
              WHEN item ->> 'document_name' LIKE 'demo_%%'
              THEN jsonb_set(item, '{document_name}', to_jsonb(regexp_replace(item ->> 'document_name', '^demo_', '')))
              ELSE item
            END
            ORDER BY position
          )::json
          FROM jsonb_array_elements(h.sources::jsonb) WITH ORDINALITY AS source(item, position)
        )
        WHERE h.sources::text LIKE '%%demo_%%'
    """)


def downgrade() -> None:
    pass
