"""
tests/integration/test_auth_postgres.py
=========================================
PostgreSQL integration tests for Stage 2B authentication persistence.

These tests require:
  UNIMATCH_TEST_DATABASE_URL  — a local psycopg URL whose database name ends in _test
  UNIMATCH_TEST_DATABASE_APPROVED=1  — explicit confirmation the test database is safe

No test runs without both variables set. These tests are excluded from the default
suite (pytest --ignore=tests/integration).

SAFETY: All tests run inside uniquely named PostgreSQL schemas created for each
fixture invocation. Tables in the public schema are NEVER created, read, modified
or dropped. Schema names follow the pattern `unimatch_auth_test_{16-hex-chars}`.
The schema is unconditionally dropped in the fixture's finally block.

DO NOT run against the production or development database.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from unimatch.auth import (
    AuthPrincipal,
    digest_token,
    generate_csrf_token,
    generate_session_token,
    hash_password,
)
from unimatch.db_models import Base, SchoolRecord
from unimatch.entities import Session, UserAccount, VerificationRecord
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.provisioning import AccountAlreadyExistsError
from unimatch.repositories.postgres import (
    PostgresSessionRepository,
    PostgresUserAccountRepository,
    PostgresVerificationRecordRepository,
)


# ─────────────────────────────────────────────────────────────────────────────
# Safety guards — identical to the existing business-repo integration tests
# ─────────────────────────────────────────────────────────────────────────────

def _safe_test_url() -> URL:
    raw_url = os.environ.get("UNIMATCH_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "Set UNIMATCH_TEST_DATABASE_URL to run PostgreSQL auth integration tests"
        )
    if os.environ.get("UNIMATCH_TEST_DATABASE_APPROVED") != "1":
        pytest.skip(
            "Set UNIMATCH_TEST_DATABASE_APPROVED=1 after verifying the test database"
        )

    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database is None
        or not url.database.endswith("_test")
    ):
        pytest.fail(
            "Auth integration tests require a local psycopg URL "
            "whose database name ends in _test"
        )

    application_url = os.environ.get("DATABASE_URL")
    if application_url and (
        make_url(application_url).render_as_string(hide_password=True)
        == url.render_as_string(hide_password=True)
    ):
        pytest.fail("The integration test URL must be separate from DATABASE_URL")

    return url


# ─────────────────────────────────────────────────────────────────────────────
# Schema-isolation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_alembic_on_schema(engine, schema_name: str) -> None:
    """Run all Alembic migrations inside the isolated schema.

    Injects a pre-configured connection into migrations/env.py via
    config.attributes['connection'] so that env.py uses the given connection
    (with search_path already set) rather than building a new engine.

    The injected connection path in env.py was added in Stage 2C-A to support
    this pattern without modifying the migration scripts themselves.
    """
    from alembic import command as alembic_command
    from alembic.config import Config

    alembic_root = Path(__file__).parents[2]
    cfg = Config(str(alembic_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(alembic_root / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(alembic_root / "src"))

    with engine.connect() as conn:
        # Direct all unqualified DDL into the isolated schema.
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        conn.commit()   # search_path is session-level; commit flushes any open txn
        cfg.attributes["connection"] = conn
        alembic_command.upgrade(cfg, "head")


# ─────────────────────────────────────────────────────────────────────────────
# Fixture A — ORM-level repository tests (Base.metadata.create_all)
#
# Uses schema_translate_map (same pattern as test_postgres_repositories.py).
# The public schema is never touched.  Drop schema is unconditional (finally).
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def orm_factory():
    """Fresh schema for each repository-level integration test."""
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_auth_test_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {quote(schema_name)}"))

    isolated_engine = engine.execution_options(
        schema_translate_map={None: schema_name}
    )
    try:
        Base.metadata.create_all(isolated_engine)
        factory = sessionmaker(bind=isolated_engine, expire_on_commit=False)
        yield factory, engine, schema_name
    finally:
        Base.metadata.drop_all(isolated_engine)
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {quote(schema_name)} CASCADE"))
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Fixture B — Migration-level verification (actual Alembic upgrade)
#
# Runs the real Alembic migrations (0001_initial + 0002_auth_tables) inside an
# isolated schema so that migration-produced DDL (functional indexes, FK rules,
# partial unique indexes) can be inspected without touching the public schema.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def migration_schema():
    """Isolated schema populated via actual Alembic migrations."""
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_migr_test_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {quote(schema_name)}"))

    try:
        _run_alembic_on_schema(engine, schema_name)
        yield engine, schema_name
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {quote(schema_name)} CASCADE"))
        engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_account(
    email: str,
    role: RoleEnum = RoleEnum.SchoolAdmin,
    state: AccountStateEnum = AccountStateEnum.Active,
    failed_attempts: int = 0,
) -> UserAccount:
    return UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash=hash_password("TestPass1!"),
        role=role,
        account_state=state,
        failed_attempts=failed_attempts,
    )


def _uid() -> str:
    """Short random hex suffix for unique email addresses within a test run."""
    return uuid4().hex[:8]


# ─────────────────────────────────────────────────────────────────────────────
# Fixture A tests — ORM-level repository behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountPersistence:
    """Account records survive new sessionmaker instances (simulates restart)."""

    def test_account_survives_new_session_factory(self, orm_factory):
        factory, *_ = orm_factory
        repo1 = PostgresUserAccountRepository(factory)
        account = _make_account(
            f"persist_{_uid()}@test.com",
            role=RoleEnum.SystemAdmin,
        )
        repo1.save(account)
        repo2 = PostgresUserAccountRepository(factory)
        found = repo2.find_by_email(account.email)
        assert found is not None
        assert found.user_id == account.user_id
        assert found.role == RoleEnum.SystemAdmin

    def test_account_state_persists(self, orm_factory):
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"state_{_uid()}@test.com"
        account = _make_account(email, state=AccountStateEnum.Pending)
        repo.save(account)
        found = repo.find_by_email(email)
        assert found is not None
        assert found.account_state == AccountStateEnum.Pending

    def test_case_insensitive_email_lookup(self, orm_factory):
        """find_by_email must find an account regardless of the caller's capitalisation."""
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"case_{_uid()}@test.com"
        account = _make_account(email)
        repo.save(account)
        found = repo.find_by_email(email.upper())
        assert found is not None
        assert found.user_id == account.user_id

    def test_duplicate_email_raises_account_already_exists_error(self, orm_factory):
        """MEDIUM-1 verification: save() must map email UniqueViolation to
        AccountAlreadyExistsError via constraint_name substring matching."""
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"dup_{_uid()}@test.com"
        repo.save(_make_account(email))
        with pytest.raises(AccountAlreadyExistsError):
            repo.save(_make_account(email))

    def test_duplicate_system_admin_raises_runtime_error(self, orm_factory):
        """MEDIUM-1 verification: second SystemAdmin must raise RuntimeError via
        uq_accounts_single_system_admin partial unique index."""
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        repo.save(_make_account(f"sa1_{_uid()}@test.com", role=RoleEnum.SystemAdmin))
        with pytest.raises(RuntimeError, match="already exists"):
            repo.save(_make_account(f"sa2_{_uid()}@test.com", role=RoleEnum.SystemAdmin))


class TestSessionPersistence:
    """Session state survives new sessionmaker instances."""

    def test_active_session_persists(self, orm_factory):
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        session_repo = PostgresSessionRepository(factory)
        account = _make_account(f"sess_{_uid()}@test.com")
        account_repo.save(account)
        token = generate_session_token()
        s = Session(
            session_id=uuid4(),
            account_id=account.user_id,
            token_digest=digest_token(token),
            csrf_token=generate_csrf_token(),
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session_repo.save(s)
        repo2 = PostgresSessionRepository(factory)
        found = repo2.find_by_token_digest(digest_token(token))
        assert found is not None
        assert found.is_active()
        assert found.account_id == account.user_id

    def test_csrf_token_persists_bound_to_session(self, orm_factory):
        """csrf_token column must survive a round-trip and be retrievable."""
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        session_repo = PostgresSessionRepository(factory)
        account = _make_account(f"csrf_{_uid()}@test.com")
        account_repo.save(account)
        csrf = generate_csrf_token()
        s = Session(
            session_id=uuid4(),
            account_id=account.user_id,
            token_digest=digest_token(generate_session_token()),
            csrf_token=csrf,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session_repo.save(s)
        found = session_repo.find_by_id(s.session_id)
        assert found is not None
        assert found.csrf_token == csrf

    def test_revoked_session_inactive_after_new_factory(self, orm_factory):
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        session_repo = PostgresSessionRepository(factory)
        account = _make_account(f"revoke_{_uid()}@test.com")
        account_repo.save(account)
        token = generate_session_token()
        s = Session(
            session_id=uuid4(),
            account_id=account.user_id,
            token_digest=digest_token(token),
            csrf_token=generate_csrf_token(),
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session_repo.save(s)
        s.revoke()
        session_repo.save(s)
        repo2 = PostgresSessionRepository(factory)
        found = repo2.find_by_token_digest(digest_token(token))
        assert found is not None
        assert not found.is_active()

    def test_expired_session_inactive(self, orm_factory):
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        session_repo = PostgresSessionRepository(factory)
        account = _make_account(f"exp_{_uid()}@test.com")
        account_repo.save(account)
        token = generate_session_token()
        s = Session(
            session_id=uuid4(),
            account_id=account.user_id,
            token_digest=digest_token(token),
            csrf_token=generate_csrf_token(),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session_repo.save(s)
        found = session_repo.find_by_token_digest(digest_token(token))
        assert found is not None
        assert not found.is_active()

    def test_lockout_visible_across_separate_session_factories(self, orm_factory):
        """Lockout state written by one session must be immediately visible to another.

        This simulates two separate API instances sharing the PostgreSQL database:
        one triggers lockout, the other must observe it.
        """
        factory, *_ = orm_factory
        repo_a = PostgresUserAccountRepository(factory)
        email = f"lock_vis_{_uid()}@test.com"
        account = _make_account(email, failed_attempts=0)
        repo_a.save(account)

        # Simulate the lockout being set (as record_failed_login does at threshold).
        from datetime import datetime, timezone, timedelta
        locked_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        account2 = repo_a.find_by_email(email)
        account2.locked_until = locked_at
        repo_a.save(account2)

        # A separate sessionmaker (simulating another API instance) must see the lockout.
        repo_b = PostgresUserAccountRepository(factory)
        found = repo_b.find_by_email(email)
        assert found is not None
        assert found.locked_until is not None
        assert found.is_locked()


class TestLockoutPersistence:
    """Login lockout threshold, duration, and reset persist correctly."""

    def test_record_failed_login_increments_counter(self, orm_factory):
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"fl_inc_{_uid()}@test.com"
        repo.save(_make_account(email))
        account_id = repo.find_by_email(email).user_id

        result = repo.record_failed_login(account_id)
        assert result is False  # 1 < threshold(5), not yet locked
        found = repo.find_by_email(email)
        assert found.failed_attempts == 1

    def test_threshold_triggers_lockout_and_resets_counter(self, orm_factory, monkeypatch):
        """At LOCKOUT_THRESHOLD failures, locked_until is set and failed_attempts resets."""
        monkeypatch.setenv("LOCKOUT_THRESHOLD", "3")
        monkeypatch.setenv("LOCKOUT_DURATION_SECONDS", "900")

        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"fl_thr_{_uid()}@test.com"
        repo.save(_make_account(email))
        account_id = repo.find_by_email(email).user_id

        before = datetime.now(timezone.utc)
        for i in range(2):
            result = repo.record_failed_login(account_id)
            assert result is False, f"Should not be locked after {i+1} failures"

        # Third failure triggers lockout.
        result = repo.record_failed_login(account_id)
        assert result is True
        after = datetime.now(timezone.utc)

        found = repo.find_by_email(email)
        assert found.failed_attempts == 0          # reset after lockout applied
        assert found.locked_until is not None
        assert found.locked_until >= before + timedelta(seconds=900)
        assert found.locked_until <= after + timedelta(seconds=901)
        assert found.is_locked()

    def test_record_successful_login_resets_counter_and_clears_lockout(self, orm_factory):
        """record_successful_login must clear failed_attempts and locked_until."""
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"fl_rst_{_uid()}@test.com"
        account = _make_account(email, failed_attempts=3)
        account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        repo.save(account)
        account_id = repo.find_by_email(email).user_id

        repo.record_successful_login(account_id)

        found = repo.find_by_email(email)
        assert found.failed_attempts == 0
        assert found.locked_until is None
        assert not found.is_locked()

    def test_already_locked_record_failed_login_does_not_increment(self, orm_factory):
        """record_failed_login re-checks locked_until under FOR UPDATE; returns True
        immediately without incrementing if the account is already locked."""
        factory, *_ = orm_factory
        repo = PostgresUserAccountRepository(factory)
        email = f"fl_alr_{_uid()}@test.com"
        account = _make_account(email, failed_attempts=0)
        account.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        repo.save(account)
        account_id = repo.find_by_email(email).user_id

        result = repo.record_failed_login(account_id)
        assert result is True   # already locked
        found = repo.find_by_email(email)
        assert found.failed_attempts == 0  # not incremented


class TestVerificationRecordPersistence:
    """Verification records are append-only and ordered correctly."""

    def test_verification_record_persists(self, orm_factory):
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        vr_repo = PostgresVerificationRecordRepository(factory)
        subject = _make_account(f"subj_{_uid()}@test.com", state=AccountStateEnum.Pending)
        verifier = _make_account(f"verif_{_uid()}@test.com")
        account_repo.save(subject)
        account_repo.save(verifier)
        vr = VerificationRecord(
            record_id=uuid4(),
            subject_account_id=subject.user_id,
            verifier_account_id=verifier.user_id,
            subject_role=RoleEnum.SchoolAdmin,
            evidence_reference="REF-001",
            school_scope=[uuid4()],
            university_id=None,
            created_at=datetime.now(timezone.utc),
            outcome="Verified",
        )
        vr_repo.save(vr)
        records = vr_repo.find_by_subject(subject.user_id)
        assert len(records) == 1
        assert records[0].evidence_reference == "REF-001"
        assert records[0].outcome == "Verified"

    def test_verification_records_ordered_ascending(self, orm_factory):
        """find_by_subject orders ascending; service uses [-1] for the most recent."""
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        vr_repo = PostgresVerificationRecordRepository(factory)
        subject = _make_account(f"ord_{_uid()}@test.com", state=AccountStateEnum.Pending)
        verifier = _make_account(f"ordv_{_uid()}@test.com")
        account_repo.save(subject)
        account_repo.save(verifier)
        base_time = datetime.now(timezone.utc)
        for i in range(3):
            vr_repo.save(VerificationRecord(
                record_id=uuid4(),
                subject_account_id=subject.user_id,
                verifier_account_id=verifier.user_id,
                subject_role=RoleEnum.SchoolAdmin,
                evidence_reference=f"REF-{i}",
                school_scope=[],
                university_id=None,
                created_at=base_time + timedelta(seconds=i),
                outcome="Verified",
            ))
        records = vr_repo.find_by_subject(subject.user_id)
        assert len(records) == 3
        assert records[-1].evidence_reference == "REF-2"

    def test_verification_record_append_only_raises_on_duplicate(self, orm_factory):
        """save() on an existing record_id must raise IntegrityError (PK violation)."""
        from sqlalchemy.exc import IntegrityError
        factory, *_ = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        vr_repo = PostgresVerificationRecordRepository(factory)
        subject = _make_account(f"ao_{_uid()}@test.com", state=AccountStateEnum.Pending)
        verifier = _make_account(f"aov_{_uid()}@test.com")
        account_repo.save(subject)
        account_repo.save(verifier)
        vr_id = uuid4()
        vr = VerificationRecord(
            record_id=vr_id,
            subject_account_id=subject.user_id,
            verifier_account_id=verifier.user_id,
            subject_role=RoleEnum.SchoolAdmin,
            evidence_reference="REF-AO",
            school_scope=[],
            university_id=None,
            created_at=datetime.now(timezone.utc),
            outcome="Verified",
        )
        vr_repo.save(vr)
        with pytest.raises(IntegrityError):
            vr_repo.save(vr)   # Same record_id — primary key violation


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency tests — require threading + PostgreSQL FOR UPDATE semantics
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrencyGuarantees:
    """PostgreSQL FOR UPDATE serializes concurrent state transitions correctly.

    A threading.Barrier is used so that all worker threads are released at
    approximately the same instant, maximising the chance that their database
    calls overlap.  A barrier does NOT guarantee that the database transactions
    are simultaneously in flight — network latency, OS scheduling and connection-
    pool acquisition still affect real overlap.  What the barrier does establish
    is that all threads have been created and are ready before any of them begins
    the database call, which is the closest Python threading can come to
    simultaneous execution.
    """

    _THREAD_TIMEOUT_S = 10   # seconds; prevents tests from hanging on deadlock

    def test_concurrent_activation_exactly_one_succeeds(self, orm_factory):
        """Two threads call activate_with_lock simultaneously; exactly one must
        succeed and the other must raise AlreadyActiveError.

        A Barrier ensures both threads reach their database call before either
        proceeds.  Unhandled exceptions inside threads are captured and
        re-raised in the main thread so they surface as test failures.
        """
        from unimatch.provisioning import AlreadyActiveError

        factory, engine, schema_name = orm_factory
        account_repo = PostgresUserAccountRepository(factory)
        vr_repo = PostgresVerificationRecordRepository(factory)

        # Set up: Pending account + verified record.  Creator is different from
        # both activators, satisfying the two-person rule.
        creator   = _make_account(f"creator_{_uid()}@test.com")
        activator1 = _make_account(f"act1_{_uid()}@test.com")
        activator2 = _make_account(f"act2_{_uid()}@test.com")
        pending   = _make_account(f"pend_{_uid()}@test.com",
                                  state=AccountStateEnum.Pending)
        pending.creator_id = creator.user_id
        school_id = uuid4()
        pending.school_id = school_id
        for acct in [creator, activator1, activator2]:
            account_repo.save(acct)
        now = datetime.now(timezone.utc)
        with factory() as session:
            session.add(SchoolRecord(
                school_id=school_id,
                official_name=f"Concurrency Test School {school_id}",
                emis_number=None,
                province="Gauteng",
                district="Integration Tests",
                contact_email=None,
                contact_phone=None,
                status="Active",
                creator_id=creator.user_id,
                created_at=now,
                updated_at=now,
            ))
            session.commit()
        account_repo.save(pending)

        vr_repo.save(VerificationRecord(
            record_id=uuid4(),
            subject_account_id=pending.user_id,
            verifier_account_id=creator.user_id,
            subject_role=RoleEnum.SchoolAdmin,
            evidence_reference="REF-CONC-ACT",
            school_scope=[school_id],
            university_id=None,
            created_at=datetime.now(timezone.utc),
            outcome="Verified",
        ))

        actor1 = AuthPrincipal(account_id=activator1.user_id,
                               role=RoleEnum.SystemAdmin,
                               account_state=AccountStateEnum.Active)
        actor2 = AuthPrincipal(account_id=activator2.user_id,
                               role=RoleEnum.SystemAdmin,
                               account_state=AccountStateEnum.Active)

        n_workers = 2
        barrier   = threading.Barrier(n_workers, timeout=self._THREAD_TIMEOUT_S)
        successes: list = []
        errors:    list = []
        result_lock = threading.Lock()

        def try_activate(actor):
            # Each thread uses its own sessionmaker — separate connection, separate txn.
            thread_engine  = engine.execution_options(
                schema_translate_map={None: schema_name}
            )
            thread_factory = sessionmaker(bind=thread_engine, expire_on_commit=False)
            repo = PostgresUserAccountRepository(thread_factory)
            try:
                barrier.wait()   # release all workers simultaneously
                account = repo.activate_with_lock(pending.user_id, actor)
                with result_lock:
                    successes.append(account)
            except AlreadyActiveError as e:
                with result_lock:
                    errors.append(("expected", e))
            except Exception as e:
                with result_lock:
                    errors.append(("unexpected", e))

        threads = [threading.Thread(target=try_activate, args=(a,),
                                    daemon=True)
                   for a in (actor1, actor2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=self._THREAD_TIMEOUT_S + 2)
            assert not t.is_alive(), "Worker thread timed out — possible deadlock"

        # Surface any unexpected exceptions from worker threads.
        unexpected = [e for kind, e in errors if kind == "unexpected"]
        if unexpected:
            raise AssertionError(
                f"Worker thread raised an unexpected exception: {unexpected[0]!r}"
            )

        expected_errors = [e for kind, e in errors if kind == "expected"]
        assert len(successes) == 1, (
            f"Expected exactly 1 activation success, got {len(successes)}"
        )
        assert len(expected_errors) == 1, (
            f"Expected exactly 1 AlreadyActiveError, got {len(expected_errors)}"
        )
        final = account_repo.find_by_id(pending.user_id)
        assert final.account_state == AccountStateEnum.Active

    def test_concurrent_failed_logins_at_threshold_serialize_correctly(
        self, orm_factory, monkeypatch
    ):
        """Four threads call record_failed_login simultaneously when the account
        is one attempt below the lockout threshold (LOCKOUT_THRESHOLD=3,
        failed_attempts=2).  Expected outcomes after FOR UPDATE serialization:

        - Exactly one thread increments the counter from 2 to 3, triggering
          lockout: locked_until is set and failed_attempts is reset to 0.
        - All remaining threads see locked_until IS NOT NULL on their locked
          read and return True without further incrementing.

        A Barrier maximises overlap; the same caveat as the activation test
        applies — genuine database-level concurrency is not guaranteed.
        """
        monkeypatch.setenv("LOCKOUT_THRESHOLD", "3")
        monkeypatch.setenv("LOCKOUT_DURATION_SECONDS", "900")

        factory, engine, schema_name = orm_factory
        account_repo = PostgresUserAccountRepository(factory)

        # One below threshold so the first thread to commit triggers lockout.
        email = f"conc_lock_{_uid()}@test.com"
        account_repo.save(_make_account(email, failed_attempts=2))
        account_id = account_repo.find_by_email(email).user_id

        n_workers = 4
        barrier   = threading.Barrier(n_workers, timeout=self._THREAD_TIMEOUT_S)
        results:  list = []
        errors:   list = []
        result_lock = threading.Lock()

        def try_fail_login():
            thread_engine  = engine.execution_options(
                schema_translate_map={None: schema_name}
            )
            thread_factory = sessionmaker(bind=thread_engine, expire_on_commit=False)
            repo = PostgresUserAccountRepository(thread_factory)
            try:
                barrier.wait()   # release all workers simultaneously
                result = repo.record_failed_login(account_id)
                with result_lock:
                    results.append(result)
            except Exception as e:
                with result_lock:
                    errors.append(e)

        threads = [threading.Thread(target=try_fail_login, daemon=True)
                   for _ in range(n_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=self._THREAD_TIMEOUT_S + 2)
            assert not t.is_alive(), "Worker thread timed out — possible deadlock"

        if errors:
            raise AssertionError(
                f"Worker thread raised an unexpected exception: {errors[0]!r}"
            )

        # Every result must be True (locked), because:
        # - the first thread to commit locked the account, and
        # - all subsequent threads re-checked locked_until under FOR UPDATE
        #   and returned True immediately without incrementing.
        assert all(r is True for r in results), (
            f"Every worker should see the account as locked; got: {results}"
        )
        assert len(results) == n_workers, (
            f"Expected {n_workers} results, got {len(results)}"
        )

        final = account_repo.find_by_email(email)
        assert final.locked_until is not None, (
            "Account must be locked after threshold was reached"
        )
        assert final.failed_attempts == 0, (
            "failed_attempts must be reset to 0 when lockout is applied; "
            f"got {final.failed_attempts}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fixture B tests — migration-produced schema verification
#
# These tests verify the ACTUAL DDL output from running the Alembic migrations,
# not just the ORM model definitions.  They inspect pg_indexes, pg_constraint
# and information_schema to confirm the migration creates the required structure.
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrationSchema:
    """Verify that the Alembic migrations produce the correct DDL."""

    def _schema_query(self, engine, schema_name: str, sql: str, **params):
        with engine.connect() as conn:
            conn.execute(text(f'SET search_path TO "{schema_name}"'))
            result = conn.execute(text(sql), params)
            return result.fetchall()

    def test_migration_chain_applied_in_order(self, migration_schema):
        """alembic_version must record the current head after full upgrade."""
        engine, schema_name = migration_schema
        rows = self._schema_query(
            engine, schema_name,
            "SELECT version_num FROM alembic_version"
        )
        versions = {row[0] for row in rows}
        # The auth revision is an ancestor of the current lifecycle migration head.
        assert "0011_university_directory" in versions, (
            f"Expected current head 0011_university_directory in alembic_version, found: {versions}"
        )

    def test_all_expected_tables_exist(self, migration_schema):
        """All nine ORM-mapped tables must exist in the migration schema."""
        engine, schema_name = migration_schema
        rows = self._schema_query(
            engine, schema_name,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name",
            schema=schema_name,
        )
        found = {row[0] for row in rows}
        expected = {
            "learners", "marks", "university_programmes", "scoring_rules",
            "applications", "application_status_history",
            "accounts", "account_sessions", "verification_records",
        }
        missing = expected - found
        assert not missing, f"Missing tables after migration: {missing}"

    def test_case_insensitive_email_index_exists(self, migration_schema):
        """uq_accounts_email_ci functional unique index must exist."""
        engine, schema_name = migration_schema
        rows = self._schema_query(
            engine, schema_name,
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = 'accounts' "
            "  AND indexname = 'uq_accounts_email_ci'",
            schema=schema_name,
        )
        assert rows, "uq_accounts_email_ci index not found after migration"

    def test_single_system_admin_partial_index_exists(self, migration_schema):
        """uq_accounts_single_system_admin partial unique index must exist."""
        engine, schema_name = migration_schema
        rows = self._schema_query(
            engine, schema_name,
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = 'accounts' "
            "  AND indexname = 'uq_accounts_single_system_admin'",
            schema=schema_name,
        )
        assert rows, "uq_accounts_single_system_admin index not found after migration"
        index_def = rows[0][1].lower()
        assert "where" in index_def and "systemadmin" in index_def.replace(" ", ""), (
            f"Partial index predicate missing from definition: {rows[0][1]}"
        )

    def test_foreign_keys_and_deletion_rules(self, migration_schema):
        """All four FK deletion rules must match the specification:
          - accounts.creator_id           → accounts       ON DELETE RESTRICT
          - account_sessions.account_id   → accounts       ON DELETE CASCADE
          - verification_records.subject_account_id   → accounts  ON DELETE RESTRICT
          - verification_records.verifier_account_id  → accounts  ON DELETE RESTRICT
        """
        engine, schema_name = migration_schema

        # Keyed by (table_name, column_name) to avoid collision when multiple tables
        # share a column name (e.g., two tables both have an 'account_id' FK).
        rows = self._schema_query(
            engine, schema_name,
            "SELECT tc.table_name, kcu.column_name, rc.delete_rule "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema   = kcu.table_schema "
            "JOIN information_schema.referential_constraints rc "
            "  ON tc.constraint_name = rc.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "  AND tc.table_schema   = :schema "
            "ORDER BY tc.table_name, kcu.column_name",
            schema=schema_name,
        )

        # Build lookup: (table_name, column_name) → delete_rule
        fk_rules: dict[tuple[str, str], str] = {}
        for table_name, column_name, delete_rule in rows:
            fk_rules[(table_name, column_name)] = delete_rule

        expected = {
            ("accounts",             "creator_id"):          "RESTRICT",
            ("account_sessions",     "account_id"):          "CASCADE",
            ("verification_records", "subject_account_id"):  "RESTRICT",
            ("verification_records", "verifier_account_id"): "RESTRICT",
        }
        for (table, col), expected_rule in expected.items():
            key = (table, col)
            assert key in fk_rules, (
                f"FK not found: {table}.{col}. Available FKs: {list(fk_rules.keys())}"
            )
            assert fk_rules[key] == expected_rule, (
                f"{table}.{col}: expected ON DELETE {expected_rule}, "
                f"got ON DELETE {fk_rules[key]}"
            )

    def test_migration_schema_contains_auth_tables_and_correct_revision(
        self, migration_schema
    ):
        """Verify that the migration-produced schema contains all three authentication
        tables and records the expected Alembic revision.

        This test does NOT call the production _verify_auth_schema() function.
        That function hardcodes table_schema = 'public' and is incompatible with
        schema-isolated migration testing.  The production startup validation is
        tested separately via the database-independent test suite.

        What this test establishes:
        - All three auth tables exist in the isolated schema after Alembic upgrade.
        - The alembic_version table records the current lifecycle migration head.
        """
        engine, schema_name = migration_schema

        # 1. Confirm all three auth tables exist in the isolated schema.
        rows = self._schema_query(
            engine, schema_name,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema "
            "  AND table_name = ANY(ARRAY['accounts','account_sessions','verification_records'])"
            " ORDER BY table_name",
            schema=schema_name,
        )
        found_tables = {row[0] for row in rows}
        for expected in ("accounts", "account_sessions", "verification_records"):
            assert expected in found_tables, (
                f"Auth table '{expected}' missing from migration schema '{schema_name}'"
            )

        # 2. Confirm alembic_version records the expected head revision.
        version_rows = self._schema_query(
            engine, schema_name,
            "SELECT version_num FROM alembic_version",
        )
        versions = {row[0] for row in version_rows}
        assert "0011_university_directory" in versions, (
            "Expected current head '0011_university_directory' in "
            f"alembic_version, found: {versions}"
        )
