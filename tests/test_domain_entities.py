from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from unimatch.entities import Application, Document, Mark, UniversityProgramme, UserAccount
from unimatch.enums import ApplicationStatusEnum, ProfileStatusEnum, ProgrammeStatusEnum, RoleEnum


def test_user_account_locks_after_three_failures() -> None:
    u = UserAccount(
        user_id=uuid4(),
        email="a@b.c",
        password_hash="secret",
        role=RoleEnum.Learner,
    )
    for _ in range(3):
        with pytest.raises(ValueError):
            u.login("a@b.c", "wrong")
    assert u.is_locked() is True
    with pytest.raises(ValueError):
        u.login("a@b.c", "secret")


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
        required_documents=["ID"],
        status=ProgrammeStatusEnum.Published,
        published_by=uuid4(),
    )
    doc = Document(
        document_id=uuid4(),
        learner_id=learner,
        application_id=None,
        document_type="LO",
        filename="x.pdf",
        storage_path="/tmp/x",
        mime_type="application/pdf",
        size_bytes=10,
        uploaded_by=uuid4(),
        virus_scan_status="Clean",
        status="LinkedToApp",
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
    assert app.can_submit() is True


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
