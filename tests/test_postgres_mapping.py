from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from unimatch.entities import UniversityProgramme
from unimatch.enums import ProgrammeStatusEnum
from unimatch.repositories.postgres import (
    _programme_from_snapshot,
    _programme_snapshot,
)


def test_programme_snapshot_round_trips_domain_fields():
    programme = UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="Synthetic Programme",
        faculty="Science",
        minimum_aps=30,
        application_deadline=date(2099, 12, 31),
        application_fee=Decimal("125.50"),
        required_documents=["ID", "Transcript"],
        status=ProgrammeStatusEnum.Deactivated,
        published_by=uuid4(),
        version=2,
        required_subjects={"Mathematics": 60},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    assert _programme_from_snapshot(_programme_snapshot(programme)) == programme
