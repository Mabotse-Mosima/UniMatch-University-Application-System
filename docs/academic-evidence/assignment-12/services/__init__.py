"""
services/__init__.py
====================
Business-logic service layer for UniMatch (Assignment 12).

Three core services are implemented here:
  - LearnerProfileService   – manage learner profiles and APS scoring
  - UniversityProgrammeService – manage programme listings with eligibility checks
  - ApplicationService      – handle application lifecycle with business rules
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

# ---------------------------------------------------------------------------
# Import domain entities, enums, and repository interfaces
# ---------------------------------------------------------------------------
# NOTE: paths adjusted to import from the flat ASSIGNMENT_12 layout
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from entities import (
    Application,
    LearnerProfile,
    Mark,
    Notification,
    RecommendationResult,
    UniversityProgramme,
    UserAccount,
)
from enums import (
    ApplicationStatusEnum,
    EligibilityEnum,
    PaymentStatusEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
    RoleEnum,
)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class LearnerNotFoundError(Exception):
    """Raised when a LearnerProfile cannot be located."""
    def __init__(self, learner_id: UUID):
        super().__init__(f"Learner {learner_id} not found")
        self.learner_id = learner_id


class ProgrammeNotFoundError(Exception):
    """Raised when a UniversityProgramme cannot be located."""
    def __init__(self, programme_id: UUID):
        super().__init__(f"Programme {programme_id} not found")
        self.programme_id = programme_id


class ApplicationNotFoundError(Exception):
    """Raised when an Application cannot be located."""
    def __init__(self, application_id: UUID):
        super().__init__(f"Application {application_id} not found")
        self.application_id = application_id


class TooManyActiveApplicationsError(Exception):
    """Raised when a learner exceeds the maximum allowed active applications."""
    MAX = 5

    def __init__(self, learner_id: UUID):
        super().__init__(
            f"Learner {learner_id} already has {self.MAX} active applications. "
            "Cancel one before applying again."
        )
        self.learner_id = learner_id


class DuplicateApplicationError(Exception):
    """Raised when a learner tries to apply to the same programme twice."""
    def __init__(self, learner_id: UUID, programme_id: UUID):
        super().__init__(
            f"Learner {learner_id} already has an active application for programme {programme_id}"
        )


class ProgrammeNotActiveError(Exception):
    """Raised when trying to apply to a programme that is not published/active."""
    def __init__(self, programme_id: UUID):
        super().__init__(f"Programme {programme_id} is not currently accepting applications")


class IneligibleLearnerError(Exception):
    """Raised when a learner's APS score is below the programme minimum."""
    def __init__(self, learner_aps: int, minimum_aps: int):
        super().__init__(
            f"Learner APS {learner_aps} is below the programme minimum of {minimum_aps}"
        )


class InvalidStatusTransitionError(Exception):
    """Raised when an application status update is not allowed."""
    def __init__(self, current: ApplicationStatusEnum, requested: ApplicationStatusEnum):
        super().__init__(f"Cannot transition application from {current.value} to {requested.value}")


# ---------------------------------------------------------------------------
# Simple repository protocols (duck-typed to avoid circular imports in tests)
# ---------------------------------------------------------------------------

class _LearnerRepo:
    def find_by_id(self, lid: UUID) -> Optional[LearnerProfile]: ...
    def find_all(self) -> List[LearnerProfile]: ...
    def save(self, p: LearnerProfile) -> None: ...
    def delete(self, lid: UUID) -> None: ...


class _ProgrammeRepo:
    def find_by_id(self, pid: UUID) -> Optional[UniversityProgramme]: ...
    def find_all(self) -> List[UniversityProgramme]: ...
    def save(self, p: UniversityProgramme) -> None: ...
    def delete(self, pid: UUID) -> None: ...
    def find_published(self) -> List[UniversityProgramme]: ...


class _ApplicationRepo:
    def find_by_id(self, aid: UUID) -> Optional[Application]: ...
    def find_all(self) -> List[Application]: ...
    def find_by_learner(self, lid: UUID) -> List[Application]: ...
    def find_by_programme(self, pid: UUID) -> List[Application]: ...
    def save(self, a: Application) -> None: ...
    def delete(self, aid: UUID) -> None: ...


# ---------------------------------------------------------------------------
# LearnerProfileService
# ---------------------------------------------------------------------------

@dataclass
class LearnerProfileService:
    """Manages learner profiles and APS calculation.

    Business rules enforced here:
    - A profile must have at least one mark to be considered complete.
    - APS is the sum of the top-6 NSC point values; fewer than 6 subjects
      uses all available marks.
    - Deactivating a profile cancels its active applications.
    """

    learner_repo: _LearnerRepo  # type: ignore[type-arg]
    application_repo: _ApplicationRepo  # type: ignore[type-arg]

    # ── CRUD ────────────────────────────────────────────────────────────────

    def create_profile(self, profile: LearnerProfile) -> LearnerProfile:
        """Persist a new learner profile."""
        self.learner_repo.save(profile)
        return profile

    def get_profile(self, learner_id: UUID) -> LearnerProfile:
        """Return a learner profile or raise :class:`LearnerNotFoundError`."""
        profile = self.learner_repo.find_by_id(learner_id)
        if profile is None:
            raise LearnerNotFoundError(learner_id)
        return profile

    def list_profiles(self) -> List[LearnerProfile]:
        """Return all learner profiles."""
        return self.learner_repo.find_all()

    def update_profile(self, learner_id: UUID, **kwargs) -> LearnerProfile:
        """Update allowed scalar fields on an existing profile."""
        profile = self.get_profile(learner_id)
        allowed = {"full_name", "grade", "school_id_number"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(profile, key, value)
        self.learner_repo.save(profile)
        return profile

    def delete_profile(self, learner_id: UUID) -> None:
        """Remove a learner profile. Raises if it does not exist."""
        self.get_profile(learner_id)  # ensures 404 if missing
        self.learner_repo.delete(learner_id)

    # ── Domain operations ────────────────────────────────────────────────────

    def add_mark(self, learner_id: UUID, mark: Mark) -> LearnerProfile:
        """Append a validated mark to the learner's profile."""
        if not mark.is_valid():
            raise ValueError(f"Mark score {mark.score} is out of the valid 0–100 range")
        profile = self.get_profile(learner_id)
        profile.marks.append(mark)
        profile.status = ProfileStatusEnum.MarksRecorded
        self.learner_repo.save(profile)
        return profile

    def get_aps_score(self, learner_id: UUID) -> int:
        """Calculate and return the current APS score for a learner."""
        profile = self.get_profile(learner_id)
        return profile.get_aps_score()

    def deactivate_profile(self, learner_id: UUID) -> LearnerProfile:
        """Mark the profile inactive and cancel any open applications."""
        profile = self.get_profile(learner_id)
        profile.deactivate()

        # Business rule: cancel all active (non-terminal) applications
        active_apps = self.application_repo.find_by_learner(learner_id)
        terminal = {
            ApplicationStatusEnum.Accepted,
            ApplicationStatusEnum.Rejected,
            ApplicationStatusEnum.Cancelled,
            ApplicationStatusEnum.DeadlineMissed,
        }
        for app in active_apps:
            if app.status not in terminal:
                app.cancel()
                self.application_repo.save(app)

        self.learner_repo.save(profile)
        return profile


# ---------------------------------------------------------------------------
# UniversityProgrammeService
# ---------------------------------------------------------------------------

@dataclass
class UniversityProgrammeService:
    """Manages university programme listings.

    Business rules enforced here:
    - A programme can only be published if its deadline is in the future.
    - Eligibility checks compare learner APS against programme minimum APS.
    """

    programme_repo: _ProgrammeRepo  # type: ignore[type-arg]

    # ── CRUD ────────────────────────────────────────────────────────────────

    def create_programme(self, programme: UniversityProgramme) -> UniversityProgramme:
        """Persist a new programme in Draft status."""
        self.programme_repo.save(programme)
        return programme

    def get_programme(self, programme_id: UUID) -> UniversityProgramme:
        """Return a programme or raise :class:`ProgrammeNotFoundError`."""
        programme = self.programme_repo.find_by_id(programme_id)
        if programme is None:
            raise ProgrammeNotFoundError(programme_id)
        return programme

    def list_programmes(self) -> List[UniversityProgramme]:
        """Return all programmes regardless of status."""
        return self.programme_repo.find_all()

    def list_published_programmes(self) -> List[UniversityProgramme]:
        """Return only programmes that are currently published and not expired."""
        return [p for p in self.programme_repo.find_published() if not p.is_expired()]

    def update_programme(self, programme_id: UUID, **kwargs) -> UniversityProgramme:
        """Update allowed scalar fields on an existing programme."""
        programme = self.get_programme(programme_id)
        allowed = {"name", "faculty", "minimum_aps", "application_fee", "required_documents"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(programme, key, value)
        self.programme_repo.save(programme)
        return programme

    def delete_programme(self, programme_id: UUID) -> None:
        """Remove a programme. Raises if it does not exist."""
        self.get_programme(programme_id)
        self.programme_repo.delete(programme_id)

    # ── Domain operations ────────────────────────────────────────────────────

    def publish_programme(self, programme_id: UUID) -> UniversityProgramme:
        """Publish a programme so learners can apply.

        Raises :class:`ValueError` if the deadline has already passed.
        """
        programme = self.get_programme(programme_id)
        programme.publish()  # entity enforces deadline-in-future rule
        self.programme_repo.save(programme)
        return programme

    def deactivate_programme(self, programme_id: UUID) -> UniversityProgramme:
        """Take a programme offline."""
        programme = self.get_programme(programme_id)
        programme.deactivate()
        self.programme_repo.save(programme)
        return programme

    def extend_deadline(self, programme_id: UUID, new_deadline: date) -> UniversityProgramme:
        """Extend the application deadline to *new_deadline*."""
        programme = self.get_programme(programme_id)
        programme.extend_deadline(new_deadline)
        self.programme_repo.save(programme)
        return programme

    def check_eligibility(self, programme_id: UUID, learner_aps: int) -> EligibilityEnum:
        """Return an eligibility category for a learner based on APS only."""
        programme = self.get_programme(programme_id)
        diff = learner_aps - programme.minimum_aps
        if diff >= 4:
            return EligibilityEnum.Guaranteed
        if diff >= 1:
            return EligibilityEnum.Likely
        if diff >= 0:
            return EligibilityEnum.Borderline
        return EligibilityEnum.NotEligible


# ---------------------------------------------------------------------------
# ApplicationService
# ---------------------------------------------------------------------------

@dataclass
class ApplicationService:
    """Manages the full application lifecycle.

    Business rules enforced here:
    - A learner may not have more than 5 active (non-terminal) applications.
    - A learner may not apply to the same programme twice while active.
    - Applications can only be made to *Published* programmes that have not
      expired.
    - Status transitions follow the allowed graph defined on the entity;
      invalid transitions are rejected here before touching the entity.
    """

    application_repo: _ApplicationRepo  # type: ignore[type-arg]
    learner_repo: _LearnerRepo  # type: ignore[type-arg]
    programme_repo: _ProgrammeRepo  # type: ignore[type-arg]

    MAX_ACTIVE_APPLICATIONS: int = 5

    # Terminal statuses – applications in these states do not count toward the cap
    _TERMINAL: frozenset = frozenset({
        ApplicationStatusEnum.Accepted,
        ApplicationStatusEnum.Rejected,
        ApplicationStatusEnum.Cancelled,
        ApplicationStatusEnum.DeadlineMissed,
    })

    # ── CRUD ────────────────────────────────────────────────────────────────

    def get_application(self, application_id: UUID) -> Application:
        """Return an application or raise :class:`ApplicationNotFoundError`."""
        app = self.application_repo.find_by_id(application_id)
        if app is None:
            raise ApplicationNotFoundError(application_id)
        return app

    def list_applications(self) -> List[Application]:
        """Return all applications in the system."""
        return self.application_repo.find_all()

    def list_for_learner(self, learner_id: UUID) -> List[Application]:
        """Return all applications belonging to a specific learner."""
        # Confirm learner exists
        if self.learner_repo.find_by_id(learner_id) is None:
            raise LearnerNotFoundError(learner_id)
        return self.application_repo.find_by_learner(learner_id)

    def delete_application(self, application_id: UUID) -> None:
        """Hard-delete an application record. Prefer :meth:`cancel_application` for soft cancellation."""
        self.get_application(application_id)
        self.application_repo.delete(application_id)

    # ── Domain operations ────────────────────────────────────────────────────

    def create_application(
        self,
        learner_id: UUID,
        programme_id: UUID,
        fee_amount: Decimal,
        payment_reference: str = "",
        acknowledgement_reference: str = "",
    ) -> Application:
        """Create a new application enforcing all business rules.

        Raises
        ------
        LearnerNotFoundError
            If the learner does not exist.
        ProgrammeNotFoundError
            If the programme does not exist.
        ProgrammeNotActiveError
            If the programme is not in Published status or has expired.
        TooManyActiveApplicationsError
            If the learner already has 5 active applications.
        DuplicateApplicationError
            If the learner already has an active application for this programme.
        """
        # 1. Validate learner and programme exist
        learner = self.learner_repo.find_by_id(learner_id)
        if learner is None:
            raise LearnerNotFoundError(learner_id)

        programme = self.programme_repo.find_by_id(programme_id)
        if programme is None:
            raise ProgrammeNotFoundError(programme_id)

        # 2. Programme must be published and not expired
        if not programme.is_active():
            raise ProgrammeNotActiveError(programme_id)

        # 3. Active application cap
        existing = self.application_repo.find_by_learner(learner_id)
        active = [a for a in existing if a.status not in self._TERMINAL]
        if len(active) >= self.MAX_ACTIVE_APPLICATIONS:
            raise TooManyActiveApplicationsError(learner_id)

        # 4. No duplicate active application for same programme
        for a in active:
            if a.programme_id == programme_id:
                raise DuplicateApplicationError(learner_id, programme_id)

        # 5. Create the application entity
        application = Application(
            application_id=uuid4(),
            learner_id=learner_id,
            programme_id=programme_id,
            status=ApplicationStatusEnum.Draft,
            payment_reference=payment_reference,
            fee_amount=fee_amount,
            submission_timestamp=None,
            acknowledgement_reference=acknowledgement_reference,
            linked_programme=programme,
        )
        self.application_repo.save(application)
        return application

    def update_status(
        self,
        application_id: UUID,
        new_status: ApplicationStatusEnum,
        actor_id: UUID,
        note: str = "",
    ) -> Application:
        """Transition an application to a new status.

        The entity's :meth:`~entities.Application.update_status` method enforces
        the transition graph; this service layer adds the 404 guard.
        """
        app = self.get_application(application_id)
        try:
            app.update_status(new_status, actor_id, note)
        except ValueError as exc:
            raise InvalidStatusTransitionError(app.status, new_status) from exc
        self.application_repo.save(app)
        return app

    def submit_application(self, application_id: UUID) -> Application:
        """Attempt to submit an application.

        The entity's :meth:`~entities.Application.submit` enforces readiness
        checks (fee paid, documents linked, deadline not passed).
        """
        app = self.get_application(application_id)
        app.submit()
        self.application_repo.save(app)
        return app

    def cancel_application(self, application_id: UUID) -> Application:
        """Cancel an application softly (sets status to Cancelled)."""
        app = self.get_application(application_id)
        if app.status in self._TERMINAL:
            raise InvalidStatusTransitionError(app.status, ApplicationStatusEnum.Cancelled)
        app.cancel()
        self.application_repo.save(app)
        return app


__all__ = [
    "LearnerProfileService",
    "UniversityProgrammeService",
    "ApplicationService",
    "LearnerNotFoundError",
    "ProgrammeNotFoundError",
    "ApplicationNotFoundError",
    "TooManyActiveApplicationsError",
    "DuplicateApplicationError",
    "ProgrammeNotActiveError",
    "IneligibleLearnerError",
    "InvalidStatusTransitionError",
]
