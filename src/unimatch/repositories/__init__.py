"""
unimatch/repositories/__init__.py
==================================
Generic repository interface and all entity-specific repository interfaces
for the UniMatch domain.

Design rationale
----------------
- A single ``Repository[T, ID]`` generic base avoids duplicate CRUD
  signatures across every entity.
- Each entity-specific interface can add domain query methods (e.g.
  ``find_by_email``) without polluting the generic contract.
- All methods use Python's built-in ``Optional`` / ``list`` types so the
  interfaces remain framework-free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar
from uuid import UUID

T = TypeVar("T")
ID = TypeVar("ID")


class Repository(ABC, Generic[T, ID]):
    """Generic CRUD contract for all UniMatch repositories."""

    @abstractmethod
    def save(self, entity: T) -> None:
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, entity_id: ID) -> Optional[T]:
        raise NotImplementedError

    @abstractmethod
    def find_all(self) -> List[T]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: ID) -> None:
        raise NotImplementedError


class UserAccountRepository(Repository["UserAccount", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_email(self, email: str) -> "Optional[UserAccount]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_role(self, role: "RoleEnum") -> "List[UserAccount]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def set_account_state(self, account_id: UUID, state: "AccountStateEnum") -> "UserAccount":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def set_password(self, account_id: UUID, password: str) -> "UserAccount":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def bootstrap_first_school_admin(self, school_id: UUID, account_id: UUID, actor: "AuthPrincipal", verification_evidence_reference: str, evidence_reference: str, reason: str) -> "UserAccount":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def bootstrap_first_university_admissions(self, university_id: UUID, account_id: UUID, actor: "AuthPrincipal", verification_evidence_reference: str, evidence_reference: str, reason: str, audit_repository: AuditLogRepository) -> "UserAccount":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def activate_with_lock(self, target_id: UUID, actor: "AuthPrincipal") -> "UserAccount":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def record_failed_login(self, account_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    def record_successful_login(self, account_id: UUID) -> None:
        raise NotImplementedError


class SchoolRepository(Repository["School", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_emis(self, emis_number: str) -> "Optional[School]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def set_status(self, school_id: UUID, status: str) -> "School":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def count_status(self, status: str) -> int:
        raise NotImplementedError


class AccountInvitationRepository(ABC):
    @abstractmethod
    def create(self, account_id: UUID, actor_id: UUID, token_digest: str, expires_at) -> None:
        raise NotImplementedError

    @abstractmethod
    def consume(self, token_digest: str, password: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_ready(self, account_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_active(self, account_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    def latest_status(self, account_id: UUID) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def revoke_pending(
        self, account_id: UUID, actor_id: UUID, reason: str, school_id: UUID | None,
        university_id: UUID | None = None,
    ) -> bool:
        """Atomically revoke the latest invitation and append its audit event."""
        raise NotImplementedError

class SessionRepository(Repository["Session", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_token_digest(self, token_digest: str) -> "Optional[Session]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_account(self, account_id: UUID) -> "List[Session]":  # type: ignore[name-defined]
        raise NotImplementedError


class VerificationRecordRepository(Repository["VerificationRecord", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_subject(self, account_id: UUID) -> "List[VerificationRecord]":  # type: ignore[name-defined]
        raise NotImplementedError


class LearnerProfileRepository(Repository["LearnerProfile", UUID], ABC):  # type: ignore[type-arg]
    def save_many(self, entities: List["LearnerProfile"]) -> None:  # type: ignore[name-defined]
        """Persist several profiles; implementations may provide atomicity."""
        for entity in entities:
            self.save(entity)

    @abstractmethod
    def find_by_counselor(self, counselor_id: UUID) -> "List[LearnerProfile]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_school(self, school_id: UUID) -> "List[LearnerProfile]":  # type: ignore[name-defined]
        raise NotImplementedError


class UniversityProgrammeRepository(Repository["UniversityProgramme", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_university(self, university_id: UUID) -> "List[UniversityProgramme]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_published(self) -> "List[UniversityProgramme]":  # type: ignore[name-defined]
        raise NotImplementedError


class ApplicationRepository(Repository["Application", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[Application]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_programme(self, programme_id: UUID) -> "List[Application]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_status(self, status: "ApplicationStatusEnum") -> "List[Application]":  # type: ignore[name-defined]
        raise NotImplementedError


class DocumentRepository(Repository["Document", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[Document]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_application(self, application_id: UUID) -> "List[Document]":  # type: ignore[name-defined]
        raise NotImplementedError


class MarkRepository(Repository["Mark", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[Mark]":  # type: ignore[name-defined]
        raise NotImplementedError


class PaymentTransactionRepository(Repository["PaymentTransaction", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_application(self, application_id: UUID) -> "List[PaymentTransaction]":  # type: ignore[name-defined]
        raise NotImplementedError


class NotificationRepository(Repository["Notification", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_recipient(self, recipient_id: UUID) -> "List[Notification]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_unread(self, recipient_id: UUID) -> "List[Notification]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_event_key(self, event_key: str) -> "Optional[Notification]":  # type: ignore[name-defined]
        raise NotImplementedError


class AuditLogRepository(Repository["AuditLogEntry", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_actor(self, actor_id: UUID) -> "List[AuditLogEntry]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_target(self, target_id: UUID) -> "List[AuditLogEntry]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_school(self, school_id: UUID) -> "List[AuditLogEntry]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_university(self, university_id: UUID) -> "List[AuditLogEntry]":  # type: ignore[name-defined]
        raise NotImplementedError


class GuidanceSessionRepository(Repository["GuidanceSession", UUID], ABC):  # type: ignore[type-arg]
    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[GuidanceSession]":  # type: ignore[name-defined]
        raise NotImplementedError

    @abstractmethod
    def find_by_school(self, school_id: UUID) -> "List[GuidanceSession]":  # type: ignore[name-defined]
        raise NotImplementedError


class ScoringRuleRepository(Repository["ScoringRule", UUID], ABC):  # type: ignore[type-arg]
    """Repository for per-university ScoringRule objects (REQ-002).

    One rule per university_id. find_by_university returns None when no
    university-specific rule has been registered; callers should fall back
    to NSC_DEFAULT_SCORING_RULE in that case.
    """

    @abstractmethod
    def find_by_university(self, university_id: UUID) -> "Optional[ScoringRule]":  # type: ignore[name-defined]
        """Return the ScoringRule for the given university, or None."""
        raise NotImplementedError


__all__ = [
    "Repository",
    "UserAccountRepository",
    "SessionRepository",
    "VerificationRecordRepository",
    "LearnerProfileRepository",
    "UniversityProgrammeRepository",
    "ApplicationRepository",
    "DocumentRepository",
    "MarkRepository",
    "PaymentTransactionRepository",
    "NotificationRepository",
    "AuditLogRepository",
    "GuidanceSessionRepository",
    "ScoringRuleRepository",
]
