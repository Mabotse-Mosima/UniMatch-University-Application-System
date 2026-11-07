"""Persist embedding identity and dimensions for safe semantic retrieval.

Revision ID: 0006_semantic_embedding_metadata
Revises: 0005_rag_knowledge_base
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_semantic_embedding_metadata"
down_revision = "0005_rag_knowledge_base"
branch_labels = None
depends_on = None

LEGACY_MODEL = "legacy-feature-hash-v1"


def upgrade() -> None:
    op.add_column(
        "rag_documents",
        sa.Column(
            "embedding_model",
            sa.String(length=255),
            nullable=False,
            server_default=LEGACY_MODEL,
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "embedding_revision",
            sa.String(length=100),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("384"),
        ),
    )
    op.create_check_constraint(
        "ck_rag_documents_embedding_dimensions",
        "rag_documents",
        "embedding_dimensions > 0",
    )
    op.create_index(
        "ix_rag_documents_university_embedding",
        "rag_documents",
        ["university_id", "embedding_model", "embedding_revision"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    incompatible_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM rag_documents "
            "WHERE embedding_model <> :legacy_model"
        ),
        {"legacy_model": LEGACY_MODEL},
    ).scalar_one()
    if incompatible_count:
        raise RuntimeError(
            f"Downgrade refused: {incompatible_count} document(s) use semantic "
            "embeddings. Preserve their model metadata with a forward migration."
        )

    op.drop_index(
        "ix_rag_documents_university_embedding",
        table_name="rag_documents",
    )
    op.drop_constraint(
        "ck_rag_documents_embedding_dimensions",
        "rag_documents",
        type_="check",
    )
    op.drop_column("rag_documents", "embedding_dimensions")
    op.drop_column("rag_documents", "embedding_revision")
    op.drop_column("rag_documents", "embedding_model")
