"""Remove legacy demo wording from operational records.

Revision ID: 0007
Revises: 0006
"""

from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE tasks
        SET description = 'Ichki ish jarayonida nazorat qilinadigan topshiriq.'
        WHERE description ILIKE '%development/demo%'
           OR description ILIKE '%namoyish%'
    """)
    op.execute("UPDATE tasks SET title = replace(title, 'NHH metadata ma’lumotlarini', 'NHH metama’lumotlarini')")
    op.execute("UPDATE tasks SET title = replace(title, 'Test hujjat parsing', 'Hujjat parsing')")


def downgrade() -> None:
    pass
