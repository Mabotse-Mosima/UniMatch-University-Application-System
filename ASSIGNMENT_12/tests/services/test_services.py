"""
tests/services/test_services.py
================================
Unit tests for the three UniMatch service classes (Assignment 12).

Tests cover all business rules:
  - LearnerProfileService  (create, get, update, delete, add_mark, aps, deactivate)
  - UniversityProgrammeService (CRUD, publish, deactivate, eligibility)
  - ApplicationService     (create, cap at 5, duplicate guard, cancel, status update)
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from entities import Application, LearnerProfile, Mark, UniversityProgramme
from enums import (
    ApplicationStatusEnum,
    EligibilityEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
)
from repositories_inmemory import (
    InMemoryApplicationRepository,
    InMemoryLearnerProfileRepository,
    InMemoryUniversityProgrammeRepository,
)
from services import (
    ApplicationNotFoundError,
    ApplicationService,
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    LearnerNotFoundError,
    LearnerProfileService,
    ProgrammeNotActiveError,
    ProgrammeNotFoundError,
    TooManyActiveApplicationsError,
    UniversityProgrammeService,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def learner_repo():
    return InMemoryLearnerProfileRepository()


@pytest.fixture
def programme_repo():
    return InMemoryUniversityProgrammeRepository()


@pytest.fixture
def application_repo():
    return InMemoryApplicationRepository()


@pytest.fixture
def learner_svc(learner_repo, application_repo):
    return LearnerProfileService(learner_repo=learner_repo, application_repo=application_repo)


@pytest.fixture
def programme_svc(programme_repo):
    return UniversityProgrammeService(programme_repo=programme_repo)


@pytest.fixture
def application_svc(application_repo, learner_repo, programme_repo):
    return ApplicationService(
        application_repo=application_repo,
        learner_repo=learner_repo,
        programme_repo=programme_repo,
    )


def _make_learner() -> LearnerProfile:
    return LearnerProfile(
        learner_id=uuid4(),
        full_name="Thabo Nkosi",
        school_id_number="SCH-001",
        grade=12,
        status=ProfileStatusEnum.Incomplete,
        counselor_id=uuid4(),
        school_id=uuid4(),
    )


def _make_programme(deadline: date = date(2099, 12, 31), aps: int = 28) -> UniversityProgramme:
    return UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="BSc Computer Science",
        faculty="Science",
        minimum_aps=aps,
        application_deadline=deadline,
        application_fee=Decimal("200.00"),
        required_documents=["ID", "Matric Certificate"],
        status=ProgrammeStatusEnum.Draft,
        published_by=uuid4(),
    )


def _make_mark(learner_id, score: int = 75) -> Mark:
    return Mark(
        mark_id=uuid4(),
        learner_id=learner_id,
        subject_name="Mathematics",
        score=score,
        exam_type="NSC",
        academic_year=2024,
    )


# ─────────────────────────────────────────────────────────────────────────────
# LearnerProfileService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLearnerProfileService:

    def test_create_and_get_profile(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        retrieved = learner_svc.get_profile(learner.learner_id)
        assert retrieved.learner_id == learner.learner_id
        assert retrieved.full_name == "Thabo Nkosi"

    def test_get_nonexistent_profile_raises(self, learner_svc):
        with pytest.raises(LearnerNotFoundError):
            learner_svc.get_profile(uuid4())

    def test_list_profiles(self, learner_svc):
        learner_svc.create_profile(_make_learner())
        learner_svc.create_profile(_make_learner())
        assert len(learner_svc.list_profiles()) == 2

    def test_update_profile(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        updated = learner_svc.update_profile(learner.learner_id, full_name="Sipho Dlamini")
        assert updated.full_name == "Sipho Dlamini"

    def test_update_nonexistent_profile_raises(self, learner_svc):
        with pytest.raises(LearnerNotFoundError):
            learner_svc.update_profile(uuid4(), full_name="Ghost")

    def test_delete_profile(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        learner_svc.delete_profile(learner.learner_id)
        with pytest.raises(LearnerNotFoundError):
            learner_svc.get_profile(learner.learner_id)

    def test_add_valid_mark(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        mark = _make_mark(learner.learner_id, score=80)
        result = learner_svc.add_mark(learner.learner_id, mark)
        assert len(result.marks) == 1
        profile = learner_svc.get_profile(learner.learner_id)
        assert len(profile.marks) == 1

    def test_add_invalid_mark_raises(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        bad_mark = _make_mark(learner.learner_id, score=150)  # out of range
        with pytest.raises(ValueError):
            learner_svc.add_mark(learner.learner_id, bad_mark)

    def test_aps_score_top_6(self, learner_svc):
        """APS uses NSC point table and takes top six subjects."""
        learner = _make_learner()
        learner_svc.create_profile(learner)
        # 90,80→7 pts each; 70→6; 60→5; 50→4; 40→3; 30→2 → top 6 = 7+7+6+5+4+3 = 32
        scores = [90, 80, 70, 60, 50, 40, 30]
        for score in scores:
            learner_svc.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=score))
        aps = learner_svc.get_aps_score(learner.learner_id)
        assert aps == 32

    def test_aps_fewer_than_6_subjects(self, learner_svc):
        """With fewer than six marks, all are summed (score 80 → 7 APS points each)."""
        learner = _make_learner()
        learner_svc.create_profile(learner)
        learner_svc.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=80))
        learner_svc.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=80))
        assert learner_svc.get_aps_score(learner.learner_id) == 14

    def test_deactivate_cancels_active_applications(self, learner_svc, application_repo, programme_repo):
        learner = _make_learner()
        learner_svc.create_profile(learner)

        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)

        # Manually create an active application
        app = Application(
            application_id=uuid4(),
            learner_id=learner.learner_id,
            programme_id=prog.programme_id,
            status=ApplicationStatusEnum.Draft,
            payment_reference="",
            fee_amount=Decimal("200"),
            submission_timestamp=None,
            acknowledgement_reference="",
        )
        application_repo.save(app)

        learner_svc.deactivate_profile(learner.learner_id)
        cancelled_app = application_repo.find_by_id(app.application_id)
        assert cancelled_app.status == ApplicationStatusEnum.Cancelled


# ─────────────────────────────────────────────────────────────────────────────
# UniversityProgrammeService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUniversityProgrammeService:

    def test_create_and_get_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        retrieved = programme_svc.get_programme(prog.programme_id)
        assert retrieved.name == "BSc Computer Science"

    def test_get_nonexistent_programme_raises(self, programme_svc):
        with pytest.raises(ProgrammeNotFoundError):
            programme_svc.get_programme(uuid4())

    def test_list_programmes(self, programme_svc):
        programme_svc.create_programme(_make_programme())
        programme_svc.create_programme(_make_programme())
        assert len(programme_svc.list_programmes()) == 2

    def test_update_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        updated = programme_svc.update_programme(prog.programme_id, name="BSc Data Science")
        assert updated.name == "BSc Data Science"

    def test_delete_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        programme_svc.delete_programme(prog.programme_id)
        with pytest.raises(ProgrammeNotFoundError):
            programme_svc.get_programme(prog.programme_id)

    def test_publish_programme(self, programme_svc):
        prog = _make_programme(deadline=date(2099, 12, 31))
        programme_svc.create_programme(prog)
        published = programme_svc.publish_programme(prog.programme_id)
        assert published.status == ProgrammeStatusEnum.Published

    def test_publish_with_past_deadline_raises(self, programme_svc):
        prog = _make_programme(deadline=date(2000, 1, 1))  # past date
        programme_svc.create_programme(prog)
        with pytest.raises(ValueError):
            programme_svc.publish_programme(prog.programme_id)

    def test_deactivate_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        programme_svc.publish_programme(prog.programme_id)
        result = programme_svc.deactivate_programme(prog.programme_id)
        assert result.status == ProgrammeStatusEnum.Deactivated

    def test_list_published_only(self, programme_svc):
        prog1 = _make_programme()
        prog2 = _make_programme()
        programme_svc.create_programme(prog1)
        programme_svc.create_programme(prog2)
        programme_svc.publish_programme(prog1.programme_id)
        published = programme_svc.list_published_programmes()
        assert len(published) == 1
        assert published[0].programme_id == prog1.programme_id

    def test_eligibility_guaranteed(self, programme_svc):
        prog = _make_programme(aps=20)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 24) == EligibilityEnum.Guaranteed

    def test_eligibility_likely(self, programme_svc):
        prog = _make_programme(aps=20)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 22) == EligibilityEnum.Likely

    def test_eligibility_borderline(self, programme_svc):
        prog = _make_programme(aps=20)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 20) == EligibilityEnum.Borderline

    def test_eligibility_not_eligible(self, programme_svc):
        prog = _make_programme(aps=28)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 20) == EligibilityEnum.NotEligible


# ─────────────────────────────────────────────────────────────────────────────
# ApplicationService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationService:

    def _setup(self, learner_repo, programme_repo):
        """Create and persist a learner + published programme."""
        learner = _make_learner()
        learner_repo.save(learner)

        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)

        return learner, prog

    def test_create_application_success(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(
            learner_id=learner.learner_id,
            programme_id=prog.programme_id,
            fee_amount=Decimal("200"),
        )
        assert app.status == ApplicationStatusEnum.Draft
        assert app.learner_id == learner.learner_id

    def test_create_application_learner_not_found(self, application_svc, programme_repo):
        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)
        with pytest.raises(LearnerNotFoundError):
            application_svc.create_application(uuid4(), prog.programme_id, Decimal("200"))

    def test_create_application_programme_not_found(self, application_svc, learner_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        with pytest.raises(ProgrammeNotFoundError):
            application_svc.create_application(learner.learner_id, uuid4(), Decimal("200"))

    def test_create_application_programme_not_active(self, application_svc, learner_repo, programme_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        prog = _make_programme()  # status = Draft, not Published
        programme_repo.save(prog)
        with pytest.raises(ProgrammeNotActiveError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_create_application_expired_programme(self, application_svc, learner_repo, programme_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        prog = _make_programme(deadline=date(2000, 1, 1))
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)
        with pytest.raises(ProgrammeNotActiveError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_create_application_duplicate_rejected(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        with pytest.raises(DuplicateApplicationError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_create_application_cap_at_5(self, application_svc, learner_repo, programme_repo):
        """A learner may not have more than 5 active applications."""
        learner = _make_learner()
        learner_repo.save(learner)

        for _ in range(5):
            prog = _make_programme()
            prog.status = ProgrammeStatusEnum.Published
            programme_repo.save(prog)
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

        # 6th should be blocked
        extra_prog = _make_programme()
        extra_prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(extra_prog)
        with pytest.raises(TooManyActiveApplicationsError):
            application_svc.create_application(learner.learner_id, extra_prog.programme_id, Decimal("200"))

    def test_cancelled_applications_dont_count_toward_cap(self, application_svc, learner_repo, programme_repo):
        """Cancelled (terminal) applications do not count against the 5-app limit."""
        learner = _make_learner()
        learner_repo.save(learner)

        programmes = []
        for _ in range(5):
            prog = _make_programme()
            prog.status = ProgrammeStatusEnum.Published
            programme_repo.save(prog)
            programmes.append(prog)
            app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
            application_svc.cancel_application(app.application_id)

        # All 5 are cancelled → should be able to create a new one
        new_prog = _make_programme()
        new_prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(new_prog)
        app6 = application_svc.create_application(learner.learner_id, new_prog.programme_id, Decimal("200"))
        assert app6.status == ApplicationStatusEnum.Draft

    def test_get_application(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        retrieved = application_svc.get_application(app.application_id)
        assert retrieved.application_id == app.application_id

    def test_get_nonexistent_application_raises(self, application_svc):
        with pytest.raises(ApplicationNotFoundError):
            application_svc.get_application(uuid4())

    def test_list_for_learner(self, application_svc, learner_repo, programme_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        for _ in range(3):
            prog = _make_programme()
            prog.status = ProgrammeStatusEnum.Published
            programme_repo.save(prog)
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        apps = application_svc.list_for_learner(learner.learner_id)
        assert len(apps) == 3

    def test_cancel_application(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        cancelled = application_svc.cancel_application(app.application_id)
        assert cancelled.status == ApplicationStatusEnum.Cancelled

    def test_cancel_accepted_application_raises(self, application_svc, learner_repo, programme_repo, application_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        # Force status to Accepted in the repo
        app.status = ApplicationStatusEnum.Accepted
        application_repo.save(app)
        with pytest.raises(InvalidStatusTransitionError):
            application_svc.cancel_application(app.application_id)

    def test_delete_application(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        application_svc.delete_application(app.application_id)
        with pytest.raises(ApplicationNotFoundError):
            application_svc.get_application(app.application_id)
