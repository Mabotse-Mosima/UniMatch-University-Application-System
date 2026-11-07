"""Persist learner document metadata and human review history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_learner_document_storage"
down_revision = "0007_rag_document_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learner_documents",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.learner_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.application_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "virus_scan_status",
            sa.String(30),
            nullable=False,
            server_default="NotScanned",
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="PendingReview",
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(
            "status IN ('PendingReview', 'Verified', 'Rejected')",
            name="ck_learner_documents_status",
        ),
        sa.CheckConstraint(
            "virus_scan_status = 'NotScanned'",
            name="ck_learner_documents_scan_status",
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 5242880",
            name="ck_learner_documents_size",
        ),
        sa.CheckConstraint(
            "mime_type IN ('application/pdf', 'application/msword', "
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document')",
            name="ck_learner_documents_mime_type",
        ),
    )
    op.create_index(
        "ix_learner_documents_learner_id",
        "learner_documents",
        ["learner_id"],
    )
    op.create_index(
        "ix_learner_documents_application_id",
        "learner_documents",
        ["application_id"],
    )
    op.create_index(
        "ix_learner_documents_school_id",
        "learner_documents",
        ["school_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_learner_documents_school_id", table_name="learner_documents")
    op.drop_index(
        "ix_learner_documents_application_id", table_name="learner_documents"
    )
    op.drop_index("ix_learner_documents_learner_id", table_name="learner_documents")
    op.drop_table("learner_documents")
