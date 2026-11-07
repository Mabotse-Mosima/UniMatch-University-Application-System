"""
unimatch/bootstrap.py
=====================
Secure operator-run command to create the initial SystemAdmin account.

This module does NOT expose any HTTP endpoint. The account is created only
through this CLI function, which requires direct operator access to the
running process.

IMPORTANT: In Stage 1B the repository is in-memory. The bootstrapped account
will not persist across application restarts. Stage 2 (persistent storage)
is required before this bootstrap is meaningful in production.
"""
from __future__ import annotations

import os
import sys
from uuid import uuid4

from unimatch.auth import hash_password
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.entities import UserAccount


def bootstrap_system_admin(
    account_repo,
    *,
    _email: str | None = None,
    _password: str | None = None,
) -> UserAccount:
    """Create the initial SystemAdmin in the given repository.

    Parameters _email and _password are for automated tests only and must
    never be supplied via command-line arguments in production. When omitted,
    the function prompts securely via getpass so the password is never echoed.

    Raises RuntimeError if a SystemAdmin already exists in the repository.
    Raises ValueError for empty or invalid credentials.
    """
    existing = account_repo.find_by_role(RoleEnum.SystemAdmin)
    if existing:
        raise RuntimeError(
            "A SystemAdmin account already exists. "
            "Bootstrap refuses to create a second initial administrator."
        )

    if _email is not None:
        email = _email.strip().lower()
    else:
        try:
            email = input("SystemAdmin email: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise ValueError("Bootstrap cancelled.")

    if not email:
        raise ValueError("Email cannot be empty.")

    if account_repo.find_by_email(email) is not None:
        raise ValueError("An account with that email already exists.")

    if _password is not None:
        password = _password
    else:
        import getpass as _getpass
        try:
            password = _getpass.getpass("SystemAdmin password: ")
            confirm = _getpass.getpass("Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            raise ValueError("Bootstrap cancelled.")
        if password != confirm:
            raise ValueError("Passwords do not match.")

    if not password:
        raise ValueError("Password cannot be empty.")

    account = UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash=hash_password(password),
        role=RoleEnum.SystemAdmin,
        account_state=AccountStateEnum.Active,
        creator_id=None,
    )
    account_repo.save(account)
    return account


def bootstrap_system_admin_postgres(database_url: str) -> "UserAccount":
    """Create the initial SystemAdmin in the configured PostgreSQL database.

    Connects to the same database used by the running application. Prompts
    for credentials interactively (password via getpass — never echoed).
    Handles concurrent bootstrap attempts safely via the database's partial
    unique index on (role) WHERE role = 'SystemAdmin'.

    Never logs the database_url, password, or any credential.
    On success, returns the created UserAccount.

    Raises RuntimeError if a SystemAdmin already exists or tables are absent.
    Raises ValueError for empty or invalid credentials.
    """
    from unimatch.database import create_session_factory
    from unimatch.repositories.postgres import PostgresUserAccountRepository
    from unimatch.api import _verify_auth_schema

    engine, session_factory = create_session_factory(database_url)
    try:
        _verify_auth_schema(engine)
        account_repo = PostgresUserAccountRepository(session_factory)
        return bootstrap_system_admin(account_repo)
    finally:
        engine.dispose()


def main() -> None:  # pragma: no cover
    """CLI entry point — not callable from HTTP."""
    use_postgres = "--postgres" in sys.argv

    if use_postgres:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            print(
                "Bootstrap failed: DATABASE_URL environment variable is not set.\n"
                "Load it from a protected secret source before running bootstrap.",
                file=sys.stderr,
            )
            sys.exit(1)
        print("UniMatch — Production SystemAdmin Bootstrap")
        print("Connecting to the configured PostgreSQL database...")
        print()
        try:
            account = bootstrap_system_admin_postgres(database_url)
            print(f"\nSystemAdmin created: {account.email}")
            print(f"Account ID:         {account.user_id}")
            print("\nNext: provision and activate additional accounts via the API.")
        except (ValueError, RuntimeError) as exc:
            print(f"\nBootstrap failed: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        print("UniMatch — SystemAdmin Bootstrap")
        print()
        print("WARNING: This creates an in-memory account for development only.")
        print("Use '--postgres' with DATABASE_URL set for production bootstrap.")
        print()
        from unimatch.repositories.inmemory import InMemoryUserAccountRepository
        repo = InMemoryUserAccountRepository()
        try:
            account = bootstrap_system_admin(repo)
            print(f"\nSystemAdmin created: {account.email}")
            print(f"Account ID: {account.user_id}")
            print("\nWARNING: This account is in-memory and will not persist across restarts.")
        except (ValueError, RuntimeError) as exc:
            print(f"\nBootstrap failed: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
