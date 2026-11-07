"""
tests/test_auth.py
==================
Focused unit tests for authentication primitives (no database, no HTTP).
Tests: password hashing, session token generation, token digesting, principal.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from unimatch.auth import (
    AuthPrincipal,
    DUMMY_PASSWORD_HASH,
    digest_token,
    generate_session_token,
    hash_password,
    verify_password,
)
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.entities import Session


# ── Password hashing ─────────────────────────────────────────────────────────

class TestHashPassword:
    def test_correct_password_verifies(self):
        stored = hash_password("SecurePass1!")
        assert verify_password("SecurePass1!", stored) is True

    def test_wrong_password_fails(self):
        stored = hash_password("SecurePass1!")
        assert verify_password("WrongPass!", stored) is False

    def test_different_salts_produce_different_hashes(self):
        h1 = hash_password("SamePassword")
        h2 = hash_password("SamePassword")
        assert h1 != h2

    def test_hash_is_not_plaintext(self):
        pw = "MyPlaintextPassword"
        stored = hash_password(pw)
        assert pw not in stored

    def test_stored_format_is_versioned(self):
        stored = hash_password("anything")
        parts = stored.split("$")
        assert parts[0] == "scrypt"
        assert len(parts) == 6

    def test_empty_password_hashes_and_verifies(self):
        stored = hash_password("")
        assert verify_password("", stored) is True
        assert verify_password("notempty", stored) is False


class TestVerifyPassword:
    def test_malformed_hash_returns_false(self):
        assert verify_password("password", "not-a-hash") is False

    def test_wrong_version_returns_false(self):
        assert verify_password("password", "sha256$abc$def") is False

    def test_truncated_hash_returns_false(self):
        assert verify_password("password", "scrypt$32768$8$1$aa") is False

    def test_non_hex_salt_returns_false(self):
        assert verify_password("password", "scrypt$32768$8$1$notHex$aabbcc") is False

    def test_empty_stored_returns_false(self):
        assert verify_password("password", "") is False

    def test_plaintext_stored_returns_false(self):
        assert verify_password("password", "password") is False


# ── Session tokens ────────────────────────────────────────────────────────────

class TestSessionToken:
    def test_tokens_are_unique(self):
        tokens = {generate_session_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_token_has_reasonable_length(self):
        token = generate_session_token()
        assert len(token) >= 20

    def test_digest_is_deterministic(self):
        token = generate_session_token()
        assert digest_token(token) == digest_token(token)

    def test_digest_differs_for_different_tokens(self):
        t1 = generate_session_token()
        t2 = generate_session_token()
        assert digest_token(t1) != digest_token(t2)

    def test_digest_does_not_contain_raw_token(self):
        token = generate_session_token()
        assert token not in digest_token(token)

    def test_digest_is_hex_string(self):
        digest = digest_token("any-token")
        int(digest, 16)  # should not raise


# ── Session entity ────────────────────────────────────────────────────────────

class TestSession:
    def _make_session(self, *, offset_seconds: int = 3600) -> Session:
        now = datetime.now(timezone.utc)
        return Session(
            session_id=uuid4(),
            account_id=uuid4(),
            token_digest="digest",
            created_at=now,
            expires_at=now + timedelta(seconds=offset_seconds),
        )

    def test_active_session_is_active(self):
        session = self._make_session(offset_seconds=3600)
        assert session.is_active() is True

    def test_expired_session_is_not_active(self):
        session = self._make_session(offset_seconds=-1)
        assert session.is_active() is False

    def test_revoked_session_is_not_active(self):
        session = self._make_session(offset_seconds=3600)
        session.revoke()
        assert session.is_active() is False

    def test_revoke_sets_revoked_at(self):
        session = self._make_session()
        assert session.revoked_at is None
        session.revoke()
        assert session.revoked_at is not None


# ── AuthPrincipal ─────────────────────────────────────────────────────────────

class TestAuthPrincipal:
    def test_active_account(self):
        p = AuthPrincipal(
            account_id=uuid4(),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Active,
        )
        assert p.is_active_account() is True

    def test_pending_account_not_active(self):
        p = AuthPrincipal(
            account_id=uuid4(),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Pending,
        )
        assert p.is_active_account() is False

    def test_suspended_account_not_active(self):
        p = AuthPrincipal(
            account_id=uuid4(),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Suspended,
        )
        assert p.is_active_account() is False

    def test_has_school_access_matches(self):
        school_id = uuid4()
        p = AuthPrincipal(
            account_id=uuid4(),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Active,
            school_id=school_id,
        )
        assert p.has_school_access(school_id) is True

    def test_has_school_access_different_school(self):
        p = AuthPrincipal(
            account_id=uuid4(),
            role=RoleEnum.SchoolAdmin,
            account_state=AccountStateEnum.Active,
            school_id=uuid4(),
        )
        assert p.has_school_access(uuid4()) is False

    def test_no_school_id_returns_false(self):
        p = AuthPrincipal(
            account_id=uuid4(),
            role=RoleEnum.SystemAdmin,
            account_state=AccountStateEnum.Active,
            school_id=None,
        )
        assert p.has_school_access(uuid4()) is False


# ── Dummy password hash (timing oracle prevention) ────────────────────────────

class TestDummyPasswordHash:
    def test_valid_scrypt_format(self):
        """DUMMY_PASSWORD_HASH must parse without short-circuiting so scrypt runs."""
        parts = DUMMY_PASSWORD_HASH.split("$")
        assert len(parts) == 6
        assert parts[0] == "scrypt"
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        assert n >= 1 and r >= 1 and p >= 1

    def test_expected_output_long_enough_to_run_scrypt(self):
        """Expected output must be >= 16 bytes; shorter would short-circuit before scrypt."""
        parts = DUMMY_PASSWORD_HASH.split("$")
        expected = bytes.fromhex(parts[5])
        assert len(expected) >= 16, (
            f"DUMMY_PASSWORD_HASH expected output is {len(expected)} bytes — "
            "verify_password would short-circuit before scrypt runs"
        )

    def test_always_returns_false(self):
        """DUMMY_PASSWORD_HASH must never match any password."""
        assert verify_password("", DUMMY_PASSWORD_HASH) is False
        assert verify_password("anypassword", DUMMY_PASSWORD_HASH) is False
        assert verify_password("0" * 100, DUMMY_PASSWORD_HASH) is False

    def test_verify_password_does_not_raise_on_dummy(self):
        """verify_password must return False, not raise, when given the dummy hash."""
        result = verify_password("somepassword", DUMMY_PASSWORD_HASH)
        assert result is False
