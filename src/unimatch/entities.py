from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from math import floor, isfinite
from typing import Any
from uuid import UUID, uuid4

from unimatch.auth import hash_password, verify_password
from unimatch.enums import (
    AccountStateEnum,
    ApplicationStatusEnum,
    EligibilityEnum,
    PaymentStatusEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
    RoleEnum,
)
from unimatch.status_history import StatusHistoryEntry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UserAccount:
    user_id: UUID
    email: str
    password_hash: str
    role: RoleEnum
    failed_attempts: int = 0
    locked_until: datetime | None = None
    mfa_secret: str = ""
    account_state: AccountStateEnum = field(default_factory=lambda: AccountStateEnum.Active)
    school_id: UUID | None = None
    university_id: UUID | None = None
    creator_id: UUID | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    university_ids: set[UUID] = field(default_factory=set)

    @property
    def is_active(self) -> bool:
        return self.account_state == AccountStateEnum.Active

    def login(self, email: str, password: str) -> str:
        if not self.is_active:
            raise ValueError("Account not active")
        if self.is_locked():
            raise ValueError("Account locked")
        if email != self.email or not verify_password(password, self.password_hash):
            self.failed_attempts += 1
            self.updated_at = _utcnow()
            raise ValueError("Invalid credentials")
        self.failed_attempts = 0
        self.updated_at = _utcnow()
        return "authenticated"

    def verify_mfa(self, otp: str) -> bool:
        return bool(otp) and otp == self.mfa_secret

    def reset_password(self, new_password: str) -> None:
        self.password_hash = hash_password(new_password)
        self.failed_attempts = 0
        self.locked_until = None
        self.updated_at = _utcnow()

    def is_locked(self) -> bool:
        """Return True only when locked_until is set and has not yet expired.

        Lockout is triggered exclusively by record_failed_login() when the
        configured threshold (Settings.lockout_threshold) is reached. The
        configured duration (Settings.lockout_duration) determines when it expires.
        No threshold value is hard-coded here.
        """
        if self.locked_until is None:
            return False
        return _utcnow() < self.locked_until

    def has_role(self, role: RoleEnum) -> bool:
        return self.role == role

    def logout(self) -> None:
        self.updated_at = _utcnow()


@dataclass
class Session:
    """Server-side session record. The raw token never appears here — only its digest."""
    session_id: UUID
    account_id: UUID
    token_digest: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    csrf_token: str = ""

    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return datetime.now(timezone.utc) < self.expires_at

    def revoke(self) -> None:
        self.revoked_at = datetime.now(timezone.utc)


@dataclass
class VerificationRecord:
    """Records an authorized operator's review of identity evidence for an account.

    The operator reviews evidence from an authoritative external source and records
    a reference here. This software does not verify the evidence itself.
    """
    record_id: UUID
    subject_account_id: UUID
    verifier_account_id: UUID
    subject_role: RoleEnum
    evidence_reference: str
    school_scope: list[UUID]
    university_id: UUID | None
    created_at: datetime
    outcome: str  # "Verified" or "Rejected"


@dataclass
class School:
    school_id: UUID
    official_name: str
    emis_number: str | None
    province: str
    district: str
    contact_email: str | None
    contact_phone: str | None
    status: str
    creator_id: UUID | None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class SchoolAdminBootstrapEvent:
    event_id: UUID
    school_id: UUID
    target_account_id: UUID
    actor_id: UUID
    verification_evidence_reference: str
    evidence_reference: str
    reason: str
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class Mark:
    mark_id: UUID
    learner_id: UUID
    subject_name: str
    score: int
    exam_type: str
    academic_year: int
    created_at: datetime = field(default_factory=_utcnow)

    def is_valid(self) -> bool:
        return 0 <= self.score <= 100

    def to_aps_points(self) -> int:
        if not self.is_valid():
            return 0
        s = self.score
        if s >= 80:
            return 7
        if s >= 70:
            return 6
        if s >= 60:
            return 5
        if s >= 50:
            return 4
        if s >= 40:
            return 3
        if s >= 30:
            return 2
        return 1

    def get_level(self) -> int:
        return self.to_aps_points()


@dataclass
class LearnerProfile:
    learner_id: UUID
    full_name: str
    school_id_number: str
    grade: int
    status: ProfileStatusEnum
    counselor_id: UUID | None
    school_id: UUID
    marks: list[Mark] = field(default_factory=list)
    applications: list[Application] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    recommendations: list[RecommendationResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def is_complete(self) -> bool:
        return bool(self.full_name and self.school_id_number and self.grade and len(self.marks) >= 1)

    def get_aps_score(self) -> int:
        if len(self.marks) < 6:
            return sum(m.to_aps_points() for m in self.marks)
        ranked = sorted((m.to_aps_points() for m in self.marks), reverse=True)
        return sum(ranked[:6])

    def get_subject_marks(self) -> list[Mark]:
        return list(self.marks)

    def generate_recommendations(self) -> list[RecommendationResult]:
        return list(self.recommendations)

    def get_active_applications(self) -> list[Application]:
        terminal = {
            ApplicationStatusEnum.Accepted,
            ApplicationStatusEnum.Rejected,
            ApplicationStatusEnum.Cancelled,
            ApplicationStatusEnum.DeadlineMissed,
        }
        return [a for a in self.applications if a.status not in terminal]

    def deactivate(self) -> None:
        self.status = ProfileStatusEnum.Inactive
        self.updated_at = _utcnow()


@dataclass
class UniversityProgramme:
    programme_id: UUID
    university_id: UUID
    name: str
    faculty: str
    minimum_aps: int
    application_deadline: date
    application_fee: Decimal
    required_documents: list[str]
    status: ProgrammeStatusEnum
    published_by: UUID
    version: int = 1
    # required_subjects maps subject name to the minimum mark (0-100) a learner
    # must hold in that subject. An empty dict means no subject-specific requirements
    # beyond the minimum APS. (REQ-003)
    required_subjects: dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    source_document_id: UUID | None = None
    source_draft_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate required_subjects at construction time.

        Each minimum mark must be within the valid NSC score range 0-100.
        Raises ValueError for any out-of-range value.
        """
        for subject, min_mark in self.required_subjects.items():
            if not (0 <= min_mark <= 100):
                raise ValueError(
                    f"required_subjects['{subject}'] = {min_mark} "
                    "is outside the valid 0-100 NSC score range"
                )

    def is_active(self) -> bool:
        return self.status == ProgrammeStatusEnum.Published and not self.is_expired()

    def is_expired(self) -> bool:
        return date.today() > self.application_deadline

    def publish(self) -> None:
        today = date.today()
        if self.application_deadline <= today:
            raise ValueError("Deadline must be in the future to publish")
        self.status = ProgrammeStatusEnum.Published
        self.updated_at = _utcnow()

    def deactivate(self) -> None:
        self.status = ProgrammeStatusEnum.Deactivated
        self.updated_at = _utcnow()

    def meets_subject_requirements(self, marks: list[Mark]) -> bool:
        """Check whether the learner's stored marks satisfy every required subject.

        For each entry in required_subjects, the learner must have at least one
        mark for that subject whose score meets or exceeds the specified minimum.
        Where a learner has multiple marks for the same subject (e.g. Grade 11 and
        Grade 12 entries), the highest recorded score is used for this check.

        Returns True immediately when required_subjects is empty.
        """
        if not self.required_subjects:
            return True
        best_by_subject: dict[str, int] = {}
        for m in marks:
            best_by_subject[m.subject_name] = max(
                best_by_subject.get(m.subject_name, 0), m.score
            )
        for subject, min_mark in self.required_subjects.items():
            best = best_by_subject.get(subject)
            if best is None:
                return False  # required subject not present in learner's marks
            if best < min_mark:
                return False  # best available mark is below the requirement
        return True

    def meets_requirements(self, profile: LearnerProfile) -> bool:
        """Return True when the learner meets both the APS minimum and all
        required-subject thresholds (REQ-003)."""
        return (
            profile.get_aps_score() >= self.minimum_aps
            and self.meets_subject_requirements(profile.marks)
        )

    def extend_deadline(self, new_date: date) -> None:
        self.application_deadline = new_date
        self.updated_at = _utcnow()


@dataclass
class PaymentTransaction:
    transaction_id: UUID
    application_id: UUID
    status: PaymentStatusEnum
    payment_reference: str
    amount: Decimal
    initiated_at: datetime = field(default_factory=_utcnow)
    resolved_at: datetime | None = None

    def initiate(self) -> None:
        self.status = PaymentStatusEnum.Initiated
        self.initiated_at = _utcnow()

    def confirm(self, reference: str) -> None:
        self.status = PaymentStatusEnum.Confirmed
        self.payment_reference = reference
        self.resolved_at = _utcnow()

    def decline(self, reason: str) -> None:
        self.status = PaymentStatusEnum.Declined
        self.payment_reference = reason
        self.resolved_at = _utcnow()

    def timeout(self) -> None:
        self.status = PaymentStatusEnum.TimedOut
        self.resolved_at = _utcnow()


@dataclass
class Document:
    document_id: UUID
    learner_id: UUID
    application_id: UUID | None
    document_type: str
    filename: str
    storage_path: str
    mime_type: str
    size_bytes: int
    uploaded_by: UUID
    virus_scan_status: str
    status: str
    school_id: UUID
    uploaded_at: datetime = field(default_factory=_utcnow)
    content_sha256: str = ""
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str = ""

    _allowed_mimes = {"application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    _max_bytes = 5 * 1024 * 1024

    def is_valid(self) -> bool:
        if self.mime_type not in self._allowed_mimes:
            return False
        if not 0 < self.size_bytes <= self._max_bytes:
            return False
        return True

    def link_to_application(self, application_id: UUID) -> None:
        self.application_id = application_id

    def review(self, decision: str, reviewer_id: UUID, note: str) -> None:
        if self.status != "PendingReview":
            raise ValueError("Only documents pending review can be reviewed.")
        if decision not in {"Verified", "Rejected"}:
            raise ValueError("Document review decision must be Verified or Rejected.")
        if not note.strip():
            raise ValueError("A review note is required.")
        self.status = decision
        self.reviewed_by = reviewer_id
        self.reviewed_at = _utcnow()
        self.review_note = note.strip()

    def delete(self) -> None:
        self.status = "Rejected"


@dataclass
class Application:
    application_id: UUID
    learner_id: UUID
    programme_id: UUID
    status: ApplicationStatusEnum
    payment_reference: str
    fee_amount: Decimal
    submission_timestamp: datetime | None
    acknowledgement_reference: str
    linked_programme: UniversityProgramme | None = None
    documents: list[Document] = field(default_factory=list)
    status_history: list[StatusHistoryEntry] = field(default_factory=list)
    payment: PaymentTransaction | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def can_submit(self) -> bool:
        if self.is_deadline_passed():
            return False
        from decimal import Decimal
        if not self.payment_reference and self.fee_amount != Decimal("0"):
            return False
        linked = [
            document
            for document in self.documents
            if document.application_id == self.application_id
            and document.status == "Verified"
        ]
        if not linked:
            return False
        if self.linked_programme is not None:
            linked_types = {document.document_type for document in linked}
            if not set(self.linked_programme.required_documents).issubset(linked_types):
                return False
        return self.status in (
            ApplicationStatusEnum.PackageReady,
            ApplicationStatusEnum.FeePaid,
        )

    def submit(self, actor_id: UUID) -> None:
        if not self.can_submit():
            raise ValueError("Cannot submit application in current state")
        self._transition(ApplicationStatusEnum.Submitted, actor_id)
        self.submission_timestamp = _utcnow()
        self.acknowledgement_reference = str(uuid4())

    def update_status(self, status: ApplicationStatusEnum, actor_id: UUID, note: str = "") -> None:
        prev = self.status
        if not self._allowed_transition(prev, status):
            raise ValueError("Invalid status transition")
        self._transition(status, actor_id, prev=prev, note=note)

    def _transition(
        self,
        new_status: ApplicationStatusEnum,
        actor_id: UUID,
        prev: ApplicationStatusEnum | None = None,
        note: str = "",
    ) -> None:
        previous = prev if prev is not None else self.status
        self.status = new_status
        self.status_history.append(
            StatusHistoryEntry.create(self.application_id, previous, new_status, actor_id, note)
        )
        self.updated_at = _utcnow()

    def _allowed_transition(self, prev: ApplicationStatusEnum, new: ApplicationStatusEnum) -> bool:
        allowed_transitions = {
            ApplicationStatusEnum.Draft: {
                ApplicationStatusEnum.FeeOutstanding,
                ApplicationStatusEnum.Cancelled,
                ApplicationStatusEnum.DeadlineMissed,
            },
            ApplicationStatusEnum.FeeOutstanding: {
                ApplicationStatusEnum.FeePaid,
                ApplicationStatusEnum.PackageReady,
                ApplicationStatusEnum.Cancelled,
                ApplicationStatusEnum.DeadlineMissed,
            },
            ApplicationStatusEnum.FeePaid: {
                ApplicationStatusEnum.PackageIncomplete,
                ApplicationStatusEnum.PackageReady,
            },
            ApplicationStatusEnum.PackageIncomplete: {
                ApplicationStatusEnum.PackageReady,
            },
            ApplicationStatusEnum.PackageReady: {
                ApplicationStatusEnum.Submitted,
                ApplicationStatusEnum.DeadlineMissed,
            },
            ApplicationStatusEnum.Submitted: {
                ApplicationStatusEnum.UnderReview,
                ApplicationStatusEnum.Accepted,
                ApplicationStatusEnum.Rejected,
            },
            ApplicationStatusEnum.UnderReview: {
                ApplicationStatusEnum.DocsRequested,
                ApplicationStatusEnum.Accepted,
                ApplicationStatusEnum.Rejected,
                ApplicationStatusEnum.Waitlisted,
            },
            ApplicationStatusEnum.DocsRequested: {
                ApplicationStatusEnum.PackageIncomplete,
            },
            ApplicationStatusEnum.Waitlisted: {
                ApplicationStatusEnum.Accepted,
                ApplicationStatusEnum.Rejected,
            },
        }
        return new in allowed_transitions.get(prev, set())

    def is_deadline_passed(self) -> bool:
        if self.linked_programme is None:
            return False
        return date.today() > self.linked_programme.application_deadline

    def get_status_history(self) -> list[StatusHistoryEntry]:
        return list(self.status_history)

    def get_documents(self) -> list[Document]:
        return list(self.documents)

    def cancel(self, actor_id: UUID, note: str = "") -> None:
        self.update_status(ApplicationStatusEnum.Cancelled, actor_id, note)


@dataclass
class RecommendationResult:
    result_id: UUID
    learner_id: UUID
    programme_id: UUID
    eligibility_category: EligibilityEnum
    learner_aps: int
    programme_minimum_aps: int
    is_stale: bool = False
    generated_at: datetime = field(default_factory=_utcnow)

    def classify(self) -> EligibilityEnum:
        return self.eligibility_category

    def get_explanation(self) -> str:
        return f"APS {self.learner_aps} vs minimum {self.programme_minimum_aps}"

    def mark_stale(self) -> None:
        self.is_stale = True

    def is_current_for(self, profile: LearnerProfile) -> bool:
        return not self.is_stale and self.learner_id == profile.learner_id


@dataclass
class Notification:
    notification_id: UUID
    recipient_id: UUID
    type: str
    status: str
    message: str
    retry_count: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    sent_at: datetime | None = None
    event_key: str | None = None

    def dispatch(self) -> None:
        self.status = "Sent"
        self.sent_at = _utcnow()

    def retry(self) -> None:
        self.retry_count += 1

    def mark_read(self) -> None:
        self.status = "Read"

    def mark_failed(self) -> None:
        self.status = "Failed"


@dataclass
class AuditLogEntry:
    entry_id: UUID
    actor_id: UUID
    action: str
    target_type: str
    target_id: UUID
    old_value: Any
    new_value: Any
    timestamp: datetime
    school_id: UUID | None = None
    university_id: UUID | None = None

    @classmethod
    def create(
        cls,
        actor: UUID,
        action: str,
        target_type: str,
        target_id: UUID,
        old: Any,
        new: Any,
        *,
        school_id: UUID | None = None,
        university_id: UUID | None = None,
    ) -> AuditLogEntry:
        return cls(
            entry_id=uuid4(),
            actor_id=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            old_value=old,
            new_value=new,
            timestamp=_utcnow(),
            school_id=school_id,
            university_id=university_id,
        )


@dataclass
class GuidanceSession:
    guidance_session_id: UUID
    learner_id: UUID
    school_id: UUID
    responsible_staff_id: UUID
    session_date: date
    purpose: str
    notes: str
    status: str
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS scoring (REQ-002)
# ─────────────────────────────────────────────────────────────────────────────

# Standard NSC point-conversion bands: (minimum_score, aps_points).
# Source: South African NSC assessment guidelines (standard scale).
_NSC_STANDARD_BANDS: list[tuple[int, int]] = [
    (80, 7), (70, 6), (60, 5), (50, 4), (40, 3), (30, 2),
]


def _score_to_points(score: int, band_thresholds: list[tuple[int, int]]) -> int:
    """Convert a raw score to APS points using the supplied band thresholds.

    Thresholds need not be pre-sorted; the function handles any order.
    Returns 0 for scores outside the valid 0-100 range.
    Returns 1 for any valid score that falls below every threshold band
    (consistent with the NSC minimum-point rule).
    """
    if not (0 <= score <= 100):
        return 0
    for min_score, points in sorted(band_thresholds, key=lambda t: t[0], reverse=True):
        if score >= min_score:
            return points
    return 1


@dataclass
class ScoringRule:
    """Per-university APS calculation rule (REQ-002).

    South African universities apply different point bands, subject exclusions,
    and subject weightings when computing a learner's APS. A ScoringRule
    captures these per-institution parameters so the same NSC marks can produce
    a correctly calculated, institution-specific APS.

    The NSC_DEFAULT_SCORING_RULE constant provides the standard unweighted formula
    as a fallback when no university-specific rule has been configured.

    IMPORTANT — synthetic test data only:
        Real per-university scoring rules (for Wits, UCT, CPUT or any other
        institution) must be sourced from each university's current admissions
        documents and are NOT represented by any ScoringRule instance in this
        codebase. All ScoringRule instances used in tests are synthetic and are
        labelled as such to avoid misrepresenting any institution's rules.
    """

    university_id: UUID
    band_thresholds: list[tuple[int, int]]  # (min_score, points); order does not matter
    subject_count: int                       # how many top subjects are summed
    excluded_subjects: list[str]             # subject names not counted toward APS
    subject_weightings: dict[str, float]     # per-subject multiplier (default 1.0)

    def __post_init__(self) -> None:
        """Validate the scoring-rule configuration at construction time.

        Raises ValueError for configurations that would produce nonsensical APS
        values, specifically:
        - subject_count < 1 (would select no subjects, forcing APS to 0)
        - empty band_thresholds (would silently assign minimum points to all scores)
        - band_threshold min_score outside 0-100 (inconsistent with NSC score range)
        - band_threshold points < 1 (inconsistent with NSC minimum point value)
        - duplicate min_score values (ambiguous band assignment)
        - non-finite or non-positive subject weightings (would produce negative
          or undefined APS contributions)
        """
        if self.subject_count < 1:
            raise ValueError(
                f"ScoringRule.subject_count must be at least 1, got {self.subject_count}"
            )

        if not self.band_thresholds:
            raise ValueError(
                "ScoringRule.band_thresholds must not be empty; "
                "provide at least one (min_score, points) entry"
            )

        seen_scores: set[int] = set()
        for min_score, points in self.band_thresholds:
            if not (0 <= min_score <= 100):
                raise ValueError(
                    f"ScoringRule.band_thresholds contains min_score={min_score} "
                    "which is outside the valid 0-100 NSC score range"
                )
            if points < 1:
                raise ValueError(
                    f"ScoringRule.band_thresholds contains points={points} "
                    "which is below the NSC minimum of 1"
                )
            if min_score in seen_scores:
                raise ValueError(
                    f"ScoringRule.band_thresholds contains duplicate min_score={min_score}"
                )
            seen_scores.add(min_score)

        # Monotone ordering: a higher minimum score band must not award fewer points
        # than a lower one. Inconsistent ordering would produce APS that can decrease
        # as a learner's mark improves, contradicting the NSC scoring semantics.
        sorted_bands = sorted(self.band_thresholds, key=lambda t: t[0])
        for i in range(1, len(sorted_bands)):
            prev_score, prev_pts = sorted_bands[i - 1]
            curr_score, curr_pts = sorted_bands[i]
            if curr_pts < prev_pts:
                raise ValueError(
                    f"ScoringRule.band_thresholds: min_score={curr_score} awards {curr_pts} "
                    f"point(s) but min_score={prev_score} awards {prev_pts} — "
                    "higher score bands must award at least as many points as lower ones"
                )

        for subject, weight in self.subject_weightings.items():
            if not isfinite(weight):
                raise ValueError(
                    f"ScoringRule.subject_weightings['{subject}'] = {weight} "
                    "is not a finite number"
                )
            if weight <= 0:
                raise ValueError(
                    f"ScoringRule.subject_weightings['{subject}'] = {weight} "
                    "must be strictly positive"
                )


# Sentinel UUID for the default (non-university-specific) rule.
_NSC_DEFAULT_UNIVERSITY_ID = UUID("00000000-0000-0000-0000-000000000000")

# Standard NSC formula used when no university-specific ScoringRule is registered.
# top-6 subjects, no exclusions, no weightings, standard NSC point bands.
NSC_DEFAULT_SCORING_RULE = ScoringRule(
    university_id=_NSC_DEFAULT_UNIVERSITY_ID,
    band_thresholds=_NSC_STANDARD_BANDS,
    subject_count=6,
    excluded_subjects=[],
    subject_weightings={},
)


def calc_aps_for_university(marks: list[Mark], rule: ScoringRule) -> int:
    """Calculate a learner's APS using a university-specific ScoringRule.

    Steps (matching the approved design, Section 3.2.2b):
    1. Exclude marks for subjects listed in rule.excluded_subjects.
    2. Convert each remaining mark to points via rule.band_thresholds.
    3. Apply rule.subject_weightings (default multiplier 1.0).
    4. Select the top rule.subject_count subjects by weighted points.
    5. Return floor(sum) so fractional weights produce whole-number APS.

    If fewer eligible marks exist than rule.subject_count, all are summed
    (consistent with LearnerProfile.get_aps_score() for the default formula).
    """
    eligible_points = [
        _score_to_points(m.score, rule.band_thresholds)
        * rule.subject_weightings.get(m.subject_name, 1.0)
        for m in marks
        if m.subject_name not in rule.excluded_subjects
    ]
    ranked = sorted(eligible_points, reverse=True)
    return floor(sum(ranked[:rule.subject_count]))
