from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from unimatch.api import create_app
from unimatch.auth import AuthPrincipal, digest_token, hash_password
from unimatch.db_models import SchoolAdminBootstrapRecord, AccountRecord
from unimatch.entities import School, UserAccount, VerificationRecord
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.repositories.postgres import (
    PostgresAccountInvitationRepository,
    PostgresSchoolRepository,
    PostgresUserAccountRepository,
    PostgresVerificationRecordRepository,
)
from unimatch.provisioning import AlreadyActiveError, ProvisioningError


def _safe_test_url() -> URL:
    raw_url = os.environ.get("UNIMATCH_TEST_DATABASE_URL")
    if not raw_url or os.environ.get("UNIMATCH_TEST_DATABASE_APPROVED") != "1":
        pytest.skip("Explicitly approved local PostgreSQL test URL is required.")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or not url.database
        or not url.database.endswith("_test")
    ):
        pytest.fail("SystemAdmin integration tests require a local *_test database.")
    application_url = os.environ.get("DATABASE_URL")
    if application_url and make_url(application_url).render_as_string(
        hide_password=True
    ) == url.render_as_string(hide_password=True):
        pytest.fail("The PostgreSQL test database must be separate from DATABASE_URL.")
    return url


def _upgrade(engine, schema_name: str, revision: str) -> None:
    root = Path(__file__).parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("prepend_sys_path", str(root / "src"))
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema_name}"'))
        connection.commit()
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


@pytest.fixture
def migrated_schema():
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_admin_test_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {quote(schema_name)}")
    try:
        _upgrade(engine, schema_name, "head")
        isolated_engine = engine.execution_options(
            schema_translate_map={None: schema_name}
        )
        factory = sessionmaker(bind=isolated_engine, expire_on_commit=False)
        yield url, engine, schema_name, factory
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP SCHEMA IF EXISTS {quote(schema_name)} CASCADE"
            )
        engine.dispose()


def _account(
    email: str,
    role: RoleEnum,
    state: AccountStateEnum,
    *,
    school_id=None,
    creator_id=None,
) -> UserAccount:
    return UserAccount(
        user_id=uuid4(),
        email=email,
        password_hash=hash_password("Synthetic-Integration-Password-1!"),
        role=role,
        account_state=state,
        school_id=school_id,
        creator_id=creator_id,
    )


def _school(school_id, creator_id, status="Active") -> School:
    now = datetime.now(timezone.utc)
    return School(
        school_id=school_id,
        official_name=f"Synthetic Integration School {school_id}",
        emis_number=None,
        province="Gauteng",
        district="Synthetic Tests",
        contact_email=None,
        contact_phone=None,
        status=status,
        creator_id=creator_id,
        created_at=now,
        updated_at=now,
    )


def test_migration_0009_backfills_legacy_school_as_needs_review_without_reassigning_account():
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_0009_backfill_test_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {quote(schema_name)}")
    school_id = uuid4()
    account_id = uuid4()
    try:
        _upgrade(engine, schema_name, "0008_learner_document_storage")
        with engine.connect() as connection:
            connection.execute(text(f'SET search_path TO "{schema_name}"'))
            connection.commit()
            connection.execute(
                text(
                    "INSERT INTO accounts "
                    "(account_id, email, password_hash, role, account_state, "
                    "created_at, updated_at, school_id) "
                    "VALUES (:account_id, :email, :password_hash, :role, :state, "
                    ":created_at, :updated_at, :school_id)"
                ),
                {
                    "account_id": account_id,
                    "email": f"legacy-admin-{uuid4().hex}@test.invalid",
                    "password_hash": "synthetic-hash",
                    "role": "SchoolAdmin",
                    "state": "Active",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "school_id": school_id,
                },
            )
            connection.commit()

        _upgrade(engine, schema_name, "0009_school_administration")
        with engine.connect() as connection:
            connection.execute(text(f'SET search_path TO "{schema_name}"'))
            connection.commit()
            legacy_account = connection.execute(
                text("SELECT school_id FROM accounts WHERE account_id = :account_id"),
                {"account_id": account_id},
            ).one()
            legacy_school = connection.execute(
                text(
                    "SELECT school_id, official_name, status FROM schools "
                    "WHERE school_id = :school_id"
                ),
                {"school_id": school_id},
            ).one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert legacy_account.school_id == school_id
        assert legacy_school.school_id == school_id
        assert legacy_school.official_name == f"Unverified legacy school {school_id}"
        assert legacy_school.status == "NeedsReview"
        assert revision == "0009_school_administration"
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP SCHEMA IF EXISTS {quote(schema_name)} CASCADE"
            )
        engine.dispose()


def test_system_admin_school_invitation_bootstrap_and_school_session_lifecycle(
    migrated_schema,
):
    url, _engine, schema_name, factory = migrated_schema
    accounts = PostgresUserAccountRepository(factory)
    actor = _account(
        f"system-admin-{uuid4().hex}@test.invalid",
        RoleEnum.SystemAdmin,
        AccountStateEnum.Active,
    )
    accounts.save(actor)

    api_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
        query={**url.query, "options": f"-csearch_path={schema_name}"},
    )
    app = create_app(database_url=api_url.render_as_string(hide_password=False))
    with TestClient(app, raise_server_exceptions=False) as admin:
        assert admin.post(
            "/api/auth/login",
            json={"email": actor.email, "password": "Synthetic-Integration-Password-1!"},
        ).status_code == 200
        csrf = admin.get("/api/auth/csrf").json()["csrf_token"]

        created = admin.post(
            "/api/admin/schools",
            headers={"X-CSRF-Token": csrf},
            json={
                "official_name": f"Postgres Admin Test {uuid4().hex}",
                "province": "Gauteng",
                "district": "Synthetic Tests",
            },
        )
        assert created.status_code == 201, created.text
        school_id = created.json()["school_id"]
        assert created.json()["status"] == "PendingVerification"
        activated = admin.post(
            f"/api/admin/schools/{school_id}/status",
            headers={"X-CSRF-Token": csrf},
            json={"status": "Active", "evidence_reference": "SCHOOL-VERIFY-INT-01"},
        )
        assert activated.status_code == 200, activated.text
        assert admin.get("/api/admin/schools").json()[0]["school_id"] == school_id

        invited = admin.post(
            "/api/admin/school-admins/invite",
            headers={"X-CSRF-Token": csrf},
            json={
                "email": f"school-admin-{uuid4().hex}@test.invalid",
                "school_id": school_id,
            },
        )
        assert invited.status_code == 201, invited.text
        invitation = invited.json()
        assert datetime.now(timezone.utc) + timedelta(hours=71) < datetime.fromisoformat(
            invitation["expires_at"].replace("Z", "+00:00")
        ) < datetime.now(timezone.utc) + timedelta(hours=73)

        token = invitation["setup_token"]
        completed = admin.post(
            "/api/auth/invitations/complete",
            json={"token": token, "password": "Synthetic-School-Password-2!"},
        )
        assert completed.status_code == 200, completed.text
        assert admin.post(
            "/api/auth/invitations/complete",
            json={"token": token, "password": "Synthetic-School-Password-3!"},
        ).status_code == 400

        account_id = invitation["account"]["account_id"]
        verified = admin.post(
            f"/api/auth/accounts/{account_id}/verify",
            headers={"X-CSRF-Token": csrf},
            json={
                "evidence_reference": "SCHOOL-AUTHORITY-INT-01",
                "school_scope": [school_id],
                "outcome": "Verified",
            },
        )
        assert verified.status_code == 200, verified.text
        bootstrapped = admin.post(
            f"/api/admin/accounts/{account_id}/bootstrap-first-school-admin",
            headers={"X-CSRF-Token": csrf},
            json={
                "evidence_reference": "SCHOOL-RESOLUTION-INT-01",
                "reason": "Synthetic integration bootstrap evidence.",
            },
        )
        assert bootstrapped.status_code == 200, bootstrapped.text
        assert bootstrapped.json()["account_state"] == "Active"
        assert admin.post(
            f"/api/admin/accounts/{account_id}/bootstrap-first-school-admin",
            headers={"X-CSRF-Token": csrf},
            json={
                "evidence_reference": "SCHOOL-RESOLUTION-INT-02",
                "reason": "Attempt to replay synthetic bootstrap.",
            },
        ).status_code in {409, 422}

        school_admin = TestClient(app, raise_server_exceptions=False)
        login = school_admin.post(
            "/api/auth/login",
            json={
                "email": invitation["account"]["email"],
                "password": "Synthetic-School-Password-2!",
            },
        )
        assert login.status_code == 200, login.text
        assert school_admin.get("/api/learners").status_code == 200
        assert school_admin.get("/api/admin/schools").status_code == 403

        needs_review = admin.post(
            f"/api/admin/schools/{school_id}/status",
            headers={"X-CSRF-Token": csrf},
            json={"status": "NeedsReview", "evidence_reference": "SCHOOL-REVIEW-INT-01"},
        )
        assert needs_review.status_code == 200, needs_review.text
        assert school_admin.get("/api/auth/me").status_code == 401
        assert school_admin.post(
            "/api/auth/login",
            json={
                "email": invitation["account"]["email"],
                "password": "Synthetic-School-Password-2!",
            },
        ).status_code == 403
        restored = admin.post(
            f"/api/admin/schools/{school_id}/status",
            headers={"X-CSRF-Token": csrf},
            json={"status": "Active", "evidence_reference": "SCHOOL-REVIEW-INT-02"},
        )
        assert restored.status_code == 200, restored.text
        assert school_admin.get("/api/auth/me").status_code == 401

    with factory() as session:
        assert session.query(SchoolAdminBootstrapRecord).filter_by(
            target_account_id=UUID(account_id)
        ).count() == 1


def test_postgres_invitation_expiry_and_single_use(migrated_schema):
    _url, _engine, _schema_name, factory = migrated_schema
    accounts = PostgresUserAccountRepository(factory)
    schools = PostgresSchoolRepository(factory)
    invitations = PostgresAccountInvitationRepository(factory)
    actor = _account(
        f"invite-actor-{uuid4().hex}@test.invalid",
        RoleEnum.SystemAdmin,
        AccountStateEnum.Active,
    )
    accounts.save(actor)
    school_id = uuid4()
    schools.save(_school(school_id, actor.user_id))
    target = _account(
        f"invite-target-{uuid4().hex}@test.invalid",
        RoleEnum.SchoolAdmin,
        AccountStateEnum.Pending,
        school_id=school_id,
        creator_id=actor.user_id,
    )
    accounts.save(target)

    expired_token = uuid4().hex + uuid4().hex
    invitations.create(
        target.user_id,
        actor.user_id,
        digest_token(expired_token),
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert invitations.consume(digest_token(expired_token), "Expired-Password-1!") is False

    valid_token = uuid4().hex + uuid4().hex
    invitations.create(
        target.user_id,
        actor.user_id,
        digest_token(valid_token),
        datetime.now(timezone.utc) + timedelta(hours=72),
    )
    assert invitations.consume(digest_token(valid_token), "Valid-Password-2!") is True
    assert invitations.consume(digest_token(valid_token), "Replay-Password-3!") is False
    assert invitations.is_ready(target.user_id) is True


def test_concurrent_postgres_first_admin_bootstrap_has_one_winner(migrated_schema):
    _url, _engine, _schema_name, factory = migrated_schema
    accounts = PostgresUserAccountRepository(factory)
    schools = PostgresSchoolRepository(factory)
    invitations = PostgresAccountInvitationRepository(factory)
    verifications = PostgresVerificationRecordRepository(factory)
    actor = _account(
        f"bootstrap-actor-{uuid4().hex}@test.invalid",
        RoleEnum.SystemAdmin,
        AccountStateEnum.Active,
    )
    accounts.save(actor)
    school_id = uuid4()
    schools.save(_school(school_id, actor.user_id))
    targets = []
    for index in range(2):
        target = _account(
            f"bootstrap-target-{index}-{uuid4().hex}@test.invalid",
            RoleEnum.SchoolAdmin,
            AccountStateEnum.Pending,
            school_id=school_id,
            creator_id=actor.user_id,
        )
        accounts.save(target)
        token = uuid4().hex + uuid4().hex
        invitations.create(
            target.user_id,
            actor.user_id,
            digest_token(token),
            datetime.now(timezone.utc) + timedelta(hours=72),
        )
        assert invitations.consume(digest_token(token), "Bootstrap-Password-1!")
        verifications.save(VerificationRecord(
            record_id=uuid4(),
            subject_account_id=target.user_id,
            verifier_account_id=actor.user_id,
            subject_role=RoleEnum.SchoolAdmin,
            evidence_reference=f"SCHOOL-AUTHORITY-{index}",
            school_scope=[school_id],
            university_id=None,
            created_at=datetime.now(timezone.utc) + timedelta(seconds=index),
            outcome="Verified",
        ))
        targets.append(target)

    principal = AuthPrincipal(
        account_id=actor.user_id,
        role=RoleEnum.SystemAdmin,
        account_state=AccountStateEnum.Active,
    )
    barrier = Barrier(2)

    def bootstrap(target):
        barrier.wait(timeout=10)
        try:
            accounts.bootstrap_first_school_admin(
                school_id,
                target.user_id,
                principal,
                "SCHOOL-AUTHORITY-CONCURRENT",
                f"BOOTSTRAP-{target.user_id}",
                "Synthetic concurrent bootstrap test.",
            )
            return "success"
        except (AlreadyActiveError, ProvisioningError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(bootstrap, targets))
    assert outcomes.count("success") == 1
    assert outcomes.count("rejected") == 1
    with factory() as session:
        assert session.query(SchoolAdminBootstrapRecord).filter_by(
            school_id=school_id
        ).count() == 1
        assert session.query(AccountRecord).filter_by(
            school_id=school_id,
            role=RoleEnum.SchoolAdmin.value,
            account_state=AccountStateEnum.Active.value,
        ).count() == 1
