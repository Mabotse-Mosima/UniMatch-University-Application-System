from __future__ import annotations

from dataclasses import replace
from html import escape
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy.dialects.postgresql import JSONB

from unimatch.db_models import RagChunkRecord, RagDocumentRecord

from unimatch.rag import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    LEGACY_EMBEDDING_MODEL,
    EmbeddingState,
    ExtractiveGroundedAnswerProvider,
    RagGenerationUnavailableError,
    InMemoryRagRepository,
    RagChunk,
    RagDocument,
    LogicalDocumentState,
    PhysicalDocumentState,
    RagLifecycleError,
    RagLogicalDocumentNotFoundError,
    RagReindexRequiredError,
    RagInputError,
    _validate_generated_citations,
    chunk_text,
    embed_text,
    extract_document_text,
    generate_grounded_answer,
    retrieve_chunks,
)


def _lifecycle_document(
    university_id,
    *,
    digest="a" * 64,
    logical_document_id=None,
    document_id=None,
    embedding_model=EMBEDDING_MODEL,
    embedding_revision=EMBEDDING_REVISION,
    embedding_state=EmbeddingState.REINDEX_REQUIRED,
    version_number=1,
    lifecycle_state=PhysicalDocumentState.ACTIVE,
):
    return RagDocument(
        document_id=document_id or uuid4(),
        university_id=university_id,
        title="Admissions guide",
        file_name="admissions-guide.pdf",
        content_type="application/pdf",
        content_sha256=digest,
        uploaded_by=uuid4(),
        embedding_model=embedding_model,
        embedding_revision=embedding_revision,
        logical_document_id=logical_document_id,
        version_number=version_number,
        lifecycle_state=lifecycle_state,
        embedding_state=embedding_state,
    )


def _lifecycle_chunks(document, count=1):
    embedding = (1.0,) * document.embedding_dimensions
    return [
        RagChunk(
            chunk_id=uuid4(),
            document_id=document.document_id,
            chunk_index=index,
            text=f"Admissions passage {index}",
            embedding=embedding,
        )
        for index in range(count)
    ]


def _repository_state(repository):
    return (
        repository._logical_documents.copy(),
        repository._documents.copy(),
        {
            document_id: list(chunks)
            for document_id, chunks in repository._chunks.items()
        },
        repository._conversations.copy(),
        {
            conversation_id: list(messages)
            for conversation_id, messages in repository._messages.items()
        },
    )


def _docx_bytes(text: str) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p></w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def _pdf_bytes(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, content in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(content)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def test_docx_extraction_cleans_text_and_rejects_empty_or_invalid_documents():
    text, content_type = extract_document_text(
        "synthetic-rules-fixture.docx",
        _docx_bytes("  Mathematics   is required.\n Applications close in September. "),
    )

    assert text == "Mathematics is required.\nApplications close in September."
    assert content_type.endswith("wordprocessingml.document")

    with pytest.raises(RagInputError, match="could not be read"):
        extract_document_text("broken.docx", b"not a zip file")
    with pytest.raises(RagInputError, match="valid PDF"):
        extract_document_text("broken.pdf", b"not a PDF")
    with pytest.raises(RagInputError, match="Only PDF and DOCX"):
        extract_document_text("rules.txt", b"plain text")


def test_pdf_extraction_reads_real_selectable_text():
    text, content_type = extract_document_text(
        "synthetic-rules-fixture.pdf",
        _pdf_bytes("Mathematics is required for admission."),
    )

    assert text == "Mathematics is required for admission."
    assert content_type == "application/pdf"


def test_chunking_respects_size_and_overlap():
    text = "Admissions requirements " * 120

    chunks = chunk_text(text)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 900 for chunk in chunks)
    assert set(chunks[0][-80:].split()).intersection(chunks[1][:80].split())


def test_semantic_retrieval_ranks_paraphrased_question_and_cites_the_source():
    relevant = RagDocument(
        document_id=uuid4(),
        university_id=uuid4(),
        title="Synthetic admissions fixture",
        file_name="synthetic-admissions.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content_sha256="a" * 64,
        uploaded_by=uuid4(),
    )
    unrelated = RagDocument(
        document_id=uuid4(),
        university_id=uuid4(),
        title="Synthetic transport fixture",
        file_name="synthetic-transport.pdf",
        content_type="application/pdf",
        content_sha256="b" * 64,
        uploaded_by=uuid4(),
    )
    relevant_text = (
        "Applicants to the BSc Computer Science programme need a score of at least "
        "70 percent in Mathematics. Applications close on 30 September."
    )
    unrelated_text = (
        "Campus shuttle routes run between residences and lecture halls."
    )
    question = "What math grade do I need to be accepted?"
    matches = retrieve_chunks(
        question,
        [
            (
                unrelated,
                RagChunk(uuid4(), unrelated.document_id, 0, unrelated_text, embed_text(unrelated_text)),
            ),
            (
                relevant,
                RagChunk(uuid4(), relevant.document_id, 0, relevant_text, embed_text(relevant_text)),
            ),
        ],
    )

    answer, sources = generate_grounded_answer(
        question,
        matches,
    )

    assert matches
    assert matches[0][1].document_id == relevant.document_id
    assert "Mathematics" in answer
    assert sources[0]["document_id"] == str(relevant.document_id)
    assert sources[0]["university_id"] == str(relevant.university_id)
    assert sources[0]["file_name"] == "synthetic-admissions.docx"
    assert sources[0]["passage"] == relevant_text
    assert matches[0][0] >= 0.30


def test_unrelated_question_returns_insufficient_retrieval_without_fabrication():
    document = RagDocument(
        document_id=uuid4(),
        university_id=uuid4(),
        title="Admissions",
        file_name="admissions.pdf",
        content_type="application/pdf",
        content_sha256="c" * 64,
        uploaded_by=uuid4(),
    )
    passage = "Applicants must submit a Mathematics result with their application."
    matches = retrieve_chunks(
        "What is the weather tomorrow?",
        [
            (
                document,
                RagChunk(uuid4(), document.document_id, 0, passage, embed_text(passage)),
            )
        ],
    )

    answer, sources = generate_grounded_answer("What is the weather tomorrow?", matches)

    assert not matches
    assert not sources
    assert "could not find a sufficiently relevant" in answer


def test_learner_results_are_labeled_as_deterministic_and_not_admission_decisions():
    eligibility = [
        {
            "programme_name": "BSc Example",
            "aps_score": 30,
            "minimum_aps": 25,
            "eligibility": "NotEligible",
            "unmet_subjects": ["Mathematics (minimum 70; recorded 50)"],
        }
    ]

    answer, sources = generate_grounded_answer(
        "Why is my APS eligibility NotEligible for BSc Example?",
        [],
        eligibility=eligibility,
    )

    assert not sources
    assert "BSc Example: APS 30 against minimum APS 25; result NotEligible." in answer
    assert "Mathematics (minimum 70; recorded 50)" in answer
    assert "not admission decisions" in answer


def test_semantic_model_identity_and_dimensions_are_pinned():
    vector = embed_text("Mathematics is a compulsory admission subject.")

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert sum(value * value for value in vector) == pytest.approx(1.0, abs=1e-5)
    assert EMBEDDING_MODEL == "sentence-transformers/all-MiniLM-L6-v2"
    assert EMBEDDING_REVISION == "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def test_postgres_rag_orm_exposes_embedding_metadata_and_jsonb_vectors():
    document_columns = RagDocumentRecord.__table__.c
    constraints = {
        constraint.name for constraint in RagDocumentRecord.__table__.constraints
    }
    indexes = {index.name for index in RagDocumentRecord.__table__.indexes}

    assert {
        "embedding_model",
        "embedding_revision",
        "embedding_dimensions",
    }.issubset(document_columns.keys())
    assert "ck_rag_documents_embedding_dimensions" in constraints
    assert "ix_rag_documents_university_embedding" in indexes
    assert isinstance(RagChunkRecord.__table__.c.embedding.type, JSONB)


def test_retrieval_rejects_vectors_from_another_embedding_model():
    document = RagDocument(
        document_id=uuid4(),
        university_id=uuid4(),
        title="Synthetic admissions fixture",
        file_name="synthetic-admissions.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content_sha256="d" * 64,
        uploaded_by=uuid4(),
        embedding_model=LEGACY_EMBEDDING_MODEL,
        embedding_revision="legacy",
    )
    text = "Applicants need Mathematics to meet the programme entry requirements."
    chunk = RagChunk(uuid4(), document.document_id, 0, text, embed_text(text))

    with pytest.raises(RagReindexRequiredError, match="Re-index"):
        retrieve_chunks("What maths subject is needed?", [(document, chunk)])


def test_in_memory_reindex_and_delete_are_university_scoped():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    other_university_id = uuid4()
    document = RagDocument(
        document_id=uuid4(),
        university_id=university_id,
        title="Synthetic admissions fixture",
        file_name="synthetic-admissions.pdf",
        content_type="application/pdf",
        content_sha256="e" * 64,
        uploaded_by=uuid4(),
        embedding_model=LEGACY_EMBEDDING_MODEL,
        embedding_revision="legacy",
    )
    text = "Applicants need Mathematics to meet the programme entry requirements."
    chunk = RagChunk(uuid4(), document.document_id, 0, text, embed_text(text))
    repository.ingest_document(document, [chunk])

    assert repository.list_chunks({other_university_id}) == []
    with pytest.raises(RagReindexRequiredError, match="Re-index"):
        retrieve_chunks(
            "What maths subject is needed?",
            repository.list_chunks({university_id}),
        )

    indexed = repository.reindex_document(
        document.document_id,
        university_id,
        [chunk],
    )

    assert indexed is not None
    assert indexed.embedding_model == EMBEDDING_MODEL
    assert indexed.embedding_revision == EMBEDDING_REVISION
    assert indexed.embedding_dimensions == EMBEDDING_DIMENSIONS
    assert retrieve_chunks(
        "What maths subject is needed?",
        repository.list_chunks({university_id}),
    )
    assert not repository.delete_document(document.document_id, other_university_id)
    assert repository.delete_document(document.document_id, university_id)
    deleted = repository.list_documents(university_id)
    assert len(deleted) == 1
    assert deleted[0].document_id == document.document_id
    assert deleted[0].lifecycle_state is PhysicalDocumentState.DELETED
    assert deleted[0].embedding_state is EmbeddingState.EMBEDDINGS_READY
    assert repository.list_chunks({university_id}) == []
    assert repository.get_document_chunks(document.document_id, university_id) is None


def test_first_upload_creates_logical_document_and_active_version_one():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    candidate = _lifecycle_document(university_id, digest="1" * 64)

    stored = repository.ingest_document(candidate, _lifecycle_chunks(candidate))

    assert stored.document_id == candidate.document_id
    assert stored.logical_document_id is not None
    assert stored.version_number == 1
    assert stored.lifecycle_state is PhysicalDocumentState.ACTIVE
    assert stored.embedding_state is EmbeddingState.EMBEDDINGS_READY
    assert repository.find_logical_document(
        stored.logical_document_id, university_id
    ).lifecycle_state is LogicalDocumentState.ACTIVE


def test_replacement_uses_only_an_explicit_existing_logical_identity():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="2" * 64)
    stored_first = repository.ingest_document(first, _lifecycle_chunks(first))

    independent = _lifecycle_document(university_id, digest="3" * 64)
    stored_independent = repository.ingest_document(
        independent, _lifecycle_chunks(independent)
    )
    assert stored_independent.logical_document_id != stored_first.logical_document_id

    unknown_identity = _lifecycle_document(
        university_id, digest="4" * 64, logical_document_id=uuid4()
    )
    with pytest.raises(RagLogicalDocumentNotFoundError):
        repository.ingest_document(
            unknown_identity, _lifecycle_chunks(unknown_identity)
        )


def test_replacements_increment_versions_and_supersede_the_previous_active_version():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="5" * 64)
    version_one = repository.ingest_document(first, _lifecycle_chunks(first))

    second = _lifecycle_document(
        university_id,
        digest="6" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_two = repository.ingest_document(second, _lifecycle_chunks(second))
    assert version_two.version_number == 2
    assert next(
        item
        for item in repository.list_documents(university_id)
        if item.document_id == version_one.document_id
    ).lifecycle_state is PhysicalDocumentState.SUPERSEDED

    third = _lifecycle_document(
        university_id,
        digest="7" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_three = repository.ingest_document(third, _lifecycle_chunks(third))

    assert version_three.version_number == 3
    assert sum(
        item.lifecycle_state is PhysicalDocumentState.ACTIVE
        for item in repository.list_documents(university_id)
        if item.logical_document_id == version_one.logical_document_id
    ) == 1


def test_deleted_logical_documents_cannot_be_replaced():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="8" * 64)
    stored = repository.ingest_document(first, _lifecycle_chunks(first))
    assert repository.delete_document(stored.document_id, university_id)

    replacement = _lifecycle_document(
        university_id,
        digest="9" * 64,
        logical_document_id=stored.logical_document_id,
    )
    with pytest.raises(RagLifecycleError, match="deleted"):
        repository.ingest_document(replacement, _lifecycle_chunks(replacement))


def test_duplicate_active_content_is_rejected_but_same_logical_replacement_is_allowed():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="b" * 64)
    stored = repository.ingest_document(first, _lifecycle_chunks(first))

    duplicate = _lifecycle_document(university_id, digest="b" * 64)
    with pytest.raises(ValueError, match="already indexed"):
        repository.ingest_document(duplicate, _lifecycle_chunks(duplicate))

    replacement = _lifecycle_document(
        university_id,
        digest="b" * 64,
        logical_document_id=stored.logical_document_id,
    )
    version_two = repository.ingest_document(
        replacement, _lifecycle_chunks(replacement)
    )
    assert version_two.version_number == 2
    assert repository.find_document_by_hash(university_id, "b" * 64) == version_two


def test_logical_document_ownership_is_university_scoped():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    other_university_id = uuid4()
    first = _lifecycle_document(university_id, digest="c" * 64)
    stored = repository.ingest_document(first, _lifecycle_chunks(first))

    assert repository.find_logical_document(
        stored.logical_document_id, other_university_id
    ) is None
    assert not repository.delete_logical_document(
        stored.logical_document_id, other_university_id
    )
    assert not repository.delete_document(stored.document_id, other_university_id)
    replacement = _lifecycle_document(
        other_university_id,
        digest="d" * 64,
        logical_document_id=stored.logical_document_id,
    )
    with pytest.raises(RagLogicalDocumentNotFoundError):
        repository.ingest_document(replacement, _lifecycle_chunks(replacement))


def test_active_chunks_require_active_logical_physical_and_ready_embedding_states():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="e" * 64)
    version_one = repository.ingest_document(first, _lifecycle_chunks(first))
    second = _lifecycle_document(
        university_id,
        digest="f" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_two = repository.ingest_document(second, _lifecycle_chunks(second))

    legacy = _lifecycle_document(
        university_id,
        digest="a" * 63 + "0",
        embedding_model=LEGACY_EMBEDDING_MODEL,
        embedding_revision="legacy",
    )
    stored_legacy = repository.ingest_document(legacy, _lifecycle_chunks(legacy))
    no_chunks = _lifecycle_document(university_id, digest="a" * 63 + "1")
    stored_no_chunks = repository.ingest_document(no_chunks, [])

    active_chunks = repository.list_active_chunks({university_id})
    assert [document.document_id for document, _chunk in active_chunks] == [
        version_two.document_id
    ]
    assert stored_legacy.embedding_state is EmbeddingState.REINDEX_REQUIRED
    assert stored_no_chunks.embedding_state is EmbeddingState.REINDEX_REQUIRED
    assert {
        document.document_id
        for document, _chunk in repository.list_chunks({university_id})
    } == {
        version_one.document_id,
        version_two.document_id,
        stored_legacy.document_id,
    }


def test_deleting_active_physical_version_deletes_its_logical_document_and_chunks():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    document = _lifecycle_document(university_id, digest="2" * 64)
    stored = repository.ingest_document(document, _lifecycle_chunks(document, count=2))

    assert repository.delete_document(stored.document_id, university_id)
    history = repository.list_documents(university_id)
    assert len(history) == 1
    assert history[0].lifecycle_state is PhysicalDocumentState.DELETED
    logical = repository.find_logical_document(stored.logical_document_id, university_id)
    assert logical is not None
    assert logical.lifecycle_state is LogicalDocumentState.DELETED
    assert repository.list_chunks({university_id}) == []


def test_deleting_superseded_physical_version_preserves_active_sibling():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="3" * 64)
    version_one = repository.ingest_document(first, _lifecycle_chunks(first))
    second = _lifecycle_document(
        university_id,
        digest="4" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_two = repository.ingest_document(second, _lifecycle_chunks(second))

    assert repository.delete_document(version_one.document_id, university_id)
    versions = repository.list_documents(university_id)
    states = {item.document_id: item.lifecycle_state for item in versions}
    assert states[version_one.document_id] is PhysicalDocumentState.DELETED
    assert states[version_two.document_id] is PhysicalDocumentState.ACTIVE
    assert repository.find_logical_document(
        version_one.logical_document_id, university_id
    ).lifecycle_state is LogicalDocumentState.ACTIVE
    assert [document.document_id for document, _ in repository.list_active_chunks(
        {university_id}
    )] == [version_two.document_id]


def test_logical_deletion_removes_only_its_versions_chunks_and_preserves_history():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="5" * 64)
    version_one = repository.ingest_document(first, _lifecycle_chunks(first))
    second = _lifecycle_document(
        university_id,
        digest="6" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_two = repository.ingest_document(second, _lifecycle_chunks(second))
    assert repository.delete_document(version_one.document_id, university_id)
    third = _lifecycle_document(
        university_id,
        digest="7" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_three = repository.ingest_document(third, _lifecycle_chunks(third))
    other = _lifecycle_document(university_id, digest="8" * 64)
    other_logical = repository.ingest_document(other, _lifecycle_chunks(other))

    assert repository.delete_logical_document(
        version_one.logical_document_id, university_id
    )

    history = {item.document_id: item for item in repository.list_documents(university_id)}
    assert history[version_one.document_id].lifecycle_state is PhysicalDocumentState.DELETED
    assert history[version_two.document_id].lifecycle_state is PhysicalDocumentState.SUPERSEDED
    assert history[version_three.document_id].lifecycle_state is PhysicalDocumentState.DELETED
    assert history[other_logical.document_id].lifecycle_state is PhysicalDocumentState.ACTIVE
    remaining = repository.list_chunks({university_id})
    assert {document.document_id for document, _ in remaining} == {
        other_logical.document_id
    }
    assert [document.document_id for document, _ in repository.list_active_chunks(
        {university_id}
    )] == [other_logical.document_id]


@pytest.mark.parametrize(
    "overrides",
    [
        {"version_number": 0},
        {"version_number": -1},
        {"version_number": 1.5},
        {"lifecycle_state": "Archived"},
        {"embedding_state": "Indexed"},
        {
            "embedding_state": EmbeddingState.EMBEDDINGS_READY,
            "embedding_model": LEGACY_EMBEDDING_MODEL,
        },
    ],
)
def test_invalid_document_version_and_state_combinations_are_rejected(overrides):
    with pytest.raises(ValueError):
        _lifecycle_document(uuid4(), **overrides)


def test_ingestion_rejects_non_active_new_physical_versions():
    repository = InMemoryRagRepository()
    document = _lifecycle_document(
        uuid4(),
        digest="9" * 64,
        lifecycle_state=PhysicalDocumentState.SUPERSEDED,
    )

    with pytest.raises(RagLifecycleError, match="New uploads"):
        repository.ingest_document(document, _lifecycle_chunks(document))


def test_lifecycle_invariant_rejects_duplicate_logical_document_versions():
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="c" * 64)
    version_one = repository.ingest_document(first, _lifecycle_chunks(first))
    second = _lifecycle_document(
        university_id,
        digest="d" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_two = repository.ingest_document(second, _lifecycle_chunks(second))
    repository._documents[version_two.document_id] = replace(
        version_two, version_number=version_one.version_number
    )

    with pytest.raises(RagLifecycleError, match="duplicate version"):
        repository._assert_lifecycle_invariants()


@pytest.mark.parametrize(
    "embedding",
    [
        (1.0,) * (EMBEDDING_DIMENSIONS - 1),
        ("not numeric",) + (1.0,) * (EMBEDDING_DIMENSIONS - 1),
        (float("nan"),) + (1.0,) * (EMBEDDING_DIMENSIONS - 1),
        (float("inf"),) + (1.0,) * (EMBEDDING_DIMENSIONS - 1),
        (-float("inf"),) + (1.0,) * (EMBEDDING_DIMENSIONS - 1),
    ],
)
@pytest.mark.parametrize("is_replacement", [False, True])
def test_invalid_embedding_chunks_are_not_persisted_or_partially_replace(
    embedding, is_replacement
):
    repository = InMemoryRagRepository()
    university_id = uuid4()
    logical_document_id = None
    if is_replacement:
        original = _lifecycle_document(university_id, digest="e" * 64)
        stored_original = repository.ingest_document(
            original, _lifecycle_chunks(original, count=2)
        )
        logical_document_id = stored_original.logical_document_id

    document = _lifecycle_document(
        university_id,
        digest="f" * 64,
        logical_document_id=logical_document_id,
    )
    invalid_chunk = RagChunk(
        uuid4(),
        document.document_id,
        0,
        "Invalid embedding fixture",
        embedding,
    )
    state_before = _repository_state(repository)

    with pytest.raises(ValueError, match="embedding metadata"):
        repository.ingest_document(document, [invalid_chunk])

    assert _repository_state(repository) == state_before


def test_failed_replacement_rolls_back_documents_logical_state_and_chunks(monkeypatch):
    repository = InMemoryRagRepository()
    university_id = uuid4()
    original = _lifecycle_document(university_id, digest="1" * 64)
    stored_original = repository.ingest_document(
        original, _lifecycle_chunks(original, count=2)
    )
    state_before = _repository_state(repository)

    def fail_invariant_check():
        raise RuntimeError("Injected replacement failure.")

    monkeypatch.setattr(repository, "_assert_lifecycle_invariants", fail_invariant_check)
    replacement = _lifecycle_document(
        university_id,
        digest="2" * 64,
        logical_document_id=stored_original.logical_document_id,
    )
    with pytest.raises(RuntimeError, match="Injected replacement failure"):
        repository.ingest_document(replacement, _lifecycle_chunks(replacement))

    assert _repository_state(repository) == state_before
    assert repository._documents[stored_original.document_id].lifecycle_state is (
        PhysicalDocumentState.ACTIVE
    )
    assert repository._logical_documents[
        stored_original.logical_document_id
    ].lifecycle_state is LogicalDocumentState.ACTIVE


def test_failed_physical_deletion_rolls_back_lifecycle_and_chunks(monkeypatch):
    repository = InMemoryRagRepository()
    university_id = uuid4()
    document = _lifecycle_document(university_id, digest="3" * 64)
    stored = repository.ingest_document(document, _lifecycle_chunks(document, count=2))
    state_before = _repository_state(repository)

    def fail_invariant_check():
        raise RuntimeError("Injected physical deletion failure.")

    monkeypatch.setattr(repository, "_assert_lifecycle_invariants", fail_invariant_check)
    with pytest.raises(RuntimeError, match="Injected physical deletion failure"):
        repository.delete_document(stored.document_id, university_id)

    assert _repository_state(repository) == state_before


def test_failed_logical_deletion_rolls_back_all_version_states_and_chunks(monkeypatch):
    repository = InMemoryRagRepository()
    university_id = uuid4()
    first = _lifecycle_document(university_id, digest="4" * 64)
    version_one = repository.ingest_document(first, _lifecycle_chunks(first, count=2))
    second = _lifecycle_document(
        university_id,
        digest="5" * 64,
        logical_document_id=version_one.logical_document_id,
    )
    version_two = repository.ingest_document(second, _lifecycle_chunks(second, count=2))
    other = _lifecycle_document(university_id, digest="6" * 64)
    other_document = repository.ingest_document(other, _lifecycle_chunks(other))
    state_before = _repository_state(repository)

    def fail_invariant_check():
        raise RuntimeError("Injected logical deletion failure.")

    monkeypatch.setattr(repository, "_assert_lifecycle_invariants", fail_invariant_check)
    with pytest.raises(RuntimeError, match="Injected logical deletion failure"):
        repository.delete_logical_document(
            version_one.logical_document_id, university_id
        )

    assert _repository_state(repository) == state_before
    assert repository._documents[version_one.document_id].lifecycle_state is (
        PhysicalDocumentState.SUPERSEDED
    )
    assert repository._documents[version_two.document_id].lifecycle_state is (
        PhysicalDocumentState.ACTIVE
    )
    assert repository._documents[other_document.document_id].lifecycle_state is (
        PhysicalDocumentState.ACTIVE
    )


def test_extractive_provider_is_explicitly_labeled_as_fallback():
    assert ExtractiveGroundedAnswerProvider.generation_mode == "local-extractive"


def test_generated_citations_accept_references_to_supplied_sources():
    sources = [{"title": "Admissions guide"}, {"title": "Faculty rules"}]

    assert _validate_generated_citations(
        "Mathematics is required [Source 1].", sources
    ) == [sources[0]]


def test_generated_citations_reject_answers_with_missing_references():
    with pytest.raises(RagGenerationUnavailableError, match="did not cite"):
        _validate_generated_citations("Mathematics is required.", [{"title": "Guide"}])


def test_generated_citations_deduplicate_repeated_valid_references():
    source = {"title": "Admissions guide"}

    assert _validate_generated_citations(
        "See [Source 1]. As stated in [Source 1], Mathematics is required.",
        [source],
    ) == [source]


@pytest.mark.parametrize("citation", ["[Source 2]", "[Source x]"])
def test_generated_citations_reject_invalid_or_unsupplied_references(citation):
    with pytest.raises(RagGenerationUnavailableError, match="source"):
        _validate_generated_citations(f"Claim {citation}.", [{"title": "Guide"}])


def test_generated_citations_reject_any_reference_when_no_sources_were_supplied():
    with pytest.raises(RagGenerationUnavailableError, match="no source passage"):
        _validate_generated_citations("Claim [Source 1].", [])
