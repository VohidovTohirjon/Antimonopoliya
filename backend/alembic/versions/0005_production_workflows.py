"""Production workflow, NHH metadata and organization profile.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("documents", "demo_key", new_column_name="seed_key")
    op.execute("ALTER INDEX IF EXISTS ix_documents_demo_key RENAME TO ix_documents_seed_key")
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("nhh_documents", sa.Column("official_number", sa.String(120), nullable=True))
    op.add_column("nhh_documents", sa.Column("adoption_date", sa.Date(), nullable=True))
    op.add_column("nhh_documents", sa.Column("extraction_status", sa.String(30), nullable=False, server_default="completed"))
    op.add_column("nhh_documents", sa.Column("indexing_status", sa.String(30), nullable=False, server_default="completed"))
    op.add_column("nhh_documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("nhh_documents", sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("nhh_documents", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_nhh_documents_official_number", "nhh_documents", ["official_number"])
    op.create_index("ix_nhh_documents_extraction_status", "nhh_documents", ["extraction_status"])
    op.create_index("ix_nhh_documents_indexing_status", "nhh_documents", ["indexing_status"])
    op.execute("UPDATE nhh_documents SET indexed_at = updated_at WHERE indexed = true")

    op.add_column("tasks", sa.Column("priority", sa.String(10), nullable=False, server_default="odatiy"))
    op.add_column("tasks", sa.Column("related_document_id", sa.String(36), nullable=True))
    op.add_column("tasks", sa.Column("seed_key", sa.String(120), nullable=True))
    op.add_column("tasks", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_tasks_related_document", "tasks", "documents", ["related_document_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_related_document_id", "tasks", ["related_document_id"])
    op.create_index("ix_tasks_seed_key", "tasks", ["seed_key"], unique=True)
    op.execute("UPDATE tasks SET seed_key = 'legacy-operational:' || id WHERE title ~* '^\\[DEMO\\]'")
    op.execute("UPDATE tasks SET title = regexp_replace(title, '^\\[DEMO\\]\\s*', '', 'i') WHERE title ~* '^\\[DEMO\\]'")
    op.execute("UPDATE documents SET filename = regexp_replace(filename, '^demo_', '') WHERE filename LIKE 'demo_%'")
    op.execute("UPDATE users SET username = 'rahbar_analitika', full_name = 'Analitika bo‘limi rahbari' WHERE username = 'demo_rahbar'")
    op.execute("UPDATE users SET username = 'xodim_huquq', full_name = 'Huquqiy tahlil bo‘yicha xodim' WHERE username = 'demo_xodim'")

    op.create_table(
        "task_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("changes", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index("ix_task_events_actor_id", "task_events", ["actor_id"])
    op.create_index("ix_task_events_event_type", "task_events", ["event_type"])

    op.create_table(
        "organization_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_name", sa.String(300), nullable=False, server_default=""),
        sa.Column("short_name", sa.String(160), nullable=False, server_default=""),
        sa.Column("address", sa.String(500), nullable=False, server_default=""),
        sa.Column("phone", sa.String(120), nullable=False, server_default=""),
        sa.Column("email", sa.String(200), nullable=False, server_default=""),
        sa.Column("website", sa.String(300), nullable=False, server_default=""),
        sa.Column("outgoing_prefix", sa.String(60), nullable=False, server_default=""),
        sa.Column("signatory_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("signatory_title", sa.String(200), nullable=False, server_default=""),
        sa.Column("logo_stored_name", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("organization_profiles")
    op.drop_index("ix_task_events_event_type", table_name="task_events")
    op.drop_index("ix_task_events_actor_id", table_name="task_events")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_tasks_seed_key", table_name="tasks")
    op.drop_index("ix_tasks_related_document_id", table_name="tasks")
    op.drop_index("ix_tasks_priority", table_name="tasks")
    op.drop_constraint("fk_tasks_related_document", "tasks", type_="foreignkey")
    for column in ("completed_at", "updated_at", "seed_key", "related_document_id", "priority"):
        op.drop_column("tasks", column)
    op.drop_index("ix_nhh_documents_indexing_status", table_name="nhh_documents")
    op.drop_index("ix_nhh_documents_extraction_status", table_name="nhh_documents")
    op.drop_index("ix_nhh_documents_official_number", table_name="nhh_documents")
    for column in ("indexed_at", "uploaded_at", "processing_error", "indexing_status", "extraction_status", "adoption_date", "official_number"):
        op.drop_column("nhh_documents", column)
    op.drop_column("users", "last_login_at")
    op.execute("ALTER INDEX IF EXISTS ix_documents_seed_key RENAME TO ix_documents_demo_key")
    op.alter_column("documents", "seed_key", new_column_name="demo_key")
