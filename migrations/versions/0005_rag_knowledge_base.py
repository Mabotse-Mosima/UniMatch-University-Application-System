"""Add persistent university RAG sources, vectors, and chat history.

Revision ID: 0005_rag_knowledge_base
Revises: 0004_school_operations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_rag_knowledge_base"
down_revision = "0004_school_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_documents",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["accounts.account_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint(
            "university_id",
            "content_sha256",
            name="uq_rag_documents_university_digest",
        ),
    )
    op.create_index(
        "ix_rag_documents_university_id", "rag_documents", ["university_id"]
    )

    op.create_table(
        "rag_chunks",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["rag_documents.document_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_rag_chunks_document_position"
        ),
    )
    op.create_index("ix_rag_chunks_document_id", "rag_chunks", ["document_id"])

    op.create_table(
        "rag_conversations",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_rag_conversations_account_id", "rag_conversations", ["account_id"]
    )
    op.create_index(
        "ix_rag_conversations_school_id", "rag_conversations", ["school_id"]
    )

    op.create_table(
        "rag_messages",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_rag_messages_role"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["rag_conversations.conversation_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint(
            "conversation_id", "position", name="uq_rag_messages_conversation_position"
        ),
    )
    op.create_index(
        "ix_rag_messages_conversation_id", "rag_messages", ["conversation_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("rag_messages", "rag_conversations", "rag_chunks", "rag_documents"):
        count = connection.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()
        if count:
            raise RuntimeError(
                f"Downgrade refused: {count} row(s) exist in '{table}'. "
                "Preserve indexed source and conversation data with a forward migration."
            )

    op.drop_index("ix_rag_messages_conversation_id", table_name="rag_messages")
    op.drop_table("rag_messages")
    op.drop_index("ix_rag_conversations_school_id", table_name="rag_conversations")
    op.drop_index("ix_rag_conversations_account_id", table_name="rag_conversations")
    op.drop_table("rag_conversations")
    op.drop_index("ix_rag_chunks_document_id", table_name="rag_chunks")
    op.drop_table("rag_chunks")
    op.drop_index("ix_rag_documents_university_id", table_name="rag_documents")
    op.drop_table("rag_documents")
