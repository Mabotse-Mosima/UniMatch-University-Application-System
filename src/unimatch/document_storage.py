from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from unimatch.entities import Document

_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_DOC_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_MAX_DOCX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
_MAX_DOCX_ENTRIES = 500


class InvalidDocumentUpload(ValueError):
    pass


def validate_document_upload(
    filename: str, mime_type: str, contents: bytes
) -> str:
    safe_filename = Path(filename.replace("\\", "/")).name.strip()
    if not safe_filename or safe_filename in {".", ".."}:
        raise InvalidDocumentUpload("A valid filename is required.")
    if len(safe_filename) > 255 or any(
        ord(character) < 32 or ord(character) == 127 for character in safe_filename
    ):
        raise InvalidDocumentUpload("Filename is invalid or exceeds 255 characters.")
    extension = Path(safe_filename).suffix.lower()
    if _MIME_BY_EXTENSION.get(extension) != mime_type:
        raise InvalidDocumentUpload("File extension and content type do not match.")
    if not 0 < len(contents) <= Document._max_bytes:
        raise InvalidDocumentUpload("Document size must be between 1 byte and 5 MB.")

    if extension == ".pdf" and not contents.startswith(b"%PDF-"):
        raise InvalidDocumentUpload("The uploaded file is not a valid PDF.")
    if extension == ".doc" and not contents.startswith(_DOC_MAGIC):
        raise InvalidDocumentUpload("The uploaded file is not a valid DOC file.")
    if extension == ".docx":
        try:
            with ZipFile(BytesIO(contents)) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > _MAX_DOCX_ENTRIES
                    or sum(entry.file_size for entry in entries)
                    > _MAX_DOCX_UNCOMPRESSED_BYTES
                    or "[Content_Types].xml" not in archive.namelist()
                    or "word/document.xml" not in archive.namelist()
                    or any(entry.flag_bits & 0x1 for entry in entries)
                ):
                    raise InvalidDocumentUpload("The uploaded file is not a valid DOCX document.")
        except BadZipFile as exc:
            raise InvalidDocumentUpload("The uploaded file is not a valid DOCX document.") from exc

    return safe_filename


class LocalDocumentStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def save(
        self,
        school_id: UUID,
        learner_id: UUID,
        document_id: UUID,
        extension: str,
        contents: bytes,
    ) -> str:
        relative_path = Path(str(school_id), str(learner_id), f"{document_id}{extension}")
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as document_file:
            document_file.write(contents)
        return relative_path.as_posix()

    def resolve(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve(strict=True)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Document storage path escapes the configured root.") from exc
        if not target.is_file():
            raise FileNotFoundError("Stored document is not a regular file.")
        return target

    def remove(self, relative_path: str) -> None:
        try:
            target = self.resolve(relative_path)
        except FileNotFoundError:
            return
        target.unlink()
