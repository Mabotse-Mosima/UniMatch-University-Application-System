"""
unimatch/provisioning.py
========================
Account provisioning, verification recording, and two-person activation.

Service-layer enforcement — never trust caller-supplied actor IDs.
All actor identities are derived from the AuthPrincipal resolved from session.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from unimatch.auth import AuthPrincipal, hash_password
from unimatch.entities import UserAccount, VerificationRecord
from unimatch.enums import AccountStateEnum, RoleEnum


# ---------------------------------------------------------------------------
# Domain errors
# ---------------------------------------------------------------------------

class ProvisioningError(Exception):
    pass

class NotAuthorizedError(ProvisioningError):
    pass

class AccountAlreadyExistsError(ProvisioningError):
    pass

class AccountNotFoundError(ProvisioningError):
    pass

class NotVerifiedError(ProvisioningError):
    """Target account has no accepted verification record."""
    pass

class SelfActivationError(ProvisioningError):
    """Creator or target attempted to activate their own account."""
    pass

class AlreadyActiveError(ProvisioningError):
    pass

class InvalidRoleForProvisioningError(ProvisioningError):
    pass

class OutOfScopeError(ProvisioningError):
    """Actor attempted an operation outside their verified scope."""
    pass


# ---------------------------------------------------------------------------
# AccountProvisioningService
# ---------------------------------------------------------------------------

@dataclass
class AccountProvisioningService:
    """Enforces account lifecycle rules in the service layer.

    All actor identities are server-derived (AuthPrincipal). Caller-supplied
    actor IDs in request bodies are never used here.
    """
    account_repo: object  # UserAccountRepository
    verification_repo: object  # VerificationRecordRepository

    _PROVISIONABLE = frozenset({
        RoleEnum.SchoolAdmin,
        RoleEnum.DoEOfficial,
        RoleEnum.UniversityAdmissions,
    })

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _require_active(self, actor: AuthPrincipal) -> None:
        if not actor.is_active_account():
            raise NotAuthorizedError("Actor account is not active.")

    def _get_account(self, account_id: UUID) -> UserAccount:
        account = self.account_repo.find_by_id(account_id)
        if account is None:
            raise AccountNotFoundError(f"Account {account_id} not found.")
        return account

    def _get_verified_record(self, account_id: UUID) -> VerificationRecord:
        records = self.verification_repo.find_by_subject(account_id)
        latest = max(records, key=lambda r: (r.created_at, str(r.record_id)), default=None)
        if latest is None or latest.outcome != "Verified":
            raise NotVerifiedError(
                f"Account {account_id} has no current accepted verification record. "
                "The most recent verification must be approved by a SystemAdmin."
            )
        return latest

    def provision_account(
        self,
        actor: AuthPrincipal,
        email: str,
        password: str,
        role: RoleEnum,
        school_id: UUID | None = None,
        university_id: UUID | None = None,
    ) -> UserAccount:
        """Create a new account in Pending state.

        Only SystemAdmin and (within scope) verified DoEOfficial may provision accounts.
        SystemAdmin is never provisionable through this method.
        """
        self._require_active(actor)

        if role not in self._PROVISIONABLE:
            raise InvalidRoleForProvisioningError(
                f"Role {role.value!r} cannot be provisioned through this service. "
                "SystemAdmin accounts are created only via the secure bootstrap process."
            )

        if actor.role == RoleEnum.SystemAdmin:
            pass
        elif actor.role == RoleEnum.DoEOfficial:
            if role != RoleEnum.SchoolAdmin:
                raise NotAuthorizedError(
                    "DoEOfficials may only provision SchoolAdmin accounts."
                )
            try:
                doe_record = self._get_verified_record(actor.account_id)
            except NotVerifiedError as exc:
                raise NotAuthorizedError(
                    "DoEOfficial account has no current verified record. "
                    "Verification is required before provisioning SchoolAdmin accounts."
                ) from exc
            if school_id is None or school_id not in doe_record.school_scope:
                raise OutOfScopeError(
                    "School is not within this DoEOfficial's verified scope."
                )
        else:
            raise NotAuthorizedError(
                f"Role {actor.role.value!r} is not authorized to provision accounts."
            )

        normalized_email = email.strip().lower()
        if not normalized_email:
            raise ValueError("Email cannot be empty.")
        if not password:
            raise ValueError("Password cannot be empty.")
        if self.account_repo.find_by_email(normalized_email) is not None:
            raise AccountAlreadyExistsError(
                "An account with that email already exists."
            )

        account = UserAccount(
            user_id=uuid4(),
            email=normalized_email,
            password_hash=hash_password(password),
            role=role,
            account_state=AccountStateEnum.Pending,
            school_id=school_id,
            university_id=university_id,
            creator_id=actor.account_id,
        )
        self.account_repo.save(account)
        return account

    def record_verification(
        self,
        actor: AuthPrincipal,
        target_id: UUID,
        evidence_reference: str,
        school_scope: list[UUID] | None = None,
        university_id: UUID | None = None,
        outcome: str = "Verified",
    ) -> VerificationRecord:
        """Record an authorized operator's review of identity evidence.

        Only SystemAdmin may record verification. The operator must have
        reviewed evidence from an authoritative external source.
        """
        self._require_active(actor)
        if actor.role != RoleEnum.SystemAdmin:
            raise NotAuthorizedError(
                "Only SystemAdmin may record verification of accounts."
            )

        target = self._get_account(target_id)

        if not evidence_reference.strip():
            raise ValueError("evidence_reference cannot be empty.")
        if outcome not in {"Verified", "Rejected"}:
            raise ValueError("Verification outcome must be Verified or Rejected.")
        if target.role == RoleEnum.SchoolAdmin and (
            target.school_id is None or target.school_id not in (school_scope or [])
        ):
            raise NotVerifiedError(
                "SchoolAdmin verification must be scoped to the account's assigned school."
            )

        record = VerificationRecord(
            record_id=uuid4(),
            subject_account_id=target_id,
            verifier_account_id=actor.account_id,
            subject_role=self._get_account(target_id).role,
            evidence_reference=evidence_reference.strip(),
            school_scope=list(school_scope or []),
            university_id=university_id,
            created_at=self._utcnow(),
            outcome=outcome,
        )
        self.verification_repo.save(record)
        return record

    def activate_account(
        self,
        actor: AuthPrincipal,
        target_id: UUID,
    ) -> UserAccount:
        """Activate a verified Pending account.

        Two-person rule: the activator must differ from both the creator
        and the target account itself.
        """
        self._require_active(actor)

        target = self._get_account(target_id)

        if actor.account_id == target.user_id:
            raise SelfActivationError("An account cannot activate itself.")

        if target.creator_id is not None and actor.account_id == target.creator_id:
            raise SelfActivationError(
                "The account creator cannot activate the account they provisioned. "
                "A different authorized person must perform activation."
            )

        if target.account_state != AccountStateEnum.Pending:
            if target.account_state == AccountStateEnum.Active:
                raise AlreadyActiveError(f"Account {target_id} is already active.")
            raise ProvisioningError(
                f"Account {target_id} is in {target.account_state.value} state "
                "and cannot be activated."
            )

        verified_record = self._get_verified_record(target_id)

        # For UniversityAdmissions accounts the verification record must carry
        # a university scope that matches the university assigned to the account.
        # A record with no university scope, or one issued for a different university,
        # does not authorize activation of this account.
        if target.role == RoleEnum.UniversityAdmissions:
            if verified_record.university_id is None:
                raise NotVerifiedError(
                    "The verification record for this UniversityAdmissions account "
                    "does not include a university scope. Verification must record "
                    "the specific university before activation."
                )
            if verified_record.university_id != target.university_id:
                raise NotVerifiedError(
                    "The verification record's university does not match the university "
                    "assigned to this account. Re-verify with the correct university "
                    "before activating."
                )

        if target.role == RoleEnum.SchoolAdmin:
            if target.school_id is None or target.school_id not in verified_record.school_scope:
                raise NotVerifiedError(
                    "The verification record must include the SchoolAdmin's assigned school."
                )
        if actor.role == RoleEnum.SystemAdmin:
            pass
        elif actor.role == RoleEnum.DoEOfficial:
            if target.role != RoleEnum.SchoolAdmin:
                raise NotAuthorizedError(
                    "DoEOfficials may only activate SchoolAdmin accounts."
                )
            try:
                doe_record = self._get_verified_record(actor.account_id)
            except NotVerifiedError as exc:
                raise NotAuthorizedError("DoEOfficial account has no current verified record.") from exc
            if target.school_id is None or target.school_id not in doe_record.school_scope:
                raise OutOfScopeError(
                    "Target school is not within this DoEOfficial's verified scope."
                )
        else:
            raise NotAuthorizedError(
                f"Role {actor.role.value!r} is not authorized to activate accounts."
            )

        return self.account_repo.activate_with_lock(target_id, actor)

    def suspend_account(
        self,
        actor: AuthPrincipal,
        target_id: UUID,
    ) -> UserAccount:
        """Suspend an active account. Only SystemAdmin may suspend."""
        self._require_active(actor)
        if actor.role != RoleEnum.SystemAdmin:
            raise NotAuthorizedError("Only SystemAdmin may suspend accounts.")

        target = self._get_account(target_id)
        if actor.account_id == target.user_id:
            raise SelfActivationError("SystemAdmin cannot suspend their own account.")

        if target.account_state != AccountStateEnum.Active:
            raise ProvisioningError("Only an Active account can be suspended.")
        return self.account_repo.set_account_state(target_id, AccountStateEnum.Suspended)


__all__ = [
    "AccountProvisioningService",
    "ProvisioningError",
    "NotAuthorizedError",
    "AccountAlreadyExistsError",
    "AccountNotFoundError",
    "NotVerifiedError",
    "SelfActivationError",
    "AlreadyActiveError",
    "InvalidRoleForProvisioningError",
    "OutOfScopeError",
]
