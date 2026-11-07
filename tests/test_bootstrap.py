"""
tests/test_bootstrap.py
========================
Database-independent tests for the SystemAdmin bootstrap function.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from unimatch.auth import hash_password, verify_password
from unimatch.bootstrap import bootstrap_system_admin
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.repositories.inmemory import InMemoryUserAccountRepository


@pytest.fixture()
def empty_repo():
    return InMemoryUserAccountRepository()


class TestBootstrapSystemAdmin:
    def test_creates_system_admin_in_active_state(self, empty_repo):
        account = bootstrap_system_admin(
            empty_repo, _email="admin@example.com", _password="SecurePass1!"
        )
        assert account.role == RoleEnum.SystemAdmin
        assert account.account_state == AccountStateEnum.Active

    def test_hashes_password_not_plaintext(self, empty_repo):
        account = bootstrap_system_admin(
            empty_repo, _email="admin@example.com", _password="SecurePass1!"
        )
        assert account.password_hash != "SecurePass1!"
        assert verify_password("SecurePass1!", account.password_hash) is True

    def test_normalizes_email_to_lowercase(self, empty_repo):
        account = bootstrap_system_admin(
            empty_repo, _email="ADMIN@Example.COM", _password="SecurePass1!"
        )
        assert account.email == "admin@example.com"

    def test_stores_account_in_repository(self, empty_repo):
        account = bootstrap_system_admin(
            empty_repo, _email="admin@example.com", _password="SecurePass1!"
        )
        stored = empty_repo.find_by_id(account.user_id)
        assert stored is not None
        assert stored.email == "admin@example.com"

    def test_creator_id_is_none_for_bootstrap(self, empty_repo):
        account = bootstrap_system_admin(
            empty_repo, _email="admin@example.com", _password="SecurePass1!"
        )
        assert account.creator_id is None

    def test_refuses_if_system_admin_already_exists(self, empty_repo):
        bootstrap_system_admin(
            empty_repo, _email="first@example.com", _password="Pass1!"
        )
        with pytest.raises(RuntimeError, match="already exists"):
            bootstrap_system_admin(
                empty_repo, _email="second@example.com", _password="Pass2!"
            )

    def test_refuses_empty_email(self, empty_repo):
        with pytest.raises(ValueError, match="Email"):
            bootstrap_system_admin(empty_repo, _email="", _password="Pass1!")

    def test_refuses_empty_password(self, empty_repo):
        with pytest.raises(ValueError, match="Password"):
            bootstrap_system_admin(
                empty_repo, _email="admin@example.com", _password=""
            )

    def test_refuses_duplicate_email(self, empty_repo):
        from unimatch.entities import UserAccount
        existing = UserAccount(
            user_id=uuid4(),
            email="admin@example.com",
            password_hash=hash_password("existing"),
            role=RoleEnum.Teacher,
        )
        empty_repo.save(existing)
        with pytest.raises(ValueError, match="already exists"):
            bootstrap_system_admin(
                empty_repo, _email="admin@example.com", _password="Pass1!"
            )

    def test_no_public_http_bootstrap_endpoint(self):
        from unimatch.api import create_app
        from fastapi.testclient import TestClient
        client = TestClient(create_app(), raise_server_exceptions=False)
        for method in (client.post, client.get):
            resp = method("/api/auth/bootstrap")
            assert resp.status_code == 404, (
                f"Bootstrap endpoint must not exist; got {resp.status_code}"
            )
