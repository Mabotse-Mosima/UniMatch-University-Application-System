"""
unimatch/services/__init__.py
==============================
Application service layer for UniMatch.

Three core services:
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

# Sentinel UUID recorded as the actor when a status change is initiated by the
# system rather than by an identified user (e.g. bulk cancellation triggered by
# profile deactivation). Chosen to be visually distinct from real user UUIDs.
_SYSTEM_ACTOR_ID = UUID("00000000-0000-0000-0000-ffffffffffff")

from unimatch.entities import (
    Application,
    LearnerProfile,
    Mark,
    NSC_DEFAULT_SCORING_RULE,
    Notification,
    RecommendationResult,
    ScoringRule,
    UniversityProgramme,
    UserAccount,
    calc_aps_for_university,
)
from unimatch.enums import (
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
    def __init__(self, learner_id: UUID):
        super().__init__(f"Learner {learner_id} not found")
        self.learner_id = learner_id


class ProgrammeNotFoundError(Exception):
    def __init__(self, programme_id: UUID):
        super().__init__(f"Programme {programme_id} not found")
        self.programme_id = programme_id


class ApplicationNotFoundError(Exception):
    def __init__(self, application_id: UUID):
        super().__init__(f"Application {application_id} not found")
        self.application_id = application_id


class DuplicateApplicationError(Exception):
    def __init__(self, learner_id: UUID, programme_id: UUID):
        super().__init__(
            f"Learner {learner_id} already has an active application for programme {programme_id}"
        )


class ProgrammeNotActiveError(Exception):
    def __init__(self, programme_id: UUID):
        super().__init__(f"Programme {programme_id} is not currently accepting applications")


class IneligibleLearnerError(Exception):
    def __init__(self, learner_aps: int, minimum_aps: int):
        super().__init__(
            f"Learner APS {learner_aps} is below the programme minimum of {minimum_aps}"
        )


class NotEligibleError(Exception):
    """Raised when a learner's eligibility classification prevents application creation.

    Only Guaranteed and Likely learners may submit applications (REQ-004).
    Borderline and NotEligible classifications are rejected.
    """

    def __init__(self, learner_id: UUID, eligibility: EligibilityEnum, programme_id: UUID):
        super().__init__(
            f"Learner {learner_id} is classified as {eligibility.value} for programme "
            f"{programme_id}. Only Guaranteed or Likely learners may apply."
        )
        self.learner_id = learner_id
        self.eligibility = eligibility
        self.programme_id = programme_id


class InvalidStatusTransitionError(Exception):
    def __init__(self, current: ApplicationStatusEnum, requested: ApplicationStatusEnum):
        super().__init__(f"Cannot transition application from {current.value} to {requested.value}")


# ---------------------------------------------------------------------------
# Duck-typed repository protocols (avoid circular imports in tests)
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


class _ScoringRuleRepo:
    def find_by_university(self, university_id: UUID) -> Optional[ScoringRule]: ...


# ---------------------------------------------------------------------------
# LearnerProfileService
# ---------------------------------------------------------------------------

@dataclass
class LearnerProfileService:
    """Manages learner profiles and APS calculation.

    Business rules:
    - A profile must have at least one mark to be considered complete.
    - APS is the sum of the top-6 NSC point values; fewer than 6 subjects uses all available marks.
    - When a university_id is supplied and a ScoringRule is registered for that university,
      the per-university formula is used instead of the standard NSC formula (REQ-002).
    - Deactivating a profile cancels its active (non-terminal) applications.
    """

    learner_repo: _LearnerRepo  # type: ignore[type-arg]
    application_repo: _ApplicationRepo  # type: ignore[type-arg]
    scoring_rule_repo: Optional[_ScoringRuleRepo] = None  # type: ignore[type-arg]

    def create_profile(self, profile: LearnerProfile) -> LearnerProfile:
        self.learner_repo.save(profile)
        return profile

    def get_profile(self, learner_id: UUID) -> LearnerProfile:
        profile = self.learner_repo.find_by_id(learner_id)
        if profile is None:
            raise LearnerNotFoundError(learner_id)
        return profile

    def list_profiles(self) -> List[LearnerProfile]:
        return self.learner_repo.find_all()

    def update_profile(self, learner_id: UUID, **kwargs) -> LearnerProfile:
        profile = self.get_profile(learner_id)
        allowed = {"full_name", "grade", "school_id_number"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(profile, key, value)
        self.learner_repo.save(profile)
        return profile

    def delete_profile(self, learner_id: UUID) -> None:
        self.get_profile(learner_id)
        self.learner_repo.delete(learner_id)

    def add_mark(self, learner_id: UUID, mark: Mark) -> LearnerProfile:
        if not mark.is_valid():
            raise ValueError(f"Mark score {mark.score} is out of the valid 0-100 range")
        profile = self.get_profile(learner_id)
        profile.marks.append(mark)
        profile.status = ProfileStatusEnum.MarksRecorded
        self.learner_repo.save(profile)
        return profile

    def find_scoring_rule(self, university_id: UUID) -> Optional[ScoringRule]:
        """Return the ScoringRule registered for university_id, or None.

        Returns None both when no rule has been registered and when no
        scoring_rule_repo is wired into this service instance.
        Callers can use the return value to determine whether a
        university-specific formula was actually applied.
        """
        if self.scoring_rule_repo is None:
            return None
        return self.scoring_rule_repo.find_by_university(university_id)

    def get_aps_score(self, learner_id: UUID, university_id: Optional[UUID] = None) -> int:
        """Return the learner's APS score.

        When university_id is supplied and a ScoringRule is registered for that
        university, the university-specific formula is applied (REQ-002).
        Falls back to the standard NSC formula if no rule is found.
        Callers that need to know which formula was applied should use
        find_scoring_rule() separately.
        """
        profile = self.get_profile(learner_id)
        if university_id is not None:
            rule = self.find_scoring_rule(university_id)
            if rule is not None:
                return calc_aps_for_university(profile.marks, rule)
        return profile.get_aps_score()

    def deactivate_profile(self, learner_id: UUID) -> LearnerProfile:
        """Mark the profile inactive and cancel any open applications."""
        profile = self.get_profile(learner_id)
        profile.deactivate()

        terminal = {
            ApplicationStatusEnum.Accepted,
            ApplicationStatusEnum.Rejected,
            ApplicationStatusEnum.Cancelled,
            ApplicationStatusEnum.DeadlineMissed,
        }
        for app in self.application_repo.find_by_learner(learner_id):
            if app.status not in terminal:
                app.cancel(_SYSTEM_ACTOR_ID, note="Cancelled by system: learner profile deactivated")
                self.application_repo.save(app)

        self.learner_repo.save(profile)
        return profile


# ---------------------------------------------------------------------------
# UniversityProgrammeService
# ---------------------------------------------------------------------------

@dataclass
class UniversityProgrammeService:
    """Manages university programme listings.

    Business rules:
    - A programme can only be published if its deadline is in the future.
    - Only Draft programmes may be published; only Published programmes may be deactivated.
    - Published programmes cannot be hard-deleted; deactivate them instead.
    - Eligibility checks compare learner APS against programme minimum APS.
    - Programme name cannot be updated to a blank or whitespace-only string.
    """

    programme_repo: _ProgrammeRepo  # type: ignore[type-arg]

    def create_programme(self, programme: UniversityProgramme) -> UniversityProgramme:
        self.programme_repo.save(programme)
        return programme

    def get_programme(self, programme_id: UUID) -> UniversityProgramme:
        programme = self.programme_repo.find_by_id(programme_id)
        if programme is None:
            raise ProgrammeNotFoundError(programme_id)
        return programme

    def list_programmes(self) -> List[UniversityProgramme]:
        return self.programme_repo.find_all()

    def list_published_programmes(self) -> List[UniversityProgramme]:
        return [p for p in self.programme_repo.find_published() if not p.is_expired()]

    def update_programme(self, programme_id: UUID, **kwargs) -> UniversityProgramme:
        """Update allowed scalar fields. Raises ValueError if name is blank or if
        any required_subjects minimum mark is outside the valid 0-100 range."""
        if "name" in kwargs and not str(kwargs["name"]).strip():
            raise ValueError("Programme name cannot be blank")
        if "required_subjects" in kwargs:
            for subject, min_mark in kwargs["required_subjects"].items():
                if not (0 <= min_mark <= 100):
                    raise ValueError(
                        f"required_subjects['{subject}'] = {min_mark} "
                        "is outside the valid 0-100 NSC score range"
                    )
        programme = self.get_programme(programme_id)
        allowed = {
            "name", "faculty", "minimum_aps", "application_fee",
            "required_documents", "required_subjects",
        }
        for key, value in kwargs.items():
            if key in allowed:
                setattr(programme, key, value)
        self.programme_repo.save(programme)
        return programme

    def delete_programme(self, programme_id: UUID) -> None:
        """Remove a programme. Raises if it is Published (deactivate it first)."""
        programme = self.get_programme(programme_id)
        if programme.status == ProgrammeStatusEnum.Published:
            raise ValueError(
                f"Programme {programme_id} is Published and cannot be deleted. "
                "Deactivate it first."
            )
        self.programme_repo.delete(programme_id)

    def publish_programme(self, programme_id: UUID) -> UniversityProgramme:
        """Publish a programme so learners can apply. Deadline must be in the future."""
        programme = self.get_programme(programme_id)
        programme.publish()
        self.programme_repo.save(programme)
        return programme

    def deactivate_programme(self, programme_id: UUID) -> UniversityProgramme:
        """Take a programme offline. Only Published programmes may be deactivated."""
        programme = self.get_programme(programme_id)
        if programme.status != ProgrammeStatusEnum.Published:
            raise ValueError(
                f"Programme {programme_id} is in {programme.status.value} status "
                "and cannot be deactivated. Only Published programmes may be deactivated."
            )
        programme.deactivate()
        self.programme_repo.save(programme)
        return programme

    def extend_deadline(self, programme_id: UUID, new_deadline: date) -> UniversityProgramme:
        programme = self.get_programme(programme_id)
        programme.extend_deadline(new_deadline)
        self.programme_repo.save(programme)
        return programme

    def check_eligibility(
        self,
        programme_id: UUID,
        learner_aps: int,
        marks: Optional[List[Mark]] = None,
    ) -> EligibilityEnum:
        """Return an eligibility category for a learner (REQ-003).

        When marks are provided they must be the learner's stored marks, not
        client-supplied values. The caller is responsible for fetching them from
        the repository so this layer never trusts arbitrary mark data.

        Subject requirements are evaluated first. A learner who is missing a
        required subject or whose best mark in that subject is below the minimum
        is classified as Not Eligible regardless of their APS margin.

        When marks is None, only the APS margin is considered (backward-compatible
        behaviour for callers that have not yet been updated to supply marks).
        """
        programme = self.get_programme(programme_id)
        if marks is not None and not programme.meets_subject_requirements(marks):
            return EligibilityEnum.NotEligible
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

    Business rules:
    - Applications require Guaranteed or Likely eligibility (REQ-004).
    - Eligibility is assessed from the learner's stored marks and the programme's
      APS minimum and compulsory subject requirements — never from client-supplied data.
    - When a ScoringRule is registered for the programme's university, the
      university-specific APS formula is used for eligibility gating (REQ-002).
      Falls back to the standard NSC formula when no rule is registered.
    - A learner may not apply to the same programme twice while active.
    - Applications can only be made to Published programmes that have not expired.
    - Status transitions follow the allowed graph defined on the entity.
    """

    application_repo: _ApplicationRepo  # type: ignore[type-arg]
    learner_repo: _LearnerRepo  # type: ignore[type-arg]
    programme_repo: _ProgrammeRepo  # type: ignore[type-arg]
    scoring_rule_repo: Optional[_ScoringRuleRepo] = None  # type: ignore[type-arg]

    _TERMINAL: frozenset = frozenset({
        ApplicationStatusEnum.Accepted,
        ApplicationStatusEnum.Rejected,
        ApplicationStatusEnum.Cancelled,
        ApplicationStatusEnum.DeadlineMissed,
    })

    def get_application(self, application_id: UUID) -> Application:
        app = self.application_repo.find_by_id(application_id)
        if app is None:
            raise ApplicationNotFoundError(application_id)
        return app

    def list_applications(self) -> List[Application]:
        return self.application_repo.find_all()

    def list_for_learner(self, learner_id: UUID) -> List[Application]:
        if self.learner_repo.find_by_id(learner_id) is None:
            raise LearnerNotFoundError(learner_id)
        return self.application_repo.find_by_learner(learner_id)

    def delete_application(self, application_id: UUID) -> None:
        self.get_application(application_id)
        self.application_repo.delete(application_id)

    def create_application(
        self,
        learner_id: UUID,
        programme_id: UUID,
        fee_amount: Decimal,
        payment_reference: str = "",
        acknowledgement_reference: str = "",
    ) -> Application:
        """Create a new application enforcing all business rules (REQ-004)."""
        learner = self.learner_repo.find_by_id(learner_id)
        if learner is None:
            raise LearnerNotFoundError(learner_id)

        programme = self.programme_repo.find_by_id(programme_id)
        if programme is None:
            raise ProgrammeNotFoundError(programme_id)

        if not programme.is_active():
            raise ProgrammeNotActiveError(programme_id)

        existing = self.application_repo.find_by_learner(learner_id)
        active = [a for a in existing if a.status not in self._TERMINAL]

        for a in active:
            if a.programme_id == programme_id:
                raise DuplicateApplicationError(learner_id, programme_id)

        # Enforce eligibility using the learner's stored marks (REQ-004).
        # Subject requirements are checked first; a learner who fails any
        # compulsory subject check is immediately NotEligible regardless of APS.
        if not programme.meets_subject_requirements(learner.marks):
            raise NotEligibleError(learner_id, EligibilityEnum.NotEligible, programme_id)

        # Apply the university-specific APS formula when a ScoringRule is
        # registered for the programme's university (REQ-002). Falls back to
        # the standard NSC formula when no rule is found.
        rule = (
            self.scoring_rule_repo.find_by_university(programme.university_id)
            if self.scoring_rule_repo is not None
            else None
        )
        learner_aps = (
            calc_aps_for_university(learner.marks, rule)
            if rule is not None
            else learner.get_aps_score()
        )
        diff = learner_aps - programme.minimum_aps
        if diff >= 4:
            eligibility = EligibilityEnum.Guaranteed
        elif diff >= 1:
            eligibility = EligibilityEnum.Likely
        elif diff >= 0:
            eligibility = EligibilityEnum.Borderline
        else:
            eligibility = EligibilityEnum.NotEligible

        if eligibility not in (EligibilityEnum.Guaranteed, EligibilityEnum.Likely):
            raise NotEligibleError(learner_id, eligibility, programme_id)

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
        app = self.get_application(application_id)
        try:
            app.update_status(new_status, actor_id, note)
        except ValueError as exc:
            raise InvalidStatusTransitionError(app.status, new_status) from exc
        self.application_repo.save(app)
        return app

    def submit_application(self, application_id: UUID) -> Application:
        app = self.get_application(application_id)
        app.submit()
        self.application_repo.save(app)
        return app

    def cancel_application(self, application_id: UUID, actor_id: UUID) -> Application:
        app = self.get_application(application_id)
        if app.status in self._TERMINAL:
            raise InvalidStatusTransitionError(app.status, ApplicationStatusEnum.Cancelled)
        app.cancel(actor_id)
        self.application_repo.save(app)
        return app


__all__ = [
    "LearnerProfileService",
    "UniversityProgrammeService",
    "ApplicationService",
    "LearnerNotFoundError",
    "ProgrammeNotFoundError",
    "ApplicationNotFoundError",
    "DuplicateApplicationError",
    "ProgrammeNotActiveError",
    "IneligibleLearnerError",
    "NotEligibleError",
    "InvalidStatusTransitionError",
]
