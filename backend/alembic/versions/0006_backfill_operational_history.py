"""Backfill existing operational task history and verified NHH number metadata.

Revision ID: 0006
Revises: 0005
"""

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    # Stable UUID-shaped ids derived from existing task ids make this backfill idempotent.
    connection.exec_driver_sql("""
        INSERT INTO task_events (id, task_id, actor_id, event_type, message, changes, created_at)
        SELECT
          substr(md5(t.id || '-created'), 1, 8) || '-' ||
          substr(md5(t.id || '-created'), 9, 4) || '-' ||
          substr(md5(t.id || '-created'), 13, 4) || '-' ||
          substr(md5(t.id || '-created'), 17, 4) || '-' ||
          substr(md5(t.id || '-created'), 21, 12),
          t.id, t.created_by, 'created', 'Mavjud topshiriq tarixga olindi',
          json_build_object('status', t.status, 'source', 'migration'), t.created_at
        FROM tasks t
        WHERE NOT EXISTS (
          SELECT 1 FROM task_events e WHERE e.task_id = t.id AND e.event_type = 'created'
        )
    """)
    # Only copy a document number that is already present verbatim in verified metadata.
    connection.exec_driver_sql("""
        UPDATE nhh_documents
        SET official_number = (regexp_match(title, '((O|O‘|O’|O'')RQ-[0-9]+)', 'i'))[1]
        WHERE official_number IS NULL
          AND title ~* '(O|O‘|O’|O'')RQ-[0-9]+'
          AND source_url LIKE 'https://lex.uz/%%'
    """)


def downgrade() -> None:
    op.execute("DELETE FROM task_events WHERE changes ->> 'source' = 'migration'")
