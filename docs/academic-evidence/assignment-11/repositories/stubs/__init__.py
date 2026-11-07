"""
repositories/stubs/__init__.py
================================
Stub (skeleton) implementations for two future storage backends:

1. ``FileSystem*Repository``  – serialises entities to a JSON file on disk.
2. ``Database*Repository``    – placeholder for a SQL/NoSQL integration.

These stubs are **not production-ready**.  They demonstrate the architectural
boundary that downstream implementors must fill in, and verify that the
repository interfaces are complete and swappable with zero changes to calling
code.

Why stubs instead of full implementations?
------------------------------------------
The assignment asks only for a *stub* of a future backend.  The in-memory
implementation is the authoritative reference.  A future developer picks up
the stub, installs the appropriate driver (e.g. ``pymysql``, ``motor``), and
fills in the method bodies — the interface contract is already defined.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional
from uuid import UUID

from unimatch.entities import Application, UserAccount
from unimatch.enums import ApplicationStatusEnum, RoleEnum
from repositories import ApplicationRepository, UserAccountRepository


# ──────────────────────────────────────────────────────────────────────────────
# Filesystem stubs  (JSON serialisation)
# ──────────────────────────────────────────────────────────────────────────────

class FileSystemUserAccountRepository(UserAccountRepository):
    """Persists ``UserAccount`` records to a JSON file.

    Serialisation strategy
    ~~~~~~~~~~~~~~~~~~~~~~
    Each entity is converted to a ``dict`` via ``dataclasses.asdict`` (or a
    custom ``to_dict`` method) and written as a JSON object.  On load the dict
    is rehydrated into the dataclass.  UUID and ``datetime`` fields require
    custom encoders/decoders — these are left as ``TODO`` markers for the
    implementor.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the backing ``.json`` file.
        Created on first write if it does not exist.
    """

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    # ── private helpers ───────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        """Load and return the raw JSON dict from disk."""
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]

    def _dump(self, data: dict[str, Any]) -> None:
        """Write *data* back to disk atomically."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)  # ``default=str`` handles UUID/datetime

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, entity: UserAccount) -> None:
        data = self._load()
        # TODO: replace ``vars(entity)`` with a proper ``to_dict`` that handles
        #       ``RoleEnum``, ``datetime``, and ``UUID`` serialisation.
        data[str(entity.user_id)] = vars(entity)
        self._dump(data)

    def find_by_id(self, entity_id: UUID) -> Optional[UserAccount]:
        data = self._load()
        raw = data.get(str(entity_id))
        if raw is None:
            return None
        # TODO: deserialise ``raw`` back into a ``UserAccount`` dataclass.
        raise NotImplementedError("Deserialisation not yet implemented")

    def find_all(self) -> List[UserAccount]:
        # TODO: deserialise every entry.
        raise NotImplementedError("Deserialisation not yet implemented")

    def delete(self, entity_id: UUID) -> None:
        data = self._load()
        data.pop(str(entity_id), None)
        self._dump(data)

    # ── Domain queries ────────────────────────────────────────────────────────

    def find_by_email(self, email: str) -> Optional[UserAccount]:
        # TODO: load and filter by email field.
        raise NotImplementedError

    def find_by_role(self, role: RoleEnum) -> List[UserAccount]:
        # TODO: load and filter by role field.
        raise NotImplementedError


class FileSystemApplicationRepository(ApplicationRepository):
    """Persists ``Application`` records to a JSON file.

    See :class:`FileSystemUserAccountRepository` for the general serialisation
    strategy — the same ``TODO`` markers apply here.
    """

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]

    def _dump(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)

    def save(self, entity: Application) -> None:
        data = self._load()
        data[str(entity.application_id)] = vars(entity)  # TODO: proper serialiser
        self._dump(data)

    def find_by_id(self, entity_id: UUID) -> Optional[Application]:
        raise NotImplementedError("Deserialisation not yet implemented")

    def find_all(self) -> List[Application]:
        raise NotImplementedError("Deserialisation not yet implemented")

    def delete(self, entity_id: UUID) -> None:
        data = self._load()
        data.pop(str(entity_id), None)
        self._dump(data)

    def find_by_learner(self, learner_id: UUID) -> List[Application]:
        raise NotImplementedError

    def find_by_programme(self, programme_id: UUID) -> List[Application]:
        raise NotImplementedError

    def find_by_status(self, status: ApplicationStatusEnum) -> List[Application]:
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────────────
# Database stubs  (SQL / NoSQL)
# ──────────────────────────────────────────────────────────────────────────────

class DatabaseUserAccountRepository(UserAccountRepository):
    """Placeholder for a SQL-backed ``UserAccount`` repository.

    Implementation guide
    ~~~~~~~~~~~~~~~~~~~~
    1. Install a DB driver, e.g. ``pip install pymysql sqlalchemy``.
    2. Inject a ``Session`` (SQLAlchemy) or ``Connection`` in ``__init__``.
    3. Map ``UserAccount`` to an ORM model or use raw SQL with parameterised
       queries.
    4. Replace every ``raise NotImplementedError`` with the appropriate driver
       call.

    Example (SQLAlchemy Core, illustrative):
    ::

        def save(self, entity: UserAccount) -> None:
            stmt = insert(user_accounts_table).values(
                user_id=str(entity.user_id),
                email=entity.email,
                ...
            ).on_conflict_do_update(index_elements=["user_id"], set_=...)
            self._conn.execute(stmt)
            self._conn.commit()
    """

    def __init__(self, connection_string: str) -> None:
        # TODO: initialise the DB engine / session here.
        self._connection_string = connection_string

    def save(self, entity: UserAccount) -> None:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_id(self, entity_id: UUID) -> Optional[UserAccount]:
        raise NotImplementedError("Database backend not yet connected")

    def find_all(self) -> List[UserAccount]:
        raise NotImplementedError("Database backend not yet connected")

    def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_email(self, email: str) -> Optional[UserAccount]:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_role(self, role: RoleEnum) -> List[UserAccount]:
        raise NotImplementedError("Database backend not yet connected")


class DatabaseApplicationRepository(ApplicationRepository):
    """Placeholder for a SQL-backed ``Application`` repository.

    See :class:`DatabaseUserAccountRepository` for the implementation guide.
    """

    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string

    def save(self, entity: Application) -> None:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_id(self, entity_id: UUID) -> Optional[Application]:
        raise NotImplementedError("Database backend not yet connected")

    def find_all(self) -> List[Application]:
        raise NotImplementedError("Database backend not yet connected")

    def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_learner(self, learner_id: UUID) -> List[Application]:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_programme(self, programme_id: UUID) -> List[Application]:
        raise NotImplementedError("Database backend not yet connected")

    def find_by_status(self, status: ApplicationStatusEnum) -> List[Application]:
        raise NotImplementedError("Database backend not yet connected")


class HttpApplicationRepository(ApplicationRepository):
    """Placeholder for an **external REST API** backend (scenario: remote CRUD).

    Wire with ``httpx`` / ``requests``: map HTTP verbs to ``save`` / ``find_by_id`` /
    ``delete`` and parse JSON into :class:`~unimatch.entities.Application`.
    Add a ``RepositoryFactory`` branch when ready (e.g. ``"HTTP"``).
    """

    def __init__(self, base_url: str, *, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def save(self, entity: Application) -> None:
        raise NotImplementedError("REST client not yet implemented")

    def find_by_id(self, entity_id: UUID) -> Optional[Application]:
        raise NotImplementedError("REST client not yet implemented")

    def find_all(self) -> List[Application]:
        raise NotImplementedError("REST client not yet implemented")

    def delete(self, entity_id: UUID) -> None:
        raise NotImplementedError("REST client not yet implemented")

    def find_by_learner(self, learner_id: UUID) -> List[Application]:
        raise NotImplementedError("REST client not yet implemented")

    def find_by_programme(self, programme_id: UUID) -> List[Application]:
        raise NotImplementedError("REST client not yet implemented")

    def find_by_status(self, status: ApplicationStatusEnum) -> List[Application]:
        raise NotImplementedError("REST client not yet implemented")


__all__ = [
    "FileSystemUserAccountRepository",
    "FileSystemApplicationRepository",
    "DatabaseUserAccountRepository",
    "DatabaseApplicationRepository",
    "HttpApplicationRepository",
]
