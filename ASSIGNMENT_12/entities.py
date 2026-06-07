from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from enums import (
    ApplicationStatusEnum,
    EligibilityEnum,
    PaymentStatusEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
    RoleEnum,
)
from status_history import StatusHistoryEntry


def _utcnow() -> datetime:
    return datetime.utcnow()


@dataclass
class UserAccount:
    user_id: UUID
    email: str
    password_hash: str
    role: RoleEnum
    failed_attempts: int = 0
    locked_until: datetime | None = None
    mfa_secret: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def login(self, email: str, password: str) -> str:
        if not self.is_active:
            raise ValueError("Account suspended")
        if self.is_locked():
            raise ValueError("Account locked")
        if email != self.email or password != self.password_hash:
            self.failed_attempts += 1
            if self.failed_attempts >= 3:
                self.locked_until = _utcnow()
            self.updated_at = _utcnow()
            raise ValueError("Invalid credentials")
        self.failed_attempts = 0
        self.updated_at = _utcnow()
        return "jwt-token-placeholder"

    def verify_mfa(self, otp: str) -> bool:
        return bool(otp) and otp == self.mfa_secret

    def reset_password(self, new_password: str) -> None:

    if len(new_password) < 8:
        raise ValueError(
            "Password must contain at least 8 characters"
        )

    if not re.search(r"\d", new_password):
        raise ValueError(
            "Password must contain a number"
        )

    if not re.search(r"[A-Z]", new_password):
        raise ValueError(
            "Password must contain an uppercase letter"
        )

    self.password_hash = new_password
    self.failed_attempts = 0
    self.locked_until = None
    self.updated_at = _utcnow()

    def is_locked(self) -> bool:
        if self.failed_attempts >= 3:
            return True
        if self.locked_until is None:
            return False
        return _utcnow() < self.locked_until

    def has_role(self, role: RoleEnum) -> bool:
        return self.role == role

    def logout(self) -> None:
        self.updated_at = _utcnow()


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
    counselor_id: UUID
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
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

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

    def meets_requirements(self, profile: LearnerProfile) -> bool:
        return profile.get_aps_score() >= self.minimum_aps

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
    uploaded_at: datetime = field(default_factory=_utcnow)

    _allowed_mimes = {"application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    _max_bytes = 5 * 1024 * 1024

    def is_valid(self) -> bool:
        if self.mime_type not in self._allowed_mimes:
            return False
        if self.size_bytes > self._max_bytes:
            return False
        return True

    def scan(self) -> str:
        if not self.is_valid():
            self.virus_scan_status = "Rejected"
            return self.virus_scan_status
        self.virus_scan_status = "Clean"
        return self.virus_scan_status

    def link_to_application(self, application_id: UUID) -> None:
        self.application_id = application_id
        self.status = "LinkedToApp"

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
        if not self.payment_reference:
            return False
        linked = [d for d in self.documents if d.application_id == self.application_id and d.status == "LinkedToApp"]
        if not linked:
            return False
        return self.status in (
            ApplicationStatusEnum.PackageReady,
            ApplicationStatusEnum.FeePaid,
        )

    def submit(self) -> None:
        if not self.can_submit():
            raise ValueError("Cannot submit application in current state")
        self._transition(ApplicationStatusEnum.Submitted, self.learner_id)
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
        if prev == ApplicationStatusEnum.Accepted and new != ApplicationStatusEnum.Accepted:
            return False
        return True

    def is_deadline_passed(self) -> bool:
        if self.linked_programme is None:
            return False
        return date.today() > self.linked_programme.application_deadline

    def get_status_history(self) -> list[StatusHistoryEntry]:
        return list(self.status_history)

    def get_documents(self) -> list[Document]:
        return list(self.documents)

    def cancel(self) -> None:
        self.status = ApplicationStatusEnum.Cancelled
        self.updated_at = _utcnow()


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

    @classmethod
    def create(cls, actor: UUID, action: str, target_type: str, target_id: UUID, old: Any, new: Any) -> AuditLogEntry:
        return cls(
            entry_id=uuid4(),
            actor_id=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            old_value=old,
            new_value=new,
            timestamp=_utcnow(),
        )
