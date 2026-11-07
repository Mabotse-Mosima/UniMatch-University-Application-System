from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from unimatch.db_models import (
    AccountRecord,
    AccountUniversityScopeRecord,
    UniversityInstitutionRecord,
    AccountInvitationRecord,
    AccountSessionRecord,
    ApplicationRecord,
    ApplicationStatusHistoryRecord,
    AuditLogRecord,
    GuidanceSessionRecord,
    LearnerRecord,
    LearnerDocumentRecord,
    MarkRecord,
    NotificationRecord,
    ProgrammeRecord,
    RagChunkRecord,
    RagConversationRecord,
    RagDocumentRecord,
    RagLogicalDocumentRecord,
    RagMessageRecord,
    ScoringRuleRecord,
    SchoolRecord,
    SchoolAdminBootstrapRecord,
    VerificationRecordORM,
)
from unimatch.entities import (
    Application,
    AuditLogEntry,
    Document,
    GuidanceSession,
    LearnerProfile,
    Mark,
    Notification,
    ScoringRule,
    Session as SessionEntity,
    UniversityProgramme,
    UserAccount,
    VerificationRecord,
    School,
)
from unimatch.enums import (
    AccountStateEnum,
    ApplicationStatusEnum,
    EligibilityEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
    RoleEnum,
)
from unimatch.repositories import (
    ApplicationRepository,
    AuditLogRepository,
    DocumentRepository,
    GuidanceSessionRepository,
    LearnerProfileRepository,
    NotificationRepository,
    ScoringRuleRepository,
    SessionRepository,
    UniversityProgrammeRepository,
    UserAccountRepository,
    VerificationRecordRepository,
    SchoolRepository,
    AccountInvitationRepository,
)
from unimatch.status_history import StatusHistoryEntry
from unimatch.rag import (
    DuplicateRagDocumentError,
    EmbeddingState,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    LogicalDocumentState,
    PhysicalDocumentState,
    RagLifecycleError,
    RagChunk,
    RagConversation,
    RagDocument,
    RagLogicalDocument,
    RagLogicalDocumentNotFoundError,
    RagMessage,
    RagReindexRequiredError,
)

if TYPE_CHECKING:
    from unimatch.auth import AuthPrincipal


class _PostgresRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _find_all(self, statement: Select, mapper: Callable[[Session, Any], Any]) -> list:
        with self._session_factory() as session:
            return [mapper(session, row) for row in session.scalars(statement).all()]


def _mark_from_record(row: MarkRecord) -> Mark:
    return Mark(
        mark_id=row.mark_id,
        learner_id=row.learner_id,
        subject_name=row.subject_name,
        score=row.score,
        exam_type=row.exam_type,
        academic_year=row.academic_year,
        created_at=row.created_at,
    )


def _learner_from_record(_session: Session, row: LearnerRecord) -> LearnerProfile:
    return LearnerProfile(
        learner_id=row.learner_id,
        full_name=row.full_name,
        school_id_number=row.school_id_number,
        grade=row.grade,
        status=ProfileStatusEnum(row.status),
        counselor_id=row.counselor_id,
        school_id=row.school_id,
        marks=[_mark_from_record(mark) for mark in row.marks],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresLearnerProfileRepository(_PostgresRepository, LearnerProfileRepository):
    def save_many(self, entities: list[LearnerProfile]) -> None:
        """Insert a set of new learner profiles and marks in one transaction."""
        with self._session_factory.begin() as session:
            for entity in entities:
                row = LearnerRecord(
                    learner_id=entity.learner_id,
                    full_name=entity.full_name,
                    school_id_number=entity.school_id_number,
                    grade=entity.grade,
                    status=entity.status.value,
                    counselor_id=entity.counselor_id,
                    school_id=entity.school_id,
                    created_at=entity.created_at,
                    updated_at=entity.updated_at,
                )
                row.marks = [
                    MarkRecord(
                        mark_id=mark.mark_id,
                        learner_id=entity.learner_id,
                        subject_name=mark.subject_name,
                        score=mark.score,
                        exam_type=mark.exam_type,
                        academic_year=mark.academic_year,
                        created_at=mark.created_at,
                        position=position,
                    )
                    for position, mark in enumerate(entity.marks)
                ]
                session.add(row)

    def save(self, entity: LearnerProfile) -> None:
        with self._session_factory() as session:
            row = session.get(
                LearnerRecord,
                entity.learner_id,
                options=(selectinload(LearnerRecord.marks),),
            )
            if row is None:
                row = LearnerRecord(learner_id=entity.learner_id)
                session.add(row)

            row.full_name = entity.full_name
            row.school_id_number = entity.school_id_number
            row.grade = entity.grade
            row.status = entity.status.value
            row.counselor_id = entity.counselor_id
            row.school_id = entity.school_id
            row.created_at = entity.created_at
            row.updated_at = entity.updated_at
            row.marks.clear()
            row.marks.extend(
                MarkRecord(
                    mark_id=mark.mark_id,
                    learner_id=entity.learner_id,
                    subject_name=mark.subject_name,
                    score=mark.score,
                    exam_type=mark.exam_type,
                    academic_year=mark.academic_year,
                    created_at=mark.created_at,
                    position=position,
                )
                for position, mark in enumerate(entity.marks)
            )
            session.commit()

    def find_by_id(self, entity_id: UUID) -> LearnerProfile | None:
        statement = (
            select(LearnerRecord)
            .where(LearnerRecord.learner_id == entity_id)
            .options(selectinload(LearnerRecord.marks))
        )
        with self._session_factory() as session:
            row = session.scalar(statement)
            return None if row is None else _learner_from_record(session, row)

    def find_all(self) -> list[LearnerProfile]:
        statement = (
            select(LearnerRecord)
            .options(selectinload(LearnerRecord.marks))
            .order_by(LearnerRecord.created_at, LearnerRecord.learner_id)
        )
        return self._find_all(statement, _learner_from_record)

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(LearnerRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_counselor(self, counselor_id: UUID) -> list[LearnerProfile]:
        statement = (
            select(LearnerRecord)
            .where(LearnerRecord.counselor_id == counselor_id)
            .options(selectinload(LearnerRecord.marks))
            .order_by(LearnerRecord.created_at, LearnerRecord.learner_id)
        )
        return self._find_all(statement, _learner_from_record)

    def find_by_school(self, school_id: UUID) -> list[LearnerProfile]:
        statement = (
            select(LearnerRecord)
            .where(LearnerRecord.school_id == school_id)
            .options(selectinload(LearnerRecord.marks))
            .order_by(LearnerRecord.created_at, LearnerRecord.learner_id)
        )
        return self._find_all(statement, _learner_from_record)


def _programme_from_record(row: ProgrammeRecord) -> UniversityProgramme:
    return UniversityProgramme(
        programme_id=row.programme_id,
        university_id=row.university_id,
        name=row.name,
        faculty=row.faculty,
        minimum_aps=row.minimum_aps,
        application_deadline=row.application_deadline,
        application_fee=row.application_fee,
        required_documents=list(row.required_documents),
        status=ProgrammeStatusEnum(row.status),
        published_by=row.published_by,
        version=row.version,
        required_subjects=dict(row.required_subjects),
        created_at=row.created_at,
        updated_at=row.updated_at,
        source_document_id=row.source_document_id,
        source_draft_id=row.source_draft_id,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


def _programme_snapshot(programme: UniversityProgramme) -> dict[str, object]:
    return {
        "programme_id": str(programme.programme_id),
        "university_id": str(programme.university_id),
        "name": programme.name,
        "faculty": programme.faculty,
        "minimum_aps": programme.minimum_aps,
        "application_deadline": programme.application_deadline.isoformat(),
        "application_fee": str(programme.application_fee),
        "required_documents": list(programme.required_documents),
        "status": programme.status.value,
        "published_by": str(programme.published_by),
        "version": programme.version,
        "required_subjects": dict(programme.required_subjects),
        "created_at": programme.created_at.isoformat(),
        "updated_at": programme.updated_at.isoformat(),
        "source_document_id": str(programme.source_document_id) if programme.source_document_id else None,
        "source_draft_id": str(programme.source_draft_id) if programme.source_draft_id else None,
        "reviewed_by": str(programme.reviewed_by) if programme.reviewed_by else None,
        "reviewed_at": programme.reviewed_at.isoformat() if programme.reviewed_at else None,
    }


def _programme_from_snapshot(snapshot: dict[str, object]) -> UniversityProgramme:
    return UniversityProgramme(
        programme_id=UUID(str(snapshot["programme_id"])),
        university_id=UUID(str(snapshot["university_id"])),
        name=str(snapshot["name"]),
        faculty=str(snapshot["faculty"]),
        minimum_aps=int(snapshot["minimum_aps"]),
        application_deadline=date.fromisoformat(str(snapshot["application_deadline"])),
        application_fee=Decimal(str(snapshot["application_fee"])),
        required_documents=list(snapshot["required_documents"]),
        status=ProgrammeStatusEnum(str(snapshot["status"])),
        published_by=UUID(str(snapshot["published_by"])),
        version=int(snapshot["version"]),
        required_subjects=dict(snapshot["required_subjects"]),
        created_at=datetime.fromisoformat(str(snapshot["created_at"])),
        updated_at=datetime.fromisoformat(str(snapshot["updated_at"])),
        source_document_id=UUID(str(snapshot["source_document_id"])) if snapshot.get("source_document_id") else None,
        source_draft_id=UUID(str(snapshot["source_draft_id"])) if snapshot.get("source_draft_id") else None,
        reviewed_by=UUID(str(snapshot["reviewed_by"])) if snapshot.get("reviewed_by") else None,
        reviewed_at=datetime.fromisoformat(str(snapshot["reviewed_at"])) if snapshot.get("reviewed_at") else None,
    )


class PostgresUniversityProgrammeRepository(
    _PostgresRepository, UniversityProgrammeRepository
):
    def save(self, entity: UniversityProgramme) -> None:
        with self._session_factory() as session:
            row = session.get(ProgrammeRecord, entity.programme_id)
            if row is None:
                row = ProgrammeRecord(programme_id=entity.programme_id)
                session.add(row)
            row.university_id = entity.university_id
            row.name = entity.name
            row.faculty = entity.faculty
            row.minimum_aps = entity.minimum_aps
            row.application_deadline = entity.application_deadline
            row.application_fee = entity.application_fee
            row.required_documents = list(entity.required_documents)
            row.status = entity.status.value
            row.published_by = entity.published_by
            row.version = entity.version
            row.required_subjects = dict(entity.required_subjects)
            row.created_at = entity.created_at
            row.updated_at = entity.updated_at
            row.source_document_id = entity.source_document_id
            row.source_draft_id = entity.source_draft_id
            row.reviewed_by = entity.reviewed_by
            row.reviewed_at = entity.reviewed_at
            session.commit()

    def find_by_id(self, entity_id: UUID) -> UniversityProgramme | None:
        with self._session_factory() as session:
            row = session.get(ProgrammeRecord, entity_id)
            return None if row is None else _programme_from_record(row)

    def find_all(self) -> list[UniversityProgramme]:
        statement = select(ProgrammeRecord).order_by(
            ProgrammeRecord.created_at, ProgrammeRecord.programme_id
        )
        return self._find_all(statement, lambda _session, row: _programme_from_record(row))

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(ProgrammeRecord, entity_id)
            if row is not None:
                linked_applications = session.scalars(
                    select(ApplicationRecord).where(
                        ApplicationRecord.programme_id == entity_id
                    )
                ).all()
                snapshot = _programme_snapshot(_programme_from_record(row))
                for application in linked_applications:
                    application.programme_snapshot = snapshot
                session.delete(row)
                session.commit()

    def find_by_university(self, university_id: UUID) -> list[UniversityProgramme]:
        statement = (
            select(ProgrammeRecord)
            .where(ProgrammeRecord.university_id == university_id)
            .order_by(ProgrammeRecord.created_at, ProgrammeRecord.programme_id)
        )
        return self._find_all(statement, lambda _session, row: _programme_from_record(row))

    def find_published(self) -> list[UniversityProgramme]:
        statement = (
            select(ProgrammeRecord)
            .where(ProgrammeRecord.status == ProgrammeStatusEnum.Published.value)
            .order_by(ProgrammeRecord.created_at, ProgrammeRecord.programme_id)
        )
        return self._find_all(statement, lambda _session, row: _programme_from_record(row))


def _application_from_record(session: Session, row: ApplicationRecord) -> Application:
    programme_row = session.get(ProgrammeRecord, row.programme_id)
    if programme_row is not None:
        linked_programme = _programme_from_record(programme_row)
    elif row.programme_snapshot is not None:
        linked_programme = _programme_from_snapshot(row.programme_snapshot)
    else:
        linked_programme = None

    history = [
        StatusHistoryEntry(
            entry_id=entry.entry_id,
            application_id=entry.application_id,
            previous_status=ApplicationStatusEnum(entry.previous_status),
            new_status=ApplicationStatusEnum(entry.new_status),
            changed_by=entry.changed_by,
            changed_at=entry.changed_at,
            note=entry.note,
        )
        for entry in row.status_history
    ]
    return Application(
        application_id=row.application_id,
        learner_id=row.learner_id,
        programme_id=row.programme_id,
        status=ApplicationStatusEnum(row.status),
        payment_reference=row.payment_reference,
        fee_amount=row.fee_amount,
        submission_timestamp=row.submission_timestamp,
        acknowledgement_reference=row.acknowledgement_reference,
        linked_programme=linked_programme,
        status_history=history,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresApplicationRepository(_PostgresRepository, ApplicationRepository):
    def save(self, entity: Application) -> None:
        with self._session_factory() as session:
            row = session.get(
                ApplicationRecord,
                entity.application_id,
                options=(selectinload(ApplicationRecord.status_history),),
            )
            if row is None:
                row = ApplicationRecord(application_id=entity.application_id)
                session.add(row)

            row.learner_id = entity.learner_id
            row.programme_id = entity.programme_id
            row.status = entity.status.value
            row.payment_reference = entity.payment_reference
            row.fee_amount = entity.fee_amount
            row.submission_timestamp = entity.submission_timestamp
            row.acknowledgement_reference = entity.acknowledgement_reference
            row.programme_snapshot = (
                _programme_snapshot(entity.linked_programme)
                if entity.linked_programme is not None
                else None
            )
            row.created_at = entity.created_at
            row.updated_at = entity.updated_at
            row.status_history.clear()
            row.status_history.extend(
                ApplicationStatusHistoryRecord(
                    entry_id=entry.entry_id,
                    application_id=entity.application_id,
                    previous_status=entry.previous_status.value,
                    new_status=entry.new_status.value,
                    changed_by=entry.changed_by,
                    changed_at=entry.changed_at,
                    note=entry.note,
                    position=position,
                )
                for position, entry in enumerate(entity.status_history)
            )
            session.commit()

    def find_by_id(self, entity_id: UUID) -> Application | None:
        statement = (
            select(ApplicationRecord)
            .where(ApplicationRecord.application_id == entity_id)
            .options(selectinload(ApplicationRecord.status_history))
        )
        with self._session_factory() as session:
            row = session.scalar(statement)
            return None if row is None else _application_from_record(session, row)

    def find_all(self) -> list[Application]:
        statement = (
            select(ApplicationRecord)
            .options(selectinload(ApplicationRecord.status_history))
            .order_by(ApplicationRecord.created_at, ApplicationRecord.application_id)
        )
        return self._find_all(statement, _application_from_record)

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(ApplicationRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_learner(self, learner_id: UUID) -> list[Application]:
        statement = (
            select(ApplicationRecord)
            .where(ApplicationRecord.learner_id == learner_id)
            .options(selectinload(ApplicationRecord.status_history))
            .order_by(ApplicationRecord.created_at, ApplicationRecord.application_id)
        )
        return self._find_all(statement, _application_from_record)

    def find_by_programme(self, programme_id: UUID) -> list[Application]:
        statement = (
            select(ApplicationRecord)
            .where(ApplicationRecord.programme_id == programme_id)
            .options(selectinload(ApplicationRecord.status_history))
            .order_by(ApplicationRecord.created_at, ApplicationRecord.application_id)
        )
        return self._find_all(statement, _application_from_record)

    def find_by_status(self, status: ApplicationStatusEnum) -> list[Application]:
        statement = (
            select(ApplicationRecord)
            .where(ApplicationRecord.status == status.value)
            .options(selectinload(ApplicationRecord.status_history))
            .order_by(ApplicationRecord.created_at, ApplicationRecord.application_id)
        )
        return self._find_all(statement, _application_from_record)


def _document_from_record(row: LearnerDocumentRecord) -> Document:
    return Document(
        document_id=row.document_id,
        learner_id=row.learner_id,
        application_id=row.application_id,
        document_type=row.document_type,
        filename=row.filename,
        storage_path=row.storage_path,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        uploaded_by=row.uploaded_by,
        virus_scan_status=row.virus_scan_status,
        status=row.status,
        school_id=row.school_id,
        uploaded_at=row.uploaded_at,
        content_sha256=row.content_sha256,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        review_note=row.review_note,
    )


class PostgresDocumentRepository(_PostgresRepository, DocumentRepository):
    def save(self, entity: Document) -> None:
        with self._session_factory() as session:
            row = session.get(LearnerDocumentRecord, entity.document_id)
            if row is None:
                row = LearnerDocumentRecord(document_id=entity.document_id)
                session.add(row)
            row.learner_id = entity.learner_id
            row.application_id = entity.application_id
            row.school_id = entity.school_id
            row.document_type = entity.document_type
            row.filename = entity.filename
            row.storage_path = entity.storage_path
            row.mime_type = entity.mime_type
            row.size_bytes = entity.size_bytes
            row.content_sha256 = entity.content_sha256
            row.uploaded_by = entity.uploaded_by
            row.virus_scan_status = entity.virus_scan_status
            row.status = entity.status
            row.uploaded_at = entity.uploaded_at
            row.reviewed_by = entity.reviewed_by
            row.reviewed_at = entity.reviewed_at
            row.review_note = entity.review_note
            session.commit()

    def find_by_id(self, entity_id: UUID) -> Document | None:
        with self._session_factory() as session:
            row = session.get(LearnerDocumentRecord, entity_id)
            return None if row is None else _document_from_record(row)

    def find_all(self) -> list[Document]:
        statement = select(LearnerDocumentRecord).order_by(
            LearnerDocumentRecord.uploaded_at,
            LearnerDocumentRecord.document_id,
        )
        return self._find_all(
            statement, lambda _session, row: _document_from_record(row)
        )

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(LearnerDocumentRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_learner(self, learner_id: UUID) -> list[Document]:
        statement = (
            select(LearnerDocumentRecord)
            .where(LearnerDocumentRecord.learner_id == learner_id)
            .order_by(LearnerDocumentRecord.uploaded_at, LearnerDocumentRecord.document_id)
        )
        return self._find_all(
            statement, lambda _session, row: _document_from_record(row)
        )

    def find_by_application(self, application_id: UUID) -> list[Document]:
        statement = (
            select(LearnerDocumentRecord)
            .where(LearnerDocumentRecord.application_id == application_id)
            .order_by(LearnerDocumentRecord.uploaded_at, LearnerDocumentRecord.document_id)
        )
        return self._find_all(
            statement, lambda _session, row: _document_from_record(row)
        )


class PostgresScoringRuleRepository(_PostgresRepository, ScoringRuleRepository):
    def save(self, entity: ScoringRule) -> None:
        with self._session_factory() as session:
            row = session.get(ScoringRuleRecord, entity.university_id)
            if row is None:
                row = ScoringRuleRecord(university_id=entity.university_id)
                session.add(row)
            row.band_thresholds = [list(band) for band in entity.band_thresholds]
            row.subject_count = entity.subject_count
            row.excluded_subjects = list(entity.excluded_subjects)
            row.subject_weightings = dict(entity.subject_weightings)
            session.commit()

    def find_by_id(self, entity_id: UUID) -> ScoringRule | None:
        return self.find_by_university(entity_id)

    def find_all(self) -> list[ScoringRule]:
        statement = select(ScoringRuleRecord).order_by(ScoringRuleRecord.university_id)
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(ScoringRuleRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_university(self, university_id: UUID) -> ScoringRule | None:
        with self._session_factory() as session:
            row = session.get(ScoringRuleRecord, university_id)
            return None if row is None else self._to_domain(row)

    @staticmethod
    def _to_domain(row: ScoringRuleRecord) -> ScoringRule:
        return ScoringRule(
            university_id=row.university_id,
            band_thresholds=[(band[0], band[1]) for band in row.band_thresholds],
            subject_count=row.subject_count,
            excluded_subjects=list(row.excluded_subjects),
            subject_weightings=dict(row.subject_weightings),
        )


class PostgresGuidanceSessionRepository(
    _PostgresRepository, GuidanceSessionRepository
):
    def save(self, entity: GuidanceSession) -> None:
        with self._session_factory() as session:
            row = session.get(GuidanceSessionRecord, entity.guidance_session_id)
            if row is None:
                row = GuidanceSessionRecord(
                    guidance_session_id=entity.guidance_session_id
                )
                session.add(row)
            row.learner_id = entity.learner_id
            row.school_id = entity.school_id
            row.responsible_staff_id = entity.responsible_staff_id
            row.session_date = entity.session_date
            row.purpose = entity.purpose
            row.notes = entity.notes
            row.status = entity.status
            row.created_at = entity.created_at
            row.updated_at = entity.updated_at
            session.commit()

    def find_by_id(self, entity_id: UUID) -> GuidanceSession | None:
        with self._session_factory() as session:
            row = session.get(GuidanceSessionRecord, entity_id)
            return None if row is None else self._to_domain(row)

    def find_all(self) -> list[GuidanceSession]:
        statement = select(GuidanceSessionRecord).order_by(
            GuidanceSessionRecord.session_date,
            GuidanceSessionRecord.created_at,
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(GuidanceSessionRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_learner(self, learner_id: UUID) -> list[GuidanceSession]:
        statement = (
            select(GuidanceSessionRecord)
            .where(GuidanceSessionRecord.learner_id == learner_id)
            .order_by(
                GuidanceSessionRecord.session_date,
                GuidanceSessionRecord.created_at,
            )
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def find_by_school(self, school_id: UUID) -> list[GuidanceSession]:
        statement = (
            select(GuidanceSessionRecord)
            .where(GuidanceSessionRecord.school_id == school_id)
            .order_by(
                GuidanceSessionRecord.session_date,
                GuidanceSessionRecord.created_at,
            )
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    @staticmethod
    def _to_domain(row: GuidanceSessionRecord) -> GuidanceSession:
        return GuidanceSession(
            guidance_session_id=row.guidance_session_id,
            learner_id=row.learner_id,
            school_id=row.school_id,
            responsible_staff_id=row.responsible_staff_id,
            session_date=row.session_date,
            purpose=row.purpose,
            notes=row.notes,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class PostgresNotificationRepository(_PostgresRepository, NotificationRepository):
    def save(self, entity: Notification) -> None:
        with self._session_factory() as session:
            row = session.get(NotificationRecord, entity.notification_id)
            if row is None:
                row = NotificationRecord(notification_id=entity.notification_id)
                session.add(row)
            row.recipient_id = entity.recipient_id
            row.notification_type = entity.type
            row.status = entity.status
            row.message = entity.message
            row.retry_count = entity.retry_count
            row.created_at = entity.created_at
            row.sent_at = entity.sent_at
            row.event_key = entity.event_key
            session.commit()

    def find_by_id(self, entity_id: UUID) -> Notification | None:
        with self._session_factory() as session:
            row = session.get(NotificationRecord, entity_id)
            return None if row is None else self._to_domain(row)

    def find_all(self) -> list[Notification]:
        statement = select(NotificationRecord).order_by(
            NotificationRecord.created_at.desc()
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(NotificationRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_recipient(self, recipient_id: UUID) -> list[Notification]:
        statement = (
            select(NotificationRecord)
            .where(NotificationRecord.recipient_id == recipient_id)
            .order_by(NotificationRecord.created_at.desc())
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def find_unread(self, recipient_id: UUID) -> list[Notification]:
        statement = (
            select(NotificationRecord)
            .where(NotificationRecord.recipient_id == recipient_id)
            .where(NotificationRecord.status.notin_(("Read", "Failed")))
            .order_by(NotificationRecord.created_at.desc())
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def find_by_event_key(self, event_key: str) -> Notification | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(NotificationRecord).where(
                    NotificationRecord.event_key == event_key
                )
            )
            return None if row is None else self._to_domain(row)

    @staticmethod
    def _to_domain(row: NotificationRecord) -> Notification:
        return Notification(
            notification_id=row.notification_id,
            recipient_id=row.recipient_id,
            type=row.notification_type,
            status=row.status,
            message=row.message,
            retry_count=row.retry_count,
            created_at=row.created_at,
            sent_at=row.sent_at,
            event_key=row.event_key,
        )


class PostgresAuditLogRepository(_PostgresRepository, AuditLogRepository):
    def save(self, entity: AuditLogEntry) -> None:
        with self._session_factory() as session:
            row = session.get(AuditLogRecord, entity.entry_id)
            if row is None:
                row = AuditLogRecord(entry_id=entity.entry_id)
                session.add(row)
            row.actor_id = entity.actor_id
            row.action = entity.action
            row.target_type = entity.target_type
            row.target_id = entity.target_id
            row.school_id = entity.school_id
            row.university_id = entity.university_id
            row.old_value = entity.old_value
            row.new_value = entity.new_value
            row.timestamp = entity.timestamp
            session.commit()

    def find_by_id(self, entity_id: UUID) -> AuditLogEntry | None:
        with self._session_factory() as session:
            row = session.get(AuditLogRecord, entity_id)
            return None if row is None else self._to_domain(row)

    def find_all(self) -> list[AuditLogEntry]:
        statement = select(AuditLogRecord).order_by(AuditLogRecord.timestamp.desc())
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(AuditLogRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_actor(self, actor_id: UUID) -> list[AuditLogEntry]:
        statement = (
            select(AuditLogRecord)
            .where(AuditLogRecord.actor_id == actor_id)
            .order_by(AuditLogRecord.timestamp.desc())
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def find_by_target(self, target_id: UUID) -> list[AuditLogEntry]:
        statement = (
            select(AuditLogRecord)
            .where(AuditLogRecord.target_id == target_id)
            .order_by(AuditLogRecord.timestamp.desc())
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def find_by_school(self, school_id: UUID) -> list[AuditLogEntry]:
        statement = (
            select(AuditLogRecord)
            .where(AuditLogRecord.school_id == school_id)
            .order_by(AuditLogRecord.timestamp.desc())
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    def find_by_university(self, university_id: UUID) -> list[AuditLogEntry]:
        statement = (
            select(AuditLogRecord)
            .where(AuditLogRecord.university_id == university_id)
            .order_by(AuditLogRecord.timestamp.desc())
        )
        return self._find_all(statement, lambda _session, row: self._to_domain(row))

    @staticmethod
    def _to_domain(row: AuditLogRecord) -> AuditLogEntry:
        return AuditLogEntry(
            entry_id=row.entry_id,
            actor_id=row.actor_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            old_value=row.old_value,
            new_value=row.new_value,
            timestamp=row.timestamp,
            school_id=row.school_id,
            university_id=row.university_id,
        )


class PostgresRagRepository(_PostgresRepository):
    def ingest_document(
        self, document: RagDocument, chunks: list[RagChunk]
    ) -> RagDocument:
        if document.lifecycle_state is not PhysicalDocumentState.ACTIVE:
            raise RagLifecycleError("New uploads must create an Active version.")
        if not chunks:
            raise ValueError("A document must contain at least one chunk.")
        self._validate_chunks(document, chunks)

        is_first_version = document.logical_document_id is None
        logical_id = document.logical_document_id or uuid4()

        try:
            with self._session_factory() as session:
                logical = None
                prior_active = None
                if is_first_version:
                    logical = RagLogicalDocumentRecord(
                        logical_document_id=logical_id,
                        university_id=document.university_id,
                        lifecycle_state=LogicalDocumentState.ACTIVE.value,
                        created_at=document.created_at,
                    )
                    version_number = 1
                else:
                    logical = session.scalar(
                        select(RagLogicalDocumentRecord)
                        .where(
                            RagLogicalDocumentRecord.logical_document_id == logical_id,
                            RagLogicalDocumentRecord.university_id == document.university_id,
                        )
                        .with_for_update()
                    )
                    if logical is None:
                        raise RagLogicalDocumentNotFoundError(
                            "The logical document does not exist in this university."
                        )
                    if logical.lifecycle_state != LogicalDocumentState.ACTIVE.value:
                        raise RagLifecycleError(
                            "A deleted logical document cannot be replaced."
                        )
                    versions = session.scalars(
                        select(RagDocumentRecord)
                        .where(RagDocumentRecord.logical_document_id == logical_id)
                        .order_by(RagDocumentRecord.version_number)
                        .with_for_update()
                    ).all()
                    active_versions = [
                        row
                        for row in versions
                        if row.lifecycle_state == PhysicalDocumentState.ACTIVE.value
                    ]
                    if len(active_versions) != 1:
                        raise RagLifecycleError(
                            "An Active logical document must have exactly one Active version."
                        )
                    prior_active = active_versions[0]
                    version_number = max(row.version_number for row in versions) + 1

                duplicate_statement = select(RagDocumentRecord.document_id).where(
                    RagDocumentRecord.university_id == document.university_id,
                    RagDocumentRecord.content_sha256 == document.content_sha256,
                    RagDocumentRecord.lifecycle_state
                    == PhysicalDocumentState.ACTIVE.value,
                )
                if not is_first_version:
                    duplicate_statement = duplicate_statement.where(
                        RagDocumentRecord.logical_document_id != logical_id
                    )
                if session.scalar(duplicate_statement) is not None:
                    raise DuplicateRagDocumentError(
                        "This document is already indexed."
                    )

                stored_document = replace(
                    document,
                    logical_document_id=logical_id,
                    version_number=version_number,
                    embedding_state=self._embedding_state_for(document, chunks),
                )
                if prior_active is not None:
                    prior_active.lifecycle_state = (
                        PhysicalDocumentState.SUPERSEDED.value
                    )
                    session.flush()
                if is_first_version:
                    session.add(logical)
                    session.flush()
                session.add(
                    RagDocumentRecord(
                        document_id=stored_document.document_id,
                        logical_document_id=logical_id,
                        university_id=stored_document.university_id,
                        version_number=version_number,
                        lifecycle_state=stored_document.lifecycle_state.value,
                        embedding_state=stored_document.embedding_state.value,
                        title=stored_document.title,
                        file_name=stored_document.file_name,
                        content_type=stored_document.content_type,
                        content_sha256=stored_document.content_sha256,
                        uploaded_by=stored_document.uploaded_by,
                        embedding_model=stored_document.embedding_model,
                        embedding_revision=stored_document.embedding_revision,
                        embedding_dimensions=stored_document.embedding_dimensions,
                        created_at=stored_document.created_at,
                        chunks=[
                            RagChunkRecord(
                                chunk_id=chunk.chunk_id,
                                document_id=stored_document.document_id,
                                chunk_index=chunk.chunk_index,
                                text=chunk.text,
                                embedding=list(chunk.embedding),
                            )
                            for chunk in chunks
                        ],
                    )
                )
                session.commit()
                return stored_document
        except IntegrityError as exc:
            constraint_name = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "uq_rag_documents_active_digest":
                raise DuplicateRagDocumentError(
                    "This document is already indexed."
                ) from exc
            raise

    @staticmethod
    def _validate_chunks(document: RagDocument, chunks: list[RagChunk]) -> None:
        chunk_ids: set[UUID] = set()
        chunk_indexes: set[int] = set()
        for chunk in chunks:
            if chunk.document_id != document.document_id:
                raise ValueError("Chunks must belong to their physical document.")
            if chunk.chunk_index < 0:
                raise ValueError("Chunk indexes cannot be negative.")
            if chunk.chunk_id in chunk_ids or chunk.chunk_index in chunk_indexes:
                raise ValueError("Chunk IDs and indexes must be unique per document.")
            chunk_ids.add(chunk.chunk_id)
            chunk_indexes.add(chunk.chunk_index)
            try:
                valid_embedding = (
                    len(chunk.embedding) == document.embedding_dimensions
                    and all(math.isfinite(value) for value in chunk.embedding)
                )
            except (OverflowError, TypeError, ValueError):
                valid_embedding = False
            if not valid_embedding:
                raise ValueError(
                    "Document and chunk embedding metadata do not match."
                )

    @staticmethod
    def _embedding_state_for(
        document: RagDocument, chunks: list[RagChunk]
    ) -> EmbeddingState:
        if (
            chunks
            and document.embedding_model == EMBEDDING_MODEL
            and document.embedding_revision == EMBEDDING_REVISION
            and document.embedding_dimensions == EMBEDDING_DIMENSIONS
        ):
            return EmbeddingState.EMBEDDINGS_READY
        return EmbeddingState.REINDEX_REQUIRED

    def find_document_by_hash(
        self, university_id: UUID, content_sha256: str
    ) -> RagDocument | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(RagDocumentRecord)
                .join(
                    RagLogicalDocumentRecord,
                    RagLogicalDocumentRecord.logical_document_id
                    == RagDocumentRecord.logical_document_id,
                )
                .where(
                    RagDocumentRecord.university_id == university_id,
                    RagDocumentRecord.content_sha256 == content_sha256,
                    RagDocumentRecord.lifecycle_state
                    == PhysicalDocumentState.ACTIVE.value,
                    RagLogicalDocumentRecord.lifecycle_state
                    == LogicalDocumentState.ACTIVE.value,
                )
            )
            return None if row is None else self._document_from_record(row)

    def find_logical_document(
        self, logical_document_id: UUID, university_id: UUID
    ) -> RagLogicalDocument | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(RagLogicalDocumentRecord).where(
                    RagLogicalDocumentRecord.logical_document_id
                    == logical_document_id,
                    RagLogicalDocumentRecord.university_id == university_id,
                )
            )
            if row is None:
                return None
            return RagLogicalDocument(
                logical_document_id=row.logical_document_id,
                university_id=row.university_id,
                lifecycle_state=LogicalDocumentState(row.lifecycle_state),
            )

    def list_documents(self, university_id: UUID) -> list[RagDocument]:
        statement = (
            select(RagDocumentRecord)
            .where(RagDocumentRecord.university_id == university_id)
            .order_by(RagDocumentRecord.created_at.desc())
        )
        return self._find_all(
            statement, lambda _session, row: self._document_from_record(row)
        )

    def list_chunks(
        self, university_ids: set[UUID]
    ) -> list[tuple[RagDocument, RagChunk]]:
        if not university_ids:
            return []
        with self._session_factory() as session:
            rows = session.execute(
                select(RagDocumentRecord, RagChunkRecord)
                .join(
                    RagChunkRecord,
                    RagChunkRecord.document_id == RagDocumentRecord.document_id,
                )
                .where(RagDocumentRecord.university_id.in_(university_ids))
                .order_by(
                    RagDocumentRecord.university_id,
                    RagDocumentRecord.document_id,
                    RagChunkRecord.chunk_index,
                )
            ).all()
            return [
                (
                    self._document_from_record(document),
                    self._chunk_from_record(chunk),
                )
                for document, chunk in rows
            ]

    def list_active_chunks(
        self, university_ids: set[UUID]
    ) -> list[tuple[RagDocument, RagChunk]]:
        if not university_ids:
            return []
        with self._session_factory() as session:
            rows = session.execute(
                select(RagDocumentRecord, RagChunkRecord)
                .join(
                    RagLogicalDocumentRecord,
                    RagLogicalDocumentRecord.logical_document_id
                    == RagDocumentRecord.logical_document_id,
                )
                .join(
                    RagChunkRecord,
                    RagChunkRecord.document_id == RagDocumentRecord.document_id,
                )
                .where(
                    RagDocumentRecord.university_id.in_(university_ids),
                    RagLogicalDocumentRecord.lifecycle_state
                    == LogicalDocumentState.ACTIVE.value,
                    RagDocumentRecord.lifecycle_state
                    == PhysicalDocumentState.ACTIVE.value,
                    RagDocumentRecord.embedding_state
                    == EmbeddingState.EMBEDDINGS_READY.value,
                    RagDocumentRecord.embedding_model == EMBEDDING_MODEL,
                    RagDocumentRecord.embedding_revision == EMBEDDING_REVISION,
                    RagDocumentRecord.embedding_dimensions == EMBEDDING_DIMENSIONS,
                )
                .order_by(
                    RagDocumentRecord.university_id,
                    RagDocumentRecord.logical_document_id,
                    RagDocumentRecord.version_number,
                    RagChunkRecord.chunk_index,
                )
            ).all()
            result = []
            for document_row, chunk_row in rows:
                if not self._stored_embedding_is_valid(
                    chunk_row.embedding, document_row.embedding_dimensions
                ):
                    raise RagReindexRequiredError(
                        "A stored document has invalid embedding data. Re-index it before searching."
                    )
                result.append(
                    (
                        self._document_from_record(document_row),
                        self._chunk_from_record(chunk_row),
                    )
                )
            return result

    @staticmethod
    def _stored_embedding_is_valid(embedding: object, dimensions: int) -> bool:
        if not isinstance(embedding, list) or len(embedding) != dimensions:
            return False
        for value in embedding:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            try:
                if not math.isfinite(value):
                    return False
            except (OverflowError, TypeError, ValueError):
                return False
        return True

    def get_document_chunks(
        self, document_id: UUID, university_id: UUID
    ) -> tuple[RagDocument, list[RagChunk]] | None:
        with self._session_factory() as session:
            document = session.scalar(
                select(RagDocumentRecord).where(
                    RagDocumentRecord.document_id == document_id,
                    RagDocumentRecord.university_id == university_id,
                    RagDocumentRecord.lifecycle_state
                    != PhysicalDocumentState.DELETED.value,
                )
            )
            if document is None:
                return None
            chunks = session.scalars(
                select(RagChunkRecord)
                .where(RagChunkRecord.document_id == document_id)
                .order_by(RagChunkRecord.chunk_index)
            ).all()
            return (
                self._document_from_record(document),
                [self._chunk_from_record(chunk) for chunk in chunks],
            )

    def reindex_document(
        self,
        document_id: UUID,
        university_id: UUID,
        chunks: list[RagChunk],
    ) -> RagDocument | None:
        with self._session_factory() as session:
            document = session.scalar(
                select(RagDocumentRecord)
                .join(
                    RagLogicalDocumentRecord,
                    RagLogicalDocumentRecord.logical_document_id
                    == RagDocumentRecord.logical_document_id,
                )
                .where(
                    RagDocumentRecord.document_id == document_id,
                    RagDocumentRecord.university_id == university_id,
                    RagDocumentRecord.lifecycle_state
                    == PhysicalDocumentState.ACTIVE.value,
                    RagLogicalDocumentRecord.lifecycle_state
                    == LogicalDocumentState.ACTIVE.value,
                )
                .with_for_update()
            )
            if document is None:
                return None
            stored_chunks = session.scalars(
                select(RagChunkRecord)
                .where(RagChunkRecord.document_id == document_id)
                .order_by(RagChunkRecord.chunk_index)
            ).all()
            if {chunk.chunk_id for chunk in stored_chunks} != {
                chunk.chunk_id for chunk in chunks
            }:
                raise ValueError("Re-indexed chunks must preserve the indexed chunk IDs.")
            self._validate_chunks(
                replace(
                    self._document_from_record(document),
                    embedding_model=EMBEDDING_MODEL,
                    embedding_revision=EMBEDDING_REVISION,
                    embedding_dimensions=EMBEDDING_DIMENSIONS,
                ),
                chunks,
            )
            new_chunks = {chunk.chunk_id: chunk for chunk in chunks}
            for stored_chunk in stored_chunks:
                stored_chunk.embedding = list(
                    new_chunks[stored_chunk.chunk_id].embedding
                )
            document.embedding_model = EMBEDDING_MODEL
            document.embedding_revision = EMBEDDING_REVISION
            document.embedding_dimensions = EMBEDDING_DIMENSIONS
            document.embedding_state = EmbeddingState.EMBEDDINGS_READY.value
            session.commit()
            return self._document_from_record(document)

    def delete_document(self, document_id: UUID, university_id: UUID) -> bool:
        with self._session_factory() as session:
            logical_id = session.scalar(
                select(RagDocumentRecord.logical_document_id).where(
                    RagDocumentRecord.document_id == document_id,
                    RagDocumentRecord.university_id == university_id,
                )
            )
            if logical_id is None:
                return False
            logical = session.scalar(
                select(RagLogicalDocumentRecord)
                .where(
                    RagLogicalDocumentRecord.logical_document_id == logical_id,
                    RagLogicalDocumentRecord.university_id == university_id,
                )
                .with_for_update()
            )
            if logical is None:
                raise RagLifecycleError(
                    "Physical document has no university-owned logical document."
                )
            document = session.scalar(
                select(RagDocumentRecord)
                .where(
                    RagDocumentRecord.document_id == document_id,
                    RagDocumentRecord.university_id == university_id,
                )
                .with_for_update()
            )
            if document is None:
                return False
            if document.lifecycle_state == PhysicalDocumentState.DELETED.value:
                return True
            if document.lifecycle_state == PhysicalDocumentState.ACTIVE.value:
                logical.lifecycle_state = LogicalDocumentState.DELETED.value
            document.lifecycle_state = PhysicalDocumentState.DELETED.value
            session.execute(
                delete(RagChunkRecord).where(
                    RagChunkRecord.document_id == document_id
                )
            )
            session.commit()
            return True

    def delete_logical_document(
        self, logical_document_id: UUID, university_id: UUID
    ) -> bool:
        with self._session_factory() as session:
            logical = session.scalar(
                select(RagLogicalDocumentRecord)
                .where(
                    RagLogicalDocumentRecord.logical_document_id
                    == logical_document_id,
                    RagLogicalDocumentRecord.university_id == university_id,
                )
                .with_for_update()
            )
            if logical is None:
                return False
            logical.lifecycle_state = LogicalDocumentState.DELETED.value
            session.execute(
                update(RagDocumentRecord)
                .where(
                    RagDocumentRecord.logical_document_id == logical_document_id,
                    RagDocumentRecord.lifecycle_state
                    == PhysicalDocumentState.ACTIVE.value,
                )
                .values(lifecycle_state=PhysicalDocumentState.DELETED.value)
            )
            session.execute(
                delete(RagChunkRecord).where(
                    RagChunkRecord.document_id.in_(
                        select(RagDocumentRecord.document_id).where(
                            RagDocumentRecord.logical_document_id
                            == logical_document_id
                        )
                    )
                )
            )
            session.commit()
            return True

    def create_conversation(self, conversation: RagConversation) -> None:
        with self._session_factory() as session:
            session.add(
                RagConversationRecord(
                    conversation_id=conversation.conversation_id,
                    account_id=conversation.account_id,
                    school_id=conversation.school_id,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            )
            session.commit()

    def find_conversation(self, conversation_id: UUID) -> RagConversation | None:
        with self._session_factory() as session:
            row = session.get(RagConversationRecord, conversation_id)
            if row is None:
                return None
            return RagConversation(
                conversation_id=row.conversation_id,
                account_id=row.account_id,
                school_id=row.school_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def append_messages(self, messages: list[RagMessage]) -> None:
        if not messages:
            return
        with self._session_factory() as session:
            conversation = session.get(
                RagConversationRecord, messages[0].conversation_id
            )
            if conversation is None:
                raise ValueError("RAG conversation does not exist.")
            for message in messages:
                session.add(
                    RagMessageRecord(
                        message_id=message.message_id,
                        conversation_id=message.conversation_id,
                        position=message.position,
                        role=message.role,
                        content=message.content,
                        sources=list(message.sources),
                        created_at=message.created_at,
                    )
                )
            conversation.updated_at = messages[-1].created_at
            session.commit()

    def list_messages(
        self, conversation_id: UUID, limit: int = 20
    ) -> list[RagMessage]:
        statement = (
            select(RagMessageRecord)
            .where(RagMessageRecord.conversation_id == conversation_id)
            .order_by(RagMessageRecord.position.desc())
            .limit(limit)
        )
        messages = self._find_all(
            statement, lambda _session, row: self._message_from_record(row)
        )
        return list(reversed(messages))

    @staticmethod
    def _document_from_record(row: RagDocumentRecord) -> RagDocument:
        return RagDocument(
            document_id=row.document_id,
            university_id=row.university_id,
            title=row.title,
            file_name=row.file_name,
            content_type=row.content_type,
            content_sha256=row.content_sha256,
            uploaded_by=row.uploaded_by,
            embedding_model=row.embedding_model,
            embedding_revision=row.embedding_revision,
            embedding_dimensions=row.embedding_dimensions,
            created_at=row.created_at,
            logical_document_id=row.logical_document_id,
            version_number=row.version_number,
            lifecycle_state=PhysicalDocumentState(row.lifecycle_state),
            embedding_state=EmbeddingState(row.embedding_state),
        )

    @staticmethod
    def _chunk_from_record(row: RagChunkRecord) -> RagChunk:
        return RagChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            chunk_index=row.chunk_index,
            text=row.text,
            embedding=tuple(float(value) for value in row.embedding),
        )

    @staticmethod
    def _message_from_record(row: RagMessageRecord) -> RagMessage:
        return RagMessage(
            message_id=row.message_id,
            conversation_id=row.conversation_id,
            position=row.position,
            role=row.role,
            content=row.content,
            sources=tuple(row.sources),
            created_at=row.created_at,
        )


# ── Auth persistence helpers ──────────────────────────────────────────────────

def _account_from_record(row: AccountRecord) -> UserAccount:
    return UserAccount(
        user_id=row.account_id,
        email=row.email,
        password_hash=row.password_hash,
        role=RoleEnum(row.role),
        failed_attempts=row.failed_attempts,
        locked_until=row.locked_until,
        account_state=AccountStateEnum(row.account_state),
        school_id=row.school_id,
        university_id=row.university_id,
        creator_id=row.creator_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        university_ids={scope.university_id for scope in row.university_scopes},
    )


def _session_from_record(row: AccountSessionRecord) -> SessionEntity:
    return SessionEntity(
        session_id=row.session_id,
        account_id=row.account_id,
        token_digest=row.token_digest,
        csrf_token=row.csrf_token,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def _verification_from_record(row: VerificationRecordORM) -> VerificationRecord:
    return VerificationRecord(
        record_id=row.record_id,
        subject_account_id=row.subject_account_id,
        verifier_account_id=row.verifier_account_id,
        subject_role=RoleEnum(row.subject_role),
        evidence_reference=row.evidence_reference,
        school_scope=[UUID(s) for s in (row.school_scope or [])],
        university_id=row.university_id,
        created_at=row.created_at,
        outcome=row.outcome,
    )


class PostgresUserAccountRepository(_PostgresRepository, UserAccountRepository):
    def save(self, entity: UserAccount) -> None:
        from psycopg.errors import UniqueViolation
        from sqlalchemy.exc import IntegrityError
        from unimatch.provisioning import AccountAlreadyExistsError
        try:
            with self._session_factory() as session:
                row = session.get(AccountRecord, entity.user_id)
                if row is None:
                    row = AccountRecord(account_id=entity.user_id)
                    session.add(row)
                row.email           = entity.email
                row.password_hash   = entity.password_hash
                row.role            = entity.role.value
                row.account_state   = entity.account_state.value
                row.failed_attempts = entity.failed_attempts
                row.locked_until    = entity.locked_until
                row.school_id       = entity.school_id
                row.university_id   = entity.university_id
                row.creator_id      = entity.creator_id
                row.created_at      = entity.created_at
                row.updated_at      = entity.updated_at
                if entity.role == RoleEnum.UniversityAdmissions and entity.university_id is not None:
                    institution = session.get(UniversityInstitutionRecord, entity.university_id)
                    if institution is None:
                        now = datetime.now(timezone.utc)
                        institution = UniversityInstitutionRecord(
                            university_id=entity.university_id,
                            name=f"Legacy institution {str(entity.university_id)[:8]}",
                            abbreviation=f"LEGACY-{str(entity.university_id)[:8]}",
                            sector="Legacy",
                            status="Unverified",
                            catalog_source="Legacy invitation scope; identity not verified",
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(institution)
                        session.flush()
                    if not any(scope.university_id == entity.university_id for scope in row.university_scopes):
                        row.university_scopes.append(AccountUniversityScopeRecord(
                            university_id=entity.university_id,
                            granted_by=entity.creator_id,
                            created_at=datetime.now(timezone.utc),
                        ))
                session.commit()
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            if isinstance(orig, UniqueViolation):
                name = getattr(getattr(orig, "diag", None), "constraint_name", "") or ""
                if "single_system_admin" in name:
                    raise RuntimeError(
                        "A SystemAdmin account already exists. "
                        "Bootstrap refuses to create a second initial administrator."
                    ) from exc
                if "email" in name:
                    raise AccountAlreadyExistsError(
                        "An account with that email already exists."
                    ) from exc
            raise

    def find_by_id(self, entity_id: UUID) -> UserAccount | None:
        with self._session_factory() as session:
            row = session.get(AccountRecord, entity_id)
            return None if row is None else _account_from_record(row)

    def find_all(self) -> list[UserAccount]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AccountRecord).order_by(AccountRecord.created_at, AccountRecord.account_id)
            ).all()
            return [_account_from_record(r) for r in rows]

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(AccountRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_email(self, email: str) -> UserAccount | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(AccountRecord).where(
                    func.lower(AccountRecord.email) == email.lower()
                )
            )
            return None if row is None else _account_from_record(row)

    def find_by_role(self, role: RoleEnum) -> list[UserAccount]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AccountRecord).where(AccountRecord.role == role.value)
            ).all()
            return [_account_from_record(r) for r in rows]

    def set_account_state(self, account_id: UUID, state: AccountStateEnum) -> UserAccount:
        from unimatch.provisioning import AccountNotFoundError, ProvisioningError
        with self._session_factory() as session:
            row = session.get(AccountRecord, account_id, with_for_update=True)
            if row is None:
                raise AccountNotFoundError("Account not found.")
            allowed = (
                row.account_state == AccountStateEnum.Active.value and state == AccountStateEnum.Suspended
            ) or (
                row.account_state == AccountStateEnum.Suspended.value and state == AccountStateEnum.Active
            )
            if not allowed:
                raise ProvisioningError("Only Active accounts can be suspended and Suspended accounts reactivated.")
            row.account_state = state.value
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return _account_from_record(row)

    def set_password(self, account_id: UUID, password: str) -> UserAccount:
        from unimatch.provisioning import AccountNotFoundError
        from unimatch.auth import hash_password
        with self._session_factory() as session:
            row = session.get(AccountRecord, account_id, with_for_update=True)
            if row is None:
                raise AccountNotFoundError("Account not found.")
            row.password_hash = hash_password(password)
            row.failed_attempts = 0
            row.locked_until = None
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return _account_from_record(row)

    def bootstrap_first_school_admin(self, school_id, account_id, actor, verification_evidence_reference, evidence_reference, reason) -> UserAccount:
        from unimatch.provisioning import (
            AccountNotFoundError, AlreadyActiveError, NotVerifiedError, ProvisioningError,
        )
        from unimatch.enums import RoleEnum

        with self._session_factory() as session:
            school = session.get(SchoolRecord, school_id, with_for_update=True)
            if school is None:
                raise AccountNotFoundError("School not found.")
            if school.status != "Active":
                raise ProvisioningError("The school must be active before first-admin bootstrap.")
            if session.scalar(select(SchoolAdminBootstrapRecord).where(SchoolAdminBootstrapRecord.school_id == school_id)):
                raise ProvisioningError("First SchoolAdmin bootstrap has already been used.")
            active_count = session.scalar(
                select(func.count()).select_from(AccountRecord)
                .where(AccountRecord.school_id == school_id)
                .where(AccountRecord.role == RoleEnum.SchoolAdmin.value)
                .where(AccountRecord.account_state == AccountStateEnum.Active.value)
            ) or 0
            if active_count:
                raise AlreadyActiveError("This school already has an active SchoolAdmin.")
            row = session.get(AccountRecord, account_id, with_for_update=True)
            if row is None:
                raise AccountNotFoundError("Account not found.")
            if row.role != RoleEnum.SchoolAdmin.value or row.school_id != school_id or row.account_state != AccountStateEnum.Pending.value:
                raise ProvisioningError("Bootstrap target must be a Pending SchoolAdmin assigned to this school.")
            invitation = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
                .with_for_update()
            )
            if invitation is not None and invitation.status != "Accepted":
                raise NotVerifiedError("The invited SchoolAdmin must complete password setup before activation.")
            verified = session.execute(
                select(VerificationRecordORM)
                .where(VerificationRecordORM.subject_account_id == account_id)
                .order_by(VerificationRecordORM.created_at.desc(), VerificationRecordORM.record_id.desc())
                .limit(1)
            ).scalar_one_or_none()
            if (
                verified is None or verified.outcome != "Verified"
                or verified.subject_role != RoleEnum.SchoolAdmin.value
                or school_id not in [UUID(value) for value in (verified.school_scope or [])]
                or not verified.evidence_reference.strip()
            ):
                raise NotVerifiedError("Independent school-authority verification for this school is required.")

            now = datetime.now(timezone.utc)
            row.account_state = AccountStateEnum.Active.value
            row.updated_at = now
            event_id = uuid4()
            session.add(SchoolAdminBootstrapRecord(
                event_id=event_id, school_id=school_id, target_account_id=account_id,
                actor_id=actor.account_id,
                verification_evidence_reference=verification_evidence_reference,
                evidence_reference=evidence_reference,
                reason=reason, created_at=now,
            ))
            session.add(AuditLogRecord(
                entry_id=uuid4(), actor_id=actor.account_id,
                action="BootstrapFirstSchoolAdmin", target_type="Account",
                target_id=account_id, school_id=school_id, university_id=None,
                old_value={"account_state": AccountStateEnum.Pending.value},
                new_value={
                    "account_state": AccountStateEnum.Active.value,
                    "school_id": str(school_id), "bootstrap_event_id": str(event_id),
                    "verification_evidence_reference": verification_evidence_reference,
                    "bootstrap_evidence_reference": evidence_reference, "reason": reason,
                }, timestamp=now,
            ))
            session.commit()
            return _account_from_record(row)

    def bootstrap_first_university_admissions(
        self, university_id, account_id, actor, verification_evidence_reference,
        evidence_reference, reason, audit_repository,
    ) -> UserAccount:
        """Activate the first scoped admissions account, with durable audit and serialization.

        PostgreSQL's transaction advisory lock serializes first-account attempts across
        API workers. The existing audit table is the durable one-time marker, so no
        new schema is required.
        """
        from unimatch.provisioning import AccountNotFoundError, ProvisioningError

        with self._session_factory() as session:
            # Fixed application lock key: all first-admissions bootstrap attempts
            # serialize before checking the audit marker or account count.
            session.execute(select(func.pg_advisory_xact_lock(1431195981, 1096109128)))
            prior_bootstrap = session.scalar(
                select(AuditLogRecord.entry_id)
                .where(AuditLogRecord.action == "BootstrapFirstUniversityAdmissions")
                .where(AuditLogRecord.university_id == university_id)
                .limit(1)
            )
            if prior_bootstrap is not None:
                raise ProvisioningError("First UniversityAdmissions bootstrap has already been used for this university.")

            scoped_accounts = session.scalar(
                select(func.count()).select_from(AccountRecord)
                .where(AccountRecord.role == RoleEnum.UniversityAdmissions.value)
                .where(AccountRecord.university_id == university_id)
            ) or 0
            if scoped_accounts != 1:
                raise ProvisioningError("Bootstrap is only available to the first UniversityAdmissions account for this university.")

            row = session.get(AccountRecord, account_id, with_for_update=True)
            if row is None:
                raise AccountNotFoundError("Account not found.")
            if (
                row.role != RoleEnum.UniversityAdmissions.value
                or row.university_id != university_id
                or row.creator_id != actor.account_id
                or row.account_state != AccountStateEnum.Pending.value
            ):
                raise ProvisioningError("Bootstrap target must be a Pending UniversityAdmissions account created by this SystemAdmin for this university.")

            invitation = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
                .with_for_update()
            )
            if invitation is None or invitation.status != "Accepted":
                raise ProvisioningError("The invited UniversityAdmissions user must complete password setup before activation.")

            verification = session.scalar(
                select(VerificationRecordORM)
                .where(VerificationRecordORM.subject_account_id == account_id)
                .order_by(VerificationRecordORM.created_at.desc(), VerificationRecordORM.record_id.desc())
                .limit(1)
                .with_for_update()
            )
            if (
                verification is None
                or verification.outcome != "Verified"
                or verification.subject_role != RoleEnum.UniversityAdmissions.value
                or verification.verifier_account_id != actor.account_id
                or verification.university_id != university_id
                or len(verification.evidence_reference.strip()) < 4
            ):
                raise ProvisioningError("Independent university authority verification for this university is required.")

            now = datetime.now(timezone.utc)
            row.account_state = AccountStateEnum.Active.value
            row.updated_at = now
            session.add(AuditLogRecord(
                entry_id=uuid4(), actor_id=actor.account_id,
                action="BootstrapFirstUniversityAdmissions", target_type="Account",
                target_id=account_id, school_id=None, university_id=university_id,
                old_value={"account_state": AccountStateEnum.Pending.value},
                new_value={
                    "account_state": AccountStateEnum.Active.value,
                    "university_id": str(university_id),
                    "verification_evidence_reference": verification_evidence_reference,
                    "bootstrap_evidence_reference": evidence_reference,
                    "reason": reason,
                },
                timestamp=now,
            ))
            session.commit()
            return _account_from_record(row)

    def activate_with_lock(self, target_id: UUID, actor: AuthPrincipal) -> UserAccount:
        from unimatch.provisioning import (
            AccountNotFoundError,
            SelfActivationError,
            AlreadyActiveError,
            ProvisioningError,
            NotVerifiedError,
        )

        with self._session_factory() as session:
            # Acquire row lock — held until session.commit().
            row = session.get(AccountRecord, target_id, with_for_update=True)
            if row is None:
                raise AccountNotFoundError(f"Account {target_id} not found.")

            # Re-validate self/creator under lock.
            if actor.account_id == target_id:
                raise SelfActivationError("An account cannot activate itself.")
            if row.creator_id is not None and actor.account_id == row.creator_id:
                raise SelfActivationError(
                    "The account creator cannot activate the account they provisioned."
                )

            # Re-validate state under lock.
            if row.account_state == AccountStateEnum.Active.value:
                raise AlreadyActiveError(f"Account {target_id} is already active.")
            if row.account_state != AccountStateEnum.Pending.value:
                raise ProvisioningError(
                    f"Account {target_id} is in {row.account_state!r} state "
                    "and cannot be activated."
                )

            # Re-read latest verified record within the same transaction.
            # READ COMMITTED sees any records committed after service Phase 1.
            vr_row = session.execute(
                select(VerificationRecordORM)
                .where(VerificationRecordORM.subject_account_id == target_id)
                .order_by(
                    VerificationRecordORM.created_at.desc(),
                    VerificationRecordORM.record_id.desc(),
                )
                .limit(1)
            ).scalar_one_or_none()

            if vr_row is None or vr_row.outcome != "Verified":
                raise NotVerifiedError(
                    f"Account {target_id} has no current accepted verification record."
                )

            # University scope re-validation under lock.
            if row.role == RoleEnum.UniversityAdmissions.value:
                if vr_row.university_id is None:
                    raise NotVerifiedError(
                        "The verification record has no university scope."
                    )
                if vr_row.university_id != row.university_id:
                    raise NotVerifiedError(
                        "The verification university does not match the account's university."
                    )

            if row.role == RoleEnum.SchoolAdmin.value:
                school = session.get(SchoolRecord, row.school_id, with_for_update=True) if row.school_id else None
                if school is None or school.status != "Active":
                    raise NotVerifiedError("The SchoolAdmin's assigned school is not active.")
                if row.school_id not in [UUID(value) for value in (vr_row.school_scope or [])]:
                    raise NotVerifiedError("The verification record does not include the assigned school.")

            row.account_state = AccountStateEnum.Active.value
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return _account_from_record(row)

    def record_failed_login(self, account_id: UUID) -> bool:
        from unimatch.config import Settings
        settings = Settings.from_environment()
        with self._session_factory() as session:
            row = session.get(AccountRecord, account_id, with_for_update=True)
            if row is None:
                return False
            now = datetime.now(timezone.utc)
            if row.locked_until is not None and row.locked_until > now:
                return True
            row.failed_attempts += 1
            if row.failed_attempts >= settings.lockout_threshold:
                row.locked_until = now + settings.lockout_duration
                row.failed_attempts = 0
            row.updated_at = now
            session.commit()
            return row.locked_until is not None and row.locked_until > now

    def record_successful_login(self, account_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(AccountRecord, account_id, with_for_update=True)
            if row is None:
                return
            row.failed_attempts = 0
            row.locked_until = None
            row.updated_at = datetime.now(timezone.utc)
            session.commit()


class PostgresSessionRepository(_PostgresRepository, SessionRepository):
    def save(self, entity: SessionEntity) -> None:
        with self._session_factory() as session:
            row = session.get(AccountSessionRecord, entity.session_id)
            if row is None:
                row = AccountSessionRecord(session_id=entity.session_id)
                session.add(row)
            row.account_id   = entity.account_id
            row.token_digest = entity.token_digest
            row.csrf_token   = entity.csrf_token
            row.created_at   = entity.created_at
            row.expires_at   = entity.expires_at
            row.revoked_at   = entity.revoked_at
            session.commit()

    def find_by_id(self, entity_id: UUID) -> SessionEntity | None:
        with self._session_factory() as session:
            row = session.get(AccountSessionRecord, entity_id)
            return None if row is None else _session_from_record(row)

    def find_all(self) -> list[SessionEntity]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AccountSessionRecord).order_by(
                    AccountSessionRecord.created_at, AccountSessionRecord.session_id
                )
            ).all()
            return [_session_from_record(r) for r in rows]

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(AccountSessionRecord, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_token_digest(self, token_digest: str) -> SessionEntity | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(AccountSessionRecord).where(
                    AccountSessionRecord.token_digest == token_digest
                )
            )
            return None if row is None else _session_from_record(row)

    def find_by_account(self, account_id: UUID) -> list[SessionEntity]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AccountSessionRecord)
                .where(AccountSessionRecord.account_id == account_id)
                .order_by(AccountSessionRecord.created_at.desc())
            ).all()
            return [_session_from_record(r) for r in rows]


class PostgresVerificationRecordRepository(_PostgresRepository, VerificationRecordRepository):
    def save(self, entity: VerificationRecord) -> None:
        """Verification records are append-only. Always INSERT; never UPDATE."""
        with self._session_factory() as session:
            # Serialize records per account so timestamp ordering remains the
            # authoritative order even when the system clock has not advanced
            # between two reviews or requests arrive concurrently.
            session.get(
                AccountRecord,
                entity.subject_account_id,
                with_for_update=True,
            )
            latest_created_at = session.scalar(
                select(func.max(VerificationRecordORM.created_at)).where(
                    VerificationRecordORM.subject_account_id
                    == entity.subject_account_id
                )
            )
            if latest_created_at is not None and entity.created_at <= latest_created_at:
                entity.created_at = latest_created_at + timedelta(microseconds=1)
            row = VerificationRecordORM(
                record_id=entity.record_id,
                subject_account_id=entity.subject_account_id,
                verifier_account_id=entity.verifier_account_id,
                subject_role=entity.subject_role.value,
                evidence_reference=entity.evidence_reference,
                school_scope=[str(uid) for uid in entity.school_scope],
                university_id=entity.university_id,
                created_at=entity.created_at,
                outcome=entity.outcome,
            )
            session.add(row)
            session.commit()

    def find_by_id(self, entity_id: UUID) -> VerificationRecord | None:
        with self._session_factory() as session:
            row = session.get(VerificationRecordORM, entity_id)
            return None if row is None else _verification_from_record(row)

    def find_all(self) -> list[VerificationRecord]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(VerificationRecordORM).order_by(
                    VerificationRecordORM.created_at, VerificationRecordORM.record_id
                )
            ).all()
            return [_verification_from_record(r) for r in rows]

    def delete(self, entity_id: UUID) -> None:
        with self._session_factory() as session:
            row = session.get(VerificationRecordORM, entity_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def find_by_subject(self, account_id: UUID) -> list[VerificationRecord]:
        """Returns records ordered ascending (created_at ASC, record_id ASC).
        Service uses [-1] to get the most recent verified record."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(VerificationRecordORM)
                .where(VerificationRecordORM.subject_account_id == account_id)
                .order_by(
                    VerificationRecordORM.created_at.asc(),
                    VerificationRecordORM.record_id.asc(),
                )
            ).all()
            return [_verification_from_record(r) for r in rows]


def _school_from_record(row: SchoolRecord) -> School:
    return School(
        school_id=row.school_id, official_name=row.official_name,
        emis_number=row.emis_number, province=row.province, district=row.district,
        contact_email=row.contact_email, contact_phone=row.contact_phone,
        status=row.status, creator_id=row.creator_id,
        created_at=row.created_at, updated_at=row.updated_at,
    )


class PostgresSchoolRepository(_PostgresRepository, SchoolRepository):
    def save(self, entity: School) -> None:
        from sqlalchemy.exc import IntegrityError
        with self._session_factory() as session:
            try:
                row = session.get(SchoolRecord, entity.school_id)
                if row is None:
                    row = SchoolRecord(school_id=entity.school_id)
                    session.add(row)
                for field in (
                    "official_name", "emis_number", "province", "district",
                    "contact_email", "contact_phone", "status", "creator_id",
                    "created_at", "updated_at",
                ):
                    setattr(row, field, getattr(entity, field))
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("A school with that EMIS number or official name already exists.") from exc

    def find_by_id(self, entity_id: UUID) -> School | None:
        with self._session_factory() as session:
            row = session.get(SchoolRecord, entity_id)
            return None if row is None else _school_from_record(row)

    def find_all(self) -> list[School]:
        with self._session_factory() as session:
            rows = session.scalars(select(SchoolRecord).order_by(SchoolRecord.official_name, SchoolRecord.school_id)).all()
            return [_school_from_record(row) for row in rows]

    def delete(self, entity_id: UUID) -> None:
        raise ValueError("Schools cannot be deleted; change their status instead.")

    def find_by_emis(self, emis_number: str) -> School | None:
        with self._session_factory() as session:
            row = session.scalar(select(SchoolRecord).where(SchoolRecord.emis_number == emis_number))
            return None if row is None else _school_from_record(row)

    def set_status(self, school_id: UUID, status: str) -> School:
        from unimatch.provisioning import AccountNotFoundError
        with self._session_factory() as session:
            row = session.get(SchoolRecord, school_id, with_for_update=True)
            if row is None:
                raise AccountNotFoundError("School not found.")
            row.status = status
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return _school_from_record(row)

    def count_status(self, status: str) -> int:
        with self._session_factory() as session:
            return int(session.scalar(
                select(func.count()).select_from(SchoolRecord).where(SchoolRecord.status == status)
            ) or 0)


class PostgresAccountInvitationRepository(_PostgresRepository, AccountInvitationRepository):
    def create(self, account_id: UUID, actor_id: UUID, token_digest: str, expires_at) -> None:
        with self._session_factory() as session:
            account = session.get(AccountRecord, account_id, with_for_update=True)
            if account is None or account.account_state != AccountStateEnum.Pending.value:
                raise ValueError("Invitations can only be created for a pending account.")
            now = datetime.now(timezone.utc)
            latest = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
                .with_for_update()
            )
            if latest is not None and now <= latest.created_at:
                now = latest.created_at + timedelta(microseconds=1)
            session.add(AccountInvitationRecord(
                invitation_id=uuid4(), account_id=account_id,
                token_digest=token_digest, created_by=actor_id,
                created_at=now, expires_at=expires_at, consumed_at=None,
                status="Pending",
            ))
            session.commit()

    def consume(self, token_digest: str, password: str) -> bool:
        from unimatch.auth import hash_password
        with self._session_factory() as session:
            invitation_ref = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.token_digest == token_digest)
            )
            if invitation_ref is None:
                return False
            account = session.get(AccountRecord, invitation_ref.account_id, with_for_update=True)
            if account is None or account.account_state != AccountStateEnum.Pending.value:
                return False
            invite = session.scalar(
                select(AccountInvitationRecord)
                .where(
                    AccountInvitationRecord.invitation_id == invitation_ref.invitation_id,
                    AccountInvitationRecord.token_digest == token_digest,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            now = datetime.now(timezone.utc)
            if invite is None or invite.status != "Pending" or invite.consumed_at is not None:
                return False
            if invite.expires_at <= now:
                invite.status = "Expired"
                session.commit()
                return False
            account.password_hash = hash_password(password)
            account.failed_attempts = 0
            account.locked_until = None
            account.updated_at = now
            invite.consumed_at = now
            invite.status = "Accepted"
            session.commit()
            return True

    def is_ready(self, account_id: UUID) -> bool:
        with self._session_factory() as session:
            row = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
            )
            return row is None or row.status == "Accepted"

    def is_active(self, account_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
            )
            if row is not None and row.status == "Pending" and row.expires_at <= now:
                row.status = "Expired"
                session.commit()
                return False
            return row is not None and row.status == "Pending" and row.consumed_at is None and row.expires_at > now

    def latest_status(self, account_id: UUID) -> str | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
            )
            if row is None:
                return None
            if row.status == "Pending" and row.expires_at <= now:
                row.status = "Expired"
                session.commit()
                return "Expired"
            return row.status

    def revoke_pending(self, account_id: UUID, actor_id: UUID, reason: str, school_id: UUID | None, university_id: UUID | None = None) -> bool:
        with self._session_factory() as session:
            account = session.get(AccountRecord, account_id, with_for_update=True)
            if account is None or account.account_state != AccountStateEnum.Pending.value:
                return False
            invite = session.scalar(
                select(AccountInvitationRecord)
                .where(AccountInvitationRecord.account_id == account_id)
                .order_by(AccountInvitationRecord.created_at.desc(), AccountInvitationRecord.invitation_id.desc())
                .limit(1)
                .with_for_update()
            )
            now = datetime.now(timezone.utc)
            if invite is None or invite.status != "Pending" or invite.consumed_at is not None:
                return False
            if invite.expires_at <= now:
                invite.status = "Expired"
                session.commit()
                return False
            latest_verification = session.scalar(
                select(VerificationRecordORM)
                .where(VerificationRecordORM.subject_account_id == account_id)
                .order_by(
                    VerificationRecordORM.created_at.desc(),
                    VerificationRecordORM.record_id.desc(),
                )
                .limit(1)
            )
            if latest_verification is not None and latest_verification.outcome == "Verified":
                return False
            invite.status = "Revoked"
            is_university_admin = account.role == RoleEnum.UniversityAdmissions.value
            session.add(AuditLogRecord(
                entry_id=uuid4(), actor_id=actor_id,
                action="UniversityAdmissionsInvitationRevoked" if is_university_admin else "SchoolAdminInvitationRevoked", target_type="Account",
                target_id=account_id, school_id=school_id, university_id=university_id,
                old_value={"invitation_id": str(invite.invitation_id), "invitation_status": "Pending"},
                new_value={"invitation_id": str(invite.invitation_id), "invitation_status": "Revoked", "reason": reason},
                timestamp=now,
            ))
            session.commit()
            return True
