from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from unimatch.document_storage import (
    InvalidDocumentUpload,
    LocalDocumentStorage,
    validate_document_upload,
)
from unimatch.entities import Document
from unimatch.repositories.local_documents import LocalDocumentRepository


def _document() -> Document:
    return Document(
        document_id=uuid4(),
        learner_id=uuid4(),
        application_id=None,
        school_id=uuid4(),
        document_type="Identity document",
        filename="identity.pdf",
        storage_path="school/learner/document.pdf",
        mime_type="application/pdf",
        size_bytes=12,
        content_sha256="a" * 64,
        uploaded_by=uuid4(),
        virus_scan_status="NotScanned",
        status="PendingReview",
        uploaded_at=datetime.now(timezone.utc),
    )


def test_local_document_metadata_and_review_survive_repository_restart(tmp_path) -> None:
    repository = LocalDocumentRepository(tmp_path)
    document = _document()
    repository.save(document)
    document.review("Verified", uuid4(), "Original checked.")
    repository.save(document)

    reopened = LocalDocumentRepository(tmp_path).find_by_id(document.document_id)

    assert reopened is not None
    assert reopened.status == "Verified"
    assert reopened.reviewed_by == document.reviewed_by
    assert reopened.reviewed_at == document.reviewed_at
    assert reopened.review_note == "Original checked."
    assert reopened.virus_scan_status == "NotScanned"


def test_upload_validation_checks_extension_mime_size_and_signature() -> None:
    content = b"%PDF-1.7\n%%EOF"
    assert (
        validate_document_upload("identity.pdf", "application/pdf", content)
        == "identity.pdf"
    )
    with pytest.raises(InvalidDocumentUpload, match="extension and content type"):
        validate_document_upload("identity.pdf", "application/msword", content)
    with pytest.raises(InvalidDocumentUpload, match="valid PDF"):
        validate_document_upload("identity.pdf", "application/pdf", b"not a PDF")


def test_local_document_storage_rejects_paths_outside_its_root(tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.7")
    storage = LocalDocumentStorage(root)

    with pytest.raises(ValueError, match="escapes"):
        storage.resolve("../outside.pdf")
