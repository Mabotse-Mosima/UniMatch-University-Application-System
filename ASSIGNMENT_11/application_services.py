"""
application_services.py
=========================
Thin application services that depend on repository **interfaces** only.

This module demonstrates **Dependency Injection (DI)**: callers construct a
service with any ``ApplicationRepository`` / ``UserAccountRepository``
implementation (in-memory, file, database, …).  **Which** concrete class to
instantiate is a separate concern — typically resolved via
:class:`~factories.RepositoryFactory` at the composition root (``main``, tests,
or a future DI container).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from repositories import ApplicationRepository, UserAccountRepository
from unimatch.entities import Application, UserAccount
from unimatch.enums import RoleEnum


@dataclass
class ApplicationService:
    """Use-case façade over :class:`~repositories.ApplicationRepository`."""

    applications: ApplicationRepository

    def save_application(self, application: Application) -> None:
        self.applications.save(application)

    def get_application(self, application_id: UUID) -> Optional[Application]:
        return self.applications.find_by_id(application_id)

    def list_all_applications(self) -> List[Application]:
        return self.applications.find_all()

    def list_for_learner(self, learner_id: UUID) -> List[Application]:
        return self.applications.find_by_learner(learner_id)

    def remove_application(self, application_id: UUID) -> None:
        self.applications.delete(application_id)


@dataclass
class UserAccountService:
    """Use-case façade over :class:`~repositories.UserAccountRepository`."""

    accounts: UserAccountRepository

    def save_account(self, account: UserAccount) -> None:
        self.accounts.save(account)

    def get_account(self, user_id: UUID) -> Optional[UserAccount]:
        return self.accounts.find_by_id(user_id)

    def find_by_email(self, email: str) -> Optional[UserAccount]:
        return self.accounts.find_by_email(email)

    def list_by_role(self, role: RoleEnum) -> List[UserAccount]:
        return self.accounts.find_by_role(role)

    def remove_account(self, user_id: UUID) -> None:
        self.accounts.delete(user_id)


__all__ = ["ApplicationService", "UserAccountService"]
