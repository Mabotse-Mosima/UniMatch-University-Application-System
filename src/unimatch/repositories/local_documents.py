from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from unimatch.entities import Document
from unimatch.repositories import DocumentRepository


class LocalDocumentRepository(DocumentRepository):
    """Atomic JSON metadata store for the single-process local prototype."""

    def __init__(self, storage_root: Path) -> None:
        self._root = storage_root.expanduser().resolve()
        self._metadata_path = self._root / "documents.json"
        self._lock = RLock()
        self._store: dict[UUID, Document] = {}
        self._loaded = False

    def save(self, entity: Document) -> None:
        with self._lock:
            self._ensure_loaded()
            previous = self._store.get(entity.document_id)
            self._store[entity.document_id] = replace(entity)
            try:
                self._write_store()
            except (OSError, TypeError, ValueError):
                if previous is None:
                    self._store.pop(entity.document_id, None)
                else:
                    self._store[entity.document_id] = previous
                raise

    def find_by_id(self, entity_id: UUID) -> Document | None:
        with self._lock:
            self._ensure_loaded()
            document = self._store.get(entity_id)
            return None if document is None else replace(document)

    def find_all(self) -> list[Document]:
        with self._lock:
            self._ensure_loaded()
            return [
                replace(document)
                for document in sorted(
                    self._store.values(),
                    key=lambda item: (item.uploaded_at, item.document_id),
                )
            ]

    def delete(self, entity_id: UUID) -> None:
        with self._lock:
            self._ensure_loaded()
            previous = self._store.pop(entity_id, None)
            if previous is None:
                return
            try:
                self._write_store()
            except (OSError, TypeError, ValueError):
                self._store[entity_id] = previous
                raise

    def find_by_learner(self, learner_id: UUID) -> list[Document]:
        with self._lock:
            self._ensure_loaded()
            return [
                replace(document)
                for document in sorted(
                    (
                        item
                        for item in self._store.values()
                        if item.learner_id == learner_id
                    ),
                    key=lambda item: (item.uploaded_at, item.document_id),
                )
            ]

    def find_by_application(self, application_id: UUID) -> list[Document]:
        with self._lock:
            self._ensure_loaded()
            return [
                replace(document)
                for document in sorted(
                    (
                        item
                        for item in self._store.values()
                        if item.application_id == application_id
                    ),
                    key=lambda item: (item.uploaded_at, item.document_id),
                )
            ]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._metadata_path.exists():
            try:
                raw_records = json.loads(self._metadata_path.read_text(encoding="utf-8"))
                if not isinstance(raw_records, list):
                    raise ValueError("Document metadata must be a JSON list.")
                self._store = {
                    document.document_id: document
                    for document in (self._document_from_json(record) for record in raw_records)
                }
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
            ) as exc:
                raise RuntimeError("The local learner-document metadata file is invalid.") from exc
        self._loaded = True

    def _write_store(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        temporary_path = self._root / f".documents-{uuid4().hex}.tmp"
        try:
            with temporary_path.open("x", encoding="utf-8") as file:
                json.dump(
                    [self._document_to_json(document) for document in self._store.values()],
                    file,
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._metadata_path)
        except (OSError, TypeError, ValueError):
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _document_to_json(document: Document) -> dict[str, Any]:
        return {
            "document_id": str(document.document_id),
            "learner_id": str(document.learner_id),
            "application_id": (
                str(document.application_id) if document.application_id is not None else None
            ),
            "school_id": str(document.school_id),
            "document_type": document.document_type,
            "filename": document.filename,
            "storage_path": document.storage_path,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "content_sha256": document.content_sha256,
            "uploaded_by": str(document.uploaded_by),
            "virus_scan_status": document.virus_scan_status,
            "status": document.status,
            "uploaded_at": document.uploaded_at.isoformat(),
            "reviewed_by": (
                str(document.reviewed_by) if document.reviewed_by is not None else None
            ),
            "reviewed_at": (
                document.reviewed_at.isoformat()
                if document.reviewed_at is not None
                else None
            ),
            "review_note": document.review_note,
        }

    @staticmethod
    def _document_from_json(record: Any) -> Document:
        if not isinstance(record, dict):
            raise ValueError("Document metadata records must be objects.")
        return Document(
            document_id=UUID(record["document_id"]),
            learner_id=UUID(record["learner_id"]),
            application_id=(
                UUID(record["application_id"])
                if record["application_id"] is not None
                else None
            ),
            school_id=UUID(record["school_id"]),
            document_type=str(record["document_type"]),
            filename=str(record["filename"]),
            storage_path=str(record["storage_path"]),
            mime_type=str(record["mime_type"]),
            size_bytes=int(record["size_bytes"]),
            content_sha256=str(record["content_sha256"]),
            uploaded_by=UUID(record["uploaded_by"]),
            virus_scan_status=str(record["virus_scan_status"]),
            status=str(record["status"]),
            uploaded_at=datetime.fromisoformat(record["uploaded_at"]),
            reviewed_by=(
                UUID(record["reviewed_by"])
                if record["reviewed_by"] is not None
                else None
            ),
            reviewed_at=(
                datetime.fromisoformat(record["reviewed_at"])
                if record["reviewed_at"] is not None
                else None
            ),
            review_note=str(record["review_note"]),
        )
