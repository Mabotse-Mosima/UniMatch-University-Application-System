"""
unimatch/repositories/inmemory.py
==================================
HashMap-backed in-memory implementations of every UniMatch repository interface.

Design notes
------------
- Each class stores entities in a plain ``dict[UUID, Entity]``.
- All ``save`` calls are upserts (create or update).
- ``delete`` is idempotent: deleting a non-existent key is a no-op.
- Zero I/O dependencies — ideal for fast unit tests and local development.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from threading import RLock

from unimatch.entities import (
    Application,
    AuditLogEntry,
    Document,
    GuidanceSession,
    LearnerProfile,
    Mark,
    Notification,
    PaymentTransaction,
    ScoringRule,
    Session,
    UniversityProgramme,
    UserAccount,
    VerificationRecord,
    School,
    SchoolAdminBootstrapEvent,
)
from unimatch.enums import ApplicationStatusEnum, ProgrammeStatusEnum, RoleEnum
from unimatch.repositories import (
    ApplicationRepository,
    AuditLogRepository,
    DocumentRepository,
    LearnerProfileRepository,
    MarkRepository,
    NotificationRepository,
    PaymentTransactionRepository,
    ScoringRuleRepository,
    SessionRepository,
    UniversityProgrammeRepository,
    UserAccountRepository,
    VerificationRecordRepository,
    GuidanceSessionRepository,
    SchoolRepository,
    AccountInvitationRepository,
)


class InMemoryUserAccountRepository(UserAccountRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, UserAccount] = {}
        self._bootstrap_events: dict[UUID, SchoolAdminBootstrapEvent] = {}
        self._university_bootstrap_events: set[UUID] = set()
        self._admin_lock = RLock()

    def save(self, entity: UserAccount) -> None:
        self._store[entity.user_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[UserAccount]:
        return self._store.get(entity_id)

    def find_all(self) -> List[UserAccount]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_email(self, email: str) -> Optional[UserAccount]:
        for account in self._store.values():
            if account.email == email:
                return account
        return None

    def find_by_role(self, role: RoleEnum) -> List[UserAccount]:
        return [a for a in self._store.values() if a.role == role]

    def set_account_state(self, account_id: UUID, state) -> UserAccount:
        with self._admin_lock:
            from unimatch.enums import AccountStateEnum
            from unimatch.provisioning import AccountNotFoundError, ProvisioningError
            account = self._store.get(account_id)
            if account is None:
                raise AccountNotFoundError("Account not found.")
            allowed = (
                account.account_state == AccountStateEnum.Active and state == AccountStateEnum.Suspended
            ) or (
                account.account_state == AccountStateEnum.Suspended and state == AccountStateEnum.Active
            )
            if not allowed:
                raise ProvisioningError("Only Active accounts can be suspended and Suspended accounts reactivated.")
            account.account_state = state
            account.updated_at = datetime.now(timezone.utc)
            return account

    def set_password(self, account_id: UUID, password: str) -> UserAccount:
        with self._admin_lock:
            account = self._store.get(account_id)
            if account is None:
                raise KeyError("Account not found.")
            account.reset_password(password)
            return account

    def bootstrap_first_school_admin(self, school_id, account_id, actor, verification_evidence_reference, evidence_reference, reason):
        with self._admin_lock:
            from unimatch.enums import AccountStateEnum
            from unimatch.provisioning import AlreadyActiveError, AccountNotFoundError, ProvisioningError
            account = self._store.get(account_id)
            if account is None:
                raise AccountNotFoundError("Account not found.")
            if any(e.school_id == school_id for e in self._bootstrap_events.values()):
                raise ProvisioningError("First SchoolAdmin bootstrap has already been used.")
            if any(a.role == RoleEnum.SchoolAdmin and a.school_id == school_id and a.account_state == AccountStateEnum.Active for a in self._store.values()):
                raise AlreadyActiveError("This school already has an active SchoolAdmin.")
            if account.role != RoleEnum.SchoolAdmin or account.school_id != school_id or account.account_state != AccountStateEnum.Pending:
                raise ProvisioningError("Bootstrap target must be a Pending SchoolAdmin assigned to this school.")
            account.account_state = AccountStateEnum.Active
            account.updated_at = datetime.now(timezone.utc)
            event = SchoolAdminBootstrapEvent(
                uuid4(), school_id, account_id, actor.account_id,
                verification_evidence_reference, evidence_reference, reason,
            )
            self._bootstrap_events[event.event_id] = event
            return account

    def bootstrap_first_university_admissions(
        self, university_id, account_id, actor, verification_evidence_reference,
        evidence_reference, reason, audit_repository,
    ):
        with self._admin_lock:
            from unimatch.enums import AccountStateEnum
            from unimatch.provisioning import AccountNotFoundError, ProvisioningError
            account = self._store.get(account_id)
            if account is None:
                raise AccountNotFoundError("Account not found.")
            if university_id in self._university_bootstrap_events:
                raise ProvisioningError("First UniversityAdmissions bootstrap has already been used for this university.")
            scoped_accounts = [
                item for item in self._store.values()
                if item.role == RoleEnum.UniversityAdmissions and item.university_id == university_id
            ]
            if len(scoped_accounts) != 1 or scoped_accounts[0].user_id != account_id:
                raise ProvisioningError("Bootstrap is only available to the first UniversityAdmissions account for this university.")
            if (
                account.role != RoleEnum.UniversityAdmissions
                or account.university_id != university_id
                or account.creator_id != actor.account_id
                or account.account_state != AccountStateEnum.Pending
            ):
                raise ProvisioningError("Bootstrap target must be a Pending UniversityAdmissions account created by this SystemAdmin for this university.")
            audit_repository.save(AuditLogEntry.create(
                actor=actor.account_id,
                action="BootstrapFirstUniversityAdmissions",
                target_type="Account",
                target_id=account_id,
                old={"account_state": AccountStateEnum.Pending.value},
                new={
                    "account_state": AccountStateEnum.Active.value,
                    "university_id": str(university_id),
                    "verification_evidence_reference": verification_evidence_reference,
                    "bootstrap_evidence_reference": evidence_reference,
                    "reason": reason,
                },
                university_id=university_id,
            ))
            account.account_state = AccountStateEnum.Active
            account.updated_at = datetime.now(timezone.utc)
            self._university_bootstrap_events.add(university_id)
            return account

    def activate_with_lock(self, target_id: UUID, actor: "UserAccount") -> "UserAccount":  # type: ignore[name-defined]
        from unimatch.provisioning import (
            AccountNotFoundError, SelfActivationError, AlreadyActiveError, ProvisioningError,
        )
        from unimatch.enums import AccountStateEnum
        account = self._store.get(target_id)
        if account is None:
            raise AccountNotFoundError(f"Account {target_id} not found.")
        if actor.account_id == account.user_id or account.creator_id == actor.account_id:
            raise SelfActivationError("The account actor cannot activate this account.")
        if account.account_state == AccountStateEnum.Active:
            raise AlreadyActiveError(f"Account {target_id} is already active.")
        if account.account_state != AccountStateEnum.Pending:
            raise ProvisioningError(f"Account {target_id} is not Pending.")
        account.account_state = AccountStateEnum.Active
        account.updated_at = datetime.now(timezone.utc)
        return account

    def record_failed_login(self, account_id: UUID) -> bool:
        from unimatch.config import Settings
        account = self._store.get(account_id)
        if account is None:
            return False
        now = datetime.now(timezone.utc)
        if account.locked_until is not None and account.locked_until > now:
            return True
        account.failed_attempts += 1
        if account.failed_attempts >= Settings.from_environment().lockout_threshold:
            account.locked_until = now + Settings.from_environment().lockout_duration
            account.failed_attempts = 0
        account.updated_at = now
        return account.locked_until is not None and account.locked_until > now

    def record_successful_login(self, account_id: UUID) -> None:
        account = self._store.get(account_id)
        if account is not None:
            account.failed_attempts = 0
            account.locked_until = None
            account.updated_at = datetime.now(timezone.utc)


class InMemorySchoolRepository(SchoolRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, School] = {}

    def save(self, entity: School) -> None:
        duplicate = self.find_by_emis(entity.emis_number) if entity.emis_number else None
        if duplicate is not None and duplicate.school_id != entity.school_id:
            raise ValueError("A school with this EMIS number already exists.")
        if any(s.school_id != entity.school_id and s.official_name.casefold() == entity.official_name.casefold() for s in self._store.values()):
            raise ValueError("A school with this official name already exists.")
        self._store[entity.school_id] = entity

    def find_by_id(self, entity_id: UUID) -> School | None:
        return self._store.get(entity_id)

    def find_all(self) -> List[School]:
        return sorted(self._store.values(), key=lambda s: (s.official_name.casefold(), str(s.school_id)))

    def delete(self, entity_id: UUID) -> None:
        raise ValueError("Schools cannot be deleted; change their status instead.")

    def find_by_emis(self, emis_number: str) -> School | None:
        return next((s for s in self._store.values() if s.emis_number == emis_number), None)

    def set_status(self, school_id: UUID, status: str) -> School:
        school = self._store.get(school_id)
        if school is None:
            raise KeyError("School not found.")
        school.status = status
        school.updated_at = datetime.now(timezone.utc)
        return school

    def count_status(self, status: str) -> int:
        return sum(1 for school in self._store.values() if school.status == status)


class InMemoryAccountInvitationRepository(AccountInvitationRepository):
    def __init__(self, account_repo: InMemoryUserAccountRepository, verification_repo=None, audit_repo=None) -> None:
        self._account_repo = account_repo
        self._verification_repo = verification_repo
        self._audit_repo = audit_repo
        self._records: dict[str, tuple[UUID, UUID, datetime, datetime, datetime | None, str, UUID]] = {}
        self._lock = RLock()

    def create(self, account_id, actor_id, token_digest, expires_at) -> None:
        with self._lock:
            now = datetime.now(timezone.utc)
            previous = self._latest(account_id)
            if previous is not None and now <= previous[2]:
                now = previous[2] + timedelta(microseconds=1)
            self._records[token_digest] = (account_id, actor_id, now, expires_at, None, "Pending", uuid4())

    def consume(self, token_digest: str, password: str) -> bool:
        with self._lock:
            record = self._records.get(token_digest)
            now = datetime.now(timezone.utc)
            if record is None or record[5] != "Pending" or record[4] is not None:
                return False
            if record[3] <= now:
                self._replace_status(record[6], "Expired")
                return False
            account = self._account_repo.find_by_id(record[0])
            if account is None or account.account_state.value != "Pending":
                return False
            account.reset_password(password)
            self._records[token_digest] = (*record[:4], now, "Accepted", record[6])
            return True

    def is_ready(self, account_id: UUID) -> bool:
        with self._lock:
            invitations = self._for_account(account_id)
            return not invitations or max(invitations, key=lambda record: record[2])[5] == "Accepted"

    def is_active(self, account_id: UUID) -> bool:
        with self._lock:
            now = datetime.now(timezone.utc)
            latest = self._latest(account_id)
            if latest is not None and latest[5] == "Pending" and latest[3] <= now:
                self._replace_status(latest[6], "Expired")
                return False
            return latest is not None and latest[5] == "Pending" and latest[4] is None and latest[3] > now

    def latest_status(self, account_id: UUID) -> str | None:
        with self._lock:
            invitation = self._latest(account_id)
            if invitation is None:
                return None
            if invitation[5] == "Pending" and invitation[3] <= datetime.now(timezone.utc):
                self._replace_status(invitation[6], "Expired")
                return "Expired"
            return invitation[5]

    def revoke_pending(self, account_id: UUID, actor_id: UUID, reason: str, school_id: UUID | None, university_id: UUID | None = None) -> bool:
        with self._lock:
            now = datetime.now(timezone.utc)
            invitation = self._latest(account_id)
            account = self._account_repo.find_by_id(account_id)
            if invitation is not None and invitation[5] == "Pending" and invitation[3] <= now:
                self._replace_status(invitation[6], "Expired")
                return False
            if (
                invitation is None
                or invitation[5] != "Pending"
                or invitation[4] is not None
                or account is None
                or account.account_state.value != "Pending"
            ):
                return False
            if self._verification_repo is not None:
                records = self._verification_repo.find_by_subject(account_id)
                latest = max(records, key=lambda row: (row.created_at, str(row.record_id)), default=None)
                if latest is not None and latest.outcome == "Verified":
                    return False
            if self._audit_repo is None:
                raise RuntimeError("Invitation revocation requires an audit repository.")
            is_university_admin = account.role == RoleEnum.UniversityAdmissions
            audit_event = AuditLogEntry.create(
                actor=actor_id,
                action="UniversityAdmissionsInvitationRevoked" if is_university_admin else "SchoolAdminInvitationRevoked",
                target_type="Account",
                target_id=account_id,
                old={"invitation_id": str(invitation[6]), "invitation_status": "Pending"},
                new={"invitation_id": str(invitation[6]), "invitation_status": "Revoked", "reason": reason},
                school_id=school_id,
                university_id=university_id,
            )
            # Audit first while holding the invitation lock. If persistence
            # raises, lifecycle state remains Pending and the token remains valid.
            self._audit_repo.save(audit_event)
            self._replace_status(invitation[6], "Revoked")
            return True

    def _for_account(self, account_id: UUID):
        return [record for record in self._records.values() if record[0] == account_id]

    def _latest(self, account_id: UUID):
        rows = self._for_account(account_id)
        return max(rows, key=lambda record: record[2], default=None)

    def _replace_status(self, invitation_id: UUID, status: str) -> None:
        for token_digest, record in self._records.items():
            if record[6] == invitation_id:
                self._records[token_digest] = (*record[:5], status, record[6])
                return

class InMemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, Session] = {}
        self._digest_index: dict[str, UUID] = {}

    def save(self, entity: Session) -> None:
        old = self._store.get(entity.session_id)
        if old is not None:
            self._digest_index.pop(old.token_digest, None)
        self._store[entity.session_id] = entity
        self._digest_index[entity.token_digest] = entity.session_id

    def find_by_id(self, entity_id: UUID) -> Optional[Session]:
        return self._store.get(entity_id)

    def find_all(self) -> List[Session]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        session = self._store.pop(entity_id, None)
        if session is not None:
            self._digest_index.pop(session.token_digest, None)

    def find_by_token_digest(self, token_digest: str) -> Optional[Session]:
        sid = self._digest_index.get(token_digest)
        if sid is None:
            return None
        return self._store.get(sid)

    def find_by_account(self, account_id: UUID) -> List[Session]:
        return [s for s in self._store.values() if s.account_id == account_id]


class InMemoryVerificationRecordRepository(VerificationRecordRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, VerificationRecord] = {}
        self._lock = RLock()

    def save(self, entity: VerificationRecord) -> None:
        with self._lock:
            previous = max(
                (
                    record
                    for record in self._store.values()
                    if record.subject_account_id == entity.subject_account_id
                ),
                key=lambda record: (record.created_at, str(record.record_id)),
                default=None,
            )
            if previous is not None and entity.created_at <= previous.created_at:
                entity.created_at = previous.created_at + timedelta(microseconds=1)
            self._store[entity.record_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[VerificationRecord]:
        return self._store.get(entity_id)

    def find_all(self) -> List[VerificationRecord]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_subject(self, account_id: UUID) -> List[VerificationRecord]:
        return [r for r in self._store.values() if r.subject_account_id == account_id]


class InMemoryLearnerProfileRepository(LearnerProfileRepository):
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


class InMemoryUniversityProgrammeRepository(UniversityProgrammeRepository):
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


class InMemoryApplicationRepository(ApplicationRepository):
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


class InMemoryDocumentRepository(DocumentRepository):
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


class InMemoryMarkRepository(MarkRepository):
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


class InMemoryPaymentTransactionRepository(PaymentTransactionRepository):
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


class InMemoryNotificationRepository(NotificationRepository):
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

    def find_by_event_key(self, event_key: str) -> Optional[Notification]:
        return next(
            (n for n in self._store.values() if n.event_key == event_key),
            None,
        )


class InMemoryAuditLogRepository(AuditLogRepository):
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

    def find_by_school(self, school_id: UUID) -> List[AuditLogEntry]:
        return [e for e in self._store.values() if e.school_id == school_id]

    def find_by_university(self, university_id: UUID) -> List[AuditLogEntry]:
        return [
            e for e in self._store.values() if e.university_id == university_id
        ]


class InMemoryGuidanceSessionRepository(GuidanceSessionRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, GuidanceSession] = {}

    def save(self, entity: GuidanceSession) -> None:
        self._store[entity.guidance_session_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[GuidanceSession]:
        return self._store.get(entity_id)

    def find_all(self) -> List[GuidanceSession]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_learner(self, learner_id: UUID) -> List[GuidanceSession]:
        return sorted(
            (s for s in self._store.values() if s.learner_id == learner_id),
            key=lambda session: (session.session_date, session.created_at),
        )

    def find_by_school(self, school_id: UUID) -> List[GuidanceSession]:
        return sorted(
            (s for s in self._store.values() if s.school_id == school_id),
            key=lambda session: (session.session_date, session.created_at),
        )


class InMemoryScoringRuleRepository(ScoringRuleRepository):
    """Stores ScoringRule objects keyed by university_id (REQ-002).

    One rule per university. The find_by_university query returns None when no
    rule has been registered, allowing callers to fall back to NSC_DEFAULT_SCORING_RULE.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, ScoringRule] = {}

    def save(self, entity: ScoringRule) -> None:
        self._store[entity.university_id] = entity

    def find_by_id(self, entity_id: UUID) -> Optional[ScoringRule]:
        return self._store.get(entity_id)

    def find_all(self) -> List[ScoringRule]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)

    def find_by_university(self, university_id: UUID) -> Optional[ScoringRule]:
        return self._store.get(university_id)


__all__ = [
    "InMemoryUserAccountRepository",
    "InMemorySessionRepository",
    "InMemoryVerificationRecordRepository",
    "InMemoryLearnerProfileRepository",
    "InMemoryUniversityProgrammeRepository",
    "InMemoryApplicationRepository",
    "InMemoryDocumentRepository",
    "InMemoryMarkRepository",
    "InMemoryPaymentTransactionRepository",
    "InMemoryNotificationRepository",
    "InMemoryAuditLogRepository",
    "InMemoryGuidanceSessionRepository",
    "InMemoryScoringRuleRepository",
]
