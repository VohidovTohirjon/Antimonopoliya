"""Boshlang‘ich ishlab chiqarish sxemasi.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    role = sa.Enum("administrator", "rahbar", "xodim", name="role", native_enum=False)
    task_status = sa.Enum("yangi", "jarayonda", "bajarildi", name="taskstatus", native_enum=False)
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("username", sa.String(80), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", role, nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("username"))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_table("documents",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(255), nullable=False, unique=True),
        sa.Column("media_type", sa.String(120), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=False), sa.Column("category", sa.String(40), nullable=False),
        sa.Column("is_confidential", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_table("nhh_documents",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(500), nullable=False),
        sa.Column("category", sa.String(120), nullable=False), sa.Column("source_url", sa.String(1000)),
        sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(255), nullable=False, unique=True),
        sa.Column("original_text", sa.Text(), nullable=False), sa.Column("indexed", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_nhh_documents_title", "nhh_documents", ["title"])
    op.create_table("chunks",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("corpus_type", sa.String(20), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("nhh_id", sa.String(36), sa.ForeignKey("nhh_documents.id", ondelete="CASCADE")),
        sa.Column("chunk_order", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("article_clause", sa.String(255)), sa.Column("page", sa.Integer()),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.CheckConstraint("(document_id IS NOT NULL) <> (nhh_id IS NOT NULL)", name="ck_chunk_one_source"))
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_nhh_id", "chunks", ["nhh_id"])
    op.create_index("ix_chunks_corpus_type", "chunks", ["corpus_type"])
    op.execute("CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")
    op.create_table("ai_history",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False), sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False), sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ai_history_user_id", "ai_history", ["user_id"])
    op.create_table("tasks",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("assigned_to", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", task_status, nullable=False), sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_tasks_assigned_to", "tasks", ["assigned_to"])
    op.create_index("ix_tasks_deadline", "tasks", ["deadline"])
    op.create_table("audit_logs",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(120), nullable=False), sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False), sa.Column("resource", sa.String(255)),
        sa.Column("status_code", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade():
    for table in ["audit_logs", "tasks", "ai_history", "chunks", "nhh_documents", "documents", "users"]:
        op.drop_table(table)

