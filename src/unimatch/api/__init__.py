"""
unimatch/api/__init__.py
=========================
FastAPI REST API for UniMatch.

Three resource groups:
  /api/learners      – LearnerProfile CRUD + APS + marks + deactivation
  /api/programmes    – UniversityProgramme CRUD + publish/deactivate/eligibility
  /api/applications  – Application lifecycle (create, status update, submit, cancel, history)

OpenAPI docs are available at /docs and /redoc outside production.
"""

from __future__ import annotations

import logging
import asyncio
import hashlib
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path, PurePath
from typing import Any, List, Literal, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()
from pydantic import BaseModel, Field, field_validator

from unimatch.auth import AuthPrincipal, DUMMY_PASSWORD_HASH, digest_token, generate_csrf_token, generate_session_token, verify_password
from unimatch.config import Settings
from unimatch.database import create_session_factory
from unimatch.university_catalog import PUBLIC_UNIVERSITIES
from unimatch.programme_extraction import extract_programme_drafts
from unimatch.document_storage import (
    InvalidDocumentUpload,
    LocalDocumentStorage,
    validate_document_upload,
)
from unimatch.entities import (
    Application,
    AuditLogEntry,
    Document,
    GuidanceSession,
    LearnerProfile,
    Mark,
    NSC_DEFAULT_SCORING_RULE,
    Notification,
    ScoringRule,
    School,
    Session,
    UniversityProgramme,
)
from unimatch.status_history import StatusHistoryEntry
from unimatch.enums import AccountStateEnum, ApplicationStatusEnum, EligibilityEnum, ProfileStatusEnum, ProgrammeStatusEnum, RoleEnum
from unimatch.repositories.inmemory import (
    InMemoryApplicationRepository,
    InMemoryAuditLogRepository,
    InMemoryGuidanceSessionRepository,
    InMemoryLearnerProfileRepository,
    InMemoryNotificationRepository,
    InMemoryScoringRuleRepository,
    InMemorySessionRepository,
    InMemoryUniversityProgrammeRepository,
    InMemoryUserAccountRepository,
    InMemoryVerificationRecordRepository,
    InMemorySchoolRepository,
    InMemoryAccountInvitationRepository,
)
from unimatch.provisioning import (
    AccountProvisioningService,
    AccountAlreadyExistsError,
    AccountNotFoundError,
    AlreadyActiveError,
    InvalidRoleForProvisioningError,
    NotAuthorizedError,
    NotVerifiedError,
    OutOfScopeError,
    SelfActivationError,
    ProvisioningError,
)
from unimatch.learner_import import (
    MAX_IMPORT_BYTES,
    LearnerImportValidationError,
    parse_learner_csv,
)
from unimatch.rag import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    MAX_DOCUMENT_BYTES,
    DuplicateRagDocumentError,
    EmbeddingState,
    ExtractiveGroundedAnswerProvider,
    GroundedAnswerProvider,
    InMemoryRagRepository,
    RagChunk,
    RagConversation,
    RagDocument,
    RagEmbeddingUnavailableError,
    RagGenerationUnavailableError,
    RagInputError,
    RagLifecycleError,
    RagLogicalDocumentNotFoundError,
    RagMessage,
    RagRepository,
    RagReindexRequiredError,
    PhysicalDocumentState,
    answer_provider_from_environment,
    chunk_text,
    embed_texts,
    extract_document_text,
    retrieve_chunks,
)
from unimatch.rag_pipeline import (
    API_RAG_COLLECTION_NAME,
    ChromaVectorStore,
    IndexedChunk,
    VectorStore,
)
from unimatch.db_models import (
    AccountRecord,
    AccountUniversityScopeRecord,
    ProgrammeImportDraftRecord,
    ProgrammeRecord,
    UniversityInstitutionRecord,
)
from unimatch.repositories import (
    ApplicationRepository,
    DocumentRepository,
    SchoolRepository,
    ScoringRuleRepository,
)
from unimatch.repositories.postgres import (
    PostgresApplicationRepository,
    PostgresAuditLogRepository,
    PostgresDocumentRepository,
    PostgresGuidanceSessionRepository,
    PostgresLearnerProfileRepository,
    PostgresNotificationRepository,
    PostgresRagRepository,
    PostgresScoringRuleRepository,
    PostgresSessionRepository,
    PostgresUniversityProgrammeRepository,
    PostgresUserAccountRepository,
    PostgresVerificationRecordRepository,
    PostgresSchoolRepository,
    PostgresAccountInvitationRepository,
)
from unimatch.repositories.local_documents import LocalDocumentRepository
from unimatch.services import (
    ApplicationNotFoundError,
    ApplicationService,
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    LearnerNotFoundError,
    LearnerProfileService,
    ProgrammeNotActiveError,
    ProgrammeNotFoundError,
    NotEligibleError,
    SimulationResult,
    UniversityProgrammeService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("unimatch.api")
DOE_SMALL_COHORT_THRESHOLD = 5
ASSISTANT_MAX_BODY_BYTES = 32 * 1024


def _assistant_citation(score: float, document: RagDocument, chunk: RagChunk) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "university": str(document.university_id),
        "title": document.title,
        "page": None,
        "section": None,
        "snippet": chunk.text[:700],
        "score": round(float(score), 6),
    }


def _assistant_numbers_match_engine(answer: str, eligibility: list[dict[str, object]]) -> bool:
    if not eligibility:
        return True
    normalized_answer = answer.casefold()
    occurrences: list[tuple[int, int, dict[str, object]]] = []
    for item in eligibility:
        name = str(item.get("programme_name", "")).strip()
        if not name:
            continue
        for match in re.finditer(re.escape(name.casefold()), normalized_answer):
            occurrences.append((match.start(), match.end(), item))
    occurrences.sort(key=lambda entry: (entry[0], -(entry[1] - entry[0])))
    aps_claim = re.compile(r"\b(?:minimum\s+)?APS\s+(\d+)\b", re.IGNORECASE)
    label_claim = re.compile(
        r"\b(Guaranteed|Likely|Borderline|Not\s*Eligible)\b", re.IGNORECASE
    )
    claims = list(aps_claim.finditer(answer)) + list(label_claim.finditer(answer))
    if claims and not occurrences:
        return False
    for index, (start, end, item) in enumerate(occurrences):
        next_start = next(
            (other_start for other_start, _other_end, _other in occurrences[index + 1:] if other_start > start),
            len(answer),
        )
        segment = answer[end:next_start]
        allowed_numbers = {str(item.get("aps_score", "")), str(item.get("minimum_aps", ""))}
        if any(match.group(1) not in allowed_numbers for match in aps_claim.finditer(segment)):
            return False
        expected_label = re.sub(r"\s+", "", str(item.get("eligibility", ""))).casefold()
        for match in label_claim.finditer(segment):
            actual_label = re.sub(r"\s+", "", match.group(1)).casefold()
            if actual_label != expected_label:
                return False
    # Every numerical or classification claim must occur inside a named
    # programme's segment; an unassociated result cannot be verified safely.
    for claim in claims:
        if not any(start <= claim.start() < next_start for index, (start, _end, _item) in enumerate(occurrences)
                   for next_start in [next((other_start for other_start, _other_end, _other in occurrences[index + 1:] if other_start > start), len(answer))]):
            return False
    return True


def _verify_auth_schema(engine) -> None:
    """Verify authentication and required operational tables exist.

    Raises RuntimeError on failure — fail-closed startup.

    Uses information_schema (never SELECT from a potentially missing table) to
    avoid leaving failed transactions open on ProgrammingError. Handles the case
    where a later migration superseded 0002_auth_tables in alembic_version.
    """
    import sqlalchemy as _sa
    from sqlalchemy.exc import OperationalError as _OpError

    required_tables = (
        "accounts",
        "account_sessions",
        "verification_records",
        "guidance_sessions",
        "notifications",
        "audit_log_entries",
        "rag_logical_documents",
        "rag_documents",
        "rag_chunks",
        "rag_conversations",
        "rag_messages",
        "learner_documents",
    )
    expected_head = "0008_learner_document_storage"

    # Step 1: confirm table existence via information_schema.
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                _sa.text(
                    "SELECT table_name "
                    "FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "  AND table_name = ANY(:tables)"
                ),
                {"tables": list(required_tables)},
            ).fetchall()
    except _OpError as exc:
        raise RuntimeError(
            "Cannot connect to the database for schema validation. "
            "Verify DATABASE_URL and network/firewall configuration. "
            f"Detail: {exc}"
        ) from exc

    found = {row[0] for row in rows}
    for table in required_tables:
        if table not in found:
            raise RuntimeError(
                f"Required application table '{table}' does not exist in the 'public' schema. "
                f"Run 'alembic upgrade {expected_head}' before starting the application."
            )

    try:
        with engine.connect() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    _sa.text(
                        "SELECT column_name "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'rag_documents'"
                    )
                ).fetchall()
            }
    except _OpError as exc:
        raise RuntimeError(
            f"Database schema validation failed: {exc}"
        ) from exc
    required_rag_columns = {
        "embedding_model",
        "embedding_revision",
        "embedding_dimensions",
        "logical_document_id",
        "version_number",
        "lifecycle_state",
        "embedding_state",
    }
    missing_rag_columns = required_rag_columns - columns
    if missing_rag_columns:
        raise RuntimeError(
            "The rag_documents table is missing semantic embedding metadata "
            f"columns: {', '.join(sorted(missing_rag_columns))}. "
            "Review and apply migration 0007_rag_document_lifecycle."
        )

    try:
        with engine.connect() as conn:
            invitation_columns = {
                row[0]
                for row in conn.execute(
                    _sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'account_invitations'"
                    )
                ).fetchall()
            }
    except _OpError as exc:
        raise RuntimeError(f"Invitation schema validation failed: {exc}") from exc
    if "status" not in invitation_columns:
        raise RuntimeError(
            "The account_invitations table is missing lifecycle status. "
            "Apply migration 0010_invitation_lifecycle before starting this application version."
        )

    # Step 2: validate Alembic migration state — separate connection.
    try:
        with engine.connect() as conn:
            av_exists = conn.execute(
                _sa.text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                )
            ).fetchone()

            if av_exists is None:
                raise RuntimeError(
                    "The 'alembic_version' table does not exist. "
                    "Alembic has never been run on this database. "
                    f"Run 'alembic upgrade {expected_head}' to initialise."
                )

            current_heads = {
                row[0]
                for row in conn.execute(
                    _sa.text("SELECT version_num FROM alembic_version")
                ).fetchall()
            }

            if not current_heads:
                raise RuntimeError(
                    "alembic_version is empty. No migrations have been applied. "
                    f"Run 'alembic upgrade {expected_head}' to initialise."
                )

            if expected_head not in current_heads:
                # A later migration may have superseded this head.
                # Table existence (checked above) is the authoritative signal.
                logger.warning(
                    "Migration '%s' is not among the current Alembic heads %s. "
                    "A later migration may have superseded it. "
                    "Continuing because all required authentication tables are present.",
                    expected_head,
                    sorted(current_heads),
                )

    except _OpError as exc:
        raise RuntimeError(
            f"Database schema validation failed: {exc}"
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class CreateLearnerRequest(BaseModel):
    full_name: str = Field(..., json_schema_extra={"example": "Thabo Nkosi"})
    school_id_number: str = Field(..., json_schema_extra={"example": "2024-0001"})
    grade: int = Field(..., ge=8, le=12, json_schema_extra={"example": 12})
    counselor_id: Optional[UUID] = None
    school_id: Optional[UUID] = None


class UpdateLearnerRequest(BaseModel):
    full_name: Optional[str] = None
    grade: Optional[int] = Field(None, ge=8, le=12)
    school_id_number: Optional[str] = None


class AddMarkRequest(BaseModel):
    subject_name: str = Field(..., json_schema_extra={"example": "Mathematics"})
    score: int = Field(..., ge=0, le=100, json_schema_extra={"example": 75})
    exam_type: str = Field(..., json_schema_extra={"example": "NSC"})
    academic_year: int = Field(..., json_schema_extra={"example": 2024})


class LearnerResponse(BaseModel):
    learner_id: UUID
    full_name: str
    school_id_number: str
    grade: int
    status: str
    counselor_id: Optional[UUID]
    school_id: UUID
    aps_score: int
    mark_count: int


class ApsResponse(BaseModel):
    learner_id: UUID
    aps_score: int
    university_id: Optional[UUID] = None  # None means standard NSC formula was used


class CreateProgrammeRequest(BaseModel):
    university_id: Optional[UUID] = Field(None, description="Derived from the authenticated UniversityAdmissions account.")
    name: str = Field(..., json_schema_extra={"example": "BSc Computer Science"})
    faculty: str = Field(..., json_schema_extra={"example": "Science"})
    minimum_aps: int = Field(..., ge=0, le=42, json_schema_extra={"example": 28})
    application_deadline: date = Field(..., json_schema_extra={"example": "2099-09-30"})
    application_fee: Decimal = Field(..., json_schema_extra={"example": "200.00"})
    required_documents: List[str] = Field(default_factory=list)
    published_by: Optional[UUID] = Field(None, description="Derived from the authenticated UniversityAdmissions account.")
    required_subjects: dict[str, int] = Field(
        default_factory=dict,
        json_schema_extra={"example": {"Mathematics": 60, "Physical Sciences": 50}},
        description=(
            "Compulsory subject requirements (REQ-003). Keys are subject names; "
            "values are minimum marks (0-100). A learner is Not Eligible if they "
            "are missing any listed subject or their best mark is below the minimum."
        ),
    )


class UpdateProgrammeRequest(BaseModel):
    name: Optional[str] = None
    faculty: Optional[str] = None
    minimum_aps: Optional[int] = Field(None, ge=0, le=42)
    application_fee: Optional[Decimal] = None
    required_documents: Optional[List[str]] = None
    required_subjects: Optional[dict[str, int]] = Field(
        None,
        description="Update compulsory subject requirements. Replaces the existing dict.",
    )


class ExtendDeadlineRequest(BaseModel):
    new_deadline: date = Field(..., json_schema_extra={"example": "2099-10-31"})


class ProgrammeResponse(BaseModel):
    programme_id: UUID
    university_id: UUID
    name: str
    faculty: str
    minimum_aps: int
    application_deadline: date
    application_fee: str
    required_documents: List[str]
    status: str
    is_active: bool
    required_subjects: dict[str, int]
    source_document_id: Optional[UUID] = None
    source_draft_id: Optional[UUID] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None


class EligibilityResponse(BaseModel):
    programme_id: UUID
    learner_aps: int
    minimum_aps: int
    eligibility: str
    subject_requirements_checked: bool = False
    assessment_type: Literal["APS_ONLY", "APS_AND_SUBJECTS"] = "APS_ONLY"
    has_subject_requirements: bool = False


class CreateApplicationRequest(BaseModel):
    learner_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000030"})
    programme_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000040"})
    fee_amount: Decimal = Field(..., json_schema_extra={"example": "200.00"})


class UpdateStatusRequest(BaseModel):
    new_status: ApplicationStatusEnum
    note: str = Field(default="", json_schema_extra={"example": "Documents verified"})


class ReviewApplicationRequest(BaseModel):
    new_status: Literal[
        "UnderReview", "DocsRequested", "Accepted", "Rejected", "Waitlisted"
    ]
    note: str = Field(default="", max_length=10000)


class CancelApplicationRequest(BaseModel):
    note: str = Field(default="", json_schema_extra={"example": "Learner withdrew application"})


class ApplicationResponse(BaseModel):
    application_id: UUID
    learner_id: UUID
    programme_id: UUID
    status: str
    fee_amount: str
    submission_timestamp: Optional[str]
    acknowledgement_reference: str
    submission_ready: bool
    submission_blockers: List[str]


class LearnerDocumentResponse(BaseModel):
    document_id: UUID
    learner_id: UUID
    application_id: UUID | None
    document_type: str
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: UUID
    virus_scan_status: str
    status: str
    uploaded_at: datetime
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_note: str
    download_url: str


class ReviewLearnerDocumentRequest(BaseModel):
    decision: Literal["Verified", "Rejected"]
    note: str = Field(..., min_length=1, max_length=1000)

    @field_validator("note")
    @classmethod
    def review_note_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A review note is required.")
        return value.strip()


class StatusHistoryEntryResponse(BaseModel):
    """One auditable status-change event on an application (REQ-007)."""
    entry_id: UUID
    application_id: UUID
    previous_status: str
    new_status: str
    changed_by: UUID
    changed_at: str  # ISO 8601 UTC
    note: str


class ApplicationReviewMarkResponse(BaseModel):
    subject_name: str
    score: int
    exam_type: str
    academic_year: int
    aps_points: int


class ApplicationReviewDocumentResponse(BaseModel):
    document_id: UUID
    document_type: str
    filename: str
    mime_type: str
    size_bytes: int
    virus_scan_status: str
    status: str
    uploaded_at: datetime
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_note: str
    download_url: str


class ApplicationReviewResponse(BaseModel):
    application_id: UUID
    status: str
    fee_amount: str
    submission_timestamp: Optional[str]
    learner_id: UUID
    learner_name: str
    learner_grade: int
    learner_aps: int
    learner_marks: List[ApplicationReviewMarkResponse]
    programme_id: UUID
    programme_name: str
    programme_faculty: str
    required_documents: List[str]
    linked_documents: List[ApplicationReviewDocumentResponse]
    document_tracking_available: bool
    status_history: List[StatusHistoryEntryResponse]


class SimulateEligibilityRequest(BaseModel):
    """Request body for the eligibility simulation endpoint (REQ-005)."""

    programme_id: UUID = Field(
        ...,
        json_schema_extra={"example": "00000000-0000-0000-0000-000000000040"},
    )
    overrides: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Hypothetical marks by subject name. Each value must be in 0-100. "
            "Overrides are treated as additional mark entries consistent with "
            "how multiple marks for the same subject are handled: the best mark "
            "wins for subject-requirement checks; all marks contribute to the "
            "APS ranking pool."
        ),
        json_schema_extra={"example": {"Mathematics": 65, "English": 75}},
    )

    @field_validator("overrides")
    @classmethod
    def _validate_override_scores(cls, v: dict[str, int]) -> dict[str, int]:
        for subject, score in v.items():
            if not (0 <= score <= 100):
                raise ValueError(
                    f"Override score for '{subject}' = {score} "
                    "is outside the valid 0-100 NSC score range"
                )
        return v


class SimulationResponse(BaseModel):
    """Result of a hypothetical-mark eligibility simulation (REQ-005).

    This response is never persisted and never creates or modifies an
    application. The is_simulation field is always True.
    """

    learner_id: UUID
    programme_id: UUID
    simulated_aps: int
    eligibility: str
    subject_requirements_checked: bool
    university_rule_applied: bool
    is_simulation: bool = True


class CompareSimulationRequest(BaseModel):
    """Request to compare current and hypothetical eligibility."""

    programme_ids: List[UUID] = Field(..., min_length=1)
    overrides: dict[str, int] = Field(default_factory=dict)

    @field_validator("programme_ids")
    @classmethod
    def _validate_programme_ids(cls, v: List[UUID]) -> List[UUID]:
        if len(v) != len(set(v)):
            raise ValueError("programme_ids must not contain duplicates")
        return v

    @field_validator("overrides")
    @classmethod
    def _validate_override_scores(cls, v: dict[str, int]) -> dict[str, int]:
        for subject, score in v.items():
            if not subject.strip():
                raise ValueError("Override subject names must not be empty")
            if not (0 <= score <= 100):
                raise ValueError(
                    f"Override score for '{subject}' = {score} "
                    "is outside the valid 0-100 NSC score range"
                )
        return v


class ProgrammeSimulationComparison(BaseModel):
    programme_id: UUID
    current_aps: int
    projected_aps: int
    current_eligibility: str
    projected_eligibility: str
    subject_requirements_checked: bool
    university_rule_applied: bool


class SimulationComparisonResponse(BaseModel):
    learner_id: UUID
    results: List[ProgrammeSimulationComparison]
    is_simulation: bool = True


class LoginRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "admin@school.example"})
    password: str = Field(..., min_length=1, json_schema_extra={"example": "changeme"})


class SessionInfoResponse(BaseModel):
    account_id: UUID
    role: str
    school_id: Optional[UUID]
    university_id: Optional[UUID] = None
    university_ids: List[UUID] = Field(default_factory=list)


class UniversityInstitutionResponse(BaseModel):
    university_id: UUID
    name: str
    abbreviation: str
    sector: Literal["Public", "Private", "Legacy"]
    dhet_reference: Optional[str]
    website: Optional[str]
    status: Literal["Active", "Inactive", "Unverified"]
    catalog_source: str
    source_checked_on: Optional[date]


class CreatePrivateUniversityRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    abbreviation: str = Field(..., min_length=2, max_length=32)
    dhet_reference: str = Field(..., min_length=4, max_length=100)
    website: Optional[str] = Field(None, max_length=500)


class VerifyPrivateUniversityRequest(BaseModel):
    evidence_reference: str = Field(..., min_length=4, max_length=500)


class GrantUniversityScopesRequest(BaseModel):
    university_ids: List[UUID] = Field(..., min_length=1, max_length=100)

    @field_validator("university_ids")
    @classmethod
    def unique_university_ids(cls, values: List[UUID]) -> List[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("University scope list contains duplicate IDs.")
        return values


class ProvisionAccountRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "schooladmin@example.com"})
    password: str = Field(..., min_length=1)
    role: str = Field(..., json_schema_extra={"example": "SchoolAdmin"})
    school_id: Optional[UUID] = None
    university_id: Optional[UUID] = None


class RecordVerificationRequest(BaseModel):
    evidence_reference: str = Field(
        ...,
        json_schema_extra={"example": "DOE-GAZETTE-2024-NW-SCH-001"},
    )
    school_scope: List[UUID] = Field(default_factory=list)
    university_id: Optional[UUID] = None
    outcome: Literal["Verified", "Rejected"] = "Verified"


class AccountResponse(BaseModel):
    account_id: UUID
    email: str
    role: str
    account_state: str
    school_id: Optional[UUID]


class AdminAccountResponse(AccountResponse):
    creator_id: Optional[UUID]
    university_id: Optional[UUID] = None
    university_ids: List[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    verification_status: str
    credentials_ready: bool
    invitation_active: bool
    invitation_status: str | None


class SchoolCreateRequest(BaseModel):
    official_name: str = Field(..., min_length=2, max_length=255)
    emis_number: Optional[str] = Field(None, max_length=32)
    province: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=150)
    contact_email: Optional[str] = Field(None, max_length=254)
    contact_phone: Optional[str] = Field(None, max_length=40)


class SchoolStatusRequest(BaseModel):
    status: Literal["Active", "Suspended", "NeedsReview"]
    evidence_reference: str = Field(..., min_length=4, max_length=500)


class SchoolResponse(BaseModel):
    school_id: UUID
    official_name: str
    emis_number: Optional[str]
    province: str
    district: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    status: str
    creator_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class FirstSchoolAdminBootstrapRequest(BaseModel):
    evidence_reference: str = Field(..., min_length=4, max_length=500)
    reason: str = Field(..., min_length=10, max_length=1000)


class FirstUniversityAdmissionsBootstrapRequest(BaseModel):
    evidence_reference: str = Field(..., min_length=4, max_length=500)
    reason: str = Field(..., min_length=10, max_length=1000)


class SchoolAdminInvitationRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    school_id: UUID


class UniversityAdmissionsInvitationRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    university_id: UUID


class RevokeInvitationRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=1000)


class InvitationRevocationResponse(BaseModel):
    account_id: UUID
    invitation_status: Literal["Revoked"]


class SchoolAdminInvitationResponse(BaseModel):
    account: AdminAccountResponse
    setup_token: str
    expires_at: datetime


class CompleteInvitationRequest(BaseModel):
    token: str = Field(..., min_length=32, max_length=256)
    password: str = Field(..., min_length=12, max_length=256)


class AdminOverviewResponse(BaseModel):
    registered_schools: int
    active_school_admins: int
    pending_accounts: int
    pending_school_verifications: int


class VerificationResponse(BaseModel):
    record_id: UUID
    subject_account_id: UUID
    verifier_account_id: UUID
    subject_role: str
    evidence_reference: str
    school_scope: List[UUID]
    university_id: Optional[UUID]
    outcome: str


class MarkResponse(BaseModel):
    mark_id: UUID
    subject_name: str
    score: int
    exam_type: str
    academic_year: int
    aps_points: int


class ProgrammeRecommendation(BaseModel):
    programme_id: UUID
    programme_name: str
    university_id: UUID
    faculty: str
    minimum_aps: int
    learner_aps: int
    eligibility: str
    explanation: str
    assessment_type: str
    has_subject_requirements: bool
    subject_requirements_met: bool
    application_deadline: date
    application_fee: str
    is_active: bool


class RecommendationsResponse(BaseModel):
    learner_id: UUID
    learner_aps: int
    recommendations: List[ProgrammeRecommendation]


class DashboardSummary(BaseModel):
    total_learners: int
    learners_with_marks: int
    applications_by_status: dict[str, int]
    eligibility_distribution: dict[str, int]
    total_applications: int


class ApplicationEligibilityCheck(BaseModel):
    learner_id: UUID
    programme_id: UUID
    learner_aps: int
    minimum_aps: int
    eligibility: str
    show_warning: bool
    warning_message: Optional[str]


class ScoringRuleRequest(BaseModel):
    university_id: Optional[UUID] = None
    band_thresholds: List[tuple[int, int]] = Field(..., min_length=1)
    subject_count: int = Field(..., ge=1)
    excluded_subjects: List[str] = Field(default_factory=list)
    subject_weightings: dict[str, float] = Field(default_factory=dict)


class ScoringRuleResponse(ScoringRuleRequest):
    university_id: UUID
    is_customized: bool


class GuidanceSessionCreateRequest(BaseModel):
    session_date: date
    purpose: str = Field(..., min_length=1, max_length=255)
    notes: str = Field(default="", max_length=10000)
    status: Literal["Scheduled", "Completed", "Cancelled"] = "Scheduled"


class GuidanceSessionUpdateRequest(BaseModel):
    session_date: Optional[date] = None
    purpose: Optional[str] = Field(None, min_length=1, max_length=255)
    notes: Optional[str] = Field(None, max_length=10000)
    status: Optional[Literal["Scheduled", "Completed", "Cancelled"]] = None


class GuidanceSessionResponse(BaseModel):
    guidance_session_id: UUID
    learner_id: UUID
    school_id: UUID
    responsible_staff_id: UUID
    session_date: date
    purpose: str
    notes: str
    status: str
    created_at: datetime
    updated_at: datetime


class NotificationResponse(BaseModel):
    notification_id: UUID
    type: str
    status: str
    message: str
    created_at: datetime


class DeadlineReminderResponse(BaseModel):
    created: int


class AuditLogResponse(BaseModel):
    entry_id: UUID
    actor_id: UUID
    action: str
    target_type: str
    target_id: UUID
    old_value: Any
    new_value: Any
    timestamp: datetime


class RagDocumentResponse(BaseModel):
    document_id: UUID
    logical_document_id: UUID
    university_id: UUID
    version_number: int
    lifecycle_state: str
    title: str
    file_name: str
    content_type: str
    embedding_model: str
    embedding_revision: str
    embedding_dimensions: int
    embedding_state: str
    reindex_required: bool
    created_at: datetime
    programme_draft_count: int = 0


class ProgrammeImportDraftResponse(BaseModel):
    draft_id: UUID
    university_id: UUID
    source_document_id: UUID
    name: str
    faculty: Optional[str]
    minimum_aps: Optional[int]
    application_deadline: Optional[date]
    application_fee: Optional[Decimal]
    required_documents: List[str]
    required_subjects: dict[str, int]
    source_evidence: str
    extraction_notes: str
    status: str
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    created_at: datetime


class UpdateProgrammeImportDraftRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    faculty: Optional[str] = Field(None, max_length=255)
    minimum_aps: Optional[int] = Field(None, ge=0, le=42)
    application_deadline: Optional[date] = None
    application_fee: Optional[Decimal] = Field(None, ge=0)
    required_documents: Optional[List[str]] = None
    required_subjects: Optional[dict[str, int]] = None

    @field_validator("required_subjects")
    @classmethod
    def validate_subject_requirements(cls, values: dict[str, int] | None):
        if values is not None and any(not isinstance(mark, int) or mark < 0 or mark > 100 for mark in values.values()):
            raise ValueError("Required-subject marks must be whole numbers from 0 to 100.")
        return values


class RagChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[UUID] = None
    learner_id: Optional[UUID] = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank.")
        return value.strip()


class RagChatResponse(BaseModel):
    conversation_id: UUID
    answer: str
    generation_mode: str
    sources: list[dict[str, Any]]
    history: list[dict[str, Any]]
    notice: str


class AssistantCitationResponse(BaseModel):
    chunk_id: str
    university: str
    title: str
    page: int | None = None
    section: str | None = None
    snippet: str
    score: float


class AssistantAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[UUID] = None
    learner_id: Optional[UUID] = None
    programme_id: Optional[UUID] = None
    university_id: Optional[UUID] = None

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


class AssistantAskResponse(BaseModel):
    answer: str
    citations: list[AssistantCitationResponse]
    mode: str
    model: str
    abstained: bool
    request_id: UUID


class SchoolReportResponse(BaseModel):
    total_learners: int
    learners_with_marks: int
    total_applications: int
    applications_by_status: dict[str, int]
    eligibility_distribution: dict[str, int]
    upcoming_deadlines: list[dict[str, Any]]


class DoEReportResponse(BaseModel):
    cohort_size: Optional[int]
    suppressed: bool
    total_learners: Optional[int]
    total_applications: Optional[int]
    applications_by_status: dict[str, Optional[int]]
    eligibility_distribution: dict[str, Optional[int]]


# ─────────────────────────────────────────────────────────────────────────────
# Response helpers
# ─────────────────────────────────────────────────────────────────────────────

def _learner_out(p: LearnerProfile) -> LearnerResponse:
    return LearnerResponse(
        learner_id=p.learner_id,
        full_name=p.full_name,
        school_id_number=p.school_id_number,
        grade=p.grade,
        status=p.status.value,
        counselor_id=p.counselor_id,
        school_id=p.school_id,
        aps_score=p.get_aps_score(),
        mark_count=len(p.marks),
    )


def _programme_out(p: UniversityProgramme) -> ProgrammeResponse:
    return ProgrammeResponse(
        programme_id=p.programme_id,
        university_id=p.university_id,
        name=p.name,
        faculty=p.faculty,
        minimum_aps=p.minimum_aps,
        application_deadline=p.application_deadline,
        application_fee=str(p.application_fee),
        required_documents=p.required_documents,
        status=p.status.value,
        is_active=p.is_active(),
        required_subjects=p.required_subjects,
        source_document_id=p.source_document_id,
        source_draft_id=p.source_draft_id,
        reviewed_by=p.reviewed_by,
        reviewed_at=p.reviewed_at,
    )


def _document_out(document: Document) -> LearnerDocumentResponse:
    return LearnerDocumentResponse(
        document_id=document.document_id,
        learner_id=document.learner_id,
        application_id=document.application_id,
        document_type=document.document_type,
        filename=document.filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        uploaded_by=document.uploaded_by,
        virus_scan_status=document.virus_scan_status,
        status=document.status,
        uploaded_at=document.uploaded_at,
        reviewed_by=document.reviewed_by,
        reviewed_at=document.reviewed_at,
        review_note=document.review_note,
        download_url=f"/api/documents/{document.document_id}/download",
    )


def _application_out(entity: Application) -> ApplicationResponse:
    blockers: list[str] = []
    if entity.status != ApplicationStatusEnum.Submitted:
        if entity.is_deadline_passed():
            blockers.append("The application deadline has passed.")
        if not entity.payment_reference and entity.fee_amount != Decimal("0"):
            blockers.append("A payment reference has not been recorded.")
        linked_documents = [
            document
            for document in entity.documents
            if document.application_id == entity.application_id
        ]
        if not linked_documents:
            blockers.append("No application documents are linked.")
        elif not any(
            document.application_id == entity.application_id
            and document.status == "Verified"
            for document in entity.documents
        ):
            blockers.append("Application documents are not verified.")
        if entity.linked_programme is not None:
            verified_types = {
                document.document_type
                for document in entity.documents
                if document.application_id == entity.application_id
                and document.status == "Verified"
            }
            missing_types = set(entity.linked_programme.required_documents) - verified_types
            if missing_types:
                blockers.append(
                    "Missing verified document types: "
                    + ", ".join(sorted(missing_types))
                    + "."
                )
        if entity.status not in (
            ApplicationStatusEnum.PackageReady,
            ApplicationStatusEnum.FeePaid,
        ):
            blockers.append("The application package is not ready.")
    return ApplicationResponse(
        application_id=entity.application_id,
        learner_id=entity.learner_id,
        programme_id=entity.programme_id,
        status=entity.status.value,
        fee_amount=str(entity.fee_amount),
        submission_timestamp=(
            entity.submission_timestamp.isoformat() if entity.submission_timestamp else None
        ),
        acknowledgement_reference=entity.acknowledgement_reference,
        submission_ready=entity.can_submit(),
        submission_blockers=blockers,
    )


def _application_review_out(
    entity: Application,
    learner: LearnerProfile,
    programme: UniversityProgramme,
) -> ApplicationReviewResponse:
    return ApplicationReviewResponse(
        application_id=entity.application_id,
        status=entity.status.value,
        fee_amount=str(entity.fee_amount),
        submission_timestamp=(
            entity.submission_timestamp.isoformat()
            if entity.submission_timestamp
            else None
        ),
        learner_id=learner.learner_id,
        learner_name=learner.full_name,
        learner_grade=learner.grade,
        learner_aps=learner.get_aps_score(),
        learner_marks=[
            ApplicationReviewMarkResponse(
                subject_name=mark.subject_name,
                score=mark.score,
                exam_type=mark.exam_type,
                academic_year=mark.academic_year,
                aps_points=mark.to_aps_points(),
            )
            for mark in learner.get_subject_marks()
        ],
        programme_id=programme.programme_id,
        programme_name=programme.name,
        programme_faculty=programme.faculty,
        required_documents=list(programme.required_documents),
        linked_documents=[
            ApplicationReviewDocumentResponse(
                document_id=document.document_id,
                document_type=document.document_type,
                filename=document.filename,
                mime_type=document.mime_type,
                size_bytes=document.size_bytes,
                virus_scan_status=document.virus_scan_status,
                status=document.status,
                uploaded_at=document.uploaded_at,
                reviewed_by=document.reviewed_by,
                reviewed_at=document.reviewed_at,
                review_note=document.review_note,
                download_url=f"/api/documents/{document.document_id}/download",
            )
            for document in entity.get_documents()
            if document.application_id == entity.application_id
        ],
        document_tracking_available=True,
        status_history=[
            _history_entry_out(entry)
            for entry in entity.get_status_history()
        ],
    )


def _history_entry_out(entry: StatusHistoryEntry) -> StatusHistoryEntryResponse:
    return StatusHistoryEntryResponse(
        entry_id=entry.entry_id,
        application_id=entry.application_id,
        previous_status=entry.previous_status.value,
        new_status=entry.new_status.value,
        changed_by=entry.changed_by,
        changed_at=entry.changed_at.isoformat(),
        note=entry.note,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app(
    scoring_rule_repo: ScoringRuleRepository | None = None,
    *,
    database_url: str | None = None,
    application_repository: ApplicationRepository | None = None,
    document_repository: DocumentRepository | None = None,
    document_storage_dir: Path | str | None = None,
    account_repo=None,
    session_repo=None,
    verification_repo=None,
    school_repo: SchoolRepository | None = None,
    invitation_repo=None,
    audit_repository=None,
    rag_repo: RagRepository | None = None,
    answer_provider: GroundedAnswerProvider | None = None,
    vector_store: VectorStore | None = None,
) -> FastAPI:
    """Create and return the UniMatch FastAPI application.

    Parameters
    ----------
    scoring_rule_repo:
        Optional pre-constructed ScoringRuleRepository. Supplying one allows
        tests to inject pre-seeded rules without a REST endpoint. Production
        callers can use the configured PostgreSQL repository when database_url
        is supplied.
    database_url:
        Optional SQLAlchemy PostgreSQL URL. When omitted, this application uses
        fresh in-memory repositories. The URL is not connected during app setup.
    """
    _settings = Settings.from_environment()
    _settings.require_secret_key()  # fails closed in production if SECRET_KEY is absent
    if _settings.is_production and database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required in production mode. "
            "Set DATABASE_URL to a valid PostgreSQL connection string before starting."
        )
    if database_url is not None and audit_repository is not None:
        raise ValueError(
            "A custom audit repository cannot participate in the PostgreSQL invitation transaction."
        )
    configured_document_storage = (
        Path(document_storage_dir).expanduser()
        if document_storage_dir is not None
        else _settings.document_storage_dir
    )
    if _settings.is_production and configured_document_storage is None:
        raise RuntimeError(
            "DOCUMENT_STORAGE_DIR is required in production mode for learner documents."
        )
    local_document_storage = LocalDocumentStorage(
        configured_document_storage
        or (Path.home() / ".unimatch" / "documents")
    )

    docs_url = None if _settings.is_production else "/docs"
    redoc_url = None if _settings.is_production else "/redoc"
    openapi_url = None if _settings.is_production else "/openapi.json"
    fastapi_app = FastAPI(
        title="UniMatch API",
        description=(
            "REST API for UniMatch: School-Based University Eligibility Recommender "
            "for South African Matriculants. Manages learner profiles, university "
            "programmes, and application workflows."
        ),
        version="1.0.0",
        contact={"name": "UniMatch Capstone Team"},
        license_info={"name": "MIT"},
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    @fastapi_app.middleware("http")
    async def log_requests(request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("Unhandled API error (%s)", type(exc).__name__)
            return JSONResponse(
                status_code=500,
                content={"detail": "An unexpected server error occurred."},
            )
        logger.info(
            "API request completed method=%s status=%s",
            request.method,
            response.status_code,
        )
        return response

    engine = None
    session_factory = None
    in_memory_university_scopes: dict[UUID, set[UUID]] = {}
    in_memory_programme_drafts: dict[UUID, dict[str, Any]] = {}
    in_memory_universities: dict[UUID, dict[str, Any]] = {
        entry.university_id: {
            "university_id": entry.university_id,
            "name": entry.name,
            "abbreviation": entry.abbreviation,
            "sector": entry.institution_type.removesuffix(" university"),
            "dhet_reference": None,
            "website": None,
            "status": "Active",
            "catalog_source": entry.source_url,
            "source_checked_on": date(2026, 11, 5),
        }
        for entry in PUBLIC_UNIVERSITIES
    }
    if database_url is None:
        learner_repo = InMemoryLearnerProfileRepository()
        programme_repo = InMemoryUniversityProgrammeRepository()
        application_repo = application_repository or InMemoryApplicationRepository()
        configured_scoring_rule_repo = scoring_rule_repo or InMemoryScoringRuleRepository()
        guidance_repo = InMemoryGuidanceSessionRepository()
        notification_repo = InMemoryNotificationRepository()
        audit_repo = audit_repository or InMemoryAuditLogRepository()
        configured_school_repo = school_repo or InMemorySchoolRepository()
        configured_invitation_repo = invitation_repo
        knowledge_repo = rag_repo or InMemoryRagRepository()
        learner_document_repo = (
            document_repository or LocalDocumentRepository(local_document_storage.root)
        )
    else:
        engine, session_factory = create_session_factory(database_url)
        learner_repo = PostgresLearnerProfileRepository(session_factory)
        programme_repo = PostgresUniversityProgrammeRepository(session_factory)
        application_repo = (
            application_repository or PostgresApplicationRepository(session_factory)
        )
        configured_scoring_rule_repo = (
            scoring_rule_repo or PostgresScoringRuleRepository(session_factory)
        )
        guidance_repo = PostgresGuidanceSessionRepository(session_factory)
        notification_repo = PostgresNotificationRepository(session_factory)
        audit_repo = audit_repository or PostgresAuditLogRepository(session_factory)
        configured_school_repo = school_repo or PostgresSchoolRepository(session_factory)
        configured_invitation_repo = invitation_repo or PostgresAccountInvitationRepository(session_factory)
        knowledge_repo = rag_repo or PostgresRagRepository(session_factory)
        learner_document_repo = (
            document_repository or PostgresDocumentRepository(session_factory)
        )

        fastapi_app.add_event_handler("shutdown", engine.dispose)

    configured_answer_provider = answer_provider or answer_provider_from_environment()
    semantic_store = vector_store
    semantic_lifecycle_lock = asyncio.Lock()

    def _get_semantic_store() -> VectorStore:
        nonlocal semantic_store
        if semantic_store is None:
            try:
                semantic_store = ChromaVectorStore(
                    collection_name=API_RAG_COLLECTION_NAME,
                    origin="api",
                )
            except Exception as exc:
                raise RuntimeError("The semantic vector store is unavailable.") from exc
        return semantic_store

    def _semantic_chunk(document: RagDocument, chunk: RagChunk) -> IndexedChunk:
        return IndexedChunk(
            chunk_id=str(chunk.chunk_id),
            source_id=str(document.document_id),
            university=str(document.university_id),
            title=document.title,
            source_url=None,
            retrieved_at=document.created_at.isoformat(),
            version=document.embedding_revision,
            page=None,
            section="Document body",
            text=chunk.text,
            origin="api",
        )

    def _sync_authorised_chunks(university_ids: set[UUID]) -> dict[str, tuple[RagDocument, RagChunk]]:
        if not university_ids:
            raise ValueError("A non-empty university scope is required for RAG synchronization.")
        indexed = knowledge_repo.list_active_chunks(university_ids)
        for document, chunk in indexed:
            if (
                document.embedding_model != EMBEDDING_MODEL
                or document.embedding_revision != EMBEDDING_REVISION
                or document.embedding_dimensions != EMBEDDING_DIMENSIONS
                or len(chunk.embedding) != EMBEDDING_DIMENSIONS
            ):
                raise RagReindexRequiredError(
                    "One or more university sources use a different embedding model or revision. "
                    "Re-index those sources before searching."
                )
        store = _get_semantic_store()
        if not callable(getattr(store, "reconcile", None)):
            raise RuntimeError("The configured vector store does not support scoped reconciliation.")
        if not callable(getattr(store, "query", None)):
            raise RuntimeError("The configured vector store does not support filtered queries.")
        chunks = [_semantic_chunk(document, chunk) for document, chunk in indexed]
        try:
            store.reconcile(
                {str(value) for value in university_ids},
                {chunk.chunk_id for chunk in chunks},
            )
            if indexed:
                store.upsert(chunks, [list(chunk.embedding) for _document, chunk in indexed])
        except Exception as exc:
            raise RuntimeError("Semantic vector synchronization failed; no answer was generated.") from exc
        return {str(chunk.chunk_id): (document, chunk) for document, chunk in indexed}

    def _retrieve_authorised_semantic(
        question: str, university_ids: set[UUID], *, limit: int = 4
    ) -> list[tuple[float, RagDocument, RagChunk]]:
        return _retrieve_authorised_semantic_locked(question, university_ids, limit=limit)

    def _retrieve_authorised_semantic_locked(
        question: str, university_ids: set[UUID], *, limit: int = 4
    ) -> list[tuple[float, RagDocument, RagChunk]]:
        if not university_ids:
            return []
        authorised = _sync_authorised_chunks(university_ids)
        if not authorised:
            return []
        query_embedding = embed_texts([question])[0]
        store = _get_semantic_store()
        try:
            rows = store.query(
                query_embedding,
                limit,
                allowed_universities={str(value) for value in university_ids},
            )
        except Exception as exc:
            raise RuntimeError("The scoped semantic query failed; no answer was generated.") from exc
        matches = []
        for indexed, score in rows:
            source = authorised.get(indexed.chunk_id)
            if source is not None and score >= 0.30:
                matches.append((float(score), source[0], source[1]))
        return matches[:limit]

    def _reconcile_semantic_university(university_id: UUID) -> None:
        _sync_authorised_chunks({university_id})

    assistant_rate_events: dict[UUID, list[float]] = {}

    def _check_assistant_rate_limit(account_id: UUID) -> None:
        now = time.monotonic()
        window_start = now - 60.0
        events = [stamp for stamp in assistant_rate_events.get(account_id, []) if stamp > window_start]
        limit = max(1, int(os.environ.get("RAG_RATE_LIMIT_PER_MINUTE", "30")))
        if len(events) >= limit:
            raise HTTPException(status_code=429, detail="Guidance assistant rate limit exceeded. Try again later.")
        events.append(now)
        assistant_rate_events[account_id] = events

    # Auth repository wiring — Stage 2B.
    # Development (database_url is None): in-memory repos.
    # Production (database_url is set): Postgres repos; startup schema validation runs.
    # Injectable for integration testing: pass pre-seeded repos to override defaults.
    if database_url is None:
        if _settings.is_production:
            raise RuntimeError(
                "DATABASE_URL is required in production mode. "
                "Set DATABASE_URL to a valid PostgreSQL connection string before starting."
            )
        _account_repo      = account_repo      if account_repo      is not None else InMemoryUserAccountRepository()
        _session_repo      = session_repo      if session_repo      is not None else InMemorySessionRepository()
        _verification_repo = verification_repo if verification_repo is not None else InMemoryVerificationRecordRepository()
    else:
        _account_repo      = account_repo      if account_repo      is not None else PostgresUserAccountRepository(session_factory)
        _session_repo      = session_repo      if session_repo      is not None else PostgresSessionRepository(session_factory)
        _verification_repo = verification_repo if verification_repo is not None else PostgresVerificationRecordRepository(session_factory)
        # Fail-closed: refuse to start if auth schema is absent.
        _verify_auth_schema(engine)
    _provisioning_svc = AccountProvisioningService(
        account_repo=_account_repo,
        verification_repo=_verification_repo,
    )
    if configured_invitation_repo is None:
        configured_invitation_repo = InMemoryAccountInvitationRepository(
            _account_repo, _verification_repo, audit_repo
        )

    learner_svc = LearnerProfileService(
        learner_repo=learner_repo,
        application_repo=application_repo,
        scoring_rule_repo=configured_scoring_rule_repo,
        programme_repo=programme_repo,
    )
    programme_svc = UniversityProgrammeService(programme_repo=programme_repo)
    application_svc = ApplicationService(
        application_repo=application_repo,
        learner_repo=learner_repo,
        programme_repo=programme_repo,
        scoring_rule_repo=configured_scoring_rule_repo,
        document_repo=learner_document_repo,
    )

    @fastapi_app.exception_handler(LearnerNotFoundError)
    async def _learner_404(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Learner not found."})

    @fastapi_app.exception_handler(ProgrammeNotFoundError)
    async def _programme_404(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Programme not found."})

    @fastapi_app.exception_handler(ApplicationNotFoundError)
    async def _application_404(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Application not found."})

    @fastapi_app.exception_handler(NotEligibleError)
    async def _not_eligible(request, exc):
        return JSONResponse(
            status_code=422,
            content={"detail": "The learner does not meet the application eligibility requirements."},
        )

    @fastapi_app.exception_handler(DuplicateApplicationError)
    async def _duplicate(request, exc):
        return JSONResponse(
            status_code=409,
            content={"detail": "An active application already exists for this programme."},
        )

    @fastapi_app.exception_handler(ProgrammeNotActiveError)
    async def _not_active(request, exc):
        return JSONResponse(status_code=409, content={"detail": "Programme is not open for applications."})

    @fastapi_app.exception_handler(InvalidStatusTransitionError)
    async def _bad_transition(request, exc):
        return JSONResponse(status_code=422, content={"detail": "This application status transition is not allowed."})

    @fastapi_app.exception_handler(ValueError)
    async def _value_error(request, exc):
        return JSONResponse(status_code=400, content={"detail": "The requested operation is invalid."})

    @fastapi_app.exception_handler(NotAuthorizedError)
    async def _not_authorized(request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @fastapi_app.exception_handler(AccountAlreadyExistsError)
    async def _account_exists(request, exc):
        return JSONResponse(status_code=409, content={"detail": "An account with this email already exists."})

    @fastapi_app.exception_handler(AccountNotFoundError)
    async def _account_not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Account not found."})

    @fastapi_app.exception_handler(NotVerifiedError)
    async def _not_verified(request, exc):
        return JSONResponse(status_code=422, content={"detail": "Required account verification is incomplete."})

    @fastapi_app.exception_handler(SelfActivationError)
    async def _self_activation(request, exc):
        return JSONResponse(status_code=422, content={"detail": "The account actor cannot activate their own account."})

    @fastapi_app.exception_handler(AlreadyActiveError)
    async def _already_active(request, exc):
        return JSONResponse(status_code=409, content={"detail": "Account is already active."})

    @fastapi_app.exception_handler(InvalidRoleForProvisioningError)
    async def _invalid_role(request, exc):
        return JSONResponse(status_code=422, content={"detail": "That account role cannot be provisioned here."})

    @fastapi_app.exception_handler(OutOfScopeError)
    async def _out_of_scope(request, exc):
        return JSONResponse(status_code=403, content={"detail": "The requested action is outside the actor's authorized scope."})

    @fastapi_app.exception_handler(ProvisioningError)
    async def _provisioning_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    # ── Auth helpers (closures over repos) ───────────────────────────────────

    _cookie_secure = _settings.is_production
    _session_lifetime = _settings.session_lifetime_seconds

    def _set_session_cookie(response, raw_token: str) -> None:
        response.set_cookie(
            key="session",
            value=raw_token,
            httponly=True,
            secure=_cookie_secure,
            samesite="strict",
            path="/api",
            max_age=_session_lifetime,
        )

    def _clear_session_cookie(response) -> None:
        response.delete_cookie(key="session", path="/api", samesite="strict", secure=_cookie_secure)

    def _resolve_principal(request: Request) -> AuthPrincipal | None:
        """Resolve the session cookie to a server-derived principal.

        Returns None when the cookie is absent, the session is invalid or
        expired, the account is not active, or the account is currently locked.
        Never raises.
        """
        raw = request.cookies.get("session")
        if not raw:
            return None
        digest = digest_token(raw)
        session = _session_repo.find_by_token_digest(digest)
        if session is None or not session.is_active():
            return None
        account = _account_repo.find_by_id(session.account_id)
        if account is None:
            return None
        if account.account_state != AccountStateEnum.Active:
            return None
        if account.is_locked():
            return None
        if account.role == RoleEnum.SchoolAdmin and account.school_id is not None:
            assigned_school = configured_school_repo.find_by_id(account.school_id)
            if assigned_school is not None and assigned_school.status != "Active":
                return None
        return AuthPrincipal(
            account_id=account.user_id,
            role=account.role,
            account_state=account.account_state,
            school_id=account.school_id,
            university_id=account.university_id,
            university_ids=frozenset(
                account.university_ids | in_memory_university_scopes.get(account.user_id, set())
            ),
        )

    def _check_csrf(request: Request) -> bool:
        """Return True when the X-CSRF-Token header matches the session's stored CSRF token.

        Returns False (not raises) so callers can produce a consistent 403 response.
        Returns True for unauthenticated requests — they will fail the auth check separately.
        """
        raw = request.cookies.get("session")
        if not raw:
            return True  # no session: auth guard will reject, CSRF is moot
        digest = digest_token(raw)
        session = _session_repo.find_by_token_digest(digest)
        if session is None or not session.is_active():
            return True  # stale session: auth guard will reject
        header_token = request.headers.get("X-CSRF-Token", "")
        return bool(session.csrf_token) and header_token == session.csrf_token

    _CSRF_PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
    _CSRF_EXEMPT_PATHS = {"/api/auth/login"}  # pre-session; SameSite=Strict protects it

    # ── Authorization helpers (closures over repos/services) ─────────────────

    def _require_auth(request: Request) -> AuthPrincipal:
        p = _resolve_principal(request)
        if p is None:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        return p

    def _require_role(principal: AuthPrincipal, *roles: RoleEnum) -> None:
        if principal.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role {principal.role.value!r} is not authorized for this operation.",
            )

    def _require_csrf(request: Request) -> None:
        if request.method in _CSRF_PROTECTED_METHODS and request.url.path not in _CSRF_EXEMPT_PATHS:
            if not _check_csrf(request):
                raise HTTPException(status_code=403, detail="CSRF token missing or invalid.")

    def _require_school_learner(learner_id: UUID, principal: AuthPrincipal) -> LearnerProfile:
        learner = learner_svc.get_profile(learner_id)
        if learner.school_id != principal.school_id:
            raise HTTPException(status_code=404, detail="Learner not found.")
        return learner

    def _require_school_document(
        document_id: UUID, principal: AuthPrincipal
    ) -> Document:
        document = learner_document_repo.find_by_id(document_id)
        if (
            document is None
            or principal.school_id is None
            or document.school_id != principal.school_id
        ):
            raise HTTPException(status_code=404, detail="Document not found.")
        return document

    def _require_document_download_access(
        document: Document, principal: AuthPrincipal
    ) -> None:
        if principal.role in {RoleEnum.SchoolAdmin, RoleEnum.Teacher}:
            if principal.school_id is None:
                raise HTTPException(status_code=403, detail="No school scope is assigned.")
            if document.school_id != principal.school_id:
                raise HTTPException(status_code=404, detail="Document not found.")
            return
        if principal.role == RoleEnum.UniversityAdmissions:
            if document.application_id is None:
                raise HTTPException(status_code=404, detail="Document not found.")
            application, _programme = _require_university_application(
                document.application_id, principal
            )
            if (
                application.learner_id != document.learner_id
                or application.status
                not in {
                    ApplicationStatusEnum.Submitted,
                    ApplicationStatusEnum.UnderReview,
                    ApplicationStatusEnum.DocsRequested,
                    ApplicationStatusEnum.Accepted,
                    ApplicationStatusEnum.Rejected,
                    ApplicationStatusEnum.Waitlisted,
                }
            ):
                raise HTTPException(status_code=404, detail="Document not found.")
            return
        raise HTTPException(status_code=403, detail="Not authorized to access documents.")

    def _require_school_application(application_id: UUID, principal: AuthPrincipal) -> Application:
        app = application_svc.get_application(application_id)
        learner = learner_svc.get_profile(app.learner_id)
        if learner.school_id != principal.school_id:
            raise HTTPException(status_code=404, detail="Application not found.")
        return app

    def _require_university_programme(programme_id: UUID, principal: AuthPrincipal) -> UniversityProgramme:
        programme = programme_svc.get_programme(programme_id)
        if not principal.has_university_access(programme.university_id):
            raise HTTPException(status_code=403, detail="Not authorized for this university's programmes.")
        return programme

    def _require_university_application(
        application_id: UUID, principal: AuthPrincipal
    ) -> tuple[Application, UniversityProgramme]:
        university_scopes = set(principal.university_ids)
        if principal.university_id is not None:
            university_scopes.add(principal.university_id)
        if not university_scopes:
            raise HTTPException(status_code=403, detail="No verified university scope for this account.")
        application = application_svc.get_application(application_id)
        programme = programme_svc.get_programme(application.programme_id)
        if not principal.has_university_access(programme.university_id):
            raise HTTPException(status_code=404, detail="Application not found.")
        return application, programme

    def _record_audit(
        principal: AuthPrincipal,
        action: str,
        target_type: str,
        target_id: UUID,
        *,
        school_id: UUID | None = None,
        university_id: UUID | None = None,
        old_value: Any = None,
        new_value: Any = None,
    ) -> None:
        audit_repo.save(
            AuditLogEntry.create(
                actor=principal.account_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                old=old_value,
                new=new_value,
                school_id=school_id,
                university_id=university_id,
            )
        )

    def _programme_draft_dict(row: Any) -> dict[str, Any]:
        return {
            "draft_id": row.draft_id,
            "university_id": row.university_id,
            "source_document_id": row.source_document_id,
            "name": row.name,
            "faculty": row.faculty,
            "minimum_aps": row.minimum_aps,
            "application_deadline": row.application_deadline,
            "application_fee": row.application_fee,
            "required_documents": list(row.required_documents or []),
            "required_subjects": dict(row.required_subjects or {}),
            "source_evidence": row.source_evidence,
            "extraction_notes": row.extraction_notes,
            "status": row.status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "created_at": row.created_at,
        }

    def _programme_drafts_for_document(document_id: UUID) -> list[dict[str, Any]]:
        if session_factory is None:
            return [
                row for row in in_memory_programme_drafts.values()
                if row["source_document_id"] == document_id
            ]
        from sqlalchemy import select
        with session_factory() as session:
            rows = session.scalars(
                select(ProgrammeImportDraftRecord)
                .where(ProgrammeImportDraftRecord.source_document_id == document_id)
                .order_by(ProgrammeImportDraftRecord.created_at, ProgrammeImportDraftRecord.draft_id)
            ).all()
            return [_programme_draft_dict(row) for row in rows]

    def _get_programme_draft(draft_id: UUID) -> dict[str, Any] | None:
        if session_factory is None:
            return in_memory_programme_drafts.get(draft_id)
        with session_factory() as session:
            row = session.get(ProgrammeImportDraftRecord, draft_id)
            return None if row is None else _programme_draft_dict(row)

    def _update_programme_draft(draft_id: UUID, updates: dict[str, Any]) -> dict[str, Any] | None:
        if session_factory is None:
            row = in_memory_programme_drafts.get(draft_id)
            if row is not None:
                row.update(updates)
            return row
        with session_factory() as session:
            row = session.get(ProgrammeImportDraftRecord, draft_id, with_for_update=True)
            if row is None:
                return None
            for key, value in updates.items():
                setattr(row, key, value)
            session.commit()
            return _programme_draft_dict(row)

    def _ensure_programme_drafts(document: RagDocument, source_text: str) -> list[dict[str, Any]]:
        existing = _programme_drafts_for_document(document.document_id)
        candidates = extract_programme_drafts(source_text)
        existing_names = {str(row["name"]).casefold() for row in existing}
        candidates = [
            candidate for candidate in candidates
            if str(candidate["name"]).casefold() not in existing_names
        ]
        if not candidates:
            return existing
        if session_factory is None:
            for candidate in candidates:
                row = {
                    **candidate,
                    "draft_id": uuid4(),
                    "university_id": document.university_id,
                    "source_document_id": document.document_id,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "created_at": datetime.now(timezone.utc),
                }
                in_memory_programme_drafts[row["draft_id"]] = row
            return _programme_drafts_for_document(document.document_id)
        from sqlalchemy.exc import IntegrityError
        try:
            with session_factory() as session:
                now = datetime.now(timezone.utc)
                for candidate in candidates:
                    session.add(ProgrammeImportDraftRecord(
                        draft_id=uuid4(),
                        university_id=document.university_id,
                        source_document_id=document.document_id,
                        created_at=now,
                        **candidate,
                    ))
                session.commit()
        except IntegrityError:
            # Concurrent regeneration may win the unique source-candidate key.
            # Read the committed candidates after rolling back the failed insert.
            pass
        return _programme_drafts_for_document(document.document_id)

    def _create_notification(
        recipient_id: UUID,
        notification_type: str,
        message: str,
        event_key: str,
    ) -> bool:
        if notification_repo.find_by_event_key(event_key) is not None:
            return False
        notification_repo.save(
            Notification(
                notification_id=uuid4(),
                recipient_id=recipient_id,
                type=notification_type,
                status="Unread",
                message=message,
                event_key=event_key,
            )
        )
        return True

    def _guidance_out(session: GuidanceSession) -> GuidanceSessionResponse:
        return GuidanceSessionResponse(
            guidance_session_id=session.guidance_session_id,
            learner_id=session.learner_id,
            school_id=session.school_id,
            responsible_staff_id=session.responsible_staff_id,
            session_date=session.session_date,
            purpose=session.purpose,
            notes=session.notes,
            status=session.status,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _audit_out(entry: AuditLogEntry) -> AuditLogResponse:
        return AuditLogResponse(
            entry_id=entry.entry_id,
            actor_id=entry.actor_id,
            action=entry.action,
            target_type=entry.target_type,
            target_id=entry.target_id,
            old_value=entry.old_value,
            new_value=entry.new_value,
            timestamp=entry.timestamp,
        )

    def _school_out(school: School) -> SchoolResponse:
        return SchoolResponse(
            school_id=school.school_id, official_name=school.official_name,
            emis_number=school.emis_number, province=school.province,
            district=school.district, contact_email=school.contact_email,
            contact_phone=school.contact_phone, status=school.status,
            creator_id=school.creator_id, created_at=school.created_at,
            updated_at=school.updated_at,
        )

    def _admin_account_out(account) -> AdminAccountResponse:
        records = _verification_repo.find_by_subject(account.user_id)
        latest = max(records, key=lambda r: (r.created_at, str(r.record_id)), default=None)
        return AdminAccountResponse(
            account_id=account.user_id, email=account.email, role=account.role.value,
            account_state=account.account_state.value, school_id=account.school_id,
            university_id=account.university_id,
            university_ids=sorted(
                account.university_ids | ({account.university_id} if account.university_id else set()),
                key=str,
            ),
            creator_id=account.creator_id, created_at=account.created_at,
            updated_at=account.updated_at,
            verification_status=latest.outcome if latest else "NotSubmitted",
            credentials_ready=configured_invitation_repo.is_ready(account.user_id),
            invitation_active=configured_invitation_repo.is_active(account.user_id),
            invitation_status=configured_invitation_repo.latest_status(account.user_id),
        )

    # ── /api/auth ────────────────────────────────────────────────────────────

    @fastapi_app.post("/api/auth/login", tags=["Auth"])
    async def login(payload: LoginRequest):
        _generic_error = JSONResponse(
            status_code=401,
            content={"detail": "Invalid credentials."},
        )

        email = payload.email.strip().lower()
        account = _account_repo.find_by_email(email)
        if account is None:
            verify_password(payload.password, DUMMY_PASSWORD_HASH)
            return _generic_error

        # Fast-path lockout check (may be stale; record_failed_login re-checks authoritatively).
        if account.is_locked():
            return _generic_error

        if not verify_password(payload.password, account.password_hash):
            _account_repo.record_failed_login(account.user_id)
            return _generic_error

        if account.account_state == AccountStateEnum.Pending:
            return JSONResponse(status_code=403, content={"detail": "Account pending verification."})
        if account.account_state == AccountStateEnum.Suspended:
            return JSONResponse(status_code=403, content={"detail": "Account suspended."})
        if account.account_state != AccountStateEnum.Active:
            return JSONResponse(status_code=403, content={"detail": "Account not active."})
        if account.role == RoleEnum.SchoolAdmin and account.school_id is not None:
            assigned_school = configured_school_repo.find_by_id(account.school_id)
            if assigned_school is not None and assigned_school.status != "Active":
                return JSONResponse(status_code=403, content={"detail": "School is not active."})

        _account_repo.record_successful_login(account.user_id)

        raw_token = generate_session_token()
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=uuid4(),
            account_id=account.user_id,
            token_digest=digest_token(raw_token),
            created_at=now,
            expires_at=now + timedelta(seconds=_session_lifetime),
            csrf_token=generate_csrf_token(),
        )
        _session_repo.save(session)

        out = JSONResponse(
            status_code=200,
            content={"message": "Logged in.", "role": account.role.value},
        )
        _set_session_cookie(out, raw_token)
        return out

    @fastapi_app.post("/api/auth/logout", tags=["Auth"])
    async def logout(request: Request):
        _require_csrf(request)
        raw = request.cookies.get("session")
        if raw:
            digest = digest_token(raw)
            session = _session_repo.find_by_token_digest(digest)
            if session is not None and session.is_active():
                session.revoke()
                _session_repo.save(session)

        out = JSONResponse(status_code=200, content={"message": "Logged out."})
        _clear_session_cookie(out)
        return out

    @fastapi_app.get("/api/auth/me", response_model=SessionInfoResponse, tags=["Auth"])
    async def session_info(request: Request):
        principal = _resolve_principal(request)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        return SessionInfoResponse(
            account_id=principal.account_id,
            role=principal.role.value,
            school_id=principal.school_id,
            university_id=principal.university_id,
            university_ids=sorted(
                principal.university_ids | ({principal.university_id} if principal.university_id else set()),
                key=str,
            ),
        )

    @fastapi_app.get(
        "/api/universities/catalog",
        response_model=List[UniversityInstitutionResponse],
        tags=["Universities"],
    )
    async def university_catalog(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin, RoleEnum.UniversityAdmissions, RoleEnum.SchoolAdmin)
        if session_factory is None:
            records = list(in_memory_universities.values())
        else:
            with session_factory() as session:
                rows = session.query(UniversityInstitutionRecord).order_by(
                    UniversityInstitutionRecord.name
                ).all()
                records = [
                    {
                        "university_id": row.university_id,
                        "name": row.name,
                        "abbreviation": row.abbreviation,
                        "sector": row.sector,
                        "dhet_reference": row.dhet_reference,
                        "website": row.website,
                        "status": row.status,
                        "catalog_source": row.catalog_source,
                        "source_checked_on": row.source_checked_on,
                    }
                    for row in rows
                ]
        if principal.role == RoleEnum.UniversityAdmissions:
            allowed = set(principal.university_ids)
            if principal.university_id is not None:
                allowed.add(principal.university_id)
            records = [record for record in records if record["university_id"] in allowed]
        return records

    @fastapi_app.post(
        "/api/admin/universities",
        response_model=UniversityInstitutionResponse,
        status_code=201,
        tags=["Administration"],
    )
    async def create_private_university(payload: CreatePrivateUniversityRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        university_id = uuid4()
        now = datetime.now(timezone.utc)
        record = {
            "university_id": university_id,
            "name": payload.name.strip(),
            "abbreviation": payload.abbreviation.strip().upper(),
            "sector": "Private",
            "dhet_reference": payload.dhet_reference.strip(),
            "website": payload.website,
            "status": "Unverified",
            "catalog_source": "DHET private higher education register; entered by SystemAdmin",
            "source_checked_on": None,
            "created_at": now,
            "updated_at": now,
        }
        if session_factory is None:
            if any(item["name"].casefold() == record["name"].casefold() for item in in_memory_universities.values()):
                raise HTTPException(status_code=409, detail="An institution with that name already exists.")
            in_memory_universities[university_id] = record
        else:
            from sqlalchemy.exc import IntegrityError
            try:
                with session_factory() as session:
                    session.add(UniversityInstitutionRecord(**record))
                    session.commit()
            except IntegrityError as exc:
                raise HTTPException(status_code=409, detail="Institution name or abbreviation already exists.") from exc
        _record_audit(
            principal, "university.institution.created", "university_institution", university_id,
            university_id=university_id,
            new_value={"name": record["name"], "sector": "Private", "status": "Unverified"},
        )
        return record

    @fastapi_app.post(
        "/api/admin/universities/{university_id}/verify",
        response_model=UniversityInstitutionResponse,
        tags=["Administration"],
    )
    async def verify_private_university(
        university_id: UUID, payload: VerifyPrivateUniversityRequest, request: Request
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        if session_factory is None:
            institution = in_memory_universities.get(university_id)
            if institution is None or institution["sector"] != "Private":
                raise HTTPException(status_code=404, detail="Private institution not found.")
            institution.update({
                "status": "Active", "verification_reference": payload.evidence_reference.strip(),
                "verified_by": principal.account_id, "verified_at": datetime.now(timezone.utc),
            })
            response = institution
        else:
            with session_factory() as session:
                institution = session.get(UniversityInstitutionRecord, university_id, with_for_update=True)
                if institution is None or institution.sector != "Private":
                    raise HTTPException(status_code=404, detail="Private institution not found.")
                institution.status = "Active"
                institution.verification_reference = payload.evidence_reference.strip()
                institution.verified_by = principal.account_id
                institution.verified_at = datetime.now(timezone.utc)
                institution.source_checked_on = date.today()
                institution.updated_at = datetime.now(timezone.utc)
                session.commit()
                response = {
                    "university_id": institution.university_id, "name": institution.name,
                    "abbreviation": institution.abbreviation, "sector": institution.sector,
                    "dhet_reference": institution.dhet_reference, "website": institution.website,
                    "status": institution.status, "catalog_source": institution.catalog_source,
                    "source_checked_on": institution.source_checked_on,
                }
        _record_audit(
            principal, "university.institution.verified", "university_institution", university_id,
            university_id=university_id,
            new_value={"status": "Active", "evidence_reference": payload.evidence_reference.strip()},
        )
        return response

    @fastapi_app.post(
        "/api/admin/accounts/{account_id}/university-scopes",
        tags=["Administration"],
    )
    async def grant_university_scopes(
        account_id: UUID, payload: GrantUniversityScopesRequest, request: Request
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        if session_factory is None:
            account = _account_repo.find_by_id(account_id)
            if account is None or account.role != RoleEnum.UniversityAdmissions:
                raise HTTPException(status_code=404, detail="UniversityAdmissions account not found.")
            for university_id in payload.university_ids:
                institution = in_memory_universities.get(university_id)
                if institution is None or institution["status"] != "Active":
                    raise HTTPException(status_code=422, detail="Every granted institution must be active.")
            in_memory_university_scopes.setdefault(account_id, set()).update(payload.university_ids)
            account.university_ids.update(payload.university_ids)
        else:
            from sqlalchemy import select
            with session_factory() as session:
                account = session.get(AccountRecord, account_id, with_for_update=True)
                if account is None or account.role != RoleEnum.UniversityAdmissions.value:
                    raise HTTPException(status_code=404, detail="UniversityAdmissions account not found.")
                institutions = session.scalars(
                    select(UniversityInstitutionRecord).where(
                        UniversityInstitutionRecord.university_id.in_(payload.university_ids),
                        UniversityInstitutionRecord.status == "Active",
                    )
                ).all()
                if {institution.university_id for institution in institutions} != set(payload.university_ids):
                    raise HTTPException(status_code=422, detail="Every granted institution must be active.")
                existing = set(session.scalars(
                    select(AccountUniversityScopeRecord.university_id).where(
                        AccountUniversityScopeRecord.account_id == account_id
                    )
                ).all())
                now = datetime.now(timezone.utc)
                for university_id in set(payload.university_ids) - existing:
                    session.add(AccountUniversityScopeRecord(
                        account_id=account_id, university_id=university_id,
                        granted_by=principal.account_id, created_at=now,
                    ))
                session.commit()
        _record_audit(
            principal, "university.account_scopes.granted", "account", account_id,
            new_value={"university_ids": [str(value) for value in sorted(set(payload.university_ids), key=str)]},
        )
        return {"account_id": str(account_id), "university_ids": [str(value) for value in sorted(set(payload.university_ids), key=str)]}

    @fastapi_app.get("/api/auth/csrf", tags=["Auth"])
    async def get_csrf_token(request: Request):
        """Return the CSRF token for the current authenticated session.

        The frontend must call this after login and include the returned value
        as the X-CSRF-Token header on every subsequent state-changing request.
        Tokens are session-specific and rotate on re-login.
        """
        raw = request.cookies.get("session")
        if not raw:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        digest = digest_token(raw)
        session = _session_repo.find_by_token_digest(digest)
        if session is None or not session.is_active():
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        if not session.csrf_token:
            return JSONResponse(status_code=401, content={"detail": "Session has no CSRF token. Please log in again."})
        return JSONResponse(status_code=200, content={"csrf_token": session.csrf_token})

    @fastapi_app.post("/api/auth/provision", response_model=AccountResponse, status_code=201, tags=["Auth"])
    async def provision_account(payload: ProvisionAccountRequest, request: Request):
        _require_csrf(request)
        principal = _resolve_principal(request)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        try:
            role = RoleEnum(payload.role)
        except ValueError:
            return JSONResponse(status_code=422, content={"detail": f"Unknown role: {payload.role!r}"})
        if role == RoleEnum.SchoolAdmin:
            _require_role(principal, RoleEnum.SystemAdmin, RoleEnum.DoEOfficial)
            if principal.role == RoleEnum.DoEOfficial:
                actor_records = _verification_repo.find_by_subject(principal.account_id)
                latest_actor_record = max(
                    actor_records, key=lambda item: (item.created_at, str(item.record_id)), default=None
                )
                if latest_actor_record is None or latest_actor_record.outcome != "Verified":
                    raise HTTPException(status_code=403, detail="DoEOfficial verification is required.")
                scope = latest_actor_record.school_scope
                if payload.school_id is None or payload.school_id not in scope:
                    raise HTTPException(status_code=403, detail="The school is outside the verified DoEOfficial scope.")
            school = configured_school_repo.find_by_id(payload.school_id) if payload.school_id else None
            if school is None or school.status != "Active":
                raise HTTPException(status_code=422, detail="Select an existing active school.")
        account = _provisioning_svc.provision_account(
            actor=principal,
            email=payload.email,
            password=payload.password,
            role=role,
            school_id=payload.school_id,
            university_id=payload.university_id,
        )
        _record_audit(principal, "AccountProvisioned", "Account", account.user_id,
                      school_id=account.school_id, university_id=account.university_id,
                      new_value={"email": account.email, "role": account.role.value,
                                 "account_state": account.account_state.value})
        return AccountResponse(
            account_id=account.user_id,
            email=account.email,
            role=account.role.value,
            account_state=account.account_state.value,
            school_id=account.school_id,
        )

    @fastapi_app.post(
        "/api/auth/accounts/{account_id}/verify",
        response_model=VerificationResponse,
        tags=["Auth"],
    )
    async def record_verification(
        account_id: UUID, payload: RecordVerificationRequest, request: Request
    ):
        _require_csrf(request)
        principal = _resolve_principal(request)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        target = _account_repo.find_by_id(account_id)
        if target is None:
            raise AccountNotFoundError("Account not found.")
        if target.role == RoleEnum.SchoolAdmin and (
            target.school_id is None or target.school_id not in payload.school_scope
        ):
            raise HTTPException(status_code=422, detail="SchoolAdmin verification must include the assigned school scope.")
        if target.role == RoleEnum.UniversityAdmissions and (
            target.university_id is None or payload.university_id != target.university_id
        ):
            raise HTTPException(status_code=422, detail="UniversityAdmissions verification must include the account's assigned university scope.")
        record = _provisioning_svc.record_verification(
            actor=principal,
            target_id=account_id,
            evidence_reference=payload.evidence_reference,
            school_scope=payload.school_scope,
            university_id=payload.university_id,
            outcome=payload.outcome,
        )
        _record_audit(principal, "AccountVerificationRecorded", "Account", account_id,
                      school_id=target.school_id, university_id=target.university_id,
                      new_value={"outcome": record.outcome,
                                 "evidence_reference": record.evidence_reference,
                                 "school_scope": [str(sid) for sid in record.school_scope]})
        return VerificationResponse(
            record_id=record.record_id,
            subject_account_id=record.subject_account_id,
            verifier_account_id=record.verifier_account_id,
            subject_role=record.subject_role.value,
            evidence_reference=record.evidence_reference,
            school_scope=record.school_scope,
            university_id=record.university_id,
            outcome=record.outcome,
        )

    @fastapi_app.post(
        "/api/auth/accounts/{account_id}/activate",
        response_model=AccountResponse,
        tags=["Auth"],
    )
    async def activate_account(account_id: UUID, request: Request):
        _require_csrf(request)
        principal = _resolve_principal(request)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        if not configured_invitation_repo.is_ready(account_id):
            raise HTTPException(status_code=422, detail="The invited user must set their password before activation.")
        target = _account_repo.find_by_id(account_id)
        if target is not None and target.role == RoleEnum.SchoolAdmin:
            school = configured_school_repo.find_by_id(target.school_id) if target.school_id else None
            if school is None or school.status != "Active":
                raise HTTPException(status_code=422, detail="The SchoolAdmin's assigned school must be active.")
        account = _provisioning_svc.activate_account(
            actor=principal,
            target_id=account_id,
        )
        _record_audit(principal, "AccountActivated", "Account", account.user_id,
                      school_id=account.school_id,
                      new_value={"role": account.role.value, "account_state": account.account_state.value})
        return AccountResponse(
            account_id=account.user_id,
            email=account.email,
            role=account.role.value,
            account_state=account.account_state.value,
            school_id=account.school_id,
        )

    @fastapi_app.post(
        "/api/auth/accounts/{account_id}/suspend",
        response_model=AccountResponse,
        tags=["Auth"],
    )
    async def suspend_account(account_id: UUID, request: Request):
        _require_csrf(request)
        principal = _resolve_principal(request)
        if principal is None:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
        account = _provisioning_svc.suspend_account(
            actor=principal,
            target_id=account_id,
        )
        for session in _session_repo.find_by_account(account.user_id):
            if session.is_active():
                session.revoke()
                _session_repo.save(session)
        _record_audit(principal, "AccountSuspended", "Account", account.user_id,
                      school_id=account.school_id,
                      new_value={"role": account.role.value, "account_state": account.account_state.value})
        return AccountResponse(
            account_id=account.user_id,
            email=account.email,
            role=account.role.value,
            account_state=account.account_state.value,
            school_id=account.school_id,
        )

    @fastapi_app.post("/api/auth/invitations/complete", tags=["Auth"])
    async def complete_account_invitation(payload: CompleteInvitationRequest):
        if not configured_invitation_repo.consume(digest_token(payload.token), payload.password):
            raise HTTPException(status_code=400, detail="Invitation is invalid, expired, already used or no longer eligible.")
        return {"message": "Password set. Your account will be available after administrator approval."}

    @fastapi_app.get("/api/admin/overview", response_model=AdminOverviewResponse, tags=["Administration"])
    async def admin_overview(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        accounts = _account_repo.find_all()
        pending = [a for a in accounts if a.account_state == AccountStateEnum.Pending]
        return AdminOverviewResponse(
            registered_schools=configured_school_repo.count_status("Active"),
            active_school_admins=sum(1 for a in accounts if a.role == RoleEnum.SchoolAdmin and a.account_state == AccountStateEnum.Active),
            pending_accounts=len(pending),
            pending_school_verifications=configured_school_repo.count_status("PendingVerification")
                + configured_school_repo.count_status("NeedsReview"),
        )

    @fastapi_app.get("/api/admin/schools", response_model=List[SchoolResponse], tags=["Administration"])
    async def admin_list_schools(request: Request, status: str | None = None):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        schools = configured_school_repo.find_all()
        return [_school_out(s) for s in schools if status is None or s.status == status]

    @fastapi_app.post("/api/admin/schools", response_model=SchoolResponse, status_code=201, tags=["Administration"])
    async def admin_create_school(payload: SchoolCreateRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        emis = payload.emis_number.strip() if payload.emis_number else None
        if emis and configured_school_repo.find_by_emis(emis):
            raise HTTPException(status_code=409, detail="A school with this EMIS number already exists.")
        school = School(
            school_id=uuid4(), official_name=payload.official_name.strip(), emis_number=emis,
            province=payload.province.strip(), district=payload.district.strip(),
            contact_email=payload.contact_email.strip().lower() if payload.contact_email else None,
            contact_phone=payload.contact_phone.strip() if payload.contact_phone else None,
            status="PendingVerification", creator_id=principal.account_id,
        )
        configured_school_repo.save(school)
        _record_audit(principal, "SchoolRegistered", "School", school.school_id,
                      school_id=school.school_id,
                      new_value={"official_name": school.official_name, "status": school.status})
        return _school_out(school)

    @fastapi_app.get("/api/admin/schools/{school_id}", response_model=SchoolResponse, tags=["Administration"])
    async def admin_get_school(school_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        school = configured_school_repo.find_by_id(school_id)
        if school is None:
            raise HTTPException(status_code=404, detail="School not found.")
        return _school_out(school)

    @fastapi_app.post("/api/admin/schools/{school_id}/status", response_model=SchoolResponse, tags=["Administration"])
    async def admin_set_school_status(school_id: UUID, payload: SchoolStatusRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        school = configured_school_repo.find_by_id(school_id)
        if school is None:
            raise HTTPException(status_code=404, detail="School not found.")
        if payload.status == school.status:
            raise HTTPException(status_code=409, detail="School already has that status.")
        if payload.status == "Active" and len(payload.evidence_reference.strip()) < 4:
            raise HTTPException(status_code=422, detail="An independent verification evidence reference is required.")
        previous_status = school.status
        updated = configured_school_repo.set_status(school_id, payload.status)
        if updated.status != "Active":
            for account in _account_repo.find_all():
                if account.role == RoleEnum.SchoolAdmin and account.school_id == school_id:
                    for session in _session_repo.find_by_account(account.user_id):
                        if session.is_active():
                            session.revoke()
                            _session_repo.save(session)
        _record_audit(principal, "SchoolStatusChanged", "School", school_id,
                      school_id=school_id,
                      old_value={"status": previous_status},
                      new_value={"status": updated.status, "evidence_reference": payload.evidence_reference.strip()})
        return _school_out(updated)

    @fastapi_app.get("/api/admin/accounts", response_model=List[AdminAccountResponse], tags=["Administration"])
    async def admin_list_accounts(request: Request, role: str | None = None,
                                  school_id: UUID | None = None, status: str | None = None,
                                  offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        accounts = sorted(_account_repo.find_all(), key=lambda a: (a.created_at, str(a.user_id)))
        if role: accounts = [a for a in accounts if a.role.value == role]
        if school_id: accounts = [a for a in accounts if a.school_id == school_id]
        if status: accounts = [a for a in accounts if a.account_state.value == status]
        return [_admin_account_out(a) for a in accounts[offset:offset + limit]]

    @fastapi_app.get("/api/admin/accounts/{account_id}", response_model=AdminAccountResponse, tags=["Administration"])
    async def admin_get_account(account_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        account = _account_repo.find_by_id(account_id)
        if account is None: raise HTTPException(status_code=404, detail="Account not found.")
        return _admin_account_out(account)

    @fastapi_app.post("/api/admin/school-admins/invite", response_model=SchoolAdminInvitationResponse, status_code=201, tags=["Administration"])
    async def admin_invite_school_admin(payload: SchoolAdminInvitationRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        school = configured_school_repo.find_by_id(payload.school_id)
        if school is None or school.status != "Active":
            raise HTTPException(status_code=422, detail="Select an existing active school.")
        # A cryptographically random internal password is replaced through a
        # one-time, hashed invitation token before this pending account can log in.
        account = _account_repo.find_by_email(payload.email)
        reinviting = account is not None
        previous_invitation_status = None
        if reinviting:
            previous_invitation_status = configured_invitation_repo.latest_status(account.user_id)
            if (
                account.role != RoleEnum.SchoolAdmin
                or account.school_id != school.school_id
                or account.account_state != AccountStateEnum.Pending
                or previous_invitation_status not in {"Revoked", "Expired"}
            ):
                raise HTTPException(status_code=409, detail="This email already belongs to an account that cannot be re-invited.")
        else:
            account = _provisioning_svc.provision_account(
                actor=principal, email=payload.email, password=secrets.token_urlsafe(48),
                role=RoleEnum.SchoolAdmin, school_id=school.school_id,
            )
        token = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(hours=72)
        configured_invitation_repo.create(account.user_id, principal.account_id, digest_token(token), expires)
        _record_audit(principal, "SchoolAdminReinvited" if reinviting else "SchoolAdminInvited", "Account", account.user_id,
                      school_id=school.school_id,
                      old_value={"invitation_status": previous_invitation_status} if reinviting else None,
                      new_value={"account_state": account.account_state.value, "invitation_status": "Pending", "invitation_expires_at": expires.isoformat()})
        return SchoolAdminInvitationResponse(account=_admin_account_out(account), setup_token=token, expires_at=expires)

    @fastapi_app.post("/api/admin/university-admissions/invite", response_model=SchoolAdminInvitationResponse, status_code=201, tags=["Administration"])
    async def admin_invite_university_admissions(payload: UniversityAdmissionsInvitationRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        account = _account_repo.find_by_email(payload.email)
        reinviting = account is not None
        previous_status = None
        if reinviting:
            previous_status = configured_invitation_repo.latest_status(account.user_id)
            if (
                account.role != RoleEnum.UniversityAdmissions
                or account.university_id != payload.university_id
                or account.account_state != AccountStateEnum.Pending
                or previous_status not in {"Expired", "Revoked"}
            ):
                raise HTTPException(status_code=409, detail="This email already belongs to an account that cannot be re-invited.")
        else:
            account = _provisioning_svc.provision_account(
                actor=principal, email=payload.email, password=secrets.token_urlsafe(48),
                role=RoleEnum.UniversityAdmissions, university_id=payload.university_id,
            )
        token = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(hours=72)
        configured_invitation_repo.create(account.user_id, principal.account_id, digest_token(token), expires)
        _record_audit(
            principal,
            "UniversityAdmissionsReinvited" if reinviting else "UniversityAdmissionsInvited",
            "Account", account.user_id, university_id=payload.university_id,
            old_value={"invitation_status": previous_status} if reinviting else None,
            new_value={"role": RoleEnum.UniversityAdmissions.value,
                       "university_id": str(payload.university_id),
                       "invitation_status": "Pending", "invitation_expires_at": expires.isoformat()},
        )
        return SchoolAdminInvitationResponse(account=_admin_account_out(account), setup_token=token, expires_at=expires)

    @fastapi_app.post(
        "/api/admin/accounts/{account_id}/revoke-invitation",
        response_model=InvitationRevocationResponse,
        tags=["Administration"],
    )
    async def admin_revoke_invitation(
        account_id: UUID, payload: RevokeInvitationRequest, request: Request
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        account = _account_repo.find_by_id(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        if account.role not in {RoleEnum.SchoolAdmin, RoleEnum.UniversityAdmissions}:
            raise HTTPException(status_code=409, detail="Only pending school or university admissions invitations can be revoked.")
        if account.account_state != AccountStateEnum.Pending:
            raise HTTPException(status_code=409, detail="Only pending school or university admissions invitations can be revoked.")
        reason = payload.reason.strip()
        if len(reason) < 10:
            raise HTTPException(status_code=422, detail="Provide a meaningful revocation reason.")
        if not configured_invitation_repo.revoke_pending(
            account_id, principal.account_id, reason, account.school_id, account.university_id
        ):
            raise HTTPException(status_code=409, detail="This invitation is expired, already used, verified, or no longer pending.")
        return InvitationRevocationResponse(account_id=account_id, invitation_status="Revoked")

    @fastapi_app.get("/api/admin/approvals", response_model=List[AdminAccountResponse], tags=["Administration"])
    async def admin_approval_queue(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        return [_admin_account_out(a) for a in _account_repo.find_all() if a.account_state == AccountStateEnum.Pending]

    @fastapi_app.post("/api/admin/accounts/{account_id}/bootstrap-first-school-admin", response_model=AccountResponse, tags=["Administration"])
    async def admin_bootstrap_first_school_admin(account_id: UUID, payload: FirstSchoolAdminBootstrapRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        evidence_reference = payload.evidence_reference.strip()
        reason = payload.reason.strip()
        if len(evidence_reference) < 4 or len(reason) < 10:
            raise HTTPException(status_code=422, detail="A meaningful evidence reference and reason are required.")
        target = _account_repo.find_by_id(account_id)
        if target is None: raise AccountNotFoundError("Account not found.")
        if target.role != RoleEnum.SchoolAdmin or target.school_id is None or target.creator_id != principal.account_id:
            raise HTTPException(status_code=422, detail="Bootstrap only applies to a SchoolAdmin created by this SystemAdmin for its assigned school.")
        school = configured_school_repo.find_by_id(target.school_id)
        if school is None or school.status != "Active":
            raise HTTPException(status_code=422, detail="The school must be registered and active.")
        verification_records = _verification_repo.find_by_subject(target.user_id)
        latest = max(verification_records, key=lambda r: (r.created_at, str(r.record_id)), default=None)
        if latest is None or latest.outcome != "Verified" or latest.verifier_account_id != principal.account_id or target.school_id not in latest.school_scope:
            raise NotVerifiedError("Record independent school-authority verification for this school before bootstrap.")
        if not configured_invitation_repo.is_ready(account_id):
            raise HTTPException(status_code=422, detail="The invited SchoolAdmin must set their password before bootstrap activation.")
        account = _account_repo.bootstrap_first_school_admin(
            target.school_id, target.user_id, principal,
            latest.evidence_reference, evidence_reference, reason,
        )
        if database_url is None:
            _record_audit(principal, "BootstrapFirstSchoolAdmin", "Account", account.user_id,
                          school_id=account.school_id,
                          new_value={"account_state": "Active",
                                     "verification_evidence_reference": latest.evidence_reference,
                                     "evidence_reference": evidence_reference, "reason": reason})
        return AccountResponse(account_id=account.user_id, email=account.email,
                              role=account.role.value, account_state=account.account_state.value,
                              school_id=account.school_id)

    @fastapi_app.post("/api/admin/accounts/{account_id}/bootstrap-first-university-admissions", response_model=AccountResponse, tags=["Administration"])
    async def admin_bootstrap_first_university_admissions(account_id: UUID, payload: FirstUniversityAdmissionsBootstrapRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        evidence_reference = payload.evidence_reference.strip()
        reason = payload.reason.strip()
        if len(evidence_reference) < 4 or len(reason) < 10:
            raise HTTPException(status_code=422, detail="A meaningful bootstrap evidence reference and reason are required.")
        target = _account_repo.find_by_id(account_id)
        if target is None:
            raise AccountNotFoundError("Account not found.")
        if (
            target.role != RoleEnum.UniversityAdmissions
            or target.university_id is None
            or target.creator_id != principal.account_id
        ):
            raise HTTPException(status_code=422, detail="Bootstrap applies only to a UniversityAdmissions account created by this SystemAdmin with a university scope.")
        records = _verification_repo.find_by_subject(target.user_id)
        latest = max(records, key=lambda row: (row.created_at, str(row.record_id)), default=None)
        if (
            latest is None or latest.outcome != "Verified"
            or latest.verifier_account_id != principal.account_id
            or latest.university_id != target.university_id
            or len(latest.evidence_reference.strip()) < 4
        ):
            raise NotVerifiedError("Record independent university authority verification for this university before bootstrap.")
        if not configured_invitation_repo.is_ready(account_id):
            raise HTTPException(status_code=422, detail="The invited UniversityAdmissions user must set their password before activation.")
        account = _account_repo.bootstrap_first_university_admissions(
            target.university_id, target.user_id, principal,
            latest.evidence_reference, evidence_reference, reason, audit_repo,
        )
        return AccountResponse(account_id=account.user_id, email=account.email,
                              role=account.role.value, account_state=account.account_state.value,
                              school_id=account.school_id)

    @fastapi_app.post("/api/admin/accounts/{account_id}/reactivate", response_model=AccountResponse, tags=["Administration"])
    async def admin_reactivate_account(account_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SystemAdmin)
        account = _account_repo.set_account_state(account_id, AccountStateEnum.Active)
        _record_audit(principal, "AccountReactivated", "Account", account.user_id,
                      school_id=account.school_id,
                      new_value={"account_state": account.account_state.value})
        return AccountResponse(account_id=account.user_id, email=account.email,
                              role=account.role.value, account_state=account.account_state.value,
                              school_id=account.school_id)

    # ── /api/learners ─────────────────────────────────────────────────────────

    @fastapi_app.get("/api/learners", response_model=List[LearnerResponse], tags=["Learners"])
    async def list_learners(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        return [_learner_out(p) for p in learner_repo.find_by_school(principal.school_id)]

    @fastapi_app.post("/api/learners", response_model=LearnerResponse, status_code=201, tags=["Learners"])
    async def create_learner(payload: CreateLearnerRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="SchoolAdmin has no school scope assigned.")
        profile = LearnerProfile(
            learner_id=uuid4(),
            full_name=payload.full_name,
            school_id_number=payload.school_id_number,
            grade=payload.grade,
            status=ProfileStatusEnum.Incomplete,
            counselor_id=payload.counselor_id,
            school_id=principal.school_id,
        )
        created = learner_svc.create_profile(profile)
        _record_audit(
            principal,
            "learner.created",
            "learner",
            created.learner_id,
            school_id=principal.school_id,
            new_value={"grade": created.grade, "status": created.status.value},
        )
        return _learner_out(created)

    @fastapi_app.post("/api/learners/import", status_code=201, tags=["Learners"])
    async def import_learners(request: Request, file: UploadFile = File(...)):
        """Import learners and marks from a school-scoped CSV spreadsheet.

        Each CSV row represents one subject mark. Repeated school ID numbers
        group subject rows for the same learner. The upload is validated in
        full before any database writes are made.
        """
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="SchoolAdmin has no school scope assigned.")
        if not file.filename or Path(file.filename).suffix.lower() != ".csv":
            raise HTTPException(status_code=415, detail="Upload a CSV spreadsheet exported from Excel or another spreadsheet app.")

        contents = await file.read(MAX_IMPORT_BYTES + 1)
        try:
            parsed_learners = parse_learner_csv(contents)
        except LearnerImportValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": str(exc), "errors": exc.errors},
            ) from exc
        finally:
            await file.close()

        existing_ids = {
            learner.school_id_number.casefold()
            for learner in learner_repo.find_by_school(principal.school_id)
        }
        duplicate_errors = [
            {
                "row": learner.first_row,
                "message": f"school_id_number {learner.school_id_number!r} already exists in your school.",
            }
            for learner in parsed_learners
            if learner.school_id_number.casefold() in existing_ids
        ]
        if duplicate_errors:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "No learners were imported because student numbers already exist.",
                    "errors": duplicate_errors,
                },
            )

        profiles: list[LearnerProfile] = []
        for learner in parsed_learners:
            learner_id = uuid4()
            profiles.append(LearnerProfile(
                learner_id=learner_id,
                full_name=learner.full_name,
                school_id_number=learner.school_id_number,
                grade=learner.grade,
                status=ProfileStatusEnum.Incomplete,
                counselor_id=None,
                school_id=principal.school_id,
                marks=[
                    Mark(
                        mark_id=uuid4(),
                        learner_id=learner_id,
                        subject_name=mark.subject_name,
                        score=mark.score,
                        exam_type=mark.exam_type,
                        academic_year=mark.academic_year,
                    )
                    for mark in learner.marks
                ],
            ))

        learner_repo.save_many(profiles)
        total_marks = sum(len(profile.marks) for profile in profiles)
        import_id = uuid4()
        _record_audit(
            principal,
            "learner.spreadsheet_imported",
            "learner_import",
            import_id,
            school_id=principal.school_id,
            new_value={"learner_count": len(profiles), "mark_count": total_marks},
        )
        return {
            "import_id": import_id,
            "imported_learners": len(profiles),
            "imported_marks": total_marks,
        }

    @fastapi_app.get("/api/learners/{learner_id}", response_model=LearnerResponse, tags=["Learners"])
    async def get_learner(learner_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        return _learner_out(_require_school_learner(learner_id, principal))

    @fastapi_app.put("/api/learners/{learner_id}", response_model=LearnerResponse, tags=["Learners"])
    async def update_learner(learner_id: UUID, payload: UpdateLearnerRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        existing = _require_school_learner(learner_id, principal)
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        updated = learner_svc.update_profile(learner_id, **updates)
        changed_fields = sorted(updates)
        _record_audit(
            principal,
            "learner.updated",
            "learner",
            learner_id,
            school_id=principal.school_id,
            old_value={
                "changed_fields": changed_fields,
                "grade": existing.grade,
                "status": existing.status.value,
            },
            new_value={
                "grade": updated.grade,
                "status": updated.status.value,
            },
        )
        return _learner_out(updated)

    @fastapi_app.delete("/api/learners/{learner_id}", status_code=204, tags=["Learners"])
    async def delete_learner(learner_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        learner = _require_school_learner(learner_id, principal)
        _record_audit(
            principal,
            "learner.deleted",
            "learner",
            learner_id,
            school_id=principal.school_id,
            old_value={"grade": learner.grade, "status": learner.status.value},
        )
        learner_svc.delete_profile(learner_id)

    @fastapi_app.post("/api/learners/{learner_id}/marks", response_model=LearnerResponse, status_code=201, tags=["Learners"])
    async def add_mark(learner_id: UUID, payload: AddMarkRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        mark = Mark(
            mark_id=uuid4(),
            learner_id=learner_id,
            subject_name=payload.subject_name,
            score=payload.score,
            exam_type=payload.exam_type,
            academic_year=payload.academic_year,
        )
        learner = learner_svc.add_mark(learner_id, mark)
        _record_audit(
            principal,
            "mark.recorded",
            "mark",
            mark.mark_id,
            school_id=principal.school_id,
            new_value={
                "learner_id": str(learner_id),
                "subject_name": mark.subject_name,
                "academic_year": mark.academic_year,
            },
        )
        return _learner_out(learner)

    @fastapi_app.get("/api/learners/{learner_id}/aps", response_model=ApsResponse, tags=["Learners"])
    async def get_aps(
        learner_id: UUID,
        request: Request,
        university_id: Optional[UUID] = Query(
            None,
            description=(
                "Optional university UUID. When supplied and a ScoringRule is registered "
                "for that university, the university-specific APS formula is applied (REQ-002). "
                "Omit to use the standard NSC formula. "
                "university_id in the response is null when the standard formula was used "
                "(either because no university_id was supplied or no rule is registered for it)."
            ),
        ),
    ):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        rule_found = (
            university_id is not None
            and learner_svc.find_scoring_rule(university_id) is not None
        )
        aps = learner_svc.get_aps_score(learner_id, university_id=university_id)
        return ApsResponse(
            learner_id=learner_id,
            aps_score=aps,
            university_id=university_id if rule_found else None,
        )

    @fastapi_app.post("/api/learners/{learner_id}/deactivate", response_model=LearnerResponse, tags=["Learners"])
    async def deactivate_learner(learner_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        return _learner_out(learner_svc.deactivate_profile(learner_id))

    @fastapi_app.post(
        "/api/learners/{learner_id}/simulate-eligibility",
        response_model=SimulationResponse,
        tags=["Learners"],
        summary="Simulate eligibility with hypothetical marks (REQ-005)",
    )
    async def simulate_eligibility(learner_id: UUID, payload: SimulateEligibilityRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        result = learner_svc.simulate_eligibility(
            learner_id=learner_id,
            programme_id=payload.programme_id,
            overrides=payload.overrides,
        )
        return SimulationResponse(
            learner_id=result.learner_id,
            programme_id=result.programme_id,
            simulated_aps=result.simulated_aps,
            eligibility=result.eligibility.value,
            subject_requirements_checked=result.subject_requirements_checked,
            university_rule_applied=result.university_rule_applied,
        )

    @fastapi_app.post(
        "/api/learners/{learner_id}/simulate-eligibility/comparison",
        response_model=SimulationComparisonResponse,
        tags=["Learners"],
        summary="Compare current and simulated eligibility across programmes",
    )
    async def compare_simulated_eligibility(
        learner_id: UUID, payload: CompareSimulationRequest, request: Request
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        learner = learner_svc.get_profile(learner_id)
        comparisons = []
        for programme_id in payload.programme_ids:
            programme = programme_svc.get_programme(programme_id)
            current_aps = learner_svc.get_aps_score(
                learner_id, university_id=programme.university_id
            )
            current_eligibility = programme_svc.check_eligibility(
                programme_id, current_aps, marks=learner.marks
            )
            projected = learner_svc.simulate_eligibility(
                learner_id, programme_id, payload.overrides
            )
            comparisons.append(
                ProgrammeSimulationComparison(
                    programme_id=programme_id,
                    current_aps=current_aps,
                    projected_aps=projected.simulated_aps,
                    current_eligibility=current_eligibility.value,
                    projected_eligibility=projected.eligibility.value,
                    subject_requirements_checked=projected.subject_requirements_checked,
                    university_rule_applied=projected.university_rule_applied,
                )
            )
        return SimulationComparisonResponse(
            learner_id=learner_id,
            results=comparisons,
            is_simulation=True,
        )

    # ── /api/programmes ───────────────────────────────────────────────────────

    @fastapi_app.get("/api/programmes", response_model=List[ProgrammeResponse], tags=["Programmes"])
    async def list_programmes(
        request: Request,
        published_only: bool = Query(False, description="Return only active published programmes"),
        university_id: UUID | None = Query(None),
    ):
        principal = _resolve_principal(request)
        published_programmes = programme_svc.list_published_programmes()
        published_ids = {programme.programme_id for programme in published_programmes}
        if principal is None:
            return [_programme_out(p) for p in published_programmes]
        if principal.role == RoleEnum.SchoolAdmin:
            programmes = published_programmes
        elif principal.role == RoleEnum.UniversityAdmissions:
            scopes = set(principal.university_ids)
            if principal.university_id is not None:
                scopes.add(principal.university_id)
            if university_id is not None:
                if university_id not in scopes:
                    raise HTTPException(status_code=404, detail="University not found.")
                scopes = {university_id}
            if not scopes:
                raise HTTPException(status_code=403, detail="No verified university scope for this account.")
            programmes = [programme for scope_id in scopes for programme in programme_repo.find_by_university(scope_id)]
        else:
            raise HTTPException(status_code=403, detail="Role is not authorized to view programmes.")
        if published_only:
            programmes = [p for p in programmes if p.programme_id in published_ids]
        return [_programme_out(p) for p in programmes]

    @fastapi_app.post("/api/programmes", response_model=ProgrammeResponse, status_code=201, tags=["Programmes"])
    async def create_programme(payload: CreateProgrammeRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        # Use the payload university_id only if it is within the principal's authorised scopes.
        # Otherwise silently override with the principal's primary university — this prevents
        # an admissions account from creating programmes for another institution.
        if payload.university_id and principal.has_university_access(payload.university_id):
            target_university_id = payload.university_id
        else:
            target_university_id = principal.university_id or next(iter(principal.university_ids), None)
        if target_university_id is None:
            raise HTTPException(status_code=403, detail="No verified university scope for this account.")
        programme = UniversityProgramme(
            programme_id=uuid4(),
            university_id=target_university_id,
            name=payload.name,
            faculty=payload.faculty,
            minimum_aps=payload.minimum_aps,
            application_deadline=payload.application_deadline,
            application_fee=payload.application_fee,
            required_documents=payload.required_documents,
            status=ProgrammeStatusEnum.Draft,
            published_by=principal.account_id,
            required_subjects=payload.required_subjects,
        )
        created = programme_svc.create_programme(programme)
        _record_audit(
            principal,
            "programme.created",
            "programme",
            created.programme_id,
            university_id=created.university_id,
            new_value={"status": created.status.value},
        )
        return _programme_out(created)

    @fastapi_app.get("/api/programmes/{programme_id}", response_model=ProgrammeResponse, tags=["Programmes"])
    async def get_programme(programme_id: UUID, request: Request):
        programme = programme_svc.get_programme(programme_id)
        principal = _resolve_principal(request)
        if principal is None:
            if programme.status != ProgrammeStatusEnum.Published or programme.is_expired():
                raise HTTPException(status_code=404, detail="Programme not found.")
        elif principal.role == RoleEnum.SchoolAdmin:
            if programme.status != ProgrammeStatusEnum.Published or programme.is_expired():
                raise HTTPException(status_code=404, detail="Programme not found.")
        elif principal.role == RoleEnum.UniversityAdmissions:
            if not principal.has_university_access(programme.university_id):
                raise HTTPException(status_code=404, detail="Programme not found.")
        else:
            raise HTTPException(status_code=403, detail="Role is not authorized to view programmes.")
        return _programme_out(programme)

    @fastapi_app.put("/api/programmes/{programme_id}", response_model=ProgrammeResponse, tags=["Programmes"])
    async def update_programme(programme_id: UUID, payload: UpdateProgrammeRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        existing = _require_university_programme(programme_id, principal)
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        updated = programme_svc.update_programme(programme_id, **updates)
        _record_audit(
            principal,
            "programme.updated",
            "programme",
            programme_id,
            university_id=existing.university_id,
            old_value={"changed_fields": sorted(updates)},
            new_value={"status": updated.status.value},
        )
        return _programme_out(updated)

    @fastapi_app.delete("/api/programmes/{programme_id}", status_code=204, tags=["Programmes"])
    async def delete_programme(programme_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        programme = _require_university_programme(programme_id, principal)
        _record_audit(
            principal,
            "programme.deleted",
            "programme",
            programme_id,
            university_id=programme.university_id,
            old_value={"status": programme.status.value},
        )
        programme_svc.delete_programme(programme_id)

    @fastapi_app.post("/api/programmes/{programme_id}/publish", response_model=ProgrammeResponse, tags=["Programmes"])
    async def publish_programme(programme_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        programme = _require_university_programme(programme_id, principal)
        published = programme_svc.publish_programme(programme_id)
        _record_audit(
            principal,
            "programme.published",
            "programme",
            programme_id,
            university_id=programme.university_id,
            old_value={"status": programme.status.value},
            new_value={"status": published.status.value},
        )
        return _programme_out(published)

    @fastapi_app.post("/api/programmes/{programme_id}/deactivate", response_model=ProgrammeResponse, tags=["Programmes"])
    async def deactivate_programme(programme_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        programme = _require_university_programme(programme_id, principal)
        deactivated = programme_svc.deactivate_programme(programme_id)
        _record_audit(
            principal,
            "programme.deactivated",
            "programme",
            programme_id,
            university_id=programme.university_id,
            old_value={"status": programme.status.value},
            new_value={"status": deactivated.status.value},
        )
        return _programme_out(deactivated)

    @fastapi_app.post("/api/programmes/{programme_id}/extend-deadline", response_model=ProgrammeResponse, tags=["Programmes"])
    async def extend_deadline(programme_id: UUID, payload: ExtendDeadlineRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        programme = _require_university_programme(programme_id, principal)
        updated = programme_svc.extend_deadline(programme_id, payload.new_deadline)
        _record_audit(
            principal,
            "programme.deadline_extended",
            "programme",
            programme_id,
            university_id=programme.university_id,
            old_value={"deadline": programme.application_deadline.isoformat()},
            new_value={"deadline": updated.application_deadline.isoformat()},
        )
        return _programme_out(updated)

    @fastapi_app.get("/api/programmes/{programme_id}/eligibility", response_model=EligibilityResponse, tags=["Programmes"])
    async def check_eligibility(
        programme_id: UUID,
        request: Request,
        learner_aps: int = Query(..., ge=0, le=42, description="The learner's APS score"),
        learner_id: Optional[UUID] = Query(
            None,
            description=(
                "Optional learner UUID. When supplied, the learner's stored marks are "
                "retrieved and used to check compulsory subject requirements (REQ-003). "
                "Requires SchoolAdmin authentication with ownership of the learner. "
                "Subject requirements are NOT checked when this parameter is omitted."
            ),
        ),
    ):
        stored_marks = None
        if learner_id is not None:
            principal = _require_auth(request)
            _require_role(principal, RoleEnum.SchoolAdmin)
            profile = _require_school_learner(learner_id, principal)
            stored_marks = profile.marks

        prog = programme_svc.get_programme(programme_id)
        if prog.status != ProgrammeStatusEnum.Published or prog.is_expired():
            raise HTTPException(status_code=404, detail="Programme not found.")
        elig = programme_svc.check_eligibility(programme_id, learner_aps, marks=stored_marks)
        full_check = learner_id is not None
        return EligibilityResponse(
            programme_id=programme_id,
            learner_aps=learner_aps,
            minimum_aps=prog.minimum_aps,
            eligibility=elig.value,
            subject_requirements_checked=full_check,
            assessment_type="APS_AND_SUBJECTS" if full_check else "APS_ONLY",
            has_subject_requirements=bool(prog.required_subjects),
        )

    # ── /api/applications ─────────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/university/applications",
        response_model=List[ApplicationReviewResponse],
        tags=["Applications"],
        summary="List submitted applications for the authenticated university",
    )
    async def list_university_applications(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        university_scopes = set(principal.university_ids)
        if principal.university_id is not None:
            university_scopes.add(principal.university_id)
        if not university_scopes:
            raise HTTPException(status_code=403, detail="No verified university scope for this account.")

        reviewable_statuses = {
            ApplicationStatusEnum.Submitted,
            ApplicationStatusEnum.UnderReview,
            ApplicationStatusEnum.DocsRequested,
            ApplicationStatusEnum.Waitlisted,
            ApplicationStatusEnum.Accepted,
            ApplicationStatusEnum.Rejected,
        }
        programmes = [programme for scope_id in university_scopes for programme in programme_repo.find_by_university(scope_id)]
        programmes_by_id = {programme.programme_id: programme for programme in programmes}
        applications = [
            application
            for application in application_svc.list_applications()
            if application.programme_id in programmes_by_id
            and application.status in reviewable_statuses
        ]
        return [
            _application_review_out(
                application,
                learner_svc.get_profile(application.learner_id),
                programmes_by_id[application.programme_id],
            )
            for application in applications
        ]

    @fastapi_app.get(
        "/api/university/applications/{application_id}",
        response_model=ApplicationReviewResponse,
        tags=["Applications"],
        summary="Get an application owned by the authenticated university",
    )
    async def get_university_application(application_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        application, programme = _require_university_application(
            application_id, principal
        )
        if application.status in {
            ApplicationStatusEnum.Draft,
            ApplicationStatusEnum.FeeOutstanding,
            ApplicationStatusEnum.FeePaid,
            ApplicationStatusEnum.PackageIncomplete,
            ApplicationStatusEnum.PackageReady,
            ApplicationStatusEnum.Cancelled,
            ApplicationStatusEnum.DeadlineMissed,
        }:
            raise HTTPException(status_code=404, detail="Application not found.")
        return _application_review_out(
            application,
            learner_svc.get_profile(application.learner_id),
            programme,
        )

    @fastapi_app.put(
        "/api/university/applications/{application_id}/review",
        response_model=ApplicationReviewResponse,
        tags=["Applications"],
        summary="Record an authorized university review decision",
    )
    async def review_university_application(
        application_id: UUID,
        payload: ReviewApplicationRequest,
        request: Request,
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        application, programme = _require_university_application(
            application_id, principal
        )
        if application.status in {
            ApplicationStatusEnum.Draft,
            ApplicationStatusEnum.FeeOutstanding,
            ApplicationStatusEnum.FeePaid,
            ApplicationStatusEnum.PackageIncomplete,
            ApplicationStatusEnum.PackageReady,
            ApplicationStatusEnum.Cancelled,
            ApplicationStatusEnum.DeadlineMissed,
        }:
            raise HTTPException(status_code=404, detail="Application not found.")
        if (
            payload.new_status == "DocsRequested"
            and not payload.note.strip()
        ):
            raise HTTPException(
                status_code=422,
                detail="Describe the additional documents required.",
            )

        old_status = application.status.value
        updated = application_svc.update_status(
            application_id,
            ApplicationStatusEnum(payload.new_status),
            principal.account_id,
            payload.note.strip(),
        )
        _record_audit(
            principal,
            "application.university_reviewed",
            "application",
            application_id,
            university_id=programme.university_id,
            old_value={"status": old_status},
            new_value={
                "status": updated.status.value,
                "note": payload.note.strip(),
            },
        )
        return _application_review_out(
            updated,
            learner_svc.get_profile(updated.learner_id),
            programme,
        )

    @fastapi_app.post(
        "/api/learners/{learner_id}/documents",
        response_model=LearnerDocumentResponse,
        status_code=201,
        tags=["Documents"],
    )
    async def upload_learner_document(
        learner_id: UUID,
        request: Request,
        document_type: str = Form(..., min_length=1, max_length=100),
        application_id: UUID | None = Form(default=None),
        file: UploadFile = File(...),
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin, RoleEnum.Teacher)
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="No school scope is assigned.")
        learner = _require_school_learner(learner_id, principal)
        if application_id is not None:
            application = _require_school_application(application_id, principal)
            if application.learner_id != learner_id:
                raise HTTPException(status_code=404, detail="Application not found.")

        payload = await file.read(Document._max_bytes + 1)
        try:
            filename = validate_document_upload(
                file.filename or "", file.content_type or "", payload
            )
        except InvalidDocumentUpload as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        clean_document_type = document_type.strip()
        if not clean_document_type:
            raise HTTPException(status_code=422, detail="Document type is required.")

        document_id = uuid4()
        extension = Path(filename).suffix.lower()
        try:
            storage_path = local_document_storage.save(
                learner.school_id,
                learner_id,
                document_id,
                extension,
                payload,
            )
        except OSError as exc:
            logger.exception("Could not store learner document %s", document_id)
            raise HTTPException(
                status_code=503, detail="Local document storage is unavailable."
            ) from exc

        document = Document(
            document_id=document_id,
            learner_id=learner_id,
            application_id=application_id,
            document_type=clean_document_type,
            filename=filename,
            storage_path=storage_path,
            mime_type=file.content_type or "",
            size_bytes=len(payload),
            uploaded_by=principal.account_id,
            virus_scan_status="NotScanned",
            status="PendingReview",
            school_id=learner.school_id,
            content_sha256=hashlib.sha256(payload).hexdigest(),
        )
        try:
            learner_document_repo.save(document)
        except Exception as exc:
            logger.exception("Could not save learner document metadata %s", document_id)
            try:
                local_document_storage.remove(storage_path)
            except OSError:
                logger.exception("Could not remove incomplete learner document %s", document_id)
            raise HTTPException(
                status_code=503, detail="Document metadata could not be saved."
            ) from exc

        _record_audit(
            principal,
            "learner_document.uploaded",
            "learner_document",
            document_id,
            school_id=learner.school_id,
            new_value={
                "learner_id": str(learner_id),
                "application_id": str(application_id) if application_id else None,
                "document_type": clean_document_type,
                "status": document.status,
            },
        )
        return _document_out(document)

    @fastapi_app.get(
        "/api/learners/{learner_id}/documents",
        response_model=List[LearnerDocumentResponse],
        tags=["Documents"],
    )
    async def list_learner_documents(learner_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin, RoleEnum.Teacher)
        _require_school_learner(learner_id, principal)
        return [
            _document_out(document)
            for document in learner_document_repo.find_by_learner(learner_id)
        ]

    @fastapi_app.get("/api/documents/{document_id}/download", tags=["Documents"])
    async def download_learner_document(document_id: UUID, request: Request):
        principal = _require_auth(request)
        document = learner_document_repo.find_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        _require_document_download_access(document, principal)
        try:
            document_path = local_document_storage.resolve(document.storage_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Document file not found.") from exc
        except ValueError as exc:
            logger.error("Unsafe stored path for learner document %s", document_id)
            raise HTTPException(status_code=500, detail="Stored document path is invalid.") from exc
        return FileResponse(
            document_path,
            media_type=document.mime_type,
            filename=document.filename,
        )

    @fastapi_app.put(
        "/api/documents/{document_id}/review",
        response_model=LearnerDocumentResponse,
        tags=["Documents"],
    )
    async def review_learner_document(
        document_id: UUID,
        payload: ReviewLearnerDocumentRequest,
        request: Request,
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin, RoleEnum.Teacher)
        document = _require_school_document(document_id, principal)
        try:
            document.review(payload.decision, principal.account_id, payload.note)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        learner_document_repo.save(document)
        _record_audit(
            principal,
            "learner_document.reviewed",
            "learner_document",
            document_id,
            school_id=document.school_id,
            old_value={"status": "PendingReview"},
            new_value={
                "status": document.status,
                "reviewed_by": str(principal.account_id),
                "reviewed_at": (
                    document.reviewed_at.isoformat()
                    if document.reviewed_at is not None
                    else None
                ),
            },
        )
        return _document_out(document)

    @fastapi_app.get("/api/applications", response_model=List[ApplicationResponse], tags=["Applications"])
    async def list_applications(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        school_learners = learner_repo.find_by_school(principal.school_id)
        learner_ids = {l.learner_id for l in school_learners}
        return [_application_out(a) for a in application_svc.list_applications() if a.learner_id in learner_ids]

    @fastapi_app.post("/api/applications", response_model=ApplicationResponse, status_code=201, tags=["Applications"])
    async def create_application(payload: CreateApplicationRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        learner = _require_school_learner(payload.learner_id, principal)
        created = application_svc.create_application(
            learner_id=payload.learner_id,
            programme_id=payload.programme_id,
            fee_amount=payload.fee_amount,
            learner=learner,
        )
        _record_audit(
            principal,
            "application.created",
            "application",
            created.application_id,
            school_id=principal.school_id,
            new_value={"status": created.status.value},
        )
        _create_notification(
            principal.account_id,
            "application.created",
            "A learner application was created.",
            f"application-created:{created.application_id}:{principal.account_id}",
        )
        return _application_out(created)

    @fastapi_app.get("/api/applications/learner/{learner_id}", response_model=List[ApplicationResponse], tags=["Applications"])
    async def list_learner_applications(learner_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        return [_application_out(a) for a in application_svc.list_for_learner(learner_id)]

    @fastapi_app.get("/api/applications/{application_id}", response_model=ApplicationResponse, tags=["Applications"])
    async def get_application(application_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        application = _require_school_application(application_id, principal)
        return _application_out(application_svc.get_application(application_id))

    @fastapi_app.get(
        "/api/applications/{application_id}/history",
        response_model=List[StatusHistoryEntryResponse],
        tags=["Applications"],
        summary="Get the full status-change audit trail for an application (REQ-007)",
    )
    async def get_application_history(application_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        application = _require_school_application(application_id, principal)
        app = application_svc.get_application(application_id)
        return [_history_entry_out(e) for e in app.get_status_history()]

    @fastapi_app.put("/api/applications/{application_id}/status", response_model=ApplicationResponse, tags=["Applications"])
    async def update_status(application_id: UUID, payload: UpdateStatusRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        application = _require_school_application(application_id, principal)
        if payload.new_status == ApplicationStatusEnum.Submitted:
            raise HTTPException(
                status_code=409,
                detail="Use the submission endpoint after payment and document prerequisites are satisfied.",
            )
        if payload.new_status == ApplicationStatusEnum.FeePaid:
            raise HTTPException(
                status_code=409,
                detail="Payment confirmation is not integrated; fee-paid status cannot be set manually.",
            )
        if payload.new_status == ApplicationStatusEnum.PackageReady:
            zero_fee = application.fee_amount == Decimal("0")
            if application.status not in {
                ApplicationStatusEnum.FeePaid,
                ApplicationStatusEnum.PackageIncomplete,
                *(
                    {ApplicationStatusEnum.FeeOutstanding, ApplicationStatusEnum.Draft}
                    if zero_fee
                    else set()
                ),
            }:
                raise HTTPException(
                    status_code=409,
                    detail="A confirmed payment is required before the application package can be marked ready.",
                )
            verified_types = {
                document.document_type
                for document in application.documents
                if document.application_id == application_id
                and document.status == "Verified"
            }
            required_types = (
                set(application.linked_programme.required_documents)
                if application.linked_programme is not None
                else set()
            )
            if not verified_types or not required_types.issubset(verified_types):
                raise HTTPException(
                    status_code=409,
                    detail="Package-ready status requires human verification of every required application document.",
                )
        if payload.new_status in {
            ApplicationStatusEnum.UnderReview,
            ApplicationStatusEnum.DocsRequested,
            ApplicationStatusEnum.Accepted,
            ApplicationStatusEnum.Rejected,
            ApplicationStatusEnum.Waitlisted,
        }:
            raise HTTPException(
                status_code=403,
                detail="University admissions review is not available through this API.",
            )
        old_status = application.status.value
        updated = application_svc.update_status(
            application_id, payload.new_status, principal.account_id, payload.note
        )
        _record_audit(
            principal,
            "application.status_changed",
            "application",
            application_id,
            school_id=principal.school_id,
            old_value={"status": old_status},
            new_value={"status": updated.status.value},
        )
        _create_notification(
            principal.account_id,
            "application.status_changed",
            f"Application status changed to {updated.status.value}.",
            f"application-status:{application_id}:{len(updated.status_history)}",
        )
        return _application_out(updated)

    @fastapi_app.post("/api/applications/{application_id}/submit", response_model=ApplicationResponse, tags=["Applications"])
    async def submit_application(application_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        application = _require_school_application(application_id, principal)
        try:
            submitted = application_svc.submit_application(
                application_id, principal.account_id
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail="Submission requires a recorded payment reference, linked documents, and a ready application.",
            ) from exc
        _record_audit(
            principal,
            "application.submitted",
            "application",
            application_id,
            school_id=principal.school_id,
            old_value={"status": application.status.value},
            new_value={"status": submitted.status.value},
        )
        return _application_out(submitted)

    @fastapi_app.post("/api/applications/{application_id}/cancel", response_model=ApplicationResponse, tags=["Applications"])
    async def cancel_application(application_id: UUID, payload: CancelApplicationRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        application = _require_school_application(application_id, principal)
        cancelled = application_svc.cancel_application(
            application_id, principal.account_id, payload.note
        )
        _record_audit(
            principal,
            "application.cancelled",
            "application",
            application_id,
            school_id=principal.school_id,
            old_value={"status": application.status.value},
            new_value={"status": cancelled.status.value},
        )
        _create_notification(
            principal.account_id,
            "application.cancelled",
            "An application was cancelled.",
            f"application-cancelled:{application_id}",
        )
        return _application_out(cancelled)

    @fastapi_app.delete("/api/applications/{application_id}", status_code=204, tags=["Applications"])
    async def delete_application(application_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        application = _require_school_application(application_id, principal)
        _record_audit(
            principal,
            "application.deleted",
            "application",
            application_id,
            school_id=principal.school_id,
            old_value={"status": application.status.value},
        )
        application_svc.delete_application(application_id)

    # ── /api/learners/{id}/marks ──────────────────────────────────────────────

    @fastapi_app.get("/api/learners/{learner_id}/marks", response_model=List[MarkResponse], tags=["Learners"])
    async def list_marks(
        learner_id: UUID,
        request: Request,
        academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    ):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        learner = _require_school_learner(learner_id, principal)
        marks = learner.marks
        if academic_year is not None:
            marks = [m for m in marks if m.academic_year == academic_year]
        return [
            MarkResponse(
                mark_id=m.mark_id,
                subject_name=m.subject_name,
                score=m.score,
                exam_type=m.exam_type,
                academic_year=m.academic_year,
                aps_points=m.to_aps_points(),
            )
            for m in marks
        ]

    # ── /api/learners/{id}/recommendations ───────────────────────────────────

    @fastapi_app.get(
        "/api/learners/{learner_id}/recommendations",
        response_model=RecommendationsResponse,
        tags=["Learners"],
        summary="Ranked programme recommendations for a learner",
    )
    async def get_recommendations(learner_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        learner = _require_school_learner(learner_id, principal)

        standard_aps = learner_svc.get_aps_score(learner_id)
        programmes = programme_svc.list_published_programmes()

        recs = []
        for prog in programmes:
            learner_aps = learner_svc.get_aps_score(learner_id, university_id=prog.university_id)
            elig = programme_svc.check_eligibility(prog.programme_id, learner_aps, marks=learner.marks)
            subjects_met = prog.meets_subject_requirements(learner.marks)
            margin = learner_aps - prog.minimum_aps
            missing_subjects = []
            if not subjects_met:
                best_by_subject: dict[str, int] = {}
                for mark in learner.marks:
                    best_by_subject[mark.subject_name] = max(
                        best_by_subject.get(mark.subject_name, 0), mark.score
                    )
                missing_subjects = [
                    f"{subject} (minimum {minimum}; recorded "
                    f"{best_by_subject.get(subject, 'no mark')})"
                    for subject, minimum in prog.required_subjects.items()
                    if best_by_subject.get(subject) is None
                    or best_by_subject[subject] < minimum
                ]
            explanation = (
                f"Compulsory subject requirements not met: {', '.join(missing_subjects)}. "
                f"APS {learner_aps} vs minimum {prog.minimum_aps}."
                if missing_subjects
                else f"APS {learner_aps} vs minimum {prog.minimum_aps} "
                f"({margin:+d} points); compulsory subject requirements met."
                if prog.required_subjects
                else f"APS {learner_aps} vs minimum {prog.minimum_aps} ({margin:+d} points); "
                "no compulsory subject requirements are configured."
            )
            recs.append(ProgrammeRecommendation(
                programme_id=prog.programme_id,
                programme_name=prog.name,
                university_id=prog.university_id,
                faculty=prog.faculty,
                minimum_aps=prog.minimum_aps,
                learner_aps=learner_aps,
                eligibility=elig.value,
                explanation=explanation,
                assessment_type="APS_AND_SUBJECTS" if prog.required_subjects else "APS_ONLY",
                has_subject_requirements=bool(prog.required_subjects),
                subject_requirements_met=subjects_met,
                application_deadline=prog.application_deadline,
                application_fee=str(prog.application_fee),
                is_active=prog.is_active(),
            ))

        _order = {"Guaranteed": 0, "Likely": 1, "Borderline": 2, "NotEligible": 3}
        recs.sort(key=lambda r: (_order.get(r.eligibility, 9), r.minimum_aps))

        return RecommendationsResponse(
            learner_id=learner_id,
            learner_aps=standard_aps,
            recommendations=recs,
        )

    # ── /api/learners/{id}/application-eligibility/{programme_id} ────────────

    @fastapi_app.get(
        "/api/learners/{learner_id}/application-eligibility/{programme_id}",
        response_model=ApplicationEligibilityCheck,
        tags=["Applications"],
    )
    async def check_application_eligibility(learner_id: UUID, programme_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        learner = _require_school_learner(learner_id, principal)

        prog = programme_svc.get_programme(programme_id)
        if prog.status != ProgrammeStatusEnum.Published or prog.is_expired():
            raise HTTPException(status_code=404, detail="Programme not found.")
        learner_aps = learner_svc.get_aps_score(
            learner_id, university_id=prog.university_id
        )
        elig = programme_svc.check_eligibility(programme_id, learner_aps, marks=learner.marks)

        show_warning = elig.value in ("Borderline", "NotEligible")
        warning_msg: Optional[str] = None
        if not prog.meets_subject_requirements(learner.marks):
            warning_msg = (
                "This learner does not meet all compulsory subject requirements. "
                "Application creation will be rejected until the recorded marks satisfy them."
            )
        elif elig.value == "NotEligible":
            warning_msg = (
                f"This learner does not meet the minimum APS of {prog.minimum_aps} "
                f"(current: {learner_aps}). Application creation will be rejected."
            )
        elif elig.value == "Borderline":
            warning_msg = (
                f"This learner meets the minimum APS of {prog.minimum_aps} with only "
                f"{learner_aps - prog.minimum_aps} point(s) to spare. "
                "Application creation requires a Likely or Guaranteed eligibility result."
            )

        return ApplicationEligibilityCheck(
            learner_id=learner_id,
            programme_id=programme_id,
            learner_aps=learner_aps,
            minimum_aps=prog.minimum_aps,
            eligibility=elig.value,
            show_warning=show_warning,
            warning_message=warning_msg,
        )

    # ── Guidance sessions ────────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/learners/{learner_id}/guidance-sessions",
        response_model=List[GuidanceSessionResponse],
        tags=["Guidance"],
    )
    async def list_guidance_sessions(learner_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        return [
            _guidance_out(item)
            for item in guidance_repo.find_by_learner(learner_id)
        ]

    @fastapi_app.post(
        "/api/learners/{learner_id}/guidance-sessions",
        response_model=GuidanceSessionResponse,
        status_code=201,
        tags=["Guidance"],
    )
    async def create_guidance_session(
        learner_id: UUID,
        payload: GuidanceSessionCreateRequest,
        request: Request,
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        _require_school_learner(learner_id, principal)
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="No school scope is assigned.")
        now = datetime.now(timezone.utc)
        guidance_session = GuidanceSession(
            guidance_session_id=uuid4(),
            learner_id=learner_id,
            school_id=principal.school_id,
            responsible_staff_id=principal.account_id,
            session_date=payload.session_date,
            purpose=payload.purpose.strip(),
            notes=payload.notes,
            status=payload.status,
            created_at=now,
            updated_at=now,
        )
        guidance_repo.save(guidance_session)
        _record_audit(
            principal,
            "guidance_session.created",
            "guidance_session",
            guidance_session.guidance_session_id,
            school_id=principal.school_id,
            new_value={"status": guidance_session.status},
        )
        _create_notification(
            principal.account_id,
            "guidance_session.created",
            "A learner guidance session was recorded.",
            f"guidance-created:{guidance_session.guidance_session_id}",
        )
        return _guidance_out(guidance_session)

    @fastapi_app.put(
        "/api/guidance-sessions/{guidance_session_id}",
        response_model=GuidanceSessionResponse,
        tags=["Guidance"],
    )
    async def update_guidance_session(
        guidance_session_id: UUID,
        payload: GuidanceSessionUpdateRequest,
        request: Request,
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        guidance_session = guidance_repo.find_by_id(guidance_session_id)
        if (
            guidance_session is None
            or guidance_session.school_id != principal.school_id
        ):
            raise HTTPException(status_code=404, detail="Guidance session not found.")
        previous_status = guidance_session.status
        updates = payload.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            if value is not None:
                setattr(
                    guidance_session,
                    field_name,
                    value.strip() if field_name == "purpose" else value,
                )
        guidance_session.updated_at = datetime.now(timezone.utc)
        guidance_repo.save(guidance_session)
        _record_audit(
            principal,
            "guidance_session.updated",
            "guidance_session",
            guidance_session.guidance_session_id,
            school_id=guidance_session.school_id,
            old_value={"status": previous_status},
            new_value={"status": guidance_session.status},
        )
        return _guidance_out(guidance_session)

    # ── Notifications ────────────────────────────────────────────────────────

    @fastapi_app.post(
        "/api/notifications/deadline-reminders",
        response_model=DeadlineReminderResponse,
        tags=["Notifications"],
    )
    async def create_deadline_reminders(request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="No school scope is assigned.")
        learner_ids = {
            learner.learner_id
            for learner in learner_repo.find_by_school(principal.school_id)
        }
        programmes = {
            programme.programme_id: programme
            for programme in programme_repo.find_all()
        }
        today = date.today()
        deadline_limit = today + timedelta(days=30)
        created = 0
        for application in application_svc.list_applications():
            if (
                application.learner_id not in learner_ids
                or application.status
                in (ApplicationStatusEnum.Submitted, ApplicationStatusEnum.Cancelled)
            ):
                continue
            programme = programmes.get(application.programme_id)
            if (
                programme is None
                or not today <= programme.application_deadline <= deadline_limit
            ):
                continue
            created += _create_notification(
                principal.account_id,
                "application.deadline",
                f"An application deadline is approaching: {programme.name} "
                f"({programme.application_deadline.isoformat()}).",
                f"deadline:{application.application_id}:{principal.account_id}:"
                f"{programme.application_deadline.isoformat()}",
            )
        return DeadlineReminderResponse(created=created)

    @fastapi_app.get(
        "/api/notifications",
        response_model=List[NotificationResponse],
        tags=["Notifications"],
    )
    async def list_notifications(request: Request):
        principal = _require_auth(request)
        return [
            NotificationResponse(
                notification_id=item.notification_id,
                type=item.type,
                status=item.status,
                message=item.message,
                created_at=item.created_at,
            )
            for item in notification_repo.find_by_recipient(principal.account_id)
        ]

    @fastapi_app.post(
        "/api/notifications/{notification_id}/read",
        response_model=NotificationResponse,
        tags=["Notifications"],
    )
    async def mark_notification_read(notification_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        notification = notification_repo.find_by_id(notification_id)
        if notification is None or notification.recipient_id != principal.account_id:
            raise HTTPException(status_code=404, detail="Notification not found.")
        notification.mark_read()
        notification_repo.save(notification)
        return NotificationResponse(
            notification_id=notification.notification_id,
            type=notification.type,
            status=notification.status,
            message=notification.message,
            created_at=notification.created_at,
        )

    # ── Audit trail ──────────────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/audit",
        response_model=List[AuditLogResponse],
        tags=["Audit"],
    )
    async def list_audit_entries(request: Request):
        principal = _require_auth(request)
        _require_role(
            principal,
            RoleEnum.SchoolAdmin,
            RoleEnum.UniversityAdmissions,
            RoleEnum.SystemAdmin,
        )
        if principal.role == RoleEnum.SchoolAdmin:
            if principal.school_id is None:
                raise HTTPException(status_code=403, detail="No school scope is assigned.")
            entries = audit_repo.find_by_school(principal.school_id)
        elif principal.role == RoleEnum.UniversityAdmissions:
            university_scopes = set(principal.university_ids)
            if principal.university_id is not None:
                university_scopes.add(principal.university_id)
            if not university_scopes:
                raise HTTPException(status_code=403, detail="No university scope is assigned.")
            entries = [entry for scope_id in university_scopes for entry in audit_repo.find_by_university(scope_id)]
        else:
            entries = audit_repo.find_all()
        return [_audit_out(entry) for entry in sorted(entries, key=lambda e: (e.timestamp, str(e.entry_id)), reverse=True)[:500]]

    # ── University scoring rules ─────────────────────────────────────────────

    @fastapi_app.get(
        "/api/universities/me/scoring-rule",
        response_model=ScoringRuleResponse,
        tags=["Scoring rules"],
    )
    async def get_my_scoring_rule(request: Request, university_id: UUID | None = Query(None)):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        target_university_id = university_id or principal.university_id
        if target_university_id is None or not principal.has_university_access(target_university_id):
            raise HTTPException(status_code=403, detail="No university scope is assigned.")
        configured = configured_scoring_rule_repo.find_by_university(
            target_university_id
        )
        rule = configured or NSC_DEFAULT_SCORING_RULE
        return ScoringRuleResponse(
            university_id=target_university_id,
            band_thresholds=rule.band_thresholds,
            subject_count=rule.subject_count,
            excluded_subjects=rule.excluded_subjects,
            subject_weightings=rule.subject_weightings,
            is_customized=configured is not None,
        )

    @fastapi_app.put(
        "/api/universities/me/scoring-rule",
        response_model=ScoringRuleResponse,
        tags=["Scoring rules"],
    )
    async def update_my_scoring_rule(
        payload: ScoringRuleRequest,
        request: Request,
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        target_university_id = payload.university_id or principal.university_id
        if target_university_id is None or not principal.has_university_access(target_university_id):
            raise HTTPException(status_code=403, detail="No university scope is assigned.")
        rule = ScoringRule(
            university_id=target_university_id,
            band_thresholds=list(payload.band_thresholds),
            subject_count=payload.subject_count,
            excluded_subjects=payload.excluded_subjects,
            subject_weightings=payload.subject_weightings,
        )
        configured_scoring_rule_repo.save(rule)
        _record_audit(
            principal,
            "scoring_rule.updated",
            "scoring_rule",
            target_university_id,
            university_id=target_university_id,
            new_value={
                "subject_count": rule.subject_count,
                "band_count": len(rule.band_thresholds),
                "excluded_subject_count": len(rule.excluded_subjects),
            },
        )
        return ScoringRuleResponse(
            university_id=target_university_id,
            band_thresholds=rule.band_thresholds,
            subject_count=rule.subject_count,
            excluded_subjects=rule.excluded_subjects,
            subject_weightings=rule.subject_weightings,
            is_customized=True,
        )

    # ── University source ingestion and school guidance assistant ───────────

    def rag_document_response(document: RagDocument) -> RagDocumentResponse:
        if document.logical_document_id is None:
            raise RuntimeError("Persisted RAG documents must have a logical ID.")
        return RagDocumentResponse(
            document_id=document.document_id,
            logical_document_id=document.logical_document_id,
            university_id=document.university_id,
            version_number=document.version_number,
            lifecycle_state=document.lifecycle_state.value,
            title=document.title,
            file_name=document.file_name,
            content_type=document.content_type,
            embedding_model=document.embedding_model,
            embedding_revision=document.embedding_revision,
            embedding_dimensions=document.embedding_dimensions,
            embedding_state=document.embedding_state.value,
            reindex_required=(
                document.embedding_state is not EmbeddingState.EMBEDDINGS_READY
            ),
            created_at=document.created_at,
        )

    @fastapi_app.post(
        "/api/agent/documents",
        response_model=RagDocumentResponse,
        status_code=201,
        tags=["AI guidance"],
    )
    async def ingest_university_document(
        request: Request,
        title: str = Form(..., min_length=1, max_length=255),
        file: UploadFile = File(...),
        logical_document_id: UUID | None = Form(None),
        university_id: UUID | None = Form(None),
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        target_university_id = university_id or principal.university_id
        if target_university_id is None or not principal.has_university_access(target_university_id):
            raise HTTPException(
                status_code=403,
                detail="This account is not authorized for the selected university.",
            )
        raw_name = file.filename or ""
        file_name = PurePath(raw_name.replace("\\", "/")).name
        if not file_name:
            raise HTTPException(status_code=422, detail="A document filename is required.")
        try:
            payload = await file.read(MAX_DOCUMENT_BYTES + 1)
        finally:
            await file.close()
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail="The document exceeds the 10 MB upload limit.",
            )
        try:
            extracted_text, content_type = extract_document_text(file_name, payload)
        except RagInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        digest = hashlib.sha256(payload).hexdigest()
        safe_title = title.strip()
        if not safe_title:
            raise HTTPException(status_code=422, detail="Document title cannot be blank.")
        document = RagDocument(
            document_id=uuid4(),
            university_id=target_university_id,
            title=safe_title,
            file_name=file_name[:255],
            content_type=content_type,
            content_sha256=digest,
            uploaded_by=principal.account_id,
            logical_document_id=logical_document_id,
        )
        chunk_texts = chunk_text(extracted_text)
        if not chunk_texts:
            raise HTTPException(
                status_code=422,
                detail="No usable text chunks could be created from this document.",
            )
        try:
            vectors = await asyncio.to_thread(embed_texts, chunk_texts)
        except RagEmbeddingUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        chunks = [
            RagChunk(
                chunk_id=uuid4(),
                document_id=document.document_id,
                chunk_index=index,
                text=text,
                embedding=vector,
            )
            for index, (text, vector) in enumerate(zip(chunk_texts, vectors))
        ]
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No usable text chunks could be created from this document.",
            )
        try:
            document = knowledge_repo.ingest_document(document, chunks)
        except DuplicateRagDocumentError as exc:
            raise HTTPException(
                status_code=409,
                detail="This document is already indexed for your university.",
            ) from exc
        except RagLogicalDocumentNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="Logical document not found."
            ) from exc
        except RagLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        programme_drafts = _ensure_programme_drafts(document, extracted_text)
        _record_audit(
            principal,
            "rag.document.ingested",
            "rag_document",
            document.document_id,
            university_id=target_university_id,
            new_value={
                "title": document.title,
                "file_name": document.file_name,
                "chunk_count": len(chunks),
                "logical_document_id": str(document.logical_document_id),
                "version_number": document.version_number,
                "programme_draft_count": len(programme_drafts),
            },
        )
        return rag_document_response(document).model_copy(
            update={"programme_draft_count": len(programme_drafts)}
        )

    @fastapi_app.get(
        "/api/agent/documents",
        response_model=List[RagDocumentResponse],
        tags=["AI guidance"],
    )
    async def list_university_documents(
        request: Request, university_id: UUID | None = Query(None)
    ):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        if university_id:
            if not principal.has_university_access(university_id):
                raise HTTPException(status_code=403, detail="This account is not authorized for the selected university.")
            scopes = {university_id}
        else:
            scopes = set(principal.university_ids)
            if principal.university_id is not None:
                scopes.add(principal.university_id)
        documents = [
            document
            for scope_id in scopes
            for document in knowledge_repo.list_documents(scope_id)
        ]
        return [rag_document_response(document) for document in documents]

    @fastapi_app.get(
        "/api/agent/documents/{document_id}/programme-drafts",
        response_model=List[ProgrammeImportDraftResponse],
        tags=["Programmes"],
    )
    async def list_document_programme_drafts(document_id: UUID, request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        stored = _get_authorised_rag_document(document_id, principal)
        if stored is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return _programme_drafts_for_document(document_id)

    @fastapi_app.post(
        "/api/agent/documents/{document_id}/programme-drafts",
        response_model=List[ProgrammeImportDraftResponse],
        tags=["Programmes"],
    )
    async def regenerate_document_programme_drafts(document_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        stored = _get_authorised_rag_document(document_id, principal)
        if stored is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        document, chunks = stored
        if document.lifecycle_state is not PhysicalDocumentState.ACTIVE:
            raise HTTPException(status_code=409, detail="Only the active prospectus version can generate programme drafts.")
        drafts = _ensure_programme_drafts(document, "\n".join(chunk.text for chunk in chunks))
        return drafts

    @fastapi_app.put(
        "/api/agent/programme-drafts/{draft_id}",
        response_model=ProgrammeImportDraftResponse,
        tags=["Programmes"],
    )
    async def update_programme_import_draft(
        draft_id: UUID, payload: UpdateProgrammeImportDraftRequest, request: Request
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        draft = _get_programme_draft(draft_id)
        if draft is None or not principal.has_university_access(draft["university_id"]):
            raise HTTPException(status_code=404, detail="Programme draft not found.")
        if draft["status"] != "NeedsReview":
            raise HTTPException(status_code=409, detail="Only drafts awaiting review can be edited.")
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return draft
        updated = _update_programme_draft(draft_id, updates)
        return updated

    @fastapi_app.post(
        "/api/agent/programme-drafts/{draft_id}/approve",
        response_model=ProgrammeImportDraftResponse,
        tags=["Programmes"],
    )
    async def approve_programme_import_draft(draft_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        draft = _get_programme_draft(draft_id)
        if draft is None or not principal.has_university_access(draft["university_id"]):
            raise HTTPException(status_code=404, detail="Programme draft not found.")
        if draft["status"] != "NeedsReview":
            raise HTTPException(status_code=409, detail="This draft is no longer awaiting review.")
        if any(draft.get(field) is None for field in ("faculty", "minimum_aps", "application_deadline")):
            raise HTTPException(status_code=422, detail="Complete faculty, APS, and deadline before approving.")
        source = knowledge_repo.get_document_chunks(draft["source_document_id"], draft["university_id"])
        if source is None or source[0].lifecycle_state.value != "Active":
            raise HTTPException(status_code=409, detail="The source prospectus is no longer active.")
        updated = _update_programme_draft(draft_id, {
            "status": "Approved", "reviewed_by": principal.account_id,
            "reviewed_at": datetime.now(timezone.utc),
        })
        _record_audit(
            principal, "programme_import.approved", "programme_import_draft", draft_id,
            university_id=draft["university_id"],
            new_value={"source_document_id": str(draft["source_document_id"]), "name": draft["name"]},
        )
        return updated

    @fastapi_app.post(
        "/api/agent/programme-drafts/{draft_id}/publish",
        response_model=ProgrammeResponse,
        tags=["Programmes"],
    )
    async def publish_approved_programme_draft(draft_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        draft = _get_programme_draft(draft_id)
        if draft is None or not principal.has_university_access(draft["university_id"]):
            raise HTTPException(status_code=404, detail="Programme draft not found.")
        existing = next((programme for programme in programme_repo.find_all() if programme.source_draft_id == draft_id), None)
        if existing is not None:
            if draft["status"] != "Submitted":
                _update_programme_draft(draft_id, {"status": "Submitted"})
            return _programme_out(existing)
        if draft["status"] != "Approved":
            raise HTTPException(status_code=409, detail="Review and approve the programme draft before publishing it.")
        source = knowledge_repo.get_document_chunks(draft["source_document_id"], draft["university_id"])
        if source is None or source[0].lifecycle_state.value != "Active":
            raise HTTPException(status_code=409, detail="The source prospectus is no longer active.")
        required_fields = ("faculty", "minimum_aps", "application_deadline")
        if any(draft.get(field) is None for field in required_fields):
            raise HTTPException(status_code=422, detail="Complete faculty, APS, and deadline before publishing.")
        programme = UniversityProgramme(
            programme_id=uuid4(),
            university_id=draft["university_id"],
            name=draft["name"],
            faculty=draft["faculty"],
            minimum_aps=draft["minimum_aps"],
            application_deadline=draft["application_deadline"],
            application_fee=draft["application_fee"] if draft["application_fee"] is not None else Decimal("0"),
            required_documents=list(draft["required_documents"]),
            status=ProgrammeStatusEnum.Draft,
            published_by=principal.account_id,
            required_subjects=dict(draft["required_subjects"]),
            source_document_id=draft["source_document_id"],
            source_draft_id=draft_id,
            reviewed_by=draft["reviewed_by"],
            reviewed_at=draft["reviewed_at"],
        )
        try:
            programme.publish()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            created = programme_svc.create_programme(programme)
        except Exception as exc:
            existing = next((item for item in programme_repo.find_all() if item.source_draft_id == draft_id), None)
            if existing is None:
                raise HTTPException(status_code=409, detail="The programme draft could not be published.") from exc
            created = existing
        _update_programme_draft(draft_id, {"status": "Submitted"})
        _record_audit(
            principal, "programme_import.published", "programme", created.programme_id,
            university_id=created.university_id,
            new_value={"source_document_id": str(draft["source_document_id"]), "source_draft_id": str(draft_id)},
        )
        return _programme_out(created)

    def _get_authorised_rag_document(document_id: UUID, principal: AuthPrincipal):
        scopes = set(principal.university_ids)
        if principal.university_id is not None:
            scopes.add(principal.university_id)
        for scope_id in scopes:
            stored = knowledge_repo.get_document_chunks(document_id, scope_id)
            if stored is not None:
                return stored
        return None

    @fastapi_app.post(
        "/api/agent/documents/{document_id}/reindex",
        response_model=RagDocumentResponse,
        tags=["AI guidance"],
    )
    async def reindex_university_document(document_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        stored = _get_authorised_rag_document(document_id, principal)
        if stored is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        document, old_chunks = stored
        try:
            vectors = await asyncio.to_thread(
                embed_texts, [chunk.text for chunk in old_chunks]
            )
        except RagEmbeddingUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        updated_chunks = [
            RagChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding=vector,
            )
            for chunk, vector in zip(old_chunks, vectors)
        ]
        try:
            updated = knowledge_repo.reindex_document(
                document_id,
                document.university_id,
                updated_chunks,
            )
        except RagLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        _record_audit(
            principal,
            "rag.document.reindexed",
            "rag_document",
            document.document_id,
            university_id=document.university_id,
            old_value={
                "embedding_model": document.embedding_model,
                "embedding_revision": document.embedding_revision,
                "embedding_dimensions": document.embedding_dimensions,
            },
            new_value={
                "embedding_model": updated.embedding_model,
                "embedding_revision": updated.embedding_revision,
                "embedding_dimensions": updated.embedding_dimensions,
                "chunk_count": len(updated_chunks),
            },
        )
        return rag_document_response(updated)

    @fastapi_app.delete(
        "/api/agent/documents/{document_id}",
        status_code=204,
        tags=["AI guidance"],
    )
    async def delete_university_document(document_id: UUID, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        async with semantic_lifecycle_lock:
            stored = _get_authorised_rag_document(document_id, principal)
            if stored is None:
                raise HTTPException(status_code=404, detail="Document not found.")
            document, chunks = stored
            if not knowledge_repo.delete_document(
                document_id, document.university_id
            ):
                raise HTTPException(status_code=404, detail="Document not found.")
            try:
                await asyncio.to_thread(
                    _reconcile_semantic_university,
                document.university_id,
                )
            except Exception as exc:
                # The relational repository is authoritative, so stale vectors are
                # excluded from answers and will be removed by the next scoped sync.
                # Return an error so operators can see that physical cleanup needs retry.
                raise HTTPException(
                    status_code=503,
                    detail="The document was removed, but vector cleanup is pending reconciliation.",
                ) from exc
        _record_audit(
            principal,
            "rag.document.deleted",
            "rag_document",
            document.document_id,
            university_id=document.university_id,
            old_value={
                "title": document.title,
                "file_name": document.file_name,
                "chunk_count": len(chunks),
            },
        )
        return Response(status_code=204)

    @fastapi_app.delete(
        "/api/agent/logical-documents/{logical_document_id}",
        status_code=204,
        tags=["AI guidance"],
    )
    async def delete_university_logical_document(
        logical_document_id: UUID, request: Request
    ):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.UniversityAdmissions)
        scopes = set(principal.university_ids)
        if principal.university_id is not None:
            scopes.add(principal.university_id)
        async with semantic_lifecycle_lock:
            logical_scope = next((scope_id for scope_id in scopes if knowledge_repo.find_logical_document(logical_document_id, scope_id) is not None), None)
            if logical_scope is None:
                raise HTTPException(status_code=404, detail="Logical document not found.")
            logical = knowledge_repo.find_logical_document(logical_document_id, logical_scope)
            if logical is None:
                raise HTTPException(status_code=404, detail="Logical document not found.")
            versions = [
                document
                for document in knowledge_repo.list_documents(
                    logical_scope
                )
                if document.logical_document_id == logical_document_id
            ]
            if not knowledge_repo.delete_logical_document(
                logical_document_id, logical_scope
            ):
                raise HTTPException(status_code=404, detail="Logical document not found.")
            try:
                await asyncio.to_thread(
                    _reconcile_semantic_university,
                    logical_scope,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="The logical document was removed, but vector cleanup is pending reconciliation.",
                ) from exc
        _record_audit(
            principal,
            "rag.logical_document.deleted",
            "rag_logical_document",
            logical_document_id,
            university_id=logical_scope,
            old_value={
                "version_count": len(versions),
                "document_ids": [
                    str(document.document_id) for document in versions
                ],
            },
        )
        return Response(status_code=204)

    @fastapi_app.post(
        "/api/v1/guidance/assistant/ask",
        response_model=AssistantAskResponse,
        tags=["AI guidance"],
    )
    async def ask_guidance_assistant(payload: AssistantAskRequest, request: Request):
        if request.headers.get("content-length") and int(request.headers["content-length"]) > ASSISTANT_MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Guidance request is too large.")
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin, RoleEnum.UniversityAdmissions)
        _check_assistant_rate_limit(principal.account_id)
        if principal.role == RoleEnum.SchoolAdmin and principal.school_id is None:
            raise HTTPException(status_code=403, detail="No school scope is assigned.")
        admission_scopes = set(principal.university_ids)
        if principal.university_id is not None:
            admission_scopes.add(principal.university_id)
        if principal.role == RoleEnum.UniversityAdmissions and not admission_scopes:
            raise HTTPException(status_code=403, detail="No university scope is assigned.")
        if payload.learner_id is not None and principal.role != RoleEnum.SchoolAdmin:
            raise HTTPException(status_code=403, detail="Learner context is available only to authorised school staff.")

        published_programmes = programme_svc.list_published_programmes()
        if principal.role == RoleEnum.UniversityAdmissions:
            university_ids = admission_scopes
        else:
            university_ids = {programme.university_id for programme in published_programmes}
        if payload.university_id is not None:
            if principal.role == RoleEnum.UniversityAdmissions and payload.university_id not in admission_scopes:
                raise HTTPException(status_code=404, detail="University source not found.")
            university_ids &= {payload.university_id}
        selected_programmes = [programme for programme in published_programmes if programme.university_id in university_ids]
        if payload.programme_id is not None:
            selected_programmes = [programme for programme in selected_programmes if programme.programme_id == payload.programme_id]
            if not selected_programmes:
                raise HTTPException(status_code=404, detail="Programme not found.")

        eligibility_context: list[dict[str, object]] | None = None
        if payload.learner_id is not None:
            learner = _require_school_learner(payload.learner_id, principal)
            eligibility_context = []
            for programme in selected_programmes:
                aps_score = learner_svc.get_aps_score(learner.learner_id, university_id=programme.university_id)
                eligibility = programme_svc.check_eligibility(programme.programme_id, aps_score, marks=learner.marks)
                best_by_subject: dict[str, int] = {}
                for mark in learner.marks:
                    best_by_subject[mark.subject_name] = max(best_by_subject.get(mark.subject_name, 0), mark.score)
                unmet_subjects = [
                    f"{subject} (minimum {minimum}; recorded {best_by_subject.get(subject, 'no mark')})"
                    for subject, minimum in programme.required_subjects.items()
                    if best_by_subject.get(subject) is None or best_by_subject[subject] < minimum
                ]
                eligibility_context.append({
                    "programme_name": programme.name,
                    "aps_score": aps_score,
                    "minimum_aps": programme.minimum_aps,
                    "eligibility": eligibility.value,
                    "unmet_subjects": unmet_subjects,
                })

        async with semantic_lifecycle_lock:
            conversation = None
            conversation_scope = principal.school_id or UUID(int=0)
            if payload.conversation_id is not None:
                conversation = knowledge_repo.find_conversation(payload.conversation_id)
                if conversation is None or conversation.account_id != principal.account_id or conversation.school_id != conversation_scope:
                    raise HTTPException(status_code=404, detail="Conversation not found.")
            else:
                conversation = RagConversation(conversation_id=uuid4(), account_id=principal.account_id, school_id=conversation_scope)
                knowledge_repo.create_conversation(conversation)
            previous_messages = knowledge_repo.list_messages(conversation.conversation_id, limit=6)
            contextual_question = " ".join([message.content for message in previous_messages if message.role == "user"][-3:] + [payload.question])
            try:
                matches = await asyncio.to_thread(
                    _retrieve_authorised_semantic, contextual_question, university_ids
                )
            except (RagEmbeddingUnavailableError, RagReindexRequiredError, RuntimeError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            external_provider = not isinstance(configured_answer_provider, ExtractiveGroundedAnswerProvider)
            send_learner_context = (not external_provider) or os.environ.get("RAG_EXTERNAL_LEARNER_CONTEXT", "false").strip().lower() == "true"
            provider_context = eligibility_context if send_learner_context else None
            response_provider = configured_answer_provider
            try:
                answer, _provider_sources = await asyncio.to_thread(response_provider.generate, contextual_question, matches, eligibility=provider_context)
            except RagGenerationUnavailableError:
                response_provider = ExtractiveGroundedAnswerProvider()
                external_provider = False
                send_learner_context = True
                answer, _provider_sources = await asyncio.to_thread(
                    response_provider.generate,
                    contextual_question,
                    matches,
                    eligibility=eligibility_context,
                )

            source_refs = [int(value) for value in re.findall(r"\[Source\s+(\d+)\]", answer)]
            retrieved_chunk_ids = {str(chunk.chunk_id) for _score, _document, chunk in matches}
            supplied_source_ids = {
                str(source.get("chunk_id")) for source in _provider_sources
                if source.get("chunk_id") is not None
            }
            citation_metadata_invalid = (
                not supplied_source_ids.issubset(retrieved_chunk_ids)
                or (source_refs and not supplied_source_ids)
            )
            guarantee = re.search(r"\b(?:you are guaranteed admission|guarantees admission|will be admitted|assured admission)\b", answer, re.IGNORECASE)
            if any(index < 1 or index > len(matches) for index in source_refs) or citation_metadata_invalid or guarantee or not _assistant_numbers_match_engine(answer, eligibility_context or []):
                response_provider = ExtractiveGroundedAnswerProvider()
                answer, _provider_sources = await asyncio.to_thread(response_provider.generate, contextual_question, matches, eligibility=eligibility_context)

            if external_provider and eligibility_context and not send_learner_context and any(term in payload.question.lower() for term in ("aps", "eligib", "subject")):
                engine_explanation, _ = await asyncio.to_thread(ExtractiveGroundedAnswerProvider().generate, payload.question, [], eligibility=eligibility_context)
                if engine_explanation and not engine_explanation.startswith("I could not find"):
                    answer = f"{answer}\n\n{engine_explanation}"

            request_id = uuid4()
            now = datetime.now(timezone.utc)
            position = previous_messages[-1].position + 1 if previous_messages else 0
            cited_chunk_ids = {
                str(source.get("chunk_id"))
                for source in _provider_sources
                if source.get("chunk_id") is not None
            }
            citations = [
                _assistant_citation(score, document, chunk)
                for score, document, chunk in matches
                if not cited_chunk_ids or str(chunk.chunk_id) in cited_chunk_ids
            ]
            knowledge_repo.append_messages([
                RagMessage(message_id=uuid4(), conversation_id=conversation.conversation_id, position=position, role="user", content=payload.question, created_at=now),
                RagMessage(message_id=uuid4(), conversation_id=conversation.conversation_id, position=position + 1, role="assistant", content=answer, sources=tuple(citations), created_at=now),
            ])
            abstained = not bool(matches)
            mode = "offline-extractive" if isinstance(response_provider, ExtractiveGroundedAnswerProvider) else response_provider.generation_mode
            model = getattr(response_provider, "model", None) or mode
            _record_audit(
                principal,
                "rag.assistant.asked",
                "rag_assistant_request",
                request_id,
                school_id=principal.school_id,
                university_id=principal.university_id,
                new_value={
                    "learner_reference": str(payload.learner_id) if payload.learner_id else None,
                    "retrieved_chunk_ids": [citation["chunk_id"] for citation in citations],
                    "mode": mode,
                    "abstained": abstained,
                },
            )
            return AssistantAskResponse(answer=answer, citations=citations, mode=mode, model=model, abstained=abstained, request_id=request_id)

    @fastapi_app.post(
        "/api/agent/chat",
        response_model=RagChatResponse,
        tags=["AI guidance"],
    )
    async def chat_with_guidance_agent(payload: RagChatRequest, request: Request):
        _require_csrf(request)
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        if principal.school_id is None:
            raise HTTPException(status_code=403, detail="No school scope is assigned.")

        published_programmes = programme_svc.list_published_programmes()
        eligibility_context: list[dict[str, object]] | None = None
        if payload.learner_id is not None:
            learner = _require_school_learner(payload.learner_id, principal)
            eligibility_context = []
            for programme in published_programmes:
                aps_score = learner_svc.get_aps_score(
                    learner.learner_id,
                    university_id=programme.university_id,
                )
                eligibility = programme_svc.check_eligibility(
                    programme.programme_id,
                    aps_score,
                    marks=learner.marks,
                )
                best_by_subject: dict[str, int] = {}
                for mark in learner.marks:
                    best_by_subject[mark.subject_name] = max(
                        best_by_subject.get(mark.subject_name, 0), mark.score
                    )
                unmet_subjects = [
                    f"{subject} (minimum {minimum}; recorded "
                    f"{best_by_subject.get(subject, 'no mark')})"
                    for subject, minimum in programme.required_subjects.items()
                    if best_by_subject.get(subject) is None
                    or best_by_subject[subject] < minimum
                ]
                eligibility_context.append(
                    {
                        "programme_name": programme.name,
                        "aps_score": aps_score,
                        "minimum_aps": programme.minimum_aps,
                        "eligibility": eligibility.value,
                        "unmet_subjects": unmet_subjects,
                    }
                )

        async with semantic_lifecycle_lock:
            if payload.conversation_id is None:
                conversation = RagConversation(
                    conversation_id=uuid4(),
                    account_id=principal.account_id,
                    school_id=principal.school_id,
                )
                knowledge_repo.create_conversation(conversation)
            else:
                conversation = knowledge_repo.find_conversation(payload.conversation_id)
                if (
                    conversation is None
                    or conversation.account_id != principal.account_id
                    or conversation.school_id != principal.school_id
                ):
                    raise HTTPException(status_code=404, detail="Conversation not found.")

            previous_messages = knowledge_repo.list_messages(
                conversation.conversation_id,
                limit=6,
            )
            previous_questions = [
                message.content
                for message in previous_messages
                if message.role == "user"
            ][-3:]
            contextual_question = " ".join(previous_questions + [payload.message])
            university_ids = {programme.university_id for programme in published_programmes}
            try:
                indexed_chunks = knowledge_repo.list_active_chunks(university_ids)
                matches = await asyncio.to_thread(retrieve_chunks, contextual_question, indexed_chunks)
            except RagEmbeddingUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except RagReindexRequiredError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            response_provider = configured_answer_provider
            try:
                answer, sources = await asyncio.to_thread(
                    response_provider.generate,
                    contextual_question,
                    matches,
                    eligibility=eligibility_context,
                )
            except RagGenerationUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            unsupported_guarantee = re.search(
                r"\b(?:you are guaranteed admission|guarantees admission|will be admitted|assured admission)\b",
                answer,
                re.IGNORECASE,
            )
            if unsupported_guarantee or not _assistant_numbers_match_engine(
                answer, eligibility_context or []
            ):
                response_provider = ExtractiveGroundedAnswerProvider()
                answer, sources = await asyncio.to_thread(
                    response_provider.generate,
                    contextual_question,
                    matches,
                    eligibility=eligibility_context,
                )
            now = datetime.now(timezone.utc)
            start_position = previous_messages[-1].position + 1 if previous_messages else 0
            knowledge_repo.append_messages(
                [
                    RagMessage(
                        message_id=uuid4(),
                        conversation_id=conversation.conversation_id,
                        position=start_position,
                        role="user",
                        content=payload.message,
                        created_at=now,
                    ),
                    RagMessage(
                        message_id=uuid4(),
                        conversation_id=conversation.conversation_id,
                        position=start_position + 1,
                        role="assistant",
                        content=answer,
                        sources=tuple(sources),
                        created_at=now,
                    ),
                ]
            )
            history = knowledge_repo.list_messages(conversation.conversation_id, limit=20)
            return RagChatResponse(
                conversation_id=conversation.conversation_id,
                answer=answer,
                generation_mode=response_provider.generation_mode,
                sources=sources,
                history=[
                    {
                        "role": message.role,
                        "content": message.content,
                        "sources": list(message.sources),
                        "created_at": message.created_at,
                    }
                    for message in history
                ],
                notice=(
                    f"Semantic retrieval uses {EMBEDDING_MODEL} at revision "
                    f"{EMBEDDING_REVISION}. Answer generation mode: "
                    f"{response_provider.generation_mode}."
                ),
            )

    # ── Reports ──────────────────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/reports/school",
        response_model=SchoolReportResponse,
        tags=["Reports"],
    )
    async def school_report(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)
        learners = learner_repo.find_by_school(principal.school_id)
        learner_ids = {learner.learner_id for learner in learners}
        applications = [
            item
            for item in application_svc.list_applications()
            if item.learner_id in learner_ids
        ]
        application_counts: dict[str, int] = {}
        for item in applications:
            application_counts[item.status.value] = (
                application_counts.get(item.status.value, 0) + 1
            )
        all_published_programmes = programme_svc.list_published_programmes()
        programmes = sorted(
            (
                item
                for item in all_published_programmes
                if item.application_deadline >= date.today()
            ),
            key=lambda item: item.application_deadline,
        )
        application_counts_by_programme: dict[UUID, int] = {}
        for application in applications:
            application_counts_by_programme[application.programme_id] = (
                application_counts_by_programme.get(application.programme_id, 0) + 1
            )
        upcoming_deadlines = [
            {
                "programme_id": item.programme_id,
                "programme_name": item.name,
                "university_id": item.university_id,
                "deadline": item.application_deadline,
                "application_count": application_counts_by_programme.get(
                    item.programme_id, 0
                ),
            }
            for item in programmes[:20]
        ]
        eligibility_distribution = {value.value: 0 for value in EligibilityEnum}
        for learner in learners:
            for programme in all_published_programmes:
                score = learner_svc.get_aps_score(
                    learner.learner_id,
                    university_id=programme.university_id,
                )
                result = programme_svc.check_eligibility(
                    programme.programme_id,
                    score,
                    marks=learner.marks,
                )
                eligibility_distribution[result.value] += 1
        return SchoolReportResponse(
            total_learners=len(learners),
            learners_with_marks=sum(bool(item.marks) for item in learners),
            total_applications=len(applications),
            applications_by_status=application_counts,
            eligibility_distribution=eligibility_distribution,
            upcoming_deadlines=upcoming_deadlines,
        )

    @fastapi_app.get(
        "/api/reports/doe",
        response_model=DoEReportResponse,
        tags=["Reports"],
    )
    async def doe_report(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.DoEOfficial)
        learners = learner_repo.find_all()
        applications = application_svc.list_applications()
        cohort_size = len(learners)
        suppressed = cohort_size < DOE_SMALL_COHORT_THRESHOLD
        status_counts: dict[str, int] = {}
        for item in applications:
            status_counts[item.status.value] = status_counts.get(item.status.value, 0) + 1
        eligibility_counts = {value.value: 0 for value in EligibilityEnum}
        doe_programmes = programme_svc.list_published_programmes()
        for learner in learners:
            for programme in doe_programmes:
                score = learner_svc.get_aps_score(
                    learner.learner_id,
                    university_id=programme.university_id,
                )
                category = programme_svc.check_eligibility(
                    programme.programme_id,
                    score,
                    marks=learner.marks,
                )
                eligibility_counts[category.value] += 1
        cohort_suppressed = cohort_size < DOE_SMALL_COHORT_THRESHOLD
        application_group_suppressed = (
            cohort_suppressed
            or len(applications) < DOE_SMALL_COHORT_THRESHOLD
            or any(
                count < DOE_SMALL_COHORT_THRESHOLD
                for count in status_counts.values()
            )
        )
        eligibility_group_suppressed = cohort_suppressed or any(
            count < DOE_SMALL_COHORT_THRESHOLD
            for count in eligibility_counts.values()
        )
        return DoEReportResponse(
            cohort_size=None if cohort_suppressed else cohort_size,
            suppressed=(
                cohort_suppressed
                or application_group_suppressed
                or eligibility_group_suppressed
            ),
            total_learners=None if cohort_suppressed else cohort_size,
            total_applications=(
                None if application_group_suppressed else len(applications)
            ),
            applications_by_status={
                key: None if application_group_suppressed else count
                for key, count in status_counts.items()
            },
            eligibility_distribution={
                key: None if eligibility_group_suppressed else count
                for key, count in eligibility_counts.items()
            },
        )

    # ── /api/dashboard/summary ────────────────────────────────────────────────

    @fastapi_app.get("/api/dashboard/summary", response_model=DashboardSummary, tags=["Dashboard"])
    async def dashboard_summary(request: Request):
        principal = _require_auth(request)
        _require_role(principal, RoleEnum.SchoolAdmin)

        school_learners = learner_repo.find_by_school(principal.school_id)
        total_learners = len(school_learners)
        learners_with_marks = sum(1 for l in school_learners if l.marks)

        learner_ids = {l.learner_id for l in school_learners}
        all_apps = [a for a in application_svc.list_applications() if a.learner_id in learner_ids]
        total_applications = len(all_apps)

        status_counts: dict[str, int] = {}
        for app in all_apps:
            status_counts[app.status.value] = status_counts.get(app.status.value, 0) + 1

        published_programmes = programme_svc.list_published_programmes()
        eligibility_distribution = {
            eligibility.value: 0 for eligibility in EligibilityEnum
        }
        for learner in school_learners:
            for programme in published_programmes:
                learner_aps = learner_svc.get_aps_score(
                    learner.learner_id,
                    university_id=programme.university_id,
                )
                eligibility = programme_svc.check_eligibility(
                    programme.programme_id,
                    learner_aps,
                    marks=learner.marks,
                )
                eligibility_distribution[eligibility.value] += 1

        return DashboardSummary(
            total_learners=total_learners,
            learners_with_marks=learners_with_marks,
            applications_by_status=status_counts,
            eligibility_distribution=eligibility_distribution,
            total_applications=total_applications,
        )

    @fastapi_app.get("/health", tags=["Health"], summary="Health check")
    async def health():
        return {"status": "ok", "service": "UniMatch API", "version": "1.0.0"}

    return fastapi_app


app = create_app(database_url=Settings.from_environment().database_url)
