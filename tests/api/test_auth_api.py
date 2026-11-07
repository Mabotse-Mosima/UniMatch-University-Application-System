"""
tests/api/test_auth_api.py
===========================
API-level tests for the login/logout/session endpoints.
Uses in-memory repos directly and the real app factory. No database required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from unimatch.api import create_app
from unimatch.auth import hash_password, digest_token, generate_session_token
from unimatch.bootstrap import bootstrap_system_admin
from unimatch.entities import Session, UserAccount
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.provisioning import AccountProvisioningService
from unimatch.repositories.inmemory import (
    InMemoryUserAccountRepository,
    InMemorySessionRepository,
    InMemoryVerificationRecordRepository,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_active_account(email: str = "admin@school.test", password: str = "TestPass1!") -> UserAccount:
    return UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash=hash_password(password),
        role=RoleEnum.SchoolAdmin,
        account_state=AccountStateEnum.Active,
    )


def _make_pending_account(email: str = "pending@school.test") -> UserAccount:
    return UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash=hash_password("TestPass1!"),
        role=RoleEnum.SchoolAdmin,
        account_state=AccountStateEnum.Pending,
    )


def _make_suspended_account(email: str = "suspended@school.test") -> UserAccount:
    return UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash=hash_password("TestPass1!"),
        role=RoleEnum.SchoolAdmin,
        account_state=AccountStateEnum.Suspended,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client_with_account():
    """Fresh in-memory app. Auth repos start empty; rejection paths don't need seeding."""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    return client


# ── Authentication endpoint tests — rejection paths ───────────────────────────

class TestAuthEndpointsUnauthenticated:
    def test_login_unknown_email_returns_401(self, client_with_account):
        resp = client_with_account.post("/api/auth/login", json={
            "email": "nobody@unknown.test",
            "password": "anypassword",
        })
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data
        assert "credential" in data["detail"].lower() or "invalid" in data["detail"].lower()

    def test_login_missing_fields_returns_422(self, client_with_account):
        resp = client_with_account.post("/api/auth/login", json={"email": "x@y.com"})
        assert resp.status_code == 422

    def test_logout_without_session_returns_200(self, client_with_account):
        resp = client_with_account.post("/api/auth/logout")
        assert resp.status_code == 200

    def test_me_without_session_returns_401(self, client_with_account):
        resp = client_with_account.get("/api/auth/me")
        assert resp.status_code == 401

    def test_login_error_response_does_not_contain_raw_token(self, client_with_account):
        resp = client_with_account.post("/api/auth/login", json={
            "email": "nobody@unknown.test",
            "password": "anypassword",
        })
        assert resp.status_code == 401
        # Response body must not look like a session token (no "session" key, no raw token)
        body = resp.text
        assert '"session"' not in body


# ── Session repo unit tests ───────────────────────────────────────────────────

class TestInMemorySessionRepository:
    def test_stores_and_retrieves_by_digest(self):
        repo = InMemorySessionRepository()
        token = generate_session_token()
        digest = digest_token(token)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=uuid4(),
            account_id=uuid4(),
            token_digest=digest,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        repo.save(session)
        found = repo.find_by_token_digest(digest)
        assert found is not None
        assert found.session_id == session.session_id

    def test_revoked_session_retrievable_but_not_active(self):
        repo = InMemorySessionRepository()
        token = generate_session_token()
        digest = digest_token(token)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=uuid4(),
            account_id=uuid4(),
            token_digest=digest,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        repo.save(session)
        session.revoke()
        repo.save(session)
        found = repo.find_by_token_digest(digest)
        assert found is not None
        assert found.is_active() is False

    def test_expired_session_not_active(self):
        repo = InMemorySessionRepository()
        token = generate_session_token()
        digest = digest_token(token)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=uuid4(),
            account_id=uuid4(),
            token_digest=digest,
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        repo.save(session)
        found = repo.find_by_token_digest(digest)
        assert found is not None
        assert found.is_active() is False

    def test_unknown_digest_returns_none(self):
        repo = InMemorySessionRepository()
        result = repo.find_by_token_digest("nonexistent-digest")
        assert result is None

    def test_raw_token_not_stored_in_repo(self):
        repo = InMemorySessionRepository()
        token = generate_session_token()
        digest = digest_token(token)
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=uuid4(),
            account_id=uuid4(),
            token_digest=digest,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        repo.save(session)
        for s in repo.find_all():
            assert token not in s.token_digest
            assert token != s.token_digest


# ── Cookie attribute tests ────────────────────────────────────────────────────

class TestProductionStartup:
    def test_production_without_secret_key_raises_at_startup(self, monkeypatch):
        """create_app() must raise RuntimeError in production mode when SECRET_KEY is absent."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError):
            create_app()

    def test_production_without_database_url_raises_at_startup(self, monkeypatch):
        """create_app() must raise RuntimeError in production mode when DATABASE_URL is absent."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "a-sufficiently-long-production-secret-key")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DATABASE_URL is required in production mode"):
            create_app(database_url=None)

    def test_development_without_secret_key_starts_successfully(self):
        """create_app() must start in development mode even without SECRET_KEY."""
        app = create_app()
        assert app is not None

    def test_development_without_database_url_starts_successfully(self):
        """create_app() in development mode without DATABASE_URL uses in-memory repos."""
        app = create_app(database_url=None)
        assert app is not None


class TestCookieAttributes:
    def test_logout_deletion_cookie_has_secure_attribute_when_configured(
        self, monkeypatch, tmp_path
    ):
        """When ENVIRONMENT signals production cookies, logout Set-Cookie includes Secure.

        Stage 2B: production mode requires DATABASE_URL, so we test cookie attributes
        by injecting in-memory repos and overriding just the environment for cookie config.
        """
        # Use development mode (no DB needed) but force ENVIRONMENT=production
        # so _cookie_secure=True is picked up by the cookie helpers.
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-cookie-attribute-test")
        monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
        # Provide a DATABASE_URL that appears non-None to trigger Postgres path,
        # but inject in-memory repos so no real connection is attempted.
        from unimatch.repositories.inmemory import (
            InMemoryUserAccountRepository,
            InMemorySessionRepository,
            InMemoryVerificationRecordRepository,
        )
        from unittest.mock import patch
        # Patch _verify_auth_schema to be a no-op so we can test cookie attributes
        # without a real database.
        with patch("unimatch.api._verify_auth_schema"):
            app = create_app(
                database_url="postgresql+psycopg://user@localhost/unimatch_test_fake",
                account_repo=InMemoryUserAccountRepository(),
                session_repo=InMemorySessionRepository(),
                verification_repo=InMemoryVerificationRecordRepository(),
            )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "secure" in set_cookie, (
            f"Logout Set-Cookie header missing 'secure' in production mode: {set_cookie!r}"
        )
        assert "samesite=strict" in set_cookie
        assert "path=/api" in set_cookie

    def test_logout_deletion_cookie_is_consistent_in_dev(self):
        """In development mode, the deletion cookie must still clear the right name/path."""
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "session=" in set_cookie
        assert "path=/api" in set_cookie
        assert "samesite=strict" in set_cookie


# ─────────────────────────────────────────────────────────────────────────────
# CSRF session security — Stage 1D regression tests
# ─────────────────────────────────────────────────────────────────────────────

def _make_school_admin_app():
    """Return (app, account_repo, session_repo, verification_repo) with one active SchoolAdmin."""
    school_id = uuid4()
    account_repo = InMemoryUserAccountRepository()
    session_repo = InMemorySessionRepository()
    verification_repo = InMemoryVerificationRecordRepository()

    from unimatch.auth import AuthPrincipal
    admin1 = bootstrap_system_admin(account_repo, _email="admin1@csrf.test", _password="AdminPass!")
    admin2 = UserAccount(
        user_id=uuid4(), email="admin2@csrf.test",
        password_hash=hash_password("Admin2Pass!"),
        role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active,
    )
    account_repo.save(admin2)

    svc = AccountProvisioningService(account_repo=account_repo, verification_repo=verification_repo)
    p1 = AuthPrincipal(account_id=admin1.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)
    p2 = AuthPrincipal(account_id=admin2.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)
    sa = svc.provision_account(p1, "sa@csrf.test", "SAPass!", RoleEnum.SchoolAdmin, school_id=school_id)
    svc.record_verification(p1, sa.user_id, "REF-CSRF", school_scope=[school_id])
    svc.activate_account(p2, sa.user_id)

    app = create_app(account_repo=account_repo, session_repo=session_repo, verification_repo=verification_repo)
    return app, school_id


class TestCsrfCrossSession:
    """A CSRF token from session A must be rejected when presented on session B."""

    def test_cross_session_csrf_token_rejected(self):
        app, school_id = _make_school_admin_app()

        # Two separate HTTP clients — each gets its own session cookie jar.
        client_a = TestClient(app, raise_server_exceptions=False)
        client_b = TestClient(app, raise_server_exceptions=False)

        # Login both clients independently.
        client_a.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_a = client_a.get("/api/auth/csrf").json()["csrf_token"]

        client_b.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_b = client_b.get("/api/auth/csrf").json()["csrf_token"]

        # The two CSRF tokens must differ (independent sessions).
        assert csrf_a != csrf_b

        # Session B cannot perform a mutation using session A's CSRF token.
        before = client_b.get("/api/learners").json()
        resp = client_b.post(
            "/api/learners",
            json={"full_name": "Cross", "school_id_number": "X", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(school_id)},
            headers={"X-CSRF-Token": csrf_a},  # A's token, B's session
        )
        assert resp.status_code == 403
        # No learner was created.
        assert client_b.get("/api/learners").json() == before

    def test_own_csrf_token_permits_mutation(self):
        app, school_id = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)
        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        resp = client.post(
            "/api/learners",
            json={"full_name": "Legit", "school_id_number": "L-01", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(school_id)},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201


class TestCsrfRevocation:
    """After a session is revoked, the associated CSRF token must no longer work."""

    def test_revoked_session_csrf_rejected(self):
        app, school_id = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Login, capture CSRF, create one learner to confirm state.
        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        client.post("/api/learners",
                    json={"full_name": "Before", "school_id_number": "B-01", "grade": 12,
                          "counselor_id": str(uuid4()), "school_id": str(school_id)},
                    headers={"X-CSRF-Token": csrf})
        before_count = len(client.get("/api/learners").json())

        # Logout (revoke session).
        resp_logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert resp_logout.status_code == 200

        # Old session cookie + old CSRF token must be rejected for mutations.
        resp = client.post(
            "/api/learners",
            json={"full_name": "After", "school_id_number": "A-01", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(school_id)},
            headers={"X-CSRF-Token": csrf},
        )
        # Auth guard rejects (401) — the revoked session is gone.
        assert resp.status_code == 401

        # /api/auth/me also fails.
        assert client.get("/api/auth/me").status_code == 401

    def test_logout_without_csrf_token_rejected_when_session_active(self):
        """Logout with an active session must be rejected if the CSRF token is missing."""
        app, school_id = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)

        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        # Session is active — /api/auth/me works.
        assert client.get("/api/auth/me").status_code == 200

        # Logout without CSRF token must be rejected.
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 403

        # Session must still be active (logout did not happen).
        assert client.get("/api/auth/me").status_code == 200

    def test_logout_without_session_succeeds_without_csrf(self):
        """Logout with no session at all is a safe no-op and does not require a CSRF token."""
        app, _ = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)
        # No login — no session cookie.
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200


class TestCsrfTokenRotation:
    """After re-login, a new CSRF token is issued; the old token must be rejected."""

    def test_new_session_gets_different_csrf_token(self):
        app, school_id = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)

        # First session.
        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_first = client.get("/api/auth/csrf").json()["csrf_token"]
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_first})

        # Second session.
        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_second = client.get("/api/auth/csrf").json()["csrf_token"]

        assert csrf_second != csrf_first

    def test_old_csrf_token_rejected_after_relogin(self):
        """The CSRF token from the previous session must not work after re-login."""
        app, school_id = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)

        # First session.
        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_old = client.get("/api/auth/csrf").json()["csrf_token"]
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_old})

        # Second session — new login.
        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})

        # Old token must be rejected (new session has a different CSRF token).
        resp = client.post(
            "/api/learners",
            json={"full_name": "Old Token", "school_id_number": "OT-1", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(school_id)},
            headers={"X-CSRF-Token": csrf_old},
        )
        assert resp.status_code == 403

    def test_new_csrf_token_permits_mutation_after_relogin(self):
        """After re-login, the new CSRF token must authorize mutations."""
        app, school_id = _make_school_admin_app()
        client = TestClient(app, raise_server_exceptions=False)

        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_old = client.get("/api/auth/csrf").json()["csrf_token"]
        client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_old})

        client.post("/api/auth/login", json={"email": "sa@csrf.test", "password": "SAPass!"})
        csrf_new = client.get("/api/auth/csrf").json()["csrf_token"]

        resp = client.post(
            "/api/learners",
            json={"full_name": "New Token", "school_id_number": "NT-1", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(school_id)},
            headers={"X-CSRF-Token": csrf_new},
        )
        assert resp.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Login lockout — Stage 2B regression tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLoginLockout:
    """Lockout tests using the in-memory repo through the real API login route."""

    def _make_lockout_app(self):
        from unimatch.auth import AuthPrincipal
        from unimatch.bootstrap import bootstrap_system_admin
        from unimatch.provisioning import AccountProvisioningService
        from unimatch.repositories.inmemory import (
            InMemoryUserAccountRepository,
            InMemorySessionRepository,
            InMemoryVerificationRecordRepository,
        )
        school_id = uuid4()
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()
        admin1 = bootstrap_system_admin(account_repo, _email="admin1@lock.test", _password="Admin1!")
        admin2 = UserAccount(
            user_id=uuid4(), email="admin2@lock.test",
            password_hash=hash_password("Admin2!"),
            role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active,
        )
        account_repo.save(admin2)
        svc = AccountProvisioningService(account_repo=account_repo, verification_repo=verification_repo)
        p1 = AuthPrincipal(account_id=admin1.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)
        p2 = AuthPrincipal(account_id=admin2.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)
        sa = svc.provision_account(p1, "victim@lock.test", "CorrectPass!", RoleEnum.SchoolAdmin, school_id=school_id)
        svc.record_verification(p1, sa.user_id, "REF-LOCK", school_scope=[school_id])
        svc.activate_account(p2, sa.user_id)
        app = create_app(account_repo=account_repo, session_repo=session_repo, verification_repo=verification_repo)
        client = TestClient(app, raise_server_exceptions=False)
        return client, account_repo, sa

    def test_failed_logins_increment_counter(self):
        client, account_repo, sa = self._make_lockout_app()
        for _ in range(3):
            client.post("/api/auth/login", json={"email": "victim@lock.test", "password": "WrongPass!"})
        account = account_repo.find_by_email("victim@lock.test")
        assert account.failed_attempts == 3

    def test_successful_login_resets_counter(self):
        client, account_repo, sa = self._make_lockout_app()
        client.post("/api/auth/login", json={"email": "victim@lock.test", "password": "WrongPass!"})
        client.post("/api/auth/login", json={"email": "victim@lock.test", "password": "WrongPass!"})
        resp = client.post("/api/auth/login", json={"email": "victim@lock.test", "password": "CorrectPass!"})
        assert resp.status_code == 200
        account = account_repo.find_by_email("victim@lock.test")
        assert account.failed_attempts == 0
        assert account.locked_until is None

    def test_account_locked_after_threshold(self, monkeypatch):
        monkeypatch.setenv("LOCKOUT_THRESHOLD", "3")
        client, account_repo, sa = self._make_lockout_app()
        for _ in range(3):
            client.post("/api/auth/login", json={"email": "victim@lock.test", "password": "WrongPass!"})
        # Now locked — even correct password must be rejected.
        resp = client.post("/api/auth/login", json={"email": "victim@lock.test", "password": "CorrectPass!"})
        assert resp.status_code == 401

    def test_record_successful_login_resets_in_memory(self):
        _, account_repo, sa = self._make_lockout_app()
        account_repo.record_failed_login(sa.user_id)
        account_repo.record_failed_login(sa.user_id)
        account_repo.record_successful_login(sa.user_id)
        account = account_repo.find_by_email("victim@lock.test")
        assert account.failed_attempts == 0
        assert account.locked_until is None

    def test_record_failed_login_re_checks_lock_under_lock(self):
        """record_failed_login does not increment counter if already locked."""
        _, account_repo, _ = self._make_lockout_app()
        # Manually lock the account.
        from datetime import datetime, timezone, timedelta
        account = account_repo.find_by_email("victim@lock.test")
        account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        account_repo.save(account)
        # Calling record_failed_login should return True and not increment.
        was_locked = account_repo.record_failed_login(account.user_id)
        assert was_locked is True
        refreshed = account_repo.find_by_email("victim@lock.test")
        assert refreshed.failed_attempts == 0  # not incremented


# ─────────────────────────────────────────────────────────────────────────────
# HIGH-1 correction — locked accounts must be denied via existing sessions
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionRejectedWhenAccountLocked:
    """An existing authenticated session must be denied when the account is locked.

    _resolve_principal re-reads account state (including locked_until) on every
    request, so lockout takes effect immediately on subsequent requests even if
    the session itself has not been revoked.
    """

    def _make_app_with_school_admin(self):
        from datetime import datetime, timezone, timedelta
        from unimatch.auth import AuthPrincipal
        from unimatch.bootstrap import bootstrap_system_admin
        from unimatch.provisioning import AccountProvisioningService

        school_id = uuid4()
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin1 = bootstrap_system_admin(
            account_repo, _email="admin1@hi1.test", _password="AdminPass!"
        )
        admin2 = UserAccount(
            user_id=uuid4(), email="admin2@hi1.test",
            password_hash=hash_password("Admin2Pass!"),
            role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active,
        )
        account_repo.save(admin2)

        svc = AccountProvisioningService(
            account_repo=account_repo, verification_repo=verification_repo
        )
        p1 = AuthPrincipal(
            account_id=admin1.user_id,
            role=RoleEnum.SystemAdmin,
            account_state=AccountStateEnum.Active,
        )
        p2 = AuthPrincipal(
            account_id=admin2.user_id,
            role=RoleEnum.SystemAdmin,
            account_state=AccountStateEnum.Active,
        )
        sa = svc.provision_account(
            p1, "sa@hi1.test", "SAPass!", RoleEnum.SchoolAdmin, school_id=school_id
        )
        svc.record_verification(p1, sa.user_id, "REF-HI1", school_scope=[school_id])
        svc.activate_account(p2, sa.user_id)

        app = create_app(
            account_repo=account_repo,
            session_repo=session_repo,
            verification_repo=verification_repo,
        )
        client = TestClient(app, raise_server_exceptions=False)
        return client, account_repo, school_id

    def test_active_session_works_before_lockout(self):
        """Baseline: an authenticated user can access a protected endpoint."""
        client, account_repo, _ = self._make_app_with_school_admin()
        client.post("/api/auth/login", json={"email": "sa@hi1.test", "password": "SAPass!"})
        resp = client.get("/api/learners")
        assert resp.status_code == 200

    def test_existing_session_denied_after_account_is_locked(self):
        """After lockout, the same session must no longer pass _resolve_principal."""
        from datetime import datetime, timezone, timedelta

        client, account_repo, _ = self._make_app_with_school_admin()
        # Establish an active session.
        client.post("/api/auth/login", json={"email": "sa@hi1.test", "password": "SAPass!"})
        assert client.get("/api/learners").status_code == 200

        # Lock the account while the session remains active and unexpired.
        account = account_repo.find_by_email("sa@hi1.test")
        account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        account_repo.save(account)

        # The same session must now be rejected.
        resp = client.get("/api/learners")
        assert resp.status_code == 401, (
            f"Locked account with active session should return 401, got {resp.status_code}"
        )

    def test_unlocked_account_still_allows_access_via_existing_session(self):
        """An account that is NOT locked continues to work via its existing session."""
        client, account_repo, _ = self._make_app_with_school_admin()
        client.post("/api/auth/login", json={"email": "sa@hi1.test", "password": "SAPass!"})
        # Confirm locked_until is None (not locked).
        account = account_repo.find_by_email("sa@hi1.test")
        assert account.locked_until is None
        resp = client.get("/api/learners")
        assert resp.status_code == 200

    def test_access_restored_after_lockout_expires(self):
        """When the lockout window passes, a valid session must work again."""
        from datetime import datetime, timezone, timedelta

        client, account_repo, _ = self._make_app_with_school_admin()
        client.post("/api/auth/login", json={"email": "sa@hi1.test", "password": "SAPass!"})

        # Set locked_until to a time already in the past — lockout has expired.
        account = account_repo.find_by_email("sa@hi1.test")
        account.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        account_repo.save(account)

        # is_locked() returns False because locked_until < now.
        assert not account.is_locked()
        resp = client.get("/api/learners")
        assert resp.status_code == 200, (
            f"Account with expired lockout and valid session should return 200, got {resp.status_code}"
        )

    def test_lockout_then_expiry_sequence(self):
        """Lock, verify denial, expire the lockout, verify access restored."""
        from datetime import datetime, timezone, timedelta

        client, account_repo, _ = self._make_app_with_school_admin()
        client.post("/api/auth/login", json={"email": "sa@hi1.test", "password": "SAPass!"})
        assert client.get("/api/learners").status_code == 200

        # Apply lockout.
        account = account_repo.find_by_email("sa@hi1.test")
        account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        account_repo.save(account)
        assert client.get("/api/learners").status_code == 401

        # Simulate lockout expiry.
        account.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        account_repo.save(account)
        assert client.get("/api/learners").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Full-flow lockout tests — exercises record_failed_login through login route
# ─────────────────────────────────────────────────────────────────────────────

class TestLoginLockoutFullFlow:
    """Tests lockout using real login requests so that record_failed_login() is
    exercised end-to-end through the API.  locked_until is never set directly
    in these tests; it is set by the repository when the threshold is reached.

    Tests use the default threshold (5) unless overridden with monkeypatch.
    Lockout expiry is simulated by setting locked_until to the past after the
    lockout has been properly triggered — verifying the time-based expiry path
    without requiring an actual 15-minute sleep.
    """

    def _make_app(self, monkeypatch=None, threshold=None, duration_seconds=None):
        """Return (app, client, account_repo) with an active SchoolAdmin."""
        if threshold is not None and monkeypatch is not None:
            monkeypatch.setenv("LOCKOUT_THRESHOLD", str(threshold))
        if duration_seconds is not None and monkeypatch is not None:
            monkeypatch.setenv("LOCKOUT_DURATION_SECONDS", str(duration_seconds))

        from unimatch.auth import AuthPrincipal
        from unimatch.bootstrap import bootstrap_system_admin
        from unimatch.provisioning import AccountProvisioningService

        school_id = uuid4()
        account_repo = InMemoryUserAccountRepository()
        session_repo = InMemorySessionRepository()
        verification_repo = InMemoryVerificationRecordRepository()

        admin1 = bootstrap_system_admin(
            account_repo, _email="admin1@flow.test", _password="AdminPass!"
        )
        admin2 = UserAccount(
            user_id=uuid4(), email="admin2@flow.test",
            password_hash=hash_password("Admin2Pass!"),
            role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active,
        )
        account_repo.save(admin2)

        svc = AccountProvisioningService(
            account_repo=account_repo, verification_repo=verification_repo
        )
        p1 = AuthPrincipal(account_id=admin1.user_id, role=RoleEnum.SystemAdmin,
                           account_state=AccountStateEnum.Active)
        p2 = AuthPrincipal(account_id=admin2.user_id, role=RoleEnum.SystemAdmin,
                           account_state=AccountStateEnum.Active)
        sa = svc.provision_account(
            p1, "sa@flow.test", "CorrectPass!", RoleEnum.SchoolAdmin, school_id=school_id
        )
        svc.record_verification(p1, sa.user_id, "REF-FLOW", school_scope=[school_id])
        svc.activate_account(p2, sa.user_id)

        app = create_app(
            account_repo=account_repo,
            session_repo=session_repo,
            verification_repo=verification_repo,
        )
        client = TestClient(app, raise_server_exceptions=False)
        return app, client, account_repo

    def _wrong(self, client, n=1):
        for _ in range(n):
            client.post("/api/auth/login",
                        json={"email": "sa@flow.test", "password": "WRONG!"})

    def test_four_failures_do_not_lock_at_default_threshold_five(self):
        """4 wrong logins with default threshold=5: account not locked, locked_until unset."""
        _, client, account_repo = self._make_app()
        self._wrong(client, 4)
        account = account_repo.find_by_email("sa@flow.test")
        assert account.failed_attempts == 4
        assert account.locked_until is None
        assert not account.is_locked()

    def test_fifth_failure_triggers_lockout_and_sets_locked_until(self):
        """5th wrong login triggers lockout: locked_until is set in the future."""
        _, client, account_repo = self._make_app()
        self._wrong(client, 5)
        account = account_repo.find_by_email("sa@flow.test")
        # record_failed_login resets failed_attempts to 0 when lockout is applied.
        assert account.failed_attempts == 0
        assert account.locked_until is not None
        assert account.is_locked()

    def test_locked_until_is_approximately_configured_duration(self):
        """locked_until after 5th failure must be approximately now + 900 s."""
        _, client, account_repo = self._make_app()
        before = datetime.now(timezone.utc)
        self._wrong(client, 5)
        after = datetime.now(timezone.utc)
        account = account_repo.find_by_email("sa@flow.test")
        assert account.locked_until is not None
        # locked_until must be between (before + 900s) and (after + 900s + 1s tolerance)
        assert account.locked_until >= before + timedelta(seconds=900)
        assert account.locked_until <= after + timedelta(seconds=901)

    def test_further_wrong_attempts_rejected_during_lockout(self):
        """A 6th wrong login attempt while locked must return 401."""
        _, client, account_repo = self._make_app()
        self._wrong(client, 5)
        resp = client.post("/api/auth/login",
                           json={"email": "sa@flow.test", "password": "WRONG!"})
        assert resp.status_code == 401

    def test_correct_password_rejected_during_lockout(self):
        """Correct password is also rejected while locked_until is in the future."""
        _, client, account_repo = self._make_app()
        self._wrong(client, 5)
        resp = client.post("/api/auth/login",
                           json={"email": "sa@flow.test", "password": "CorrectPass!"})
        assert resp.status_code == 401
        # No session was created.
        assert client.get("/api/auth/me").status_code == 401

    def test_existing_session_rejected_after_lockout_via_real_flow(self):
        """Active session is rejected after lockout triggered by real failed-login flow."""
        app, session_client, account_repo = self._make_app()
        # Establish a session for the SchoolAdmin.
        session_client.post("/api/auth/login",
                            json={"email": "sa@flow.test", "password": "CorrectPass!"})
        assert session_client.get("/api/learners").status_code == 200

        # Trigger lockout via a separate client (no session needed for wrong logins).
        attack_client = TestClient(app, raise_server_exceptions=False)
        self._wrong(attack_client, 5)

        # Original session must now be rejected (_resolve_principal checks is_locked()).
        assert session_client.get("/api/learners").status_code == 401

    def test_login_succeeds_after_lockout_expires(self):
        """After locked_until expires, login with correct password succeeds again."""
        _, client, account_repo = self._make_app()
        self._wrong(client, 5)
        assert account_repo.find_by_email("sa@flow.test").is_locked()

        # Fast-forward: move locked_until to the past.
        account = account_repo.find_by_email("sa@flow.test")
        account.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        account_repo.save(account)

        # locked_until is now in the past → is_locked() is False.
        assert not account_repo.find_by_email("sa@flow.test").is_locked()

        resp = client.post("/api/auth/login",
                           json={"email": "sa@flow.test", "password": "CorrectPass!"})
        assert resp.status_code == 200

    def test_successful_login_resets_counter_and_clears_lockout_state(self):
        """After lockout expires, a successful login clears failed_attempts and locked_until."""
        _, client, account_repo = self._make_app()
        self._wrong(client, 5)

        # Expire the lockout.
        account = account_repo.find_by_email("sa@flow.test")
        account.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        account_repo.save(account)

        client.post("/api/auth/login",
                    json={"email": "sa@flow.test", "password": "CorrectPass!"})

        account = account_repo.find_by_email("sa@flow.test")
        assert account.failed_attempts == 0
        assert account.locked_until is None
        assert not account.is_locked()

    def test_configured_threshold_respected(self, monkeypatch):
        """With threshold=3, 2 failures do not lock; 3rd failure locks."""
        _, client, account_repo = self._make_app(monkeypatch=monkeypatch, threshold=3)

        self._wrong(client, 2)
        assert not account_repo.find_by_email("sa@flow.test").is_locked()
        assert account_repo.find_by_email("sa@flow.test").failed_attempts == 2

        self._wrong(client, 1)
        assert account_repo.find_by_email("sa@flow.test").is_locked()
        assert account_repo.find_by_email("sa@flow.test").locked_until is not None

    def test_configured_duration_used_for_locked_until(self, monkeypatch):
        """With duration=1800 s, locked_until must be approximately now + 1800 s."""
        _, client, account_repo = self._make_app(
            monkeypatch=monkeypatch, threshold=2, duration_seconds=1800
        )
        before = datetime.now(timezone.utc)
        self._wrong(client, 2)
        after = datetime.now(timezone.utc)
        account = account_repo.find_by_email("sa@flow.test")
        assert account.locked_until is not None
        assert account.locked_until >= before + timedelta(seconds=1800)
        assert account.locked_until <= after + timedelta(seconds=1801)
