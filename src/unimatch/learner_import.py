"""Validation for school-scoped learner and mark CSV imports."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field


MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
MAX_IMPORT_LEARNERS = 1000

REQUIRED_COLUMNS = {
    "school_id_number",
    "full_name",
    "grade",
    "subject_name",
    "score",
    "exam_type",
    "academic_year",
}
COLUMN_ALIASES = {
    "student_number": "school_id_number",
    "student_no": "school_id_number",
    "student_id": "school_id_number",
}


@dataclass(frozen=True)
class ImportedMark:
    subject_name: str
    score: int
    exam_type: str
    academic_year: int
    row_number: int


@dataclass
class ImportedLearner:
    school_id_number: str
    full_name: str
    grade: int
    first_row: int
    marks: list[ImportedMark] = field(default_factory=list)


class LearnerImportValidationError(ValueError):
    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__("The spreadsheet has invalid rows.")
        self.errors = errors


def parse_learner_csv(contents: bytes) -> list[ImportedLearner]:
    """Parse a CSV with one row per learner subject mark.

    Required headers: school_id_number, full_name, grade, subject_name, score,
    exam_type, academic_year. Learner identity fields repeat on each mark row.
    No records are written by this parser.
    """
    if not contents:
        raise LearnerImportValidationError([{"row": 1, "message": "The file is empty."}])
    if len(contents) > MAX_IMPORT_BYTES:
        raise LearnerImportValidationError([{"row": 0, "message": "The file exceeds the 5 MB limit."}])
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LearnerImportValidationError([
            {"row": 0, "message": "Save the spreadsheet as a UTF-8 CSV file and try again."}
        ]) from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    raw_headers = reader.fieldnames or []
    headers: list[str] = []
    for header in raw_headers:
        normalized = (header or "").strip().lower().replace(" ", "_").replace("-", "_")
        headers.append(COLUMN_ALIASES.get(normalized, normalized))
    if len(headers) != len(set(headers)):
        raise LearnerImportValidationError([{"row": 1, "message": "Column names must be unique."}])
    missing = sorted(REQUIRED_COLUMNS - set(headers))
    if missing:
        raise LearnerImportValidationError([{
            "row": 1,
            "message": "Missing required columns: " + ", ".join(missing),
        }])

    learners: dict[str, ImportedLearner] = {}
    errors: list[dict[str, object]] = []
    mark_keys: dict[str, set[tuple[str, str, int]]] = {}
    rows_seen = 0

    for row_number, raw_row in enumerate(reader, start=2):
        rows_seen += 1
        if rows_seen > MAX_IMPORT_ROWS:
            errors.append({"row": row_number, "message": f"The file may contain at most {MAX_IMPORT_ROWS} rows."})
            break
        if None in raw_row:
            errors.append({"row": row_number, "message": "This row has more values than the header."})
            continue
        values = {
            headers[index]: (raw_row.get(raw_headers[index]) or "").strip()
            for index in range(len(headers))
        }
        if not any(values.values()):
            continue

        student_number = values["school_id_number"]
        full_name = values["full_name"]
        identity_key = student_number.casefold()
        row_errors: list[str] = []
        if not student_number:
            row_errors.append("school_id_number is required.")
        elif len(student_number) > 100:
            row_errors.append("school_id_number must be at most 100 characters.")
        if not full_name:
            row_errors.append("full_name is required.")
        elif len(full_name) > 255:
            row_errors.append("full_name must be at most 255 characters.")
        try:
            grade = int(values["grade"])
            if not 8 <= grade <= 12:
                row_errors.append("grade must be between 8 and 12.")
        except ValueError:
            grade = 0
            row_errors.append("grade must be a whole number between 8 and 12.")
        try:
            score = int(values["score"])
            if not 0 <= score <= 100:
                row_errors.append("score must be between 0 and 100.")
        except ValueError:
            score = -1
            row_errors.append("score must be a whole number between 0 and 100.")
        exam_type = values["exam_type"]
        if not exam_type:
            row_errors.append("exam_type is required.")
        elif len(exam_type) > 100:
            row_errors.append("exam_type must be at most 100 characters.")
        subject_name = values["subject_name"]
        if not subject_name:
            row_errors.append("subject_name is required.")
        elif len(subject_name) > 255:
            row_errors.append("subject_name must be at most 255 characters.")
        try:
            academic_year = int(values["academic_year"])
            if not 1900 <= academic_year <= 2200:
                row_errors.append("academic_year must be between 1900 and 2200.")
        except ValueError:
            academic_year = 0
            row_errors.append("academic_year must be a whole number.")

        if row_errors:
            errors.append({"row": row_number, "message": " ".join(row_errors)})
            continue

        learner = learners.get(identity_key)
        if learner is None:
            learner = ImportedLearner(student_number, full_name, grade, row_number)
            learners[identity_key] = learner
            mark_keys[identity_key] = set()
        elif learner.full_name != full_name or learner.grade != grade:
            errors.append({
                "row": row_number,
                "message": "Rows for the same school_id_number must have the same full_name and grade.",
            })
            continue

        mark_key = (subject_name.casefold(), exam_type.casefold(), academic_year)
        if mark_key in mark_keys[identity_key]:
            errors.append({
                "row": row_number,
                "message": "This learner has a duplicate subject, exam_type and academic_year entry.",
            })
            continue
        mark_keys[identity_key].add(mark_key)
        learner.marks.append(ImportedMark(subject_name, score, exam_type, academic_year, row_number))

    if not learners and not errors:
        errors.append({"row": 0, "message": "The file contains no learner mark rows."})
    if len(learners) > MAX_IMPORT_LEARNERS:
        errors.append({"row": 0, "message": f"The file may contain at most {MAX_IMPORT_LEARNERS} learners."})
    if errors:
        raise LearnerImportValidationError(errors)
    return list(learners.values())
