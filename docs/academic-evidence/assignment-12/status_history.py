from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from enums import ApplicationStatusEnum


@dataclass
class StatusHistoryEntry:
    entry_id: UUID
    application_id: UUID
    previous_status: ApplicationStatusEnum
    new_status: ApplicationStatusEnum
    changed_by: UUID
    changed_at: datetime
    note: str = ""

    @classmethod
    def create(
        cls,
        application_id: UUID,
        prev: ApplicationStatusEnum,
        next_status: ApplicationStatusEnum,
        actor: UUID,
        note: str = "",
    ) -> StatusHistoryEntry:
        return cls(
            entry_id=uuid4(),
            application_id=application_id,
            previous_status=prev,
            new_status=next_status,
            changed_by=actor,
            changed_at=datetime.utcnow(),
            note=note,
        )
