"""
tests/test_repositories.py
===========================
Unit tests for the UniMatch repository layer (Assignment 11).

Coverage
--------
- Generic CRUD: save, find_by_id, find_all, delete
- Domain queries: find_by_email, find_by_role, find_by_learner, etc.
- Edge cases: missing keys, idempotent deletes, update/overwrite semantics
- RepositoryFactory: correct types returned for MEMORY backend;
  ValueError raised for unknown backend
- Factory swapping: verify two factory calls return independent instances
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

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
from unimatch.enums import (
    ApplicationStatusEnum,
    EligibilityEnum,
    PaymentStatusEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
    RoleEnum,
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
from factories import RepositoryFactory


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

def _user(role: RoleEnum = RoleEnum.Learner, email: str = "test@example.com") -> UserAccount:
    return UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash="hashed",
        role=role,
    )


def _profile(counselor_id: None | object = None, school_id: None | object = None) -> LearnerProfile:
    return LearnerProfile(
        learner_id=uuid4(),
        full_name="Test Learner",
        school_id_number="SCH-001",
        grade=12,
        status=ProfileStatusEnum.Active,
        counselor_id=counselor_id or uuid4(),
        school_id=school_id or uuid4(),
    )


def _programme(university_id: None | object = None, status: ProgrammeStatusEnum = ProgrammeStatusEnum.Published) -> UniversityProgramme:
    return UniversityProgramme(
        programme_id=uuid4(),
        university_id=university_id or uuid4(),
        name="BSc Computer Science",
        faculty="Science",
        minimum_aps=28,
        application_deadline=date.today() + timedelta(days=30),
        application_fee=Decimal("150.00"),
        required_documents=["ID", "Transcript"],
        status=status,
        published_by=uuid4(),
    )


def _application(learner_id: None | object = None, programme_id: None | object = None) -> Application:
    return Application(
        application_id=uuid4(),
        learner_id=learner_id or uuid4(),
        programme_id=programme_id or uuid4(),
        status=ApplicationStatusEnum.Draft,
        payment_reference="",
        fee_amount=Decimal("150.00"),
        submission_timestamp=None,
        acknowledgement_reference="",
    )


def _document(learner_id: None | object = None, application_id: None | object = None) -> Document:
    return Document(
        document_id=uuid4(),
        learner_id=learner_id or uuid4(),
        application_id=application_id,
        document_type="ID",
        filename="id.pdf",
        storage_path="/tmp/id.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        uploaded_by=uuid4(),
        virus_scan_status="Clean",
        status="Uploaded",
    )


def _mark(learner_id: None | object = None) -> Mark:
    return Mark(
        mark_id=uuid4(),
        learner_id=learner_id or uuid4(),
        subject_name="Mathematics",
        score=75,
        exam_type="NSC",
        academic_year=2025,
    )


def _payment(application_id: None | object = None) -> PaymentTransaction:
    return PaymentTransaction(
        transaction_id=uuid4(),
        application_id=application_id or uuid4(),
        status=PaymentStatusEnum.Initiated,
        payment_reference="REF-XYZ",
        amount=Decimal("150.00"),
    )


def _notification(recipient_id: None | object = None, status: str = "Pending") -> Notification:
    n = Notification(
        notification_id=uuid4(),
        recipient_id=recipient_id or uuid4(),
        type="ApplicationUpdate",
        status=status,
        message="Your application has been updated.",
    )
    return n


def _audit(actor_id: None | object = None, target_id: None | object = None) -> AuditLogEntry:
    return AuditLogEntry.create(
        actor=actor_id or uuid4(),
        action="UPDATE",
        target_type="Application",
        target_id=target_id or uuid4(),
        old="Draft",
        new="Submitted",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. UserAccount Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryUserAccountRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryUserAccountRepository()

    def test_save_and_find_by_id(self) -> None:
        user = _user()
        self.repo.save(user)
        result = self.repo.find_by_id(user.user_id)
        assert result is user

    def test_find_by_id_returns_none_when_missing(self) -> None:
        assert self.repo.find_by_id(uuid4()) is None

    def test_find_all_returns_all_saved(self) -> None:
        u1, u2 = _user(email="a@x.com"), _user(email="b@x.com")
        self.repo.save(u1)
        self.repo.save(u2)
        assert len(self.repo.find_all()) == 2

    def test_find_all_empty_store(self) -> None:
        assert self.repo.find_all() == []

    def test_save_overwrites_existing_entity(self) -> None:
        user = _user()
        self.repo.save(user)
        user.email = "updated@x.com"
        self.repo.save(user)
        fetched = self.repo.find_by_id(user.user_id)
        assert fetched is not None
        assert fetched.email == "updated@x.com"
        assert len(self.repo.find_all()) == 1  # no duplicate

    def test_delete_removes_entity(self) -> None:
        user = _user()
        self.repo.save(user)
        self.repo.delete(user.user_id)
        assert self.repo.find_by_id(user.user_id) is None

    def test_delete_nonexistent_is_idempotent(self) -> None:
        self.repo.delete(uuid4())  # must not raise

    def test_find_by_email(self) -> None:
        user = _user(email="unique@test.com")
        self.repo.save(user)
        assert self.repo.find_by_email("unique@test.com") is user

    def test_find_by_email_not_found(self) -> None:
        assert self.repo.find_by_email("nobody@nowhere.com") is None

    def test_find_by_role_filters_correctly(self) -> None:
        learner = _user(role=RoleEnum.Learner, email="l@x.com")
        teacher = _user(role=RoleEnum.Teacher, email="t@x.com")
        self.repo.save(learner)
        self.repo.save(teacher)
        results = self.repo.find_by_role(RoleEnum.Learner)
        assert learner in results
        assert teacher not in results

    def test_find_by_role_returns_empty_when_no_match(self) -> None:
        self.repo.save(_user(role=RoleEnum.Learner, email="l@x.com"))
        assert self.repo.find_by_role(RoleEnum.DoEOfficial) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LearnerProfile Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryLearnerProfileRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryLearnerProfileRepository()

    def test_save_and_find_by_id(self) -> None:
        p = _profile()
        self.repo.save(p)
        assert self.repo.find_by_id(p.learner_id) is p

    def test_find_by_id_missing(self) -> None:
        assert self.repo.find_by_id(uuid4()) is None

    def test_find_all(self) -> None:
        self.repo.save(_profile())
        self.repo.save(_profile())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        p = _profile()
        self.repo.save(p)
        self.repo.delete(p.learner_id)
        assert self.repo.find_by_id(p.learner_id) is None

    def test_delete_nonexistent_does_not_raise(self) -> None:
        self.repo.delete(uuid4())

    def test_find_by_counselor(self) -> None:
        counselor = uuid4()
        p1 = _profile(counselor_id=counselor)
        p2 = _profile()  # different counselor
        self.repo.save(p1)
        self.repo.save(p2)
        results = self.repo.find_by_counselor(counselor)
        assert p1 in results
        assert p2 not in results

    def test_find_by_school(self) -> None:
        school = uuid4()
        p1 = _profile(school_id=school)
        p2 = _profile()
        self.repo.save(p1)
        self.repo.save(p2)
        results = self.repo.find_by_school(school)
        assert p1 in results
        assert p2 not in results


# ═══════════════════════════════════════════════════════════════════════════════
# 3. UniversityProgramme Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryUniversityProgrammeRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryUniversityProgrammeRepository()

    def test_save_and_retrieve(self) -> None:
        prog = _programme()
        self.repo.save(prog)
        assert self.repo.find_by_id(prog.programme_id) is prog

    def test_find_by_id_missing(self) -> None:
        assert self.repo.find_by_id(uuid4()) is None

    def test_find_all(self) -> None:
        self.repo.save(_programme())
        self.repo.save(_programme())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        prog = _programme()
        self.repo.save(prog)
        self.repo.delete(prog.programme_id)
        assert self.repo.find_by_id(prog.programme_id) is None

    def test_delete_nonexistent_is_safe(self) -> None:
        self.repo.delete(uuid4())

    def test_find_by_university(self) -> None:
        uni = uuid4()
        p1 = _programme(university_id=uni)
        p2 = _programme()
        self.repo.save(p1)
        self.repo.save(p2)
        results = self.repo.find_by_university(uni)
        assert p1 in results
        assert p2 not in results

    def test_find_published_filters_status(self) -> None:
        published = _programme(status=ProgrammeStatusEnum.Published)
        draft = _programme(status=ProgrammeStatusEnum.Draft)
        self.repo.save(published)
        self.repo.save(draft)
        results = self.repo.find_published()
        assert published in results
        assert draft not in results

    def test_find_published_returns_empty_when_none(self) -> None:
        self.repo.save(_programme(status=ProgrammeStatusEnum.Draft))
        assert self.repo.find_published() == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Application Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryApplicationRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryApplicationRepository()

    def test_save_and_find_by_id(self) -> None:
        app = _application()
        self.repo.save(app)
        assert self.repo.find_by_id(app.application_id) is app

    def test_find_by_id_missing(self) -> None:
        assert self.repo.find_by_id(uuid4()) is None

    def test_find_all(self) -> None:
        self.repo.save(_application())
        self.repo.save(_application())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        app = _application()
        self.repo.save(app)
        self.repo.delete(app.application_id)
        assert self.repo.find_by_id(app.application_id) is None

    def test_delete_nonexistent_is_safe(self) -> None:
        self.repo.delete(uuid4())

    def test_find_by_learner(self) -> None:
        learner = uuid4()
        a1 = _application(learner_id=learner)
        a2 = _application()
        self.repo.save(a1)
        self.repo.save(a2)
        results = self.repo.find_by_learner(learner)
        assert a1 in results
        assert a2 not in results

    def test_find_by_programme(self) -> None:
        prog = uuid4()
        a1 = _application(programme_id=prog)
        a2 = _application()
        self.repo.save(a1)
        self.repo.save(a2)
        results = self.repo.find_by_programme(prog)
        assert a1 in results
        assert a2 not in results

    def test_find_by_status(self) -> None:
        a_draft = _application()
        a_submitted = _application()
        a_submitted.status = ApplicationStatusEnum.Submitted
        self.repo.save(a_draft)
        self.repo.save(a_submitted)
        results = self.repo.find_by_status(ApplicationStatusEnum.Submitted)
        assert a_submitted in results
        assert a_draft not in results

    def test_save_updates_existing(self) -> None:
        app = _application()
        self.repo.save(app)
        app.status = ApplicationStatusEnum.FeePaid
        self.repo.save(app)
        assert self.repo.find_by_id(app.application_id).status == ApplicationStatusEnum.FeePaid
        assert len(self.repo.find_all()) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Document Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryDocumentRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryDocumentRepository()

    def test_save_and_find_by_id(self) -> None:
        doc = _document()
        self.repo.save(doc)
        assert self.repo.find_by_id(doc.document_id) is doc

    def test_find_by_id_missing(self) -> None:
        assert self.repo.find_by_id(uuid4()) is None

    def test_find_all(self) -> None:
        self.repo.save(_document())
        self.repo.save(_document())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        doc = _document()
        self.repo.save(doc)
        self.repo.delete(doc.document_id)
        assert self.repo.find_by_id(doc.document_id) is None

    def test_find_by_learner(self) -> None:
        learner = uuid4()
        d1 = _document(learner_id=learner)
        d2 = _document()
        self.repo.save(d1)
        self.repo.save(d2)
        results = self.repo.find_by_learner(learner)
        assert d1 in results
        assert d2 not in results

    def test_find_by_application(self) -> None:
        app_id = uuid4()
        d1 = _document(application_id=app_id)
        d2 = _document()
        self.repo.save(d1)
        self.repo.save(d2)
        results = self.repo.find_by_application(app_id)
        assert d1 in results
        assert d2 not in results

    def test_find_by_application_returns_empty_for_null_app_id(self) -> None:
        # Documents not linked to any application have application_id=None
        d = _document(application_id=None)
        self.repo.save(d)
        assert self.repo.find_by_application(uuid4()) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Mark Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryMarkRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryMarkRepository()

    def test_save_and_find_by_id(self) -> None:
        m = _mark()
        self.repo.save(m)
        assert self.repo.find_by_id(m.mark_id) is m

    def test_find_by_id_missing(self) -> None:
        assert self.repo.find_by_id(uuid4()) is None

    def test_find_all(self) -> None:
        self.repo.save(_mark())
        self.repo.save(_mark())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        m = _mark()
        self.repo.save(m)
        self.repo.delete(m.mark_id)
        assert self.repo.find_by_id(m.mark_id) is None

    def test_find_by_learner(self) -> None:
        learner = uuid4()
        m1 = _mark(learner_id=learner)
        m2 = _mark()
        self.repo.save(m1)
        self.repo.save(m2)
        results = self.repo.find_by_learner(learner)
        assert m1 in results
        assert m2 not in results

    def test_multiple_marks_same_learner(self) -> None:
        learner = uuid4()
        for _ in range(6):
            self.repo.save(_mark(learner_id=learner))
        assert len(self.repo.find_by_learner(learner)) == 6


# ═══════════════════════════════════════════════════════════════════════════════
# 7. PaymentTransaction Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryPaymentTransactionRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryPaymentTransactionRepository()

    def test_save_and_find_by_id(self) -> None:
        txn = _payment()
        self.repo.save(txn)
        assert self.repo.find_by_id(txn.transaction_id) is txn

    def test_find_all(self) -> None:
        self.repo.save(_payment())
        self.repo.save(_payment())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        txn = _payment()
        self.repo.save(txn)
        self.repo.delete(txn.transaction_id)
        assert self.repo.find_by_id(txn.transaction_id) is None

    def test_find_by_application(self) -> None:
        app_id = uuid4()
        t1 = _payment(application_id=app_id)
        t2 = _payment()
        self.repo.save(t1)
        self.repo.save(t2)
        results = self.repo.find_by_application(app_id)
        assert t1 in results
        assert t2 not in results


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Notification Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryNotificationRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryNotificationRepository()

    def test_save_and_find_by_id(self) -> None:
        n = _notification()
        self.repo.save(n)
        assert self.repo.find_by_id(n.notification_id) is n

    def test_find_all(self) -> None:
        self.repo.save(_notification())
        self.repo.save(_notification())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        n = _notification()
        self.repo.save(n)
        self.repo.delete(n.notification_id)
        assert self.repo.find_by_id(n.notification_id) is None

    def test_find_by_recipient(self) -> None:
        recipient = uuid4()
        n1 = _notification(recipient_id=recipient)
        n2 = _notification()
        self.repo.save(n1)
        self.repo.save(n2)
        results = self.repo.find_by_recipient(recipient)
        assert n1 in results
        assert n2 not in results

    def test_find_unread_excludes_read_and_failed(self) -> None:
        recipient = uuid4()
        unread = _notification(recipient_id=recipient, status="Pending")
        read = _notification(recipient_id=recipient, status="Read")
        failed = _notification(recipient_id=recipient, status="Failed")
        self.repo.save(unread)
        self.repo.save(read)
        self.repo.save(failed)
        results = self.repo.find_unread(recipient)
        assert unread in results
        assert read not in results
        assert failed not in results

    def test_find_unread_returns_empty_when_all_read(self) -> None:
        recipient = uuid4()
        n = _notification(recipient_id=recipient, status="Read")
        self.repo.save(n)
        assert self.repo.find_unread(recipient) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 9. AuditLog Repository
# ═══════════════════════════════════════════════════════════════════════════════

class TestInMemoryAuditLogRepository:
    def setup_method(self) -> None:
        self.repo = InMemoryAuditLogRepository()

    def test_save_and_find_by_id(self) -> None:
        entry = _audit()
        self.repo.save(entry)
        assert self.repo.find_by_id(entry.entry_id) is entry

    def test_find_all(self) -> None:
        self.repo.save(_audit())
        self.repo.save(_audit())
        assert len(self.repo.find_all()) == 2

    def test_delete(self) -> None:
        entry = _audit()
        self.repo.save(entry)
        self.repo.delete(entry.entry_id)
        assert self.repo.find_by_id(entry.entry_id) is None

    def test_find_by_actor(self) -> None:
        actor = uuid4()
        e1 = _audit(actor_id=actor)
        e2 = _audit()
        self.repo.save(e1)
        self.repo.save(e2)
        results = self.repo.find_by_actor(actor)
        assert e1 in results
        assert e2 not in results

    def test_find_by_target(self) -> None:
        target = uuid4()
        e1 = _audit(target_id=target)
        e2 = _audit()
        self.repo.save(e1)
        self.repo.save(e2)
        results = self.repo.find_by_target(target)
        assert e1 in results
        assert e2 not in results


# ═══════════════════════════════════════════════════════════════════════════════
# 10. RepositoryFactory
# ═══════════════════════════════════════════════════════════════════════════════

class TestRepositoryFactory:
    def test_create_user_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_user_repo("MEMORY")
        assert isinstance(repo, InMemoryUserAccountRepository)

    def test_create_learner_profile_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_learner_profile_repo("MEMORY")
        assert isinstance(repo, InMemoryLearnerProfileRepository)

    def test_create_programme_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_programme_repo("MEMORY")
        assert isinstance(repo, InMemoryUniversityProgrammeRepository)

    def test_create_application_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_application_repo("MEMORY")
        assert isinstance(repo, InMemoryApplicationRepository)

    def test_create_document_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_document_repo("MEMORY")
        assert isinstance(repo, InMemoryDocumentRepository)

    def test_create_mark_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_mark_repo("MEMORY")
        assert isinstance(repo, InMemoryMarkRepository)

    def test_create_payment_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_payment_repo("MEMORY")
        assert isinstance(repo, InMemoryPaymentTransactionRepository)

    def test_create_notification_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_notification_repo("MEMORY")
        assert isinstance(repo, InMemoryNotificationRepository)

    def test_create_audit_log_repo_returns_in_memory(self) -> None:
        repo = RepositoryFactory.create_audit_log_repo("MEMORY")
        assert isinstance(repo, InMemoryAuditLogRepository)

    def test_unknown_storage_type_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            RepositoryFactory.create_user_repo("REDIS")  # type: ignore[arg-type]

    def test_unknown_storage_type_for_application_repo(self) -> None:
        with pytest.raises(ValueError):
            RepositoryFactory.create_application_repo("REDIS")  # type: ignore[arg-type]

    def test_two_memory_repos_are_independent_instances(self) -> None:
        """Each factory call must return a fresh, isolated store."""
        repo_a = RepositoryFactory.create_user_repo("MEMORY")
        repo_b = RepositoryFactory.create_user_repo("MEMORY")
        user = _user()
        repo_a.save(user)
        assert repo_b.find_by_id(user.user_id) is None  # stores are independent

    def test_default_storage_type_is_memory(self) -> None:
        repo = RepositoryFactory.create_user_repo()
        assert isinstance(repo, InMemoryUserAccountRepository)

    def test_factory_repos_satisfy_interface_contract(self) -> None:
        """Smoke-test: factory repo can run a full CRUD cycle."""
        repo = RepositoryFactory.create_application_repo("MEMORY")
        app = _application()
        repo.save(app)
        assert repo.find_by_id(app.application_id) is app
        repo.delete(app.application_id)
        assert repo.find_by_id(app.application_id) is None
