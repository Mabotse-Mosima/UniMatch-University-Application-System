from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4
from fastapi.testclient import TestClient

from unimatch.api import create_app
from unimatch.bootstrap import bootstrap_system_admin
from unimatch.entities import UserAccount
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.provisioning import AccountProvisioningService
from unimatch.repositories.inmemory import (
    InMemoryAccountInvitationRepository,
    InMemoryAuditLogRepository,
    InMemorySchoolRepository,
    InMemorySessionRepository,
    InMemoryUserAccountRepository,
    InMemoryVerificationRecordRepository,
)


def make_admin_client(audit_repository=None):
    accounts = InMemoryUserAccountRepository()
    sessions = InMemorySessionRepository()
    verifications = InMemoryVerificationRecordRepository()
    admin = bootstrap_system_admin(accounts, _email="admin@system.test", _password="SystemAdminTestPass1!")
    app = create_app(
        account_repo=accounts, session_repo=sessions,
        verification_repo=verifications, school_repo=InMemorySchoolRepository(),
        audit_repository=audit_repository,
    )
    client = TestClient(app, raise_server_exceptions=False)
    login = client.post("/api/auth/login", json={
        "email": "admin@system.test", "password": "SystemAdminTestPass1!",
    })
    assert login.status_code == 200
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    return client, admin, csrf


def add_and_activate_school(client: TestClient, csrf: str) -> str:
    response = client.post("/api/admin/schools", headers={"X-CSRF-Token": csrf}, json={
        "official_name": "Synthetic School", "emis_number": "TEST-EMIS-01",
        "province": "Gauteng", "district": "Test District",
    })
    assert response.status_code == 201, response.text
    school_id = response.json()["school_id"]
    assert response.json()["status"] == "PendingVerification"
    activated = client.post(
        f"/api/admin/schools/{school_id}/status", headers={"X-CSRF-Token": csrf},
        json={"status": "Active", "evidence_reference": "AUTHORITY-RECORD-1001"},
    )
    assert activated.status_code == 200, activated.text
    return school_id


def test_unauthenticated_admin_routes_reject_requests():
    client = TestClient(create_app(), raise_server_exceptions=False)
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/schools").status_code == 401


def test_admin_registers_school_and_arbitrary_school_assignment_is_rejected():
    client, _, csrf = make_admin_client()
    assert client.get("/api/learners").status_code == 403
    school_id = add_and_activate_school(client, csrf)
    assert client.get("/api/admin/schools").json()[0]["school_id"] == school_id
    unknown = client.post("/api/auth/provision", headers={"X-CSRF-Token": csrf}, json={
        "email": "bad-school@system.test", "password": "NotASetupFlow1!",
        "role": "SchoolAdmin", "school_id": "41fa72d7-9e03-4dbd-b3af-e5ff57a696fe",
    })
    assert unknown.status_code == 422


def test_school_admin_invitation_setup_verification_bootstrap_and_replay_block():
    client, admin, csrf = make_admin_client()
    school_id = add_and_activate_school(client, csrf)
    invitation = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "first-admin@school.test", "school_id": school_id},
    )
    assert invitation.status_code == 201, invitation.text
    data = invitation.json()
    account_id = data["account"]["account_id"]
    token = data["setup_token"]
    assert data["account"]["account_state"] == "Pending"
    assert data["account"]["credentials_ready"] is False

    password_setup = client.post("/api/auth/invitations/complete", json={
        "token": token, "password": "SchoolAdminNewPassword1!",
    })
    assert password_setup.status_code == 200
    assert client.post("/api/auth/invitations/complete", json={
        "token": token, "password": "SchoolAdminNewPassword2!",
    }).status_code == 400

    second_invitation = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "second-admin@school.test", "school_id": school_id},
    ).json()
    second_account_id = second_invitation["account"]["account_id"]
    second_password = "SecondSchoolAdminPassword1!"
    assert client.post("/api/auth/invitations/complete", json={
        "token": second_invitation["setup_token"], "password": second_password,
    }).status_code == 200

    verify = client.post(
        f"/api/auth/accounts/{account_id}/verify", headers={"X-CSRF-Token": csrf},
        json={"evidence_reference": "SCHOOL-AUTHORITY-VERIFY-01", "school_scope": [school_id]},
    )
    assert verify.status_code == 200, verify.text
    second_verify = client.post(
        f"/api/auth/accounts/{second_account_id}/verify", headers={"X-CSRF-Token": csrf},
        json={"evidence_reference": "SCHOOL-AUTHORITY-VERIFY-02", "school_scope": [school_id]},
    )
    assert second_verify.status_code == 200, second_verify.text

    def activate_once(candidate_id: str):
        return client.post(
            f"/api/admin/accounts/{candidate_id}/bootstrap-first-school-admin",
            headers={"X-CSRF-Token": csrf},
            json={"evidence_reference": "SCHOOL-BOARD-RESOLUTION-77", "reason": "Initial authorised administrator for this registered school."},
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(activate_once, [account_id, second_account_id]))
    assert sum(response.status_code == 200 for response in responses) == 1
    assert all(response.status_code in {200, 409, 422} for response in responses)
    successful_index = next(index for index, response in enumerate(responses) if response.status_code == 200)
    active_account_id = [account_id, second_account_id][successful_index]
    active_email, active_password = (
        ("first-admin@school.test", "SchoolAdminNewPassword1!")
        if active_account_id == account_id else ("second-admin@school.test", second_password)
    )
    accounts = client.get(f"/api/admin/accounts?role=SchoolAdmin&school_id={school_id}").json()
    assert sum(item["account_state"] == "Active" for item in accounts) == 1
    assert client.post(
        f"/api/admin/accounts/{active_account_id}/bootstrap-first-school-admin",
        headers={"X-CSRF-Token": csrf},
        json={"evidence_reference": "SCHOOL-BOARD-RESOLUTION-77", "reason": "Attempt to replay a completed bootstrap operation."},
    ).status_code in {409, 422}
    events = client.get("/api/audit").json()
    assert any(event["action"] == "BootstrapFirstSchoolAdmin" and event["target_id"] == active_account_id for event in events)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    login = client.post("/api/auth/login", json={
        "email": active_email, "password": active_password,
    })
    assert login.status_code == 200
    school_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    assert client.get("/api/admin/accounts").status_code == 403
    pending_account = next(item for item in accounts if item["account_state"] == "Pending")
    assert client.post(
        f"/api/admin/accounts/{pending_account['account_id']}/revoke-invitation",
        headers={"X-CSRF-Token": school_csrf},
        json={"reason": "A school administrator cannot revoke invitations."},
    ).status_code == 403
    assert client.post("/api/admin/schools", headers={"X-CSRF-Token": school_csrf}, json={
        "official_name": "Forbidden School", "province": "Gauteng", "district": "Test",
    }).status_code == 403

    admin_client = TestClient(client.app, raise_server_exceptions=False)
    assert admin_client.post("/api/auth/login", json={
        "email": "admin@system.test", "password": "SystemAdminTestPass1!",
    }).status_code == 200
    admin_csrf = admin_client.get("/api/auth/csrf").json()["csrf_token"]
    active_revoke = admin_client.post(
        f"/api/admin/accounts/{active_account_id}/revoke-invitation",
        headers={"X-CSRF-Token": admin_csrf},
        json={"reason": "Active accounts cannot be invitation-revoked."},
    )
    assert active_revoke.status_code == 409
    suspended = admin_client.post(
        f"/api/admin/schools/{school_id}/status", headers={"X-CSRF-Token": admin_csrf},
        json={"status": "Suspended", "evidence_reference": "SCHOOL-CLOSURE-REVIEW-01"},
    )
    assert suspended.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={
        "email": active_email, "password": active_password,
    }).status_code == 403
    restored = admin_client.post(
        f"/api/admin/schools/{school_id}/status", headers={"X-CSRF-Token": admin_csrf},
        json={"status": "Active", "evidence_reference": "SCHOOL-REOPEN-AUTH-01"},
    )
    assert restored.status_code == 200
    assert client.post("/api/auth/login", json={
        "email": active_email, "password": active_password,
    }).status_code == 200
    needs_review = admin_client.post(
        f"/api/admin/schools/{school_id}/status", headers={"X-CSRF-Token": admin_csrf},
        json={"status": "NeedsReview", "evidence_reference": "SCHOOL-REVIEW-REQ-01"},
    )
    assert needs_review.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={
        "email": active_email, "password": active_password,
    }).status_code == 403
    review_resolved = admin_client.post(
        f"/api/admin/schools/{school_id}/status", headers={"X-CSRF-Token": admin_csrf},
        json={"status": "Active", "evidence_reference": "SCHOOL-REVIEW-CLOSED-01"},
    )
    assert review_resolved.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={
        "email": active_email, "password": active_password,
    }).status_code == 200


def test_pending_school_admin_invitation_can_be_revoked_and_token_replay_fails():
    client, admin, csrf = make_admin_client()
    school_id = add_and_activate_school(client, csrf)
    invited = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "revoked-admin@school.test", "school_id": school_id},
    )
    assert invited.status_code == 201, invited.text
    data = invited.json()
    account_id = data["account"]["account_id"]

    revoked = client.post(
        f"/api/admin/accounts/{account_id}/revoke-invitation",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "The school requested cancellation of this invitation."},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["invitation_status"] == "Revoked"

    replay = client.post("/api/auth/invitations/complete", json={
        "token": data["setup_token"], "password": "RevokedSetupPassword1!",
    })
    assert replay.status_code == 400

    account = client.get(f"/api/admin/accounts/{account_id}")
    assert account.status_code == 200
    assert account.json()["account_state"] == "Pending"
    assert account.json()["credentials_ready"] is False
    assert account.json()["invitation_active"] is False

    events = client.get("/api/audit").json()
    event = next(
        row for row in events
        if row["action"] == "SchoolAdminInvitationRevoked" and row["target_id"] == account_id
    )
    assert event["actor_id"] == str(admin.user_id)
    assert event["new_value"]["reason"] == "The school requested cancellation of this invitation."
    assert event["timestamp"]


def test_used_or_verified_invitation_cannot_be_revoked():
    client, _, csrf = make_admin_client()
    school_id = add_and_activate_school(client, csrf)

    used = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "used-admin@school.test", "school_id": school_id},
    ).json()
    assert client.post("/api/auth/invitations/complete", json={
        "token": used["setup_token"], "password": "AlreadyUsedPassword1!",
    }).status_code == 200
    used_result = client.post(
        f"/api/admin/accounts/{used['account']['account_id']}/revoke-invitation",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "This setup invitation has already been consumed."},
    )
    assert used_result.status_code == 409

    verified = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "verified-admin@school.test", "school_id": school_id},
    ).json()
    verified_id = verified["account"]["account_id"]
    verification = client.post(
        f"/api/auth/accounts/{verified_id}/verify",
        headers={"X-CSRF-Token": csrf},
        json={"evidence_reference": "SCHOOL-AUTHORITY-VERIFY-03", "school_scope": [school_id]},
    )
    assert verification.status_code == 200, verification.text
    verified_result = client.post(
        f"/api/admin/accounts/{verified_id}/revoke-invitation",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Verified authority records must remain available."},
    )
    assert verified_result.status_code == 409


def test_revoke_audit_failure_leaves_invitation_usable():
    class FailingRevocationAuditRepository:
        def __init__(self):
            from unimatch.repositories.inmemory import InMemoryAuditLogRepository
            self.delegate = InMemoryAuditLogRepository()

        def save(self, event):
            if event.action == "SchoolAdminInvitationRevoked":
                raise RuntimeError("synthetic audit persistence failure")
            return self.delegate.save(event)

        def __getattr__(self, name):
            return getattr(self.delegate, name)

    client, _, csrf = make_admin_client(FailingRevocationAuditRepository())
    school_id = add_and_activate_school(client, csrf)
    invited = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "audit-failure-admin@school.test", "school_id": school_id},
    ).json()
    account_id = invited["account"]["account_id"]

    failed = client.post(
        f"/api/admin/accounts/{account_id}/revoke-invitation",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Test rollback when audit persistence fails."},
    )
    assert failed.status_code == 500
    account = client.get(f"/api/admin/accounts/{account_id}").json()
    assert account["invitation_status"] == "Pending"
    assert account["invitation_active"] is True
    assert client.post("/api/auth/invitations/complete", json={
        "token": invited["setup_token"], "password": "AuditFailureSetupPassword1!",
    }).status_code == 200


def test_reinvitation_preserves_history_and_invalidates_old_token():
    client, _, csrf = make_admin_client()
    school_id = add_and_activate_school(client, csrf)
    invited = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "reinvite-admin@school.test", "school_id": school_id},
    ).json()
    account_id = invited["account"]["account_id"]
    assert client.post(
        f"/api/admin/accounts/{account_id}/revoke-invitation",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "The initial invitation must be cancelled."},
    ).status_code == 200

    other_school = client.post("/api/admin/schools", headers={"X-CSRF-Token": csrf}, json={
        "official_name": "Other Synthetic School", "emis_number": "TEST-EMIS-02",
        "province": "Gauteng", "district": "Test District",
    }).json()
    client.post(
        f"/api/admin/schools/{other_school['school_id']}/status",
        headers={"X-CSRF-Token": csrf},
        json={"status": "Active", "evidence_reference": "AUTHORITY-RECORD-1002"},
    )
    cross_school = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "reinvite-admin@school.test", "school_id": other_school["school_id"]},
    )
    assert cross_school.status_code == 409

    reinvited = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "reinvite-admin@school.test", "school_id": school_id},
    )
    assert reinvited.status_code == 201, reinvited.text
    assert reinvited.json()["account"]["account_id"] == account_id
    old_replay = client.post("/api/auth/invitations/complete", json={
        "token": invited["setup_token"], "password": "OldRevokedPassword1!",
    })
    assert old_replay.status_code == 400
    accepted = client.post("/api/auth/invitations/complete", json={
        "token": reinvited.json()["setup_token"], "password": "ReplacementPassword1!",
    })
    assert accepted.status_code == 200
    assert client.get(f"/api/admin/accounts/{account_id}").json()["invitation_status"] == "Accepted"
    rejected_revoke = client.post(
        f"/api/admin/accounts/{account_id}/revoke-invitation",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "Accepted invitations cannot be revoked."},
    )
    assert rejected_revoke.status_code == 409
    events = client.get("/api/audit").json()
    assert any(item["action"] == "SchoolAdminReinvited" and item["target_id"] == account_id for item in events)


def test_concurrent_accept_and_revoke_have_one_consistent_winner():
    client, _, csrf = make_admin_client()
    school_id = add_and_activate_school(client, csrf)
    invited = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "race-admin@school.test", "school_id": school_id},
    ).json()
    account_id = invited["account"]["account_id"]
    acceptance_client = TestClient(client.app, raise_server_exceptions=False)
    assert acceptance_client.post("/api/auth/login", json={
        "email": "admin@system.test", "password": "SystemAdminTestPass1!",
    }).status_code == 200

    barrier = Barrier(2)
    def accept():
        barrier.wait()
        return acceptance_client.post("/api/auth/invitations/complete", json={
            "token": invited["setup_token"], "password": "RacingSetupPassword1!",
        })
    def revoke():
        barrier.wait()
        return client.post(
            f"/api/admin/accounts/{account_id}/revoke-invitation",
            headers={"X-CSRF-Token": csrf},
            json={"reason": "Concurrent revoke and acceptance regression test."},
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted, revoked = list(pool.map(lambda fn: fn(), (accept, revoke)))

    account = client.get(f"/api/admin/accounts/{account_id}").json()
    if accepted.status_code == 200:
        assert revoked.status_code == 409
        assert account["invitation_status"] == "Accepted"
    else:
        assert accepted.status_code == 400
        assert revoked.status_code == 200
        assert account["invitation_status"] == "Revoked"


def test_expired_invitation_transitions_to_expired_and_cannot_be_accepted_or_revoked():
    accounts = InMemoryUserAccountRepository()
    audit = InMemoryAuditLogRepository()
    invitations = InMemoryAccountInvitationRepository(accounts, audit_repo=audit)
    account = UserAccount(
        user_id=uuid4(), email="expired-admin@school.test", password_hash="unused",
        role=RoleEnum.SchoolAdmin, account_state=AccountStateEnum.Pending,
        school_id=uuid4(),
    )
    accounts.save(account)
    invitations.create(account.user_id, uuid4(), "expired-digest", datetime.now(timezone.utc))
    assert invitations.latest_status(account.user_id) == "Expired"
    assert invitations.consume("expired-digest", "ExpiredSetupPassword1!") is False
    assert invitations.revoke_pending(account.user_id, uuid4(), "Expired links cannot be revoked.", account.school_id) is False
    assert invitations.latest_status(account.user_id) == "Expired"
    assert account.password_hash == "unused"
    assert audit.find_all() == []


def test_rejected_latest_verification_invalidates_prior_approval(monkeypatch):
    fixed_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        AccountProvisioningService,
        "_utcnow",
        lambda self: fixed_timestamp,
    )
    client, _, csrf = make_admin_client()
    school_id = add_and_activate_school(client, csrf)
    invited = client.post(
        "/api/admin/school-admins/invite", headers={"X-CSRF-Token": csrf},
        json={"email": "review-admin@school.test", "school_id": school_id},
    ).json()
    account_id = invited["account"]["account_id"]
    client.post("/api/auth/invitations/complete", json={
        "token": invited["setup_token"], "password": "ReviewSchoolAdminPassword1!",
    })
    verify_url = f"/api/auth/accounts/{account_id}/verify"
    approved = {"evidence_reference": "AUTHORITY-VERIFIED-01", "school_scope": [school_id], "outcome": "Verified"}
    rejected = {"evidence_reference": "AUTHORITY-REJECTED-02", "school_scope": [school_id], "outcome": "Rejected"}
    assert client.post(verify_url, headers={"X-CSRF-Token": csrf}, json=approved).status_code == 200
    assert client.post(verify_url, headers={"X-CSRF-Token": csrf}, json=rejected).status_code == 200
    response = client.post(
        f"/api/admin/accounts/{account_id}/bootstrap-first-school-admin",
        headers={"X-CSRF-Token": csrf},
        json={"evidence_reference": "BOARD-RESOLUTION-10", "reason": "Test that a rejection overrides an earlier approval."},
    )
    assert response.status_code == 422
