"""
tests/api/test_provisioning_api.py
====================================
Database-independent API tests for the full Stage 1B provisioning lifecycle:
bootstrap → provision → verify → activate → login → session → logout.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from unimatch.api import create_app
from unimatch.auth import hash_password
from unimatch.bootstrap import bootstrap_system_admin
from unimatch.entities import School, UserAccount, VerificationRecord
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.repositories.inmemory import (
    InMemorySessionRepository,
    InMemoryUserAccountRepository,
    InMemoryVerificationRecordRepository,
    InMemorySchoolRepository,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

SCHOOL_ID = uuid4()
SCHOOL_ID_2 = uuid4()
UNIVERSITY_ID = uuid4()


def _school_repo(*school_ids):
    repo = InMemorySchoolRepository()
    for school_id in school_ids:
        repo.save(School(
            school_id=school_id, official_name=f"Synthetic school {school_id}",
            emis_number=None, province="Test Province", district="Test District",
            contact_email=None, contact_phone=None, status="Active", creator_id=None,
        ))
    return repo


def _make_client_with_admin():
    """Create a fresh app with a bootstrapped SystemAdmin and return (client, admin_account)."""
    account_repo = InMemoryUserAccountRepository()
    session_repo = InMemorySessionRepository()
    verification_repo = InMemoryVerificationRecordRepository()
    admin = bootstrap_system_admin(
        account_repo, _email="sysadmin@unimatch.test", _password="AdminPass1!"
    )
    client = TestClient(
        create_app(
            account_repo=account_repo,
            session_repo=session_repo,
            verification_repo=verification_repo,
            school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
        ),
        raise_server_exceptions=False,
    )
    return client, admin


def _login(client, email="sysadmin@unimatch.test", password="AdminPass1!") -> str:
    """Log in and return the CSRF token for subsequent state-changing requests."""
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    csrf_resp = client.get("/api/auth/csrf")
    return csrf_resp.json()["csrf_token"]


# ── Bootstrap + login flow tests ─────────────────────────────────────────────

class TestBootstrappedLogin:
    def test_login_with_bootstrapped_admin_succeeds(self):
        client, _ = _make_client_with_admin()
        _login(client)  # asserts 200 internally
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["role"] == "SystemAdmin"

    def test_session_me_after_login(self):
        client, admin = _make_client_with_admin()
        _login(client)
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        data = me.json()
        assert data["role"] == "SystemAdmin"
        assert data["account_id"] == str(admin.user_id)

    def test_logout_revokes_session(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        assert client.get("/api/auth/me").status_code == 200
        response = client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": csrf}
        )
        assert response.status_code == 200
        assert client.get("/api/auth/me").status_code == 401

    def test_revoked_token_new_login_succeeds(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        _login(client)
        assert client.get("/api/auth/me").status_code == 200

    def test_logout_rejects_missing_or_invalid_csrf_without_revoking_session(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)

        assert client.post("/api/auth/logout").status_code == 403
        assert client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": "invalid-token"},
        ).status_code == 403
        assert client.get("/api/auth/me").status_code == 200

        assert client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        assert client.get("/api/auth/me").status_code == 401

    def test_csrf_token_rotates_after_session_revocation(self):
        client, _ = _make_client_with_admin()
        original_csrf = _login(client)
        assert client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": original_csrf},
        ).status_code == 200

        rotated_csrf = _login(client)
        assert rotated_csrf != original_csrf
        assert client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": original_csrf},
        ).status_code == 403
        assert client.get("/api/auth/me").status_code == 200
        assert client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": rotated_csrf},
        ).status_code == 200
        assert client.get("/api/auth/me").status_code == 401

    def test_openapi_endpoints_are_disabled_in_production(self, monkeypatch, tmp_path):
        database_url = "postgresql+psycopg://test:test@localhost/unimatch_test"
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "synthetic-production-test-key")
        monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
        monkeypatch.setattr(
            "unimatch.api.create_session_factory",
            lambda _url: (SimpleNamespace(dispose=lambda: None), object()),
        )
        monkeypatch.setattr("unimatch.api._verify_auth_schema", lambda _engine: None)

        app = create_app(database_url=database_url)

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None


# ── Provision endpoint tests ──────────────────────────────────────────────────

class TestProvision:
    def test_unauthenticated_cannot_provision(self):
        client, _ = _make_client_with_admin()
        resp = client.post("/api/auth/provision", json={
            "email": "new@school.test", "password": "Pass1!", "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        })
        assert resp.status_code == 401

    def test_system_admin_can_provision_school_admin(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        resp = client.post("/api/auth/provision", json={
            "email": "schooladmin@school.test",
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "SchoolAdmin"
        assert data["account_state"] == "Pending"
        assert data["school_id"] == str(SCHOOL_ID)

    def test_system_admin_can_provision_doe_official(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        resp = client.post("/api/auth/provision", json={
            "email": "doe@doe.test", "password": "DoePass1!", "role": "DoEOfficial",
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        assert resp.json()["account_state"] == "Pending"

    def test_system_admin_can_provision_university_admin(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        resp = client.post("/api/auth/provision", json={
            "email": "uniadmin@uni.test",
            "password": "UniPass1!",
            "role": "UniversityAdmissions",
            "university_id": str(UNIVERSITY_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201
        assert resp.json()["account_state"] == "Pending"

    def test_cannot_provision_system_admin_via_api(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        resp = client.post("/api/auth/provision", json={
            "email": "evil@hacker.test", "password": "EvilPass1!", "role": "SystemAdmin",
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422

    def test_duplicate_email_rejected(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        payload = {
            "email": "dup@school.test", "password": "Pass1!", "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }
        assert client.post("/api/auth/provision", json=payload, headers={"X-CSRF-Token": csrf}).status_code == 201
        assert client.post("/api/auth/provision", json=payload, headers={"X-CSRF-Token": csrf}).status_code == 409

    def test_provisioned_account_is_pending_cannot_login(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        client.post("/api/auth/provision", json={
            "email": "pending@school.test",
            "password": "PendingPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        resp = client.post("/api/auth/login", json={
            "email": "pending@school.test", "password": "PendingPass1!",
        })
        assert resp.status_code == 403


# ── Verify endpoint tests ─────────────────────────────────────────────────────

class TestVerification:
    def _provision_pending(self, client, csrf, email="schooladmin@school.test"):
        resp = client.post("/api/auth/provision", json={
            "email": email,
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201, resp.text
        return resp.json()["account_id"]

    def test_system_admin_can_record_verification(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        account_id = self._provision_pending(client, csrf)
        resp = client.post(f"/api/auth/accounts/{account_id}/verify", json={
            "evidence_reference": "DOE-2024-NW-SCH-001",
            "school_scope": [str(SCHOOL_ID)],
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "Verified"
        assert data["evidence_reference"] == "DOE-2024-NW-SCH-001"

    def test_non_system_admin_cannot_verify(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="sysadmin@test.example", _password="AdminPass1!"
        )
        doe = UserAccount(
            user_id=uuid4(),
            email="doe@doe.test",
            password_hash=hash_password("DoePass1!"),
            role=RoleEnum.DoEOfficial,
            account_state=AccountStateEnum.Active,
            creator_id=admin.user_id,
        )
        account_repo.save(doe)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf = _login(client, "doe@doe.test", "DoePass1!")
        resp = client.post(f"/api/auth/accounts/{admin.user_id}/verify", json={
            "evidence_reference": "some-ref",
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 403

    def test_empty_evidence_reference_rejected(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        account_id = self._provision_pending(client, csrf)
        resp = client.post(f"/api/auth/accounts/{account_id}/verify", json={
            "evidence_reference": "   ",
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422


# ── Activate endpoint tests ───────────────────────────────────────────────────

class TestActivation:
    def _full_provision_and_verify(self, client, csrf, email="schooladmin@school.test"):
        provision_resp = client.post("/api/auth/provision", json={
            "email": email,
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert provision_resp.status_code == 201, provision_resp.text
        account_id = provision_resp.json()["account_id"]
        verify_resp = client.post(f"/api/auth/accounts/{account_id}/verify", json={
            "evidence_reference": "DOE-2024-NW-SCH-001",
            "school_scope": [str(SCHOOL_ID)],
        }, headers={"X-CSRF-Token": csrf})
        assert verify_resp.status_code == 200, verify_resp.text
        return account_id

    def test_different_system_admin_can_activate(self):
        """Two-person rule: a second SystemAdmin activates what the first provisioned."""
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        bootstrap_system_admin(
            account_repo, _email="admin1@test.example", _password="Admin1Pass!"
        )
        admin2 = UserAccount(
            user_id=uuid4(),
            email="admin2@test.example",
            password_hash=hash_password("Admin2Pass!"),
            role=RoleEnum.SystemAdmin,
            account_state=AccountStateEnum.Active,
            creator_id=None,
        )
        account_repo.save(admin2)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf1 = _login(client, "admin1@test.example", "Admin1Pass!")
        account_id = self._full_provision_and_verify(client, csrf1)
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf1})

        csrf2 = _login(client, "admin2@test.example", "Admin2Pass!")
        resp = client.post(
            f"/api/auth/accounts/{account_id}/activate",
            headers={"X-CSRF-Token": csrf2},
        )
        assert resp.status_code == 200
        assert resp.json()["account_state"] == "Active"

    def test_creator_cannot_activate_own_provisioned_account(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        account_id = self._full_provision_and_verify(client, csrf)
        resp = client.post(
            f"/api/auth/accounts/{account_id}/activate",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_cannot_activate_without_verification(self):
        client, _ = _make_client_with_admin()
        csrf = _login(client)
        provision_resp = client.post("/api/auth/provision", json={
            "email": "noverify@school.test",
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        account_id = provision_resp.json()["account_id"]
        resp = client.post(
            f"/api/auth/accounts/{account_id}/activate",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_account_cannot_activate_itself(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="admin@test.example", _password="AdminPass1!"
        )
        self_actor = UserAccount(
            user_id=uuid4(),
            email="selfact@school.test",
            password_hash=hash_password("SelfPass1!"),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Pending,
            creator_id=admin.user_id,
        )
        account_repo.save(self_actor)
        vr = VerificationRecord(
            record_id=uuid4(),
            subject_account_id=self_actor.user_id,
            verifier_account_id=admin.user_id,
            subject_role=RoleEnum.SchoolAdmin,
            evidence_reference="REF-001",
            school_scope=[SCHOOL_ID],
            university_id=None,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            outcome="Verified",
        )
        verification_repo.save(vr)
        # Temporarily activate so they can log in to attempt self-activation
        self_actor.account_state = AccountStateEnum.Active
        account_repo.save(self_actor)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf = _login(client, "selfact@school.test", "SelfPass1!")
        # Account is Active; self-activation check fires before state check
        resp = client.post(
            f"/api/auth/accounts/{self_actor.user_id}/activate",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422

    def test_activated_account_can_login(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        bootstrap_system_admin(
            account_repo, _email="admin1@test.example", _password="Admin1Pass!"
        )
        admin2 = UserAccount(
            user_id=uuid4(),
            email="admin2@test.example",
            password_hash=hash_password("Admin2Pass!"),
            role=RoleEnum.SystemAdmin,
            account_state=AccountStateEnum.Active,
            creator_id=None,
        )
        account_repo.save(admin2)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf1 = _login(client, "admin1@test.example", "Admin1Pass!")
        provision_resp = client.post("/api/auth/provision", json={
            "email": "newschool@school.test",
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf1})
        assert provision_resp.status_code == 201
        account_id = provision_resp.json()["account_id"]
        client.post(f"/api/auth/accounts/{account_id}/verify", json={
            "evidence_reference": "DOE-2024-NW-SCH-001",
            "school_scope": [str(SCHOOL_ID)],
        }, headers={"X-CSRF-Token": csrf1})
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf1})

        csrf2 = _login(client, "admin2@test.example", "Admin2Pass!")
        activate_resp = client.post(
            f"/api/auth/accounts/{account_id}/activate",
            headers={"X-CSRF-Token": csrf2},
        )
        assert activate_resp.status_code == 200
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf2})

        login_resp = client.post("/api/auth/login", json={
            "email": "newschool@school.test", "password": "SchoolPass1!",
        })
        assert login_resp.status_code == 200
        assert login_resp.json()["role"] == "SchoolAdmin"

    def test_suspended_account_cannot_login(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="admin@test.example", _password="AdminPass1!"
        )
        suspended = UserAccount(
            user_id=uuid4(),
            email="suspended@school.test",
            password_hash=hash_password("SuspendedPass1!"),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Suspended,
            creator_id=admin.user_id,
        )
        account_repo.save(suspended)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        resp = client.post("/api/auth/login", json={
            "email": "suspended@school.test", "password": "SuspendedPass1!",
        })
        assert resp.status_code == 403


# ── DoEOfficial scope tests ───────────────────────────────────────────────────

class TestDoEOfficialScope:
    def _setup_verified_doe(self, school_scope=None):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="admin@test.example", _password="AdminPass1!"
        )
        doe = UserAccount(
            user_id=uuid4(),
            email="doe@doe.test",
            password_hash=hash_password("DoePass1!"),
            role=RoleEnum.DoEOfficial,
            account_state=AccountStateEnum.Active,
            creator_id=admin.user_id,
        )
        account_repo.save(doe)
        scope = school_scope if school_scope is not None else [SCHOOL_ID]
        vr = VerificationRecord(
            record_id=uuid4(),
            subject_account_id=doe.user_id,
            verifier_account_id=admin.user_id,
            subject_role=RoleEnum.DoEOfficial,
            evidence_reference="DOE-OFFICIAL-REF-001",
            school_scope=scope,
            university_id=None,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            outcome="Verified",
        )
        verification_repo.save(vr)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        return client, doe

    def test_verified_doe_can_provision_school_in_scope(self):
        client, _ = self._setup_verified_doe(school_scope=[SCHOOL_ID])
        csrf = _login(client, "doe@doe.test", "DoePass1!")
        resp = client.post("/api/auth/provision", json={
            "email": "schooladmin@school.test",
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 201

    def test_doe_cannot_provision_school_outside_scope(self):
        client, _ = self._setup_verified_doe(school_scope=[SCHOOL_ID])
        csrf = _login(client, "doe@doe.test", "DoePass1!")
        resp = client.post("/api/auth/provision", json={
            "email": "schooladmin2@school.test",
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID_2),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 403

    def test_doe_cannot_provision_university_admin(self):
        client, _ = self._setup_verified_doe()
        csrf = _login(client, "doe@doe.test", "DoePass1!")
        resp = client.post("/api/auth/provision", json={
            "email": "uniadmin@uni.test",
            "password": "UniPass1!",
            "role": "UniversityAdmissions",
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 403

    def test_unverified_doe_cannot_provision(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="admin@test.example", _password="AdminPass1!"
        )
        doe_unverified = UserAccount(
            user_id=uuid4(),
            email="doe_unverified@doe.test",
            password_hash=hash_password("DoePass1!"),
            role=RoleEnum.DoEOfficial,
            account_state=AccountStateEnum.Active,
            creator_id=admin.user_id,
        )
        account_repo.save(doe_unverified)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf = _login(client, "doe_unverified@doe.test", "DoePass1!")
        resp = client.post("/api/auth/provision", json={
            "email": "schooladmin@school.test",
            "password": "SchoolPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 403


# ── Role separation tests ─────────────────────────────────────────────────────

class TestRoleSeparation:
    def test_school_admin_cannot_provision_accounts(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="admin@test.example", _password="AdminPass1!"
        )
        school_admin = UserAccount(
            user_id=uuid4(),
            email="schooladmin@school.test",
            password_hash=hash_password("SchoolPass1!"),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Active,
            school_id=SCHOOL_ID,
            creator_id=admin.user_id,
        )
        account_repo.save(school_admin)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf = _login(client, "schooladmin@school.test", "SchoolPass1!")
        resp = client.post("/api/auth/provision", json={
            "email": "another@school.test",
            "password": "AnotherPass1!",
            "role": "SchoolAdmin",
            "school_id": str(SCHOOL_ID),
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 403

    def test_university_admin_cannot_provision_accounts(self):
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin = bootstrap_system_admin(
            account_repo, _email="admin@test.example", _password="AdminPass1!"
        )
        uni_admin = UserAccount(
            user_id=uuid4(),
            email="uniadmin@uni.test",
            password_hash=hash_password("UniPass1!"),
            role=RoleEnum.UniversityAdmissions,
            account_state=AccountStateEnum.Active,
            creator_id=admin.user_id,
        )
        account_repo.save(uni_admin)

        client = TestClient(
            create_app(
                account_repo=account_repo,
                session_repo=session_repo,
                verification_repo=verification_repo,
                school_repo=_school_repo(SCHOOL_ID, SCHOOL_ID_2),
            ),
            raise_server_exceptions=False,
        )
        csrf = _login(client, "uniadmin@uni.test", "UniPass1!")
        resp = client.post("/api/auth/provision", json={
            "email": "another@school.test",
            "password": "AnotherPass1!",
            "role": "SchoolAdmin",
        }, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# University verification consistency — Stage 1D regression tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUniversityVerificationConsistency:
    """VerificationRecord.university_id must match account.university_id for activation."""

    def _setup(self, school_ids=()):
        """Return two admins, a provisioning service, and an app with shared repos."""
        uni_a = uuid4()
        uni_b = uuid4()
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin1 = bootstrap_system_admin(account_repo, _email="admin1@uvc.test", _password="Admin1Pass!")
        admin2 = UserAccount(
            user_id=uuid4(), email="admin2@uvc.test",
            password_hash=hash_password("Admin2Pass!"),
            role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active,
        )
        account_repo.save(admin2)

        from unimatch.provisioning import AccountProvisioningService
        from unimatch.auth import AuthPrincipal
        svc = AccountProvisioningService(account_repo=account_repo, verification_repo=verification_repo)
        p1 = AuthPrincipal(account_id=admin1.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)
        p2 = AuthPrincipal(account_id=admin2.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)

        app = create_app(account_repo=account_repo, session_repo=session_repo, verification_repo=verification_repo,
                         school_repo=_school_repo(*school_ids))
        client = TestClient(app, raise_server_exceptions=False)
        return client, svc, p1, p2, uni_a, uni_b

    def test_matching_university_permits_activation(self):
        """A VerificationRecord with university_id matching the account activates successfully."""
        client, svc, p1, p2, uni_a, _ = self._setup()

        ua = svc.provision_account(p1, "ua@uvc.test", "UAPass!", RoleEnum.UniversityAdmissions, university_id=uni_a)
        svc.record_verification(p1, ua.user_id, "REF-A", university_id=uni_a)  # matches account

        csrf1 = _login(client, "admin1@uvc.test", "Admin1Pass!")
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf1})
        csrf2 = _login(client, "admin2@uvc.test", "Admin2Pass!")
        resp = client.post(f"/api/auth/accounts/{ua.user_id}/activate", headers={"X-CSRF-Token": csrf2})
        assert resp.status_code == 200
        assert resp.json()["account_state"] == "Active"

    def test_mismatched_university_prevents_activation(self):
        """A VerificationRecord for a different university must block activation."""
        client, svc, p1, p2, uni_a, uni_b = self._setup()

        ua = svc.provision_account(p1, "ua@uvc.test", "UAPass!", RoleEnum.UniversityAdmissions, university_id=uni_a)
        svc.record_verification(p1, ua.user_id, "REF-B", university_id=uni_b)  # WRONG university

        csrf1 = _login(client, "admin1@uvc.test", "Admin1Pass!")
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf1})
        csrf2 = _login(client, "admin2@uvc.test", "Admin2Pass!")
        resp = client.post(f"/api/auth/accounts/{ua.user_id}/activate", headers={"X-CSRF-Token": csrf2})
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Required account verification is incomplete."

    def test_missing_university_scope_in_verification_prevents_activation(self):
        """A VerificationRecord with no university_id must block activation of a UniversityAdmissions account."""
        client, svc, p1, p2, uni_a, _ = self._setup()

        ua = svc.provision_account(p1, "ua@uvc.test", "UAPass!", RoleEnum.UniversityAdmissions, university_id=uni_a)
        svc.record_verification(p1, ua.user_id, "REF-NOUNIV", university_id=None)  # no scope

        csrf1 = _login(client, "admin1@uvc.test", "Admin1Pass!")
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf1})
        csrf2 = _login(client, "admin2@uvc.test", "Admin2Pass!")
        resp = client.post(f"/api/auth/accounts/{ua.user_id}/activate", headers={"X-CSRF-Token": csrf2})
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Required account verification is incomplete."

    def test_school_admin_activation_unaffected_by_university_check(self):
        """The university scope check must not affect SchoolAdmin activation."""
        school_id = uuid4()
        client, svc, p1, p2, _, _ = self._setup([school_id])

        sa = svc.provision_account(p1, "sa@uvc.test", "SAPass!", RoleEnum.SchoolAdmin, school_id=school_id)
        svc.record_verification(p1, sa.user_id, "REF-SA", school_scope=[school_id])

        csrf1 = _login(client, "admin1@uvc.test", "Admin1Pass!")
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf1})
        csrf2 = _login(client, "admin2@uvc.test", "Admin2Pass!")
        resp = client.post(f"/api/auth/accounts/{sa.user_id}/activate", headers={"X-CSRF-Token": csrf2})
        assert resp.status_code == 200
        assert resp.json()["account_state"] == "Active"
