from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker

from unimatch.db_models import Base
from unimatch.entities import (
    Application,
    LearnerProfile,
    Mark,
    ScoringRule,
    UniversityProgramme,
)
from unimatch.enums import (
    ApplicationStatusEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
)
from unimatch.repositories.postgres import (
    PostgresApplicationRepository,
    PostgresLearnerProfileRepository,
    PostgresScoringRuleRepository,
    PostgresUniversityProgrammeRepository,
)
from unimatch.status_history import StatusHistoryEntry


def _safe_test_url() -> URL:
    raw_url = os.environ.get("UNIMATCH_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set UNIMATCH_TEST_DATABASE_URL to run PostgreSQL integration tests")
    if os.environ.get("UNIMATCH_TEST_DATABASE_APPROVED") != "1":
        pytest.skip("Set UNIMATCH_TEST_DATABASE_APPROVED=1 after verifying the test database")

    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database is None
        or not url.database.endswith("_test")
    ):
        pytest.fail(
            "PostgreSQL integration tests require a local psycopg URL whose database "
            "name ends in _test"
        )

    application_url = os.environ.get("DATABASE_URL")
    if application_url and make_url(application_url).render_as_string(
        hide_password=True
    ) == url.render_as_string(hide_password=True):
        pytest.fail("The integration test URL must be separate from DATABASE_URL")

    return url


@pytest.fixture
def postgres_repositories():
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_test_{uuid4().hex}"
    quote_identifier = engine.dialect.identifier_preparer.quote

    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {quote_identifier(schema_name)}")

    isolated_engine = engine.execution_options(
        schema_translate_map={None: schema_name}
    )
    try:
        Base.metadata.create_all(isolated_engine)
        session_factory = sessionmaker(bind=isolated_engine, expire_on_commit=False)
        yield (
            PostgresLearnerProfileRepository(session_factory),
            PostgresUniversityProgrammeRepository(session_factory),
            PostgresApplicationRepository(session_factory),
            PostgresScoringRuleRepository(session_factory),
        )
    finally:
        Base.metadata.drop_all(isolated_engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP SCHEMA {quote_identifier(schema_name)} CASCADE"
            )
        engine.dispose()


def test_postgres_repositories_round_trip_active_entities(postgres_repositories):
    learner_repo, programme_repo, application_repo, scoring_rule_repo = (
        postgres_repositories
    )
    now = datetime.now(timezone.utc)
    learner_id = uuid4()
    learner = LearnerProfile(
        learner_id=learner_id,
        full_name="Test Learner",
        school_id_number="TEST-001",
        grade=12,
        status=ProfileStatusEnum.Incomplete,
        counselor_id=uuid4(),
        school_id=uuid4(),
        marks=[
            Mark(
                mark_id=uuid4(),
                learner_id=learner_id,
                subject_name="Mathematics",
                score=80,
                exam_type="NSC",
                academic_year=2026,
                created_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    learner_repo.save(learner)

    programme = UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="Test Programme",
        faculty="Science",
        minimum_aps=30,
        application_deadline=date(2099, 12, 31),
        application_fee=Decimal("125.50"),
        required_documents=["ID"],
        status=ProgrammeStatusEnum.Published,
        published_by=uuid4(),
        required_subjects={"Mathematics": 60},
        created_at=now,
        updated_at=now,
    )
    programme_repo.save(programme)

    application = Application(
        application_id=uuid4(),
        learner_id=learner_id,
        programme_id=programme.programme_id,
        status=ApplicationStatusEnum.Draft,
        payment_reference="",
        fee_amount=Decimal("125.50"),
        submission_timestamp=None,
        acknowledgement_reference="",
        linked_programme=programme,
        created_at=now,
        updated_at=now,
    )
    application.status_history.append(
        StatusHistoryEntry.create(
            application.application_id,
            ApplicationStatusEnum.Draft,
            ApplicationStatusEnum.Cancelled,
            uuid4(),
            "Synthetic test transition",
        )
    )
    application_repo.save(application)

    scoring_rule = ScoringRule(
        university_id=programme.university_id,
        band_thresholds=[(80, 7), (50, 4)],
        subject_count=6,
        excluded_subjects=["Life Orientation"],
        subject_weightings={"Mathematics": 1.25},
    )
    scoring_rule_repo.save(scoring_rule)

    stored_learner = learner_repo.find_by_id(learner_id)
    stored_programme = programme_repo.find_by_id(programme.programme_id)
    stored_application = application_repo.find_by_id(application.application_id)
    stored_rule = scoring_rule_repo.find_by_university(programme.university_id)

    assert stored_learner is not None
    assert stored_learner.marks[0].subject_name == "Mathematics"
    assert stored_learner.marks[0].score == 80
    assert stored_programme is not None
    assert stored_programme.required_subjects == {"Mathematics": 60}
    assert stored_application is not None
    assert stored_application.status_history[0].note == "Synthetic test transition"
    assert stored_application.linked_programme is not None
    assert stored_application.linked_programme.programme_id == programme.programme_id
    assert stored_rule is not None
    assert stored_rule.band_thresholds == [(80, 7), (50, 4)]
