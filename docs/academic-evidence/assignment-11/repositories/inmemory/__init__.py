"""
repositories/inmemory/__init__.py
==================================
HashMap-backed in-memory implementations of every UniMatch repository
interface.

Design notes
------------
- Each class stores entities in a plain ``dict[UUID, Entity]`` — the
  Python equivalent of a Java ``HashMap``.
- All ``save`` calls are upserts (create **or** update).
- ``delete`` is idempotent: deleting a non-existent key is a no-op.
- These implementations carry **zero** I/O dependencies, making them
  ideal for fast unit tests and local development.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from unimatch.entities import (
    Application,
    AuditLogEntry,
    Document,
    LearnerProfile,
    Mark,
    Notification,
    PaymentTransaction,
    UniversityProgramme,
    UserAccount,
)
from unimatch.enums import ApplicationStatusEnum, ProgrammeStatusEnum, RoleEnum

from repositories import (
    ApplicationRepository,
    AuditLogRepository,
    DocumentRepository,
    LearnerProfileRepository,
    MarkRepository,
    NotificationRepository,
    PaymentTransactionRepository,
    UniversityProgrammeRepository,
    UserAccountRepository,
)


# ──────────────────────────────────────────────────────────────────────────────
# UserAccount
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryUserAccountRepository(UserAccountRepository):
    """Stores :class:`UserAccount` objects keyed by ``user_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, UserAccount] = {}

    # ── Generic CRUD ──────────────────────────────────────────────────────────

    def save(self, entity: UserAccount) -> None:
        self._store[entity.user_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[UserAccount]:
        return self._store.get(entity_id)

    def find_all(self) -> List[UserAccount]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    # ── Domain queries ────────────────────────────────────────────────────────

    def find_by_email(self, email: str) -> Optional[UserAccount]:
        for account in self._store.values():
            if account.email == email:
                return account
        return None

    def find_by_role(self, role: RoleEnum) -> List[UserAccount]:
        return [a for a in self._store.values() if a.role == role]


# ──────────────────────────────────────────────────────────────────────────────
# LearnerProfile
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryLearnerProfileRepository(LearnerProfileRepository):
    """Stores :class:`LearnerProfile` objects keyed by ``learner_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, LearnerProfile] = {}

    def save(self, entity: LearnerProfile) -> None:
        self._store[entity.learner_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[LearnerProfile]:
        return self._store.get(entity_id)

    def find_all(self) -> List[LearnerProfile]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_counselor(self, counselor_id: UUID) -> List[LearnerProfile]:
        return [p for p in self._store.values() if p.counselor_id == counselor_id]

    def find_by_school(self, school_id: UUID) -> List[LearnerProfile]:
        return [p for p in self._store.values() if p.school_id == school_id]


# ──────────────────────────────────────────────────────────────────────────────
# UniversityProgramme
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryUniversityProgrammeRepository(UniversityProgrammeRepository):
    """Stores :class:`UniversityProgramme` objects keyed by ``programme_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, UniversityProgramme] = {}

    def save(self, entity: UniversityProgramme) -> None:
        self._store[entity.programme_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[UniversityProgramme]:
        return self._store.get(entity_id)

    def find_all(self) -> List[UniversityProgramme]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_university(self, university_id: UUID) -> List[UniversityProgramme]:
        return [p for p in self._store.values() if p.university_id == university_id]

    def find_published(self) -> List[UniversityProgramme]:
        return [p for p in self._store.values() if p.status == ProgrammeStatusEnum.Published]


# ──────────────────────────────────────────────────────────────────────────────
# Application
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryApplicationRepository(ApplicationRepository):
    """Stores :class:`Application` objects keyed by ``application_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, Application] = {}

    def save(self, entity: Application) -> None:
        self._store[entity.application_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[Application]:
        return self._store.get(entity_id)

    def find_all(self) -> List[Application]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_learner(self, learner_id: UUID) -> List[Application]:
        return [a for a in self._store.values() if a.learner_id == learner_id]

    def find_by_programme(self, programme_id: UUID) -> List[Application]:
        return [a for a in self._store.values() if a.programme_id == programme_id]

    def find_by_status(self, status: ApplicationStatusEnum) -> List[Application]:
        return [a for a in self._store.values() if a.status == status]


# ──────────────────────────────────────────────────────────────────────────────
# Document
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryDocumentRepository(DocumentRepository):
    """Stores :class:`Document` objects keyed by ``document_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, Document] = {}

    def save(self, entity: Document) -> None:
        self._store[entity.document_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[Document]:
        return self._store.get(entity_id)

    def find_all(self) -> List[Document]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_learner(self, learner_id: UUID) -> List[Document]:
        return [d for d in self._store.values() if d.learner_id == learner_id]

    def find_by_application(self, application_id: UUID) -> List[Document]:
        return [d for d in self._store.values() if d.application_id == application_id]


# ──────────────────────────────────────────────────────────────────────────────
# Mark
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryMarkRepository(MarkRepository):
    """Stores :class:`Mark` objects keyed by ``mark_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, Mark] = {}

    def save(self, entity: Mark) -> None:
        self._store[entity.mark_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[Mark]:
        return self._store.get(entity_id)

    def find_all(self) -> List[Mark]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_learner(self, learner_id: UUID) -> List[Mark]:
        return [m for m in self._store.values() if m.learner_id == learner_id]


# ──────────────────────────────────────────────────────────────────────────────
# PaymentTransaction
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryPaymentTransactionRepository(PaymentTransactionRepository):
    """Stores :class:`PaymentTransaction` objects keyed by ``transaction_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, PaymentTransaction] = {}

    def save(self, entity: PaymentTransaction) -> None:
        self._store[entity.transaction_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[PaymentTransaction]:
        return self._store.get(entity_id)

    def find_all(self) -> List[PaymentTransaction]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_application(self, application_id: UUID) -> List[PaymentTransaction]:
        return [t for t in self._store.values() if t.application_id == application_id]


# ──────────────────────────────────────────────────────────────────────────────
# Notification
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryNotificationRepository(NotificationRepository):
    """Stores :class:`Notification` objects keyed by ``notification_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, Notification] = {}

    def save(self, entity: Notification) -> None:
        self._store[entity.notification_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[Notification]:
        return self._store.get(entity_id)

    def find_all(self) -> List[Notification]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_recipient(self, recipient_id: UUID) -> List[Notification]:
        return [n for n in self._store.values() if n.recipient_id == recipient_id]

    def find_unread(self, recipient_id: UUID) -> List[Notification]:
        return [
            n for n in self._store.values()
            if n.recipient_id == recipient_id and n.status not in ("Read", "Failed")
        ]


# ──────────────────────────────────────────────────────────────────────────────
# AuditLog
# ──────────────────────────────────────────────────────────────────────────────
class InMemoryAuditLogRepository(AuditLogRepository):
    """Stores :class:`AuditLogEntry` objects keyed by ``entry_id``."""

    def __init__(self) -> None:
        self._store: dict[UUID, AuditLogEntry] = {}

    def save(self, entity: AuditLogEntry) -> None:
        self._store[entity.entry_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[AuditLogEntry]:
        return self._store.get(entity_id)

    def find_all(self) -> List[AuditLogEntry]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_actor(self, actor_id: UUID) -> List[AuditLogEntry]:
        return [e for e in self._store.values() if e.actor_id == actor_id]

    def find_by_target(self, target_id: UUID) -> List[AuditLogEntry]:
        return [e for e in self._store.values() if e.target_id == target_id]


__all__ = [
    "InMemoryUserAccountRepository",
    "InMemoryLearnerProfileRepository",
    "InMemoryUniversityProgrammeRepository",
    "InMemoryApplicationRepository",
    "InMemoryDocumentRepository",
    "InMemoryMarkRepository",
    "InMemoryPaymentTransactionRepository",
    "InMemoryNotificationRepository",
    "InMemoryAuditLogRepository",
]
