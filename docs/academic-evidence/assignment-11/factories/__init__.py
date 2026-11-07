"""
factories/__init__.py
======================
``RepositoryFactory`` — a centralised factory that returns the correct
repository implementation for a requested storage backend.

Design choice: Factory Pattern (not Dependency Injection)
---------------------------------------------------------
The assignment offers two options for the abstraction mechanism:

* **Factory Pattern** – a static factory method resolves the concrete
  implementation from a string/enum key.
* **Dependency Injection** – a DI container wires implementations at
  startup and injects them into services.

We chose the **Factory Pattern** for the following reasons:

1. **Zero external dependencies** – No DI framework (e.g. ``injector``,
   ``dependency-injector``) is required, keeping the project lightweight.
2. **Explicit, readable configuration** – Storage backend selection is a
   single call ``RepositoryFactory.create_user_repo("MEMORY")``, readable
   without knowledge of a DI container's DSL.
3. **Consistent with Assignment 10** – The creational patterns assignment
   already established a ``SimpleFactory`` / ``FactoryMethod`` approach in
   the codebase; this factory extends the same idiom.
4. **Easy to extend** – Adding a new backend (e.g. ``"REDIS"``) requires
   only one new branch inside the factory, with no changes to any service
   or test that calls the factory.

How to swap backends
--------------------
Replace ``"MEMORY"`` with ``"FILE"`` or ``"DATABASE"`` in any service
constructor or test fixture:

    repo = RepositoryFactory.create_application_repo("MEMORY")
    service = ApplicationService(repo)

Later, when a PostgreSQL driver is available:

    repo = RepositoryFactory.create_application_repo("DATABASE", dsn="postgresql://...")
    service = ApplicationService(repo)

The ``ApplicationService`` is completely unaware of the change.
"""

from __future__ import annotations

from typing import Literal

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
from repositories.inmemory import (
    InMemoryApplicationRepository,
    InMemoryAuditLogRepository,
    InMemoryDocumentRepository,
    InMemoryLearnerProfileRepository,
    InMemoryMarkRepository,
    InMemoryNotificationRepository,
    InMemoryPaymentTransactionRepository,
    InMemoryUniversityProgrammeRepository,
    InMemoryUserAccountRepository,
)
from repositories.stubs import (
    DatabaseApplicationRepository,
    DatabaseUserAccountRepository,
    FileSystemApplicationRepository,
    FileSystemUserAccountRepository,
)

StorageType = Literal["MEMORY", "FILE", "DATABASE"]

_UNSUPPORTED_MSG = (
    "Storage type '{backend}' is not yet supported for {repo}. "
    "Implement the corresponding class in repositories/stubs/ first."
)


class RepositoryFactory:
    """Static factory that resolves the correct repository implementation.

    All ``create_*`` methods accept a *storage_type* keyword and optional
    keyword arguments forwarded to the concrete constructor (e.g.
    ``file_path`` for filesystem repositories or ``dsn`` for database ones).
    """

    # ── UserAccount ───────────────────────────────────────────────────────────

    @staticmethod
    def create_user_repo(
        storage_type: StorageType = "MEMORY",
        *,
        file_path: str = "data/users.json",
        dsn: str = "",
    ) -> UserAccountRepository:
        if storage_type == "MEMORY":
            return InMemoryUserAccountRepository()
        if storage_type == "FILE":
            return FileSystemUserAccountRepository(file_path)
        if storage_type == "DATABASE":
            return DatabaseUserAccountRepository(dsn)
        raise ValueError(f"Unknown storage type: '{storage_type}'")

    # ── LearnerProfile ────────────────────────────────────────────────────────

    @staticmethod
    def create_learner_profile_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> LearnerProfileRepository:
        if storage_type == "MEMORY":
            return InMemoryLearnerProfileRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="LearnerProfileRepository")
        )

    # ── UniversityProgramme ───────────────────────────────────────────────────

    @staticmethod
    def create_programme_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> UniversityProgrammeRepository:
        if storage_type == "MEMORY":
            return InMemoryUniversityProgrammeRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="UniversityProgrammeRepository")
        )

    # ── Application ───────────────────────────────────────────────────────────

    @staticmethod
    def create_application_repo(
        storage_type: StorageType = "MEMORY",
        *,
        file_path: str = "data/applications.json",
        dsn: str = "",
    ) -> ApplicationRepository:
        if storage_type == "MEMORY":
            return InMemoryApplicationRepository()
        if storage_type == "FILE":
            return FileSystemApplicationRepository(file_path)
        if storage_type == "DATABASE":
            return DatabaseApplicationRepository(dsn)
        raise ValueError(f"Unknown storage type: '{storage_type}'")

    # ── Document ──────────────────────────────────────────────────────────────

    @staticmethod
    def create_document_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> DocumentRepository:
        if storage_type == "MEMORY":
            return InMemoryDocumentRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="DocumentRepository")
        )

    # ── Mark ──────────────────────────────────────────────────────────────────

    @staticmethod
    def create_mark_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> MarkRepository:
        if storage_type == "MEMORY":
            return InMemoryMarkRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="MarkRepository")
        )

    # ── PaymentTransaction ────────────────────────────────────────────────────

    @staticmethod
    def create_payment_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> PaymentTransactionRepository:
        if storage_type == "MEMORY":
            return InMemoryPaymentTransactionRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="PaymentTransactionRepository")
        )

    # ── Notification ──────────────────────────────────────────────────────────

    @staticmethod
    def create_notification_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> NotificationRepository:
        if storage_type == "MEMORY":
            return InMemoryNotificationRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="NotificationRepository")
        )

    # ── AuditLog ──────────────────────────────────────────────────────────────

    @staticmethod
    def create_audit_log_repo(
        storage_type: StorageType = "MEMORY",
        **_kwargs: object,
    ) -> AuditLogRepository:
        if storage_type == "MEMORY":
            return InMemoryAuditLogRepository()
        raise ValueError(
            _UNSUPPORTED_MSG.format(backend=storage_type, repo="AuditLogRepository")
        )


__all__ = ["RepositoryFactory"]
