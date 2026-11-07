"""
unimatch/auth.py
================
Authentication primitives: password hashing, session-token generation, and
the server-derived authenticated principal.

Password storage format: scrypt$N$r$p$<salt_hex>$<hash_hex>
Session tokens are opaque random strings; only their SHA-256 digest is stored.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from uuid import UUID

from unimatch.enums import AccountStateEnum, RoleEnum

# scrypt parameters (interactive login profile — NIST SP 800-132 guidance)
_N = 16384   # CPU/memory cost factor (2^14); tuned for this environment's OpenSSL memory limit
_R = 8       # block size
_P = 1       # parallelisation factor
_DKLEN = 32  # derived-key length in bytes
_SALT_LEN = 16
_VERSION = "scrypt"

SESSION_TOKEN_BYTES = 32  # 256-bit raw token → 43-char URL-safe base64
CSRF_TOKEN_BYTES = 32


def generate_csrf_token() -> str:
    """Return a cryptographically secure CSRF synchronizer token."""
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)

# Hardcoded dummy hash used only in the unknown-email login path.
# It has valid scrypt parameters and a full-length (32-byte) expected output,
# so verify_password always runs scrypt instead of short-circuiting on a length
# check. The comparison always fails — this hash does not correspond to any password.
# Prevents timing-based email enumeration by equalising work for known and unknown emails.
DUMMY_PASSWORD_HASH = (
    "scrypt$16384$8$1$"
    "a5f3c8e2b1d4e9f7a2c6b8d3e1f5a9c7"
    "$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def hash_password(password: str) -> str:
    """Hash password with scrypt and return a versioned stored string.

    Never call with an already-hashed value. The caller is responsible for
    ensuring this receives the raw plaintext password from user input.
    """
    salt = os.urandom(_SALT_LEN)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_N,
        r=_R,
        p=_P,
        dklen=_DKLEN,
    )
    return f"{_VERSION}${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify plaintext against a stored hash in constant time.

    Returns False for any malformed, unsupported, or mismatched hash.
    Never raises; any internal error is treated as verification failure.
    """
    try:
        parts = stored.split("$")
        if len(parts) != 6 or parts[0] != _VERSION:
            return False
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        if n < 1 or r < 1 or p < 1:
            return False
        salt = bytes.fromhex(parts[4])
        expected = bytes.fromhex(parts[5])
        if len(expected) < 16:
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def generate_session_token() -> str:
    """Return a cryptographically secure opaque token for a new session."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def digest_token(token: str) -> str:
    """Return the SHA-256 hex digest of a raw session token.

    The digest — never the raw token — is what gets stored in the session
    repository. Raw tokens travel only via HttpOnly cookies.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthPrincipal:
    """Server-derived, trusted authenticated identity.

    Built exclusively from verified session and account data — never from
    request-body fields or client-supplied headers.
    """
    account_id: UUID
    role: RoleEnum
    account_state: AccountStateEnum
    school_id: UUID | None = None
    university_id: UUID | None = None
    university_ids: frozenset[UUID] = frozenset()

    def is_active_account(self) -> bool:
        return self.account_state == AccountStateEnum.Active

    def has_school_access(self, school_id: UUID) -> bool:
        """True only when this principal is scoped to the given school."""
        return self.school_id is not None and self.school_id == school_id

    def has_university_access(self, university_id: UUID) -> bool:
        """True only when this principal is explicitly scoped to the university."""
        return university_id == self.university_id or university_id in self.university_ids
