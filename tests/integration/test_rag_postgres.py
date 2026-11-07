from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from unimatch.db_models import AccountRecord, Base
from unimatch.rag import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    EmbeddingState,
    LogicalDocumentState,
    PhysicalDocumentState,
    RagChunk,
    RagDocument,
)
from unimatch.repositories.postgres import PostgresRagRepository


def _safe_test_url() -> URL:
    raw_url = os.environ.get("UNIMATCH_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "Set UNIMATCH_TEST_DATABASE_URL to run PostgreSQL RAG integration tests"
        )
    if os.environ.get("UNIMATCH_TEST_DATABASE_APPROVED") != "1":
        pytest.skip(
            "Set UNIMATCH_TEST_DATABASE_APPROVED=1 after verifying the test database"
        )

    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database is None
        or not url.database.endswith("_test")
    ):
        pytest.fail(
            "PostgreSQL RAG tests require a local psycopg URL whose database "
            "name ends in _test"
        )

    application_url = os.environ.get("DATABASE_URL")
    if application_url and make_url(application_url).render_as_string(
        hide_password=True
    ) == url.render_as_string(hide_password=True):
        pytest.fail("The RAG integration test URL must be separate from DATABASE_URL")
    return url


def _run_alembic(engine, schema_name: str, revision: str) -> None:
    project_root = Path(__file__).parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(project_root / "src"))
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema_name}"'))
        connection.commit()
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


@pytest.fixture(scope="module")
def migrated_schema():
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_rag_migration_test_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {quote(schema_name)}"))
    try:
        _run_alembic(engine, schema_name, "0006_semantic_embedding_metadata")
        yield engine, schema_name
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {quote(schema_name)} CASCADE"))
        engine.dispose()


@pytest.fixture
def repository():
    url = _safe_test_url()
    engine = create_engine(url, pool_pre_ping=True)
    schema_name = f"unimatch_rag_repo_test_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {quote(schema_name)}"))
    isolated_engine = engine.execution_options(
        schema_translate_map={None: schema_name}
    )
    try:
        Base.metadata.create_all(isolated_engine)
        factory = sessionmaker(bind=isolated_engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        account_id = uuid4()
        with factory() as session:
            session.add(
                AccountRecord(
                    account_id=account_id,
                    email=f"rag_{uuid4().hex}@test.invalid",
                    password_hash="synthetic-test-only",
                    role="UniversityAdmissions",
                    account_state="Active",
                    failed_attempts=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        yield PostgresRagRepository(factory), account_id
    finally:
        Base.metadata.drop_all(isolated_engine)
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {quote(schema_name)} CASCADE"))
        engine.dispose()


def _new_document(
    university_id,
    uploaded_by,
    *,
    digest: str,
    logical_document_id=None,
) -> tuple[RagDocument, list[RagChunk]]:
    document = RagDocument(
        document_id=uuid4(),
        university_id=university_id,
        title="Synthetic RAG integration fixture",
        file_name="synthetic.pdf",
        content_type="application/pdf",
        content_sha256=digest,
        uploaded_by=uploaded_by,
        logical_document_id=logical_document_id,
    )
    chunk = RagChunk(
        chunk_id=uuid4(),
        document_id=document.document_id,
        chunk_index=0,
        text="Synthetic integration passage.",
        embedding=(1.0,) * EMBEDDING_DIMENSIONS,
    )
    return document, [chunk]


def test_postgres_replacement_delete_and_history_are_atomic(repository):
    repo, account_id = repository
    university_id = uuid4()
    first, first_chunks = _new_document(
        university_id, account_id, digest="a" * 64
    )
    stored_first = repo.ingest_document(first, first_chunks)
    assert stored_first.version_number == 1
    assert stored_first.embedding_state is EmbeddingState.EMBEDDINGS_READY

    second, second_chunks = _new_document(
        university_id,
        account_id,
        digest="a" * 64,
        logical_document_id=stored_first.logical_document_id,
    )
    stored_second = repo.ingest_document(second, second_chunks)
    assert stored_second.version_number == 2
    assert repo.list_active_chunks({university_id}) == [
        (stored_second, second_chunks[0])
    ]

    assert repo.delete_document(stored_first.document_id, university_id)
    logical = repo.find_logical_document(
        stored_first.logical_document_id, university_id
    )
    assert logical is not None
    assert logical.lifecycle_state is LogicalDocumentState.ACTIVE
    assert repo.list_active_chunks({university_id}) == [
        (stored_second, second_chunks[0])
    ]

    assert repo.delete_logical_document(
        stored_first.logical_document_id, university_id
    )
    retained = {
        document.document_id: document
        for document in repo.list_documents(university_id)
    }
    assert retained[stored_first.document_id].lifecycle_state is (
        PhysicalDocumentState.DELETED
    )
    assert retained[stored_second.document_id].lifecycle_state is (
        PhysicalDocumentState.DELETED
    )
    assert repo.list_chunks({university_id}) == []
    assert repo.list_active_chunks({university_id}) == []


def test_postgres_replacement_lock_serializes_version_allocation(repository):
    repo, account_id = repository
    university_id = uuid4()
    first, chunks = _new_document(
        university_id, account_id, digest="b" * 64
    )
    stored_first = repo.ingest_document(first, chunks)

    def replace_version(digest: str):
        candidate, candidate_chunks = _new_document(
            university_id,
            account_id,
            digest=digest,
            logical_document_id=stored_first.logical_document_id,
        )
        return repo.ingest_document(candidate, candidate_chunks)

    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = list(
            executor.map(replace_version, ["c" * 64, "d" * 64])
        )

    assert sorted(document.version_number for document in versions) == [2, 3]
    all_versions = repo.list_documents(university_id)
    assert sum(
        document.lifecycle_state is PhysicalDocumentState.ACTIVE
        for document in all_versions
    ) == 1


def test_postgres_duplicate_active_content_is_blocked_across_logical_documents(
    repository,
):
    repo, account_id = repository
    university_id = uuid4()
    first, chunks = _new_document(
        university_id, account_id, digest="e" * 64
    )
    repo.ingest_document(first, chunks)
    duplicate, duplicate_chunks = _new_document(
        university_id, account_id, digest="e" * 64
    )

    from unimatch.rag import DuplicateRagDocumentError

    with pytest.raises(DuplicateRagDocumentError):
        repo.ingest_document(duplicate, duplicate_chunks)
    assert len(repo.list_documents(university_id)) == 1


def test_0007_backfills_embedding_readiness_and_enforces_lifecycle(migrated_schema):
    engine, schema_name = migrated_schema
    account_id = uuid4()
    ready_id, legacy_id, invalid_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    valid_vector = [0.25] * EMBEDDING_DIMENSIONS
    rows = [
        (ready_id, EMBEDDING_MODEL, EMBEDDING_REVISION, EMBEDDING_DIMENSIONS, valid_vector),
        (legacy_id, "legacy-feature-hash-v1", "legacy", EMBEDDING_DIMENSIONS, valid_vector),
        (invalid_id, EMBEDDING_MODEL, EMBEDDING_REVISION, 2, [0.25]),
    ]
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema_name}"'))
        connection.execute(
            text(
                "INSERT INTO accounts (account_id,email,password_hash,role,"
                "account_state,failed_attempts,created_at,updated_at) "
                "VALUES (:id,:email,'synthetic','UniversityAdmissions','Active',0,:now,:now)"
            ),
            {"id": account_id, "email": f"migration_{uuid4().hex}@test.invalid", "now": now},
        )
        for document_id, model, revision, dimensions, vector in rows:
            connection.execute(
                text(
                    "INSERT INTO rag_documents (document_id,university_id,title,file_name,"
                    "content_type,content_sha256,uploaded_by,embedding_model,"
                    "embedding_revision,embedding_dimensions,created_at) VALUES "
                    "(:id,:university,'Synthetic','synthetic.pdf','application/pdf',"
                    ":digest,:account,:model,:revision,:dimensions,:now)"
                ),
                {
                    "id": document_id,
                    "university": uuid4(),
                    "digest": str(document_id).replace("-", "") * 2,
                    "account": account_id,
                    "model": model,
                    "revision": revision,
                    "dimensions": dimensions,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO rag_chunks (chunk_id,document_id,chunk_index,text,embedding) "
                    "VALUES (:chunk,:document,0,'Synthetic passage',CAST(:embedding AS jsonb))"
                ),
                {
                    "chunk": uuid4(),
                    "document": document_id,
                    "embedding": json.dumps(vector),
                },
            )

    _run_alembic(engine, schema_name, "head")
    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema_name}"'))
        connection.commit()
        migrated = {
            row["document_id"]: row
            for row in connection.execute(
                text(
                    "SELECT document_id,logical_document_id,version_number,"
                    "lifecycle_state,embedding_state FROM rag_documents"
                )
            ).mappings()
        }
        assert migrated[ready_id]["embedding_state"] == "EmbeddingsReady"
        assert migrated[legacy_id]["embedding_state"] == "ReindexRequired"
        assert migrated[invalid_id]["embedding_state"] == "ReindexRequired"
        assert all(
            row["logical_document_id"] == row["document_id"]
            and row["version_number"] == 1
            and row["lifecycle_state"] == "Active"
            for row in migrated.values()
        )

    with engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema_name}"'))
        connection.commit()
        with pytest.raises(DBAPIError):
            with connection.begin():
                connection.execute(
                    text(
                        "UPDATE rag_logical_documents SET lifecycle_state='Deleted' "
                        "WHERE logical_document_id=:id"
                    ),
                    {"id": ready_id},
                )
