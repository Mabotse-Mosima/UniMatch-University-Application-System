from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from unimatch.auth import hash_password, verify_password
from unimatch.entities import Application, Document, Mark, UniversityProgramme, UserAccount
from unimatch.enums import ApplicationStatusEnum, ProfileStatusEnum, ProgrammeStatusEnum, RoleEnum


def test_user_account_increments_failed_attempts_on_wrong_password() -> None:
    """The entity increments failed_attempts on each wrong password.

    Entity-level lockout (is_locked) is now determined exclusively by locked_until,
    which is set only by the repository's record_failed_login() method when the
    configured threshold is reached. The entity itself no longer triggers lockout
    based on a hard-coded failed_attempts threshold.
    """
    u = UserAccount(
        user_id=uuid4(),
        email="a@b.c",
        password_hash=hash_password("secret"),
        role=RoleEnum.Learner,
    )
    for i in range(1, 4):
        with pytest.raises(ValueError):
            u.login("a@b.c", "wrong")
        assert u.failed_attempts == i

    # Entity-level is_locked() is False: no locked_until has been set.
    # Actual lockout is enforced by the repository layer (record_failed_login).
    assert u.is_locked() is False

    # Correct password still works (no entity-level lockout).
    result = u.login("a@b.c", "secret")
    assert result == "authenticated"
    assert u.failed_attempts == 0  # reset on success


def test_reset_password_stores_hashed_password() -> None:
    u = UserAccount(
        user_id=uuid4(),
        email="a@b.c",
        password_hash=hash_password("old"),
        role=RoleEnum.Learner,
    )
    u.reset_password("newpass")
    assert verify_password("newpass", u.password_hash) is True
    assert verify_password("old", u.password_hash) is False
    assert "newpass" not in u.password_hash


def test_application_can_submit_guard() -> None:
    learner = uuid4()
    prog_id = uuid4()
    programme = UniversityProgramme(
        programme_id=prog_id,
        university_id=uuid4(),
        name="BSc",
        faculty="Science",
        minimum_aps=30,
        application_deadline=date.today() + timedelta(days=7),
        application_fee=Decimal("100"),
        required_documents=["ID", "Results"],
        status=ProgrammeStatusEnum.Published,
        published_by=uuid4(),
    )
    doc = Document(
        document_id=uuid4(),
        learner_id=learner,
        application_id=None,
        document_type="ID",
        filename="x.pdf",
        storage_path="/tmp/x",
        mime_type="application/pdf",
        size_bytes=10,
        uploaded_by=uuid4(),
        virus_scan_status="NotScanned",
        status="Verified",
        school_id=uuid4(),
    )
    app = Application(
        application_id=uuid4(),
        learner_id=learner,
        programme_id=prog_id,
        status=ApplicationStatusEnum.PackageReady,
        payment_reference="REF-1",
        fee_amount=Decimal("100"),
        submission_timestamp=None,
        acknowledgement_reference="",
        linked_programme=programme,
        documents=[doc],
    )
    doc.link_to_application(app.application_id)
    assert app.can_submit() is False
    results_document = Document(
        document_id=uuid4(),
        learner_id=learner,
        application_id=app.application_id,
        document_type="Results",
        filename="results.pdf",
        storage_path="/tmp/results.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        uploaded_by=uuid4(),
        virus_scan_status="NotScanned",
        status="Verified",
        school_id=uuid4(),
    )
    app.documents.append(results_document)
    assert app.can_submit() is True
    actor_id = uuid4()
    app.submit(actor_id)
    assert app.status == ApplicationStatusEnum.Submitted
    assert app.status_history[-1].changed_by == actor_id
    assert app.submission_timestamp is not None


def test_application_submission_rejects_missing_payment_and_documents() -> None:
    learner = uuid4()
    programme = UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="BSc",
        faculty="Science",
        minimum_aps=30,
        application_deadline=date.today() + timedelta(days=7),
        application_fee=Decimal("100"),
        required_documents=["ID", "Results"],
        status=ProgrammeStatusEnum.Published,
        published_by=uuid4(),
    )
    application = Application(
        application_id=uuid4(),
        learner_id=learner,
        programme_id=programme.programme_id,
        status=ApplicationStatusEnum.PackageReady,
        payment_reference="",
        fee_amount=Decimal("100"),
        submission_timestamp=None,
        acknowledgement_reference="",
        linked_programme=programme,
    )

    assert application.can_submit() is False
    with pytest.raises(ValueError, match="Cannot submit"):
        application.submit(uuid4())


def test_application_status_transitions_follow_documented_graph() -> None:
    app = Application(
        application_id=uuid4(),
        learner_id=uuid4(),
        programme_id=uuid4(),
        status=ApplicationStatusEnum.Draft,
        payment_reference="",
        fee_amount=Decimal("100"),
        submission_timestamp=None,
        acknowledgement_reference="",
    )

    with pytest.raises(ValueError, match="Invalid status transition"):
        app.update_status(ApplicationStatusEnum.FeePaid, uuid4())

    assert app.status == ApplicationStatusEnum.Draft
    assert app.get_status_history() == []

    actor_id = uuid4()
    app.update_status(ApplicationStatusEnum.FeeOutstanding, actor_id)
    assert app.status == ApplicationStatusEnum.FeeOutstanding
    assert app.get_status_history()[-1].changed_by == actor_id

    app.cancel(actor_id)
    assert app.status == ApplicationStatusEnum.Cancelled
    with pytest.raises(ValueError, match="Invalid status transition"):
        app.cancel(actor_id)


def test_university_programme_publish_deadline_rule() -> None:
    p = UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="BSc",
        faculty="Science",
        minimum_aps=30,
        application_deadline=date.today() - timedelta(days=1),
        application_fee=Decimal("0"),
        required_documents=[],
        status=ProgrammeStatusEnum.Draft,
        published_by=uuid4(),
    )
    with pytest.raises(ValueError):
        p.publish()


def test_mark_aps_points() -> None:
    m = Mark(
        mark_id=uuid4(),
        learner_id=uuid4(),
        subject_name="English",
        score=80,
        exam_type="NSC",
        academic_year=2026,
    )
    assert m.to_aps_points() == 7
