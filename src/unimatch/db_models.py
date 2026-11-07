from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LearnerRecord(Base):
    __tablename__ = "learners"

    learner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_id_number: Mapped[str] = mapped_column(String(100), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    counselor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    marks: Mapped[list[MarkRecord]] = relationship(
        back_populates="learner",
        cascade="all, delete-orphan",
        order_by="MarkRecord.position",
        passive_deletes=True,
    )


class MarkRecord(Base):
    __tablename__ = "marks"

    mark_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    learner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learners.learner_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    exam_type: Mapped[str] = mapped_column(String(100), nullable=False)
    academic_year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    learner: Mapped[LearnerRecord] = relationship(back_populates="marks")


class ProgrammeRecord(Base):
    __tablename__ = "university_programmes"
    __table_args__ = (
        Index(
            "uq_university_programmes_source_draft",
            "source_draft_id",
            unique=True,
            postgresql_where=text("source_draft_id IS NOT NULL"),
        ),
    )

    programme_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    faculty: Mapped[str] = mapped_column(String(255), nullable=False)
    minimum_aps: Mapped[int] = mapped_column(Integer, nullable=False)
    application_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    application_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    required_documents: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    published_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    required_subjects: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rag_documents.document_id", ondelete="SET NULL")
    )
    source_draft_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("programme_import_drafts.draft_id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UniversityInstitutionRecord(Base):
    __tablename__ = "university_institutions"
    __table_args__ = (
        UniqueConstraint("abbreviation", name="uq_university_institutions_abbreviation"),
        CheckConstraint("sector IN ('Public', 'Private', 'Legacy')", name="ck_university_institutions_sector"),
        CheckConstraint("status IN ('Active', 'Inactive', 'Unverified')", name="ck_university_institutions_status"),
    )

    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(32), nullable=False)
    sector: Mapped[str] = mapped_column(String(20), nullable=False)
    dhet_reference: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'Active'"))
    catalog_source: Mapped[str] = mapped_column(String(500), nullable=False)
    source_checked_on: Mapped[date | None] = mapped_column(Date)
    verification_reference: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationRecord(Base):
    __tablename__ = "applications"

    application_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    learner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    programme_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payment_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    submission_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    programme_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status_history: Mapped[list[ApplicationStatusHistoryRecord]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistoryRecord.position",
        passive_deletes=True,
    )


class ApplicationStatusHistoryRecord(Base):
    __tablename__ = "application_status_history"

    entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_status: Mapped[str] = mapped_column(String(50), nullable=False)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    application: Mapped[ApplicationRecord] = relationship(back_populates="status_history")


class LearnerDocumentRecord(Base):
    __tablename__ = "learner_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PendingReview', 'Verified', 'Rejected')",
            name="ck_learner_documents_status",
        ),
        CheckConstraint(
            "virus_scan_status = 'NotScanned'",
            name="ck_learner_documents_scan_status",
        ),
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 5242880",
            name="ck_learner_documents_size",
        ),
        CheckConstraint(
            "mime_type IN ('application/pdf', 'application/msword', "
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document')",
            name="ck_learner_documents_mime_type",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    learner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("learners.learner_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    application_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("applications.application_id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    virus_scan_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'NotScanned'")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'PendingReview'")
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))


class ScoringRuleRecord(Base):
    __tablename__ = "scoring_rules"

    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    band_thresholds: Mapped[list[list[int]]] = mapped_column(JSONB, nullable=False)
    subject_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_subjects: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    subject_weightings: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)


class GuidanceSessionRecord(Base):
    __tablename__ = "guidance_sessions"

    guidance_session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    learner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learners.learner_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    responsible_staff_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationRecord(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    recipient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_key: Mapped[str | None] = mapped_column(String(255), unique=True)


class AuditLogRecord(Base):
    __tablename__ = "audit_log_entries"

    entry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    school_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    university_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class SchoolRecord(Base):
    __tablename__ = "schools"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PendingVerification', 'Active', 'Suspended', 'NeedsReview')",
            name="ck_schools_status",
        ),
    )

    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    official_name: Mapped[str] = mapped_column(String(255), nullable=False)
    emis_number: Mapped[str | None] = mapped_column(String(32))
    province: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    district: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PendingVerification")
    creator_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchoolAdminBootstrapRecord(Base):
    __tablename__ = "school_admin_bootstrap_events"
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    school_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schools.school_id", ondelete="RESTRICT"),
        nullable=False, unique=True, index=True,
    )
    target_account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    verification_evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountInvitationRecord(Base):
    __tablename__ = "account_invitations"
    invitation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending", server_default="Pending")


class RagLogicalDocumentRecord(Base):
    __tablename__ = "rag_logical_documents"
    __table_args__ = (
        UniqueConstraint(
            "logical_document_id",
            "university_id",
            name="uq_rag_logical_documents_id_university",
        ),
        CheckConstraint(
            "lifecycle_state IN ('Active', 'Deleted')",
            name="ck_rag_logical_documents_lifecycle_state",
        ),
    )

    logical_document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True
    )
    university_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Active", server_default="Active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RagDocumentRecord(Base):
    __tablename__ = "rag_documents"
    __table_args__ = (
        UniqueConstraint(
            "logical_document_id",
            "version_number",
            name="uq_rag_documents_logical_version",
        ),
        ForeignKeyConstraint(
            ["logical_document_id", "university_id"],
            [
                "rag_logical_documents.logical_document_id",
                "rag_logical_documents.university_id",
            ],
            ondelete="RESTRICT",
            name="fk_rag_documents_logical_owner",
        ),
        CheckConstraint(
            "embedding_dimensions > 0",
            name="ck_rag_documents_embedding_dimensions",
        ),
        CheckConstraint(
            "version_number > 0",
            name="ck_rag_documents_version_number",
        ),
        CheckConstraint(
            "lifecycle_state IN ('Active', 'Superseded', 'Deleted')",
            name="ck_rag_documents_lifecycle_state",
        ),
        CheckConstraint(
            "embedding_state IN ('EmbeddingsReady', 'ReindexRequired')",
            name="ck_rag_documents_embedding_state",
        ),
        Index(
            "ix_rag_documents_university_embedding",
            "university_id",
            "embedding_model",
            "embedding_revision",
        ),
        Index(
            "uq_rag_documents_active_version_per_logical",
            "logical_document_id",
            unique=True,
            postgresql_where=text("lifecycle_state = 'Active'"),
        ),
        Index(
            "uq_rag_documents_active_digest",
            "university_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("lifecycle_state = 'Active'"),
        ),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    logical_document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    university_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Active", server_default="Active"
    )
    embedding_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ReindexRequired", server_default="ReindexRequired"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="legacy-feature-hash-v1",
        server_default="legacy-feature-hash-v1",
    )
    embedding_revision: Mapped[str] = mapped_column(
        String(100), nullable=False, default="legacy", server_default="legacy"
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=384, server_default="384"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    chunks: Mapped[list[RagChunkRecord]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="RagChunkRecord.chunk_index",
        passive_deletes=True,
    )


class RagChunkRecord(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_rag_chunks_document_position"
        ),
    )

    chunk_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rag_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    document: Mapped[RagDocumentRecord] = relationship(back_populates="chunks")


class RagConversationRecord(Base):
    __tablename__ = "rag_conversations"

    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RagMessageRecord(Base):
    __tablename__ = "rag_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_rag_messages_role"),
        UniqueConstraint(
            "conversation_id",
            "position",
            name="uq_rag_messages_conversation_position",
        ),
    )

    message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rag_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountRecord(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index(
            "uq_accounts_email_ci",
            text("LOWER(email)"),
            unique=True,
        ),
        Index(
            "uq_accounts_single_system_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'SystemAdmin'"),
        ),
    )

    account_id:      Mapped[UUID]            = mapped_column(Uuid(as_uuid=True), primary_key=True)
    email:           Mapped[str]             = mapped_column(String(254), nullable=False)
    password_hash:   Mapped[str]             = mapped_column(String(512), nullable=False)
    role:            Mapped[str]             = mapped_column(String(30),  nullable=False)
    account_state:   Mapped[str]             = mapped_column(String(20),  nullable=False)
    failed_attempts: Mapped[int]             = mapped_column(Integer,     nullable=False, default=0)
    locked_until:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    school_id:       Mapped[UUID | None]     = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "schools.school_id",
            ondelete="RESTRICT",
            name="fk_accounts_school_id_schools",
            use_alter=True,
        ),
    )
    university_id:   Mapped[UUID | None]     = mapped_column(Uuid(as_uuid=True))
    creator_id:      Mapped[UUID | None]     = mapped_column(
                         Uuid(as_uuid=True),
                         ForeignKey("accounts.account_id", ondelete="RESTRICT"),
                     )
    created_at:      Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at:      Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False)
    university_scopes: Mapped[list[AccountUniversityScopeRecord]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="AccountUniversityScopeRecord.account_id",
    )


class AccountUniversityScopeRecord(Base):
    __tablename__ = "account_university_scopes"
    __table_args__ = (
        Index("ix_account_university_scopes_university", "university_id"),
    )

    account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="CASCADE"), primary_key=True
    )
    university_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("university_institutions.university_id", ondelete="RESTRICT"), primary_key=True
    )
    granted_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    account: Mapped[AccountRecord] = relationship(back_populates="university_scopes", foreign_keys=[account_id])


class ProgrammeImportDraftRecord(Base):
    __tablename__ = "programme_import_drafts"
    __table_args__ = (
        UniqueConstraint("source_document_id", "name", "minimum_aps", name="uq_programme_import_drafts_source_candidate"),
        CheckConstraint("status IN ('NeedsReview', 'Approved', 'Rejected', 'Submitted')", name="ck_programme_import_drafts_status"),
        CheckConstraint("minimum_aps IS NULL OR (minimum_aps >= 0 AND minimum_aps <= 42)", name="ck_programme_import_drafts_aps"),
        Index("ix_programme_import_drafts_scope_status", "university_id", "status"),
    )

    draft_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    university_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("university_institutions.university_id", ondelete="RESTRICT"), nullable=False
    )
    source_document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rag_documents.document_id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    faculty: Mapped[str | None] = mapped_column(String(255))
    minimum_aps: Mapped[int | None] = mapped_column(Integer)
    application_deadline: Mapped[date | None] = mapped_column(Date)
    application_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    required_documents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    required_subjects: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'NeedsReview'"))
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("accounts.account_id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountSessionRecord(Base):
    __tablename__ = "account_sessions"

    session_id:   Mapped[UUID]            = mapped_column(Uuid(as_uuid=True), primary_key=True)
    account_id:   Mapped[UUID]            = mapped_column(
                      Uuid(as_uuid=True),
                      ForeignKey("accounts.account_id", ondelete="CASCADE"),
                      nullable=False,
                  )
    token_digest: Mapped[str]             = mapped_column(String(64), nullable=False, unique=True)
    csrf_token:   Mapped[str]             = mapped_column(String(64), nullable=False)
    created_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationRecordORM(Base):
    __tablename__ = "verification_records"

    record_id:            Mapped[UUID]            = mapped_column(Uuid(as_uuid=True), primary_key=True)
    subject_account_id:   Mapped[UUID]            = mapped_column(
                              Uuid(as_uuid=True),
                              ForeignKey("accounts.account_id", ondelete="RESTRICT"),
                              nullable=False,
                          )
    verifier_account_id:  Mapped[UUID]            = mapped_column(
                              Uuid(as_uuid=True),
                              ForeignKey("accounts.account_id", ondelete="RESTRICT"),
                              nullable=False,
                          )
    subject_role:         Mapped[str]             = mapped_column(String(30), nullable=False)
    evidence_reference:   Mapped[str]             = mapped_column(Text, nullable=False)
    school_scope:         Mapped[list]            = mapped_column(JSONB, nullable=False)
    university_id:        Mapped[UUID | None]     = mapped_column(Uuid(as_uuid=True))
    created_at:           Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False)
    outcome:              Mapped[str]             = mapped_column(String(20), nullable=False)
