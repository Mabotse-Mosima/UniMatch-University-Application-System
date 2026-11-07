"""
Unit tests for application_services — verifies Dependency Injection wiring:
services accept repository interfaces and delegate without knowing the backend.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from application_services import ApplicationService, UserAccountService
from factories import RepositoryFactory
from unimatch.entities import Application, UserAccount
from unimatch.enums import ApplicationStatusEnum, RoleEnum

from repositories.inmemory import InMemoryApplicationRepository, InMemoryUserAccountRepository


class TestApplicationServiceDI:
    def test_accepts_in_memory_repository(self) -> None:
        repo = InMemoryApplicationRepository()
        service = ApplicationService(applications=repo)
        app = Application(
            application_id=uuid4(),
            learner_id=uuid4(),
            programme_id=uuid4(),
            status=ApplicationStatusEnum.Draft,
            payment_reference="",
            fee_amount=Decimal("0"),
            submission_timestamp=None,
            acknowledgement_reference="",
        )
        service.save_application(app)
        assert service.get_application(app.application_id) is app
        service.remove_application(app.application_id)
        assert service.get_application(app.application_id) is None

    def test_factory_created_repo_injected_into_service(self) -> None:
        repo = RepositoryFactory.create_application_repo("MEMORY")
        service = ApplicationService(applications=repo)
        app = Application(
            application_id=uuid4(),
            learner_id=uuid4(),
            programme_id=uuid4(),
            status=ApplicationStatusEnum.Draft,
            payment_reference="",
            fee_amount=Decimal("100"),
            submission_timestamp=None,
            acknowledgement_reference="",
        )
        service.save_application(app)
        assert app in service.list_for_learner(app.learner_id)
        assert app in service.list_all_applications()


class TestUserAccountServiceDI:
    def test_delegates_to_repository(self) -> None:
        repo = InMemoryUserAccountRepository()
        service = UserAccountService(accounts=repo)
        user = UserAccount(
            user_id=uuid4(),
            email="di@example.com",
            password_hash="x",
            role=RoleEnum.Learner,
        )
        service.save_account(user)
        assert service.find_by_email("di@example.com") is user
        assert service.get_account(user.user_id) is user
        learners = service.list_by_role(RoleEnum.Learner)
        assert user in learners
        service.remove_account(user.user_id)
        assert service.get_account(user.user_id) is None
