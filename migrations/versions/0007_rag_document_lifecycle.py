"""Add logical document identity, physical versions, and lifecycle state.

Revision ID: 0007_rag_document_lifecycle
Revises: 0006_semantic_embedding_metadata
"""

import math

from alembic import op
import sqlalchemy as sa

revision = "0007_rag_document_lifecycle"
down_revision = "0006_semantic_embedding_metadata"
branch_labels = None
depends_on = None

# These are migration-time facts, deliberately pinned rather than imported from
# mutable application configuration.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EMBEDDING_DIMENSIONS = 384


def _vectors_are_ready(document, chunks) -> bool:
    if (
        document["embedding_model"] != EMBEDDING_MODEL
        or document["embedding_revision"] != EMBEDDING_REVISION
        or document["embedding_dimensions"] != EMBEDDING_DIMENSIONS
        or not chunks
    ):
        return False

    for vector in chunks:
        if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
            return False
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            try:
                if not math.isfinite(value):
                    return False
            except (OverflowError, TypeError, ValueError):
                return False
    return True


def _create_lifecycle_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION check_rag_logical_lifecycle() RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        DECLARE
            affected_logical_id uuid;
            logical_state text;
            active_versions integer;
        BEGIN
            affected_logical_id := COALESCE(NEW.logical_document_id, OLD.logical_document_id);
            SELECT lifecycle_state
              INTO logical_state
              FROM rag_logical_documents
             WHERE logical_document_id = affected_logical_id;

            IF NOT FOUND THEN
                RETURN NULL;
            END IF;

            SELECT COUNT(*)
              INTO active_versions
              FROM rag_documents
             WHERE logical_document_id = affected_logical_id
               AND lifecycle_state = 'Active';

            IF logical_state = 'Active' AND active_versions <> 1 THEN
                RAISE EXCEPTION
                    'Active logical document % must have exactly one Active version',
                    affected_logical_id
                    USING ERRCODE = 'check_violation';
            ELSIF logical_state = 'Deleted' AND active_versions <> 0 THEN
                RAISE EXCEPTION
                    'Deleted logical document % cannot have an Active version',
                    affected_logical_id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
        END;
        $function$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ct_rag_logical_lifecycle
        AFTER INSERT OR UPDATE ON rag_logical_documents
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION check_rag_logical_lifecycle()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ct_rag_physical_lifecycle
        AFTER INSERT OR UPDATE ON rag_documents
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION check_rag_logical_lifecycle()
        """
    )


def upgrade() -> None:
    op.create_table(
        "rag_logical_documents",
        sa.Column("logical_document_id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column(
            "lifecycle_state",
            sa.String(length=20),
            nullable=False,
            server_default="Active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle_state IN ('Active', 'Deleted')",
            name="ck_rag_logical_documents_lifecycle_state",
        ),
        sa.PrimaryKeyConstraint("logical_document_id"),
        sa.UniqueConstraint(
            "logical_document_id",
            "university_id",
            name="uq_rag_logical_documents_id_university",
        ),
    )
    op.create_index(
        "ix_rag_logical_documents_university_id",
        "rag_logical_documents",
        ["university_id"],
    )

    op.add_column(
        "rag_documents",
        sa.Column("logical_document_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "rag_documents",
        sa.Column("version_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rag_documents",
        sa.Column(
            "lifecycle_state",
            sa.String(length=20),
            nullable=True,
        ),
    )
    op.add_column(
        "rag_documents",
        sa.Column("embedding_state", sa.String(length=30), nullable=True),
    )

    connection = op.get_bind()
    documents = connection.execute(
        sa.text(
            "SELECT document_id, university_id, created_at, embedding_model, "
            "embedding_revision, embedding_dimensions FROM rag_documents"
        )
    ).mappings().all()
    for document in documents:
        connection.execute(
            sa.text(
                "INSERT INTO rag_logical_documents "
                "(logical_document_id, university_id, lifecycle_state, created_at) "
                "VALUES (:logical_id, :university_id, 'Active', :created_at)"
            ),
            {
                "logical_id": document["document_id"],
                "university_id": document["university_id"],
                "created_at": document["created_at"],
            },
        )
        vectors = connection.execute(
            sa.text(
                "SELECT embedding FROM rag_chunks WHERE document_id = :document_id"
            ),
            {"document_id": document["document_id"]},
        ).scalars().all()
        embedding_state = (
            "EmbeddingsReady"
            if _vectors_are_ready(document, vectors)
            else "ReindexRequired"
        )
        connection.execute(
            sa.text(
                "UPDATE rag_documents SET logical_document_id = :logical_id, "
                "version_number = 1, lifecycle_state = 'Active', "
                "embedding_state = :embedding_state "
                "WHERE document_id = :document_id"
            ),
            {
                "logical_id": document["document_id"],
                "embedding_state": embedding_state,
                "document_id": document["document_id"],
            },
        )

    op.alter_column(
        "rag_documents", "logical_document_id", nullable=False
    )
    op.alter_column(
        "rag_documents",
        "version_number",
        nullable=False,
        server_default=sa.text("1"),
    )
    op.alter_column(
        "rag_documents",
        "lifecycle_state",
        nullable=False,
        server_default="Active",
    )
    op.alter_column(
        "rag_documents",
        "embedding_state",
        nullable=False,
        server_default="ReindexRequired",
    )

    op.drop_constraint(
        "uq_rag_documents_university_digest",
        "rag_documents",
        type_="unique",
    )
    op.create_foreign_key(
        "fk_rag_documents_logical_owner",
        "rag_documents",
        "rag_logical_documents",
        ["logical_document_id", "university_id"],
        ["logical_document_id", "university_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_rag_documents_logical_version",
        "rag_documents",
        ["logical_document_id", "version_number"],
    )
    op.create_check_constraint(
        "ck_rag_documents_version_number",
        "rag_documents",
        "version_number > 0",
    )
    op.create_check_constraint(
        "ck_rag_documents_lifecycle_state",
        "rag_documents",
        "lifecycle_state IN ('Active', 'Superseded', 'Deleted')",
    )
    op.create_check_constraint(
        "ck_rag_documents_embedding_state",
        "rag_documents",
        "embedding_state IN ('EmbeddingsReady', 'ReindexRequired')",
    )
    op.create_index(
        "uq_rag_documents_active_version_per_logical",
        "rag_documents",
        ["logical_document_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle_state = 'Active'"),
    )
    op.create_index(
        "uq_rag_documents_active_digest",
        "rag_documents",
        ["university_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("lifecycle_state = 'Active'"),
    )
    _create_lifecycle_trigger()


def downgrade() -> None:
    connection = op.get_bind()
    document_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM rag_documents")
    ).scalar_one()
    if document_count:
        raise RuntimeError(
            "Downgrade refused: RAG physical documents contain logical/version "
            "lifecycle data. Preserve it with a forward migration."
        )

    op.execute("DROP TRIGGER ct_rag_physical_lifecycle ON rag_documents")
    op.execute(
        "DROP TRIGGER ct_rag_logical_lifecycle ON rag_logical_documents"
    )
    op.execute("DROP FUNCTION check_rag_logical_lifecycle()")
    op.drop_index(
        "uq_rag_documents_active_digest", table_name="rag_documents"
    )
    op.drop_index(
        "uq_rag_documents_active_version_per_logical",
        table_name="rag_documents",
    )
    op.drop_constraint(
        "ck_rag_documents_embedding_state", "rag_documents", type_="check"
    )
    op.drop_constraint(
        "ck_rag_documents_lifecycle_state", "rag_documents", type_="check"
    )
    op.drop_constraint(
        "ck_rag_documents_version_number", "rag_documents", type_="check"
    )
    op.drop_constraint(
        "uq_rag_documents_logical_version",
        "rag_documents",
        type_="unique",
    )
    op.drop_constraint(
        "fk_rag_documents_logical_owner",
        "rag_documents",
        type_="foreignkey",
    )
    op.create_unique_constraint(
        "uq_rag_documents_university_digest",
        "rag_documents",
        ["university_id", "content_sha256"],
    )
    op.drop_column("rag_documents", "embedding_state")
    op.drop_column("rag_documents", "lifecycle_state")
    op.drop_column("rag_documents", "version_number")
    op.drop_column("rag_documents", "logical_document_id")
    op.drop_index(
        "ix_rag_logical_documents_university_id",
        table_name="rag_logical_documents",
    )
    op.drop_table("rag_logical_documents")
