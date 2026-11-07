"""
repositories/__init__.py
========================
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

# ──────────────────────────────────────────────────────────────────────────────
# Type variables
# ──────────────────────────────────────────────────────────────────────────────
T = TypeVar("T")
ID = TypeVar("ID")


# ──────────────────────────────────────────────────────────────────────────────
# Generic base interface
# ──────────────────────────────────────────────────────────────────────────────
class Repository(ABC, Generic[T, ID]):
    """Generic CRUD contract for all UniMatch repositories.

    Type parameters
    ~~~~~~~~~~~~~~~
    T  – the domain entity managed by this repository.
    ID – the type of the entity's primary identifier (typically ``UUID``).
    """

    @abstractmethod
    def save(self, entity: T) -> None:
        """Persist *entity*.  Creates a new record or overwrites an existing one."""
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, entity_id: ID) -> Optional[T]:
        """Return the entity with *entity_id*, or ``None`` if it does not exist."""
        raise NotImplementedError

    @abstractmethod
    def find_all(self) -> List[T]:
        """Return every entity currently held in the store."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: ID) -> None:
        """Remove the entity identified by *entity_id*.

        Silently succeeds if the entity does not exist (idempotent delete).
        """
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────────────
# Entity-specific interfaces (extend Repository with domain queries)
# ──────────────────────────────────────────────────────────────────────────────

class UserAccountRepository(Repository["UserAccount", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.UserAccount`."""

    @abstractmethod
    def find_by_email(self, email: str) -> "Optional[UserAccount]":  # type: ignore[name-defined]
        """Look up an account by its unique e-mail address."""
        raise NotImplementedError

    @abstractmethod
    def find_by_role(self, role: "RoleEnum") -> "List[UserAccount]":  # type: ignore[name-defined]
        """Return every account that holds the specified *role*."""
        raise NotImplementedError


class LearnerProfileRepository(Repository["LearnerProfile", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.LearnerProfile`."""

    @abstractmethod
    def find_by_counselor(self, counselor_id: UUID) -> "List[LearnerProfile]":  # type: ignore[name-defined]
        """Return every profile assigned to *counselor_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_by_school(self, school_id: UUID) -> "List[LearnerProfile]":  # type: ignore[name-defined]
        """Return every profile belonging to *school_id*."""
        raise NotImplementedError


class UniversityProgrammeRepository(Repository["UniversityProgramme", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.UniversityProgramme`."""

    @abstractmethod
    def find_by_university(self, university_id: UUID) -> "List[UniversityProgramme]":  # type: ignore[name-defined]
        """Return all programmes offered by *university_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_published(self) -> "List[UniversityProgramme]":  # type: ignore[name-defined]
        """Return every programme whose status is *Published*."""
        raise NotImplementedError


class ApplicationRepository(Repository["Application", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.Application`."""

    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[Application]":  # type: ignore[name-defined]
        """Return all applications submitted by *learner_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_by_programme(self, programme_id: UUID) -> "List[Application]":  # type: ignore[name-defined]
        """Return all applications targeting *programme_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_by_status(self, status: "ApplicationStatusEnum") -> "List[Application]":  # type: ignore[name-defined]
        """Return all applications in the specified *status*."""
        raise NotImplementedError


class DocumentRepository(Repository["Document", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.Document`."""

    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[Document]":  # type: ignore[name-defined]
        """Return all documents uploaded by *learner_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_by_application(self, application_id: UUID) -> "List[Document]":  # type: ignore[name-defined]
        """Return every document linked to *application_id*."""
        raise NotImplementedError


class MarkRepository(Repository["Mark", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.Mark`."""

    @abstractmethod
    def find_by_learner(self, learner_id: UUID) -> "List[Mark]":  # type: ignore[name-defined]
        """Return all mark records belonging to *learner_id*."""
        raise NotImplementedError


class PaymentTransactionRepository(Repository["PaymentTransaction", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.PaymentTransaction`."""

    @abstractmethod
    def find_by_application(self, application_id: UUID) -> "List[PaymentTransaction]":  # type: ignore[name-defined]
        """Return every payment transaction for *application_id*."""
        raise NotImplementedError


class NotificationRepository(Repository["Notification", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.Notification`."""

    @abstractmethod
    def find_by_recipient(self, recipient_id: UUID) -> "List[Notification]":  # type: ignore[name-defined]
        """Return all notifications addressed to *recipient_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_unread(self, recipient_id: UUID) -> "List[Notification]":  # type: ignore[name-defined]
        """Return notifications that have not yet been marked as *Read*."""
        raise NotImplementedError


class AuditLogRepository(Repository["AuditLogEntry", UUID], ABC):  # type: ignore[type-arg]
    """Repository for :class:`~unimatch.entities.AuditLogEntry`."""

    @abstractmethod
    def find_by_actor(self, actor_id: UUID) -> "List[AuditLogEntry]":  # type: ignore[name-defined]
        """Return every log entry recorded for *actor_id*."""
        raise NotImplementedError

    @abstractmethod
    def find_by_target(self, target_id: UUID) -> "List[AuditLogEntry]":  # type: ignore[name-defined]
        """Return every log entry that targets *target_id*."""
        raise NotImplementedError


__all__ = [
    "Repository",
    "UserAccountRepository",
    "LearnerProfileRepository",
    "UniversityProgrammeRepository",
    "ApplicationRepository",
    "DocumentRepository",
    "MarkRepository",
    "PaymentTransactionRepository",
    "NotificationRepository",
    "AuditLogRepository",
]
