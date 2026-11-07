from pathlib import Path
import os
import hashlib
import zipfile
from io import BytesIO

import pytest

from unimatch.rag import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, RagEmbeddingUnavailableError
from unimatch.rag_pipeline import Bm25Index, ChromaVectorStore, IndexedChunk, SourceRegistry, build_chunks, delete_source, ingest_file, retrieve


class SyntheticStandInEmbedder:
    """Deterministic plumbing stand-in; never use for retrieval-quality claims."""

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * 8
            for token in text.lower().split():
                vector[int(hashlib.sha256(token.encode()).hexdigest(), 16) % 8] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class MemoryStore:
    def __init__(self):
        self.rows = {}

    def upsert(self, chunks, embeddings):
        self.rows.update({chunk.chunk_id: (chunk, vector) for chunk, vector in zip(chunks, embeddings)})

    def count(self):
        return len(self.rows)

    def contains_chunks(self, chunk_ids):
        return set(chunk_ids) & self.rows.keys()

    def delete_source(self, source_id):
        self.rows = {key: value for key, value in self.rows.items() if value[0].source_id != source_id}

    def query(self, embedding, limit, allowed_universities=None):
        def score(vector):
            return sum(a * b for a, b in zip(vector, embedding))
        rows = [row for row in self.rows.values() if allowed_universities is None or row[0].university in allowed_universities]
        return [(chunk, score(vector)) for chunk, vector in sorted(rows, key=lambda row: score(row[1]), reverse=True)[:limit]]

    def reconcile(self, allowed_universities, authoritative_chunk_ids):
        stale = [key for key, (chunk, _vector) in self.rows.items() if chunk.university in allowed_universities and key not in authoritative_chunk_ids]
        for key in stale:
            del self.rows[key]
        return len(stale)


def _fixture(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.txt"
    path.write_text("SYNTHETIC TEST FIXTURE\n[SECTION] Admission requirements\nApplicants need mathematics and a minimum aggregate of 70. Contact the university for current dates.", encoding="utf-8")
    return path


def test_chunk_metadata_and_bm25(tmp_path: Path):
    chunks = build_chunks("[SECTION] Entry\nSYNTHETIC TEST FIXTURE mathematics minimum aggregate", source_id="s", university="Synthetic University", title="SYNTHETIC TEST FIXTURE")
    assert chunks[0].university == "Synthetic University"
    assert chunks[0].section == "Entry"
    assert Bm25Index(chunks).retrieve("mathematics aggregate")


def test_chroma_query_enforces_university_filter_and_reconciles_stale_ids(tmp_path: Path):
    from unimatch.rag_pipeline import (
        API_RAG_COLLECTION_NAME,
        ChromaVectorStore,
        IndexedChunk,
    )

    store = ChromaVectorStore(
        tmp_path / "actual-chroma",
        collection_name=API_RAG_COLLECTION_NAME,
        origin="api",
    )
    chunks = [
        IndexedChunk("uni-a-1", "source-a", "uni-a", "A", None, "now", "1", None, "body", "synthetic A", origin="api"),
        IndexedChunk("uni-b-1", "source-b", "uni-b", "B", None, "now", "1", None, "body", "synthetic B", origin="api"),
    ]
    store.upsert(chunks, [[1.0, 0.0], [1.0, 0.0]])
    rows = store.query([1.0, 0.0], 10, allowed_universities={"uni-a"})
    assert [chunk.chunk_id for chunk, _score in rows] == ["uni-a-1"]
    assert store.reconcile({"uni-a"}, set()) == 1
    assert [chunk.chunk_id for chunk, _score in store.query([1.0, 0.0], 10, {"uni-a", "uni-b"})] == ["uni-b-1"]
    with pytest.raises(ValueError):
        store.query([1.0, 0.0], 1)
    with pytest.raises(ValueError):
        store.reconcile(set(), set())


def test_standalone_collection_is_isolated_and_retrieves_without_api_scope(tmp_path: Path):
    import chromadb

    from unimatch.rag_pipeline import (
        API_RAG_COLLECTION_NAME,
        STANDALONE_RAG_COLLECTION_NAME,
        ChromaVectorStore,
        IndexedChunk,
    )

    directory = tmp_path / "isolated-chroma"
    client = chromadb.PersistentClient(path=str(directory))
    legacy = client.get_or_create_collection("unimatch_rag_chunks")
    legacy.add(
        ids=["legacy-vector"],
        embeddings=[[1.0, 0.0]],
        documents=["legacy synthetic content"],
        metadatas=[{"university": "uni-a"}],
    )

    api_store = ChromaVectorStore(
        directory,
        collection_name=API_RAG_COLLECTION_NAME,
        origin="api",
    )
    standalone_store = ChromaVectorStore(directory)
    api_chunk = IndexedChunk(
        "same-chunk-id", "api-source", "uni-a", "API", None, "now", "1",
        None, "body", "API synthetic passage", origin="api",
    )
    standalone_chunk = IndexedChunk(
        "same-chunk-id", "standalone-source", "uni-b", "Standalone", None,
        "now", "1", None, "body", "Standalone synthetic passage",
    )
    api_store.upsert([api_chunk], [[1.0, 0.0]])
    standalone_store.upsert([standalone_chunk], [[1.0, 0.0]])

    assert api_store.collection_name == API_RAG_COLLECTION_NAME
    assert standalone_store.collection_name == STANDALONE_RAG_COLLECTION_NAME
    assert [chunk.chunk_id for chunk, _ in standalone_store.query([1.0, 0.0], 1)] == [
        "same-chunk-id"
    ]
    assert [
        chunk.chunk_id
        for chunk, _ in api_store.query(
            [1.0, 0.0], 1, allowed_universities={"uni-a"}
        )
    ] == ["same-chunk-id"]
    assert api_store.reconcile({"uni-a"}, set()) == 1
    assert standalone_store.count() == 1
    assert legacy.count() == 1
    with pytest.raises(ValueError, match="origins"):
        api_store.upsert([standalone_chunk], [[1.0, 0.0]])


@pytest.mark.skipif(not os.getenv("RAG_RUN_LOCAL_MODEL_TESTS"), reason="local embedding model test requires an explicitly provisioned model cache")
def test_chroma_ingestion_is_idempotent_and_semantic_query_runs(tmp_path: Path):
    path = _fixture(tmp_path)
    directory = tmp_path / "index"
    try:
        _, count, changed = ingest_file(path, university="Synthetic University", directory=directory)
    except RagEmbeddingUnavailableError as exc:
        pytest.skip(f"pinned local embedding model is not cached; no model download allowed: {exc}")
    _, count_again, changed_again = ingest_file(path, university="Synthetic University", directory=directory)
    assert count > 0 and changed
    assert count_again == count and not changed_again
    assert ChromaVectorStore(directory).count() == count
    results = retrieve("What mathematics mark is needed?", directory=directory)
    assert results and results[0].chunk.title == "synthetic.txt"


def _synthetic_docx(path: Path) -> None:
    xml = "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>SYNTHETIC TEST FIXTURE DOCX requirements</w:t></w:r></w:p></w:body></w:document>"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)


def _synthetic_pdf(path: Path) -> None:
    stream = b"BT /F1 12 Tf 20 200 Td (SYNTHETIC TEST FIXTURE PDF) Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body, offsets = b"%PDF-1.4\n", [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(body)


def test_injectable_standin_covers_formats_registry_delete_and_reindex(tmp_path: Path):
    files = {"fixture.txt": "SYNTHETIC TEST FIXTURE TXT requirements", "fixture.html": "<h1>Entry</h1><p>SYNTHETIC TEST FIXTURE HTML requirements</p>"}
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    _synthetic_docx(tmp_path / "fixture.docx")
    _synthetic_pdf(tmp_path / "fixture.pdf")
    store, embedder = MemoryStore(), SyntheticStandInEmbedder()
    counts = []
    for path in sorted(tmp_path.iterdir()):
        source_id, count, changed = ingest_file(path, university="Synthetic University", directory=tmp_path / "index", store=store, embedder=embedder, source_url="https://synthetic.invalid")
        counts.append(count)
        assert changed and count > 0
        assert SourceRegistry(tmp_path / "index").read()[source_id]["embedding_model"].startswith("sentence-transformers/")
    assert len(counts) == 4 and store.count() == sum(counts)
    first = next(iter(store.rows.values()))[0]
    delete_source(first.source_id, directory=tmp_path / "index", store=store)
    assert first.source_id not in SourceRegistry(tmp_path / "index").read()
    changed = tmp_path / "fixture.txt"
    changed.write_text("SYNTHETIC TEST FIXTURE TXT revised requirements", encoding="utf-8")
    _, _, reindexed = ingest_file(changed, university="Synthetic University", directory=tmp_path / "index", store=store, embedder=embedder, version="2")
    assert reindexed


def test_registry_fast_path_repairs_missing_vectors(tmp_path: Path):
    path = tmp_path / "recover.txt"
    path.write_text("SYNTHETIC TEST FIXTURE recover missing vectors", encoding="utf-8")
    store, embedder = MemoryStore(), SyntheticStandInEmbedder()
    source_id, count, changed = ingest_file(
        path,
        university="Synthetic University",
        directory=tmp_path / "index",
        store=store,
        embedder=embedder,
    )
    assert changed and store.count() == count

    # Simulate loss of the Chroma collection while the source registry remains.
    store.rows.clear()
    repaired_id, repaired_count, repaired = ingest_file(
        path,
        university="Synthetic University",
        directory=tmp_path / "index",
        store=store,
        embedder=embedder,
    )

    assert repaired_id == source_id
    assert repaired_count == count
    assert repaired is True
    assert store.count() == count


def test_registry_fast_path_repairs_missing_actual_chroma_vectors(tmp_path: Path):
    path = tmp_path / "chroma-recover.txt"
    path.write_text("SYNTHETIC TEST FIXTURE actual chroma recovery", encoding="utf-8")
    directory = tmp_path / "chroma-index"
    store, embedder = ChromaVectorStore(directory), SyntheticStandInEmbedder()
    source_id, count, changed = ingest_file(
        path,
        university="Synthetic University",
        directory=directory,
        store=store,
        embedder=embedder,
    )
    chunks = build_chunks(
        path.read_text(encoding="utf-8"),
        source_id=source_id,
        university="Synthetic University",
        title=path.name,
    )
    store.delete_chunks([chunk.chunk_id for chunk in chunks])
    assert changed and count > 0 and store.count() == 0

    repaired_id, repaired_count, repaired = ingest_file(
        path,
        university="Synthetic University",
        directory=directory,
        store=store,
        embedder=embedder,
    )

    assert repaired_id == source_id
    assert repaired_count == count
    assert repaired is True
    assert store.count() == count


def test_failed_vector_upsert_does_not_write_successful_registry_entry(tmp_path: Path):
    path = tmp_path / "failed-index.txt"
    path.write_text("SYNTHETIC TEST FIXTURE failed vector upsert", encoding="utf-8")

    class FailingStore(MemoryStore):
        def upsert(self, chunks, embeddings):
            raise OSError("synthetic Chroma write failure")

    registry = SourceRegistry(tmp_path / "index")
    with pytest.raises(OSError, match="synthetic Chroma write failure"):
        ingest_file(
            path,
            university="Synthetic University",
            directory=tmp_path / "index",
            store=FailingStore(),
            embedder=SyntheticStandInEmbedder(),
        )

    assert registry.read() == {}
    healthy = MemoryStore()
    source_id, count, changed = ingest_file(
        path,
        university="Synthetic University",
        directory=tmp_path / "index",
        store=healthy,
        embedder=SyntheticStandInEmbedder(),
    )
    assert changed and count > 0 and healthy.count() == count
    assert source_id in registry.read()


def test_first_query_builds_missing_index_from_configured_source_dir(tmp_path: Path):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "fixture.txt").write_text("SYNTHETIC TEST FIXTURE first query admissions", encoding="utf-8")
    store, embedder = MemoryStore(), SyntheticStandInEmbedder()
    results = retrieve("admissions", directory=tmp_path / "index", source_dir=source_dir, university="Synthetic University", store=store, embedder=embedder, threshold=0.0)
    assert store.count() == 1 and results


def test_chroma_cosine_distance_is_returned_as_similarity(tmp_path: Path):
    chunk = IndexedChunk("cosine", "source", "Synthetic University", "SYNTHETIC TEST FIXTURE", None, "now", "1", None, "Entry", "synthetic passage")
    vector = [1.0] + [0.0] * 383
    store = ChromaVectorStore(tmp_path / "index")
    store.upsert([chunk], [vector])
    rows = store.query(vector, 1, allowed_universities={"Synthetic University"})
    assert rows[0][1] > 0.99


def test_identical_content_is_isolated_by_university(tmp_path: Path):
    path = tmp_path / "same.txt"
    path.write_text("SYNTHETIC TEST FIXTURE shared policy", encoding="utf-8")
    store, embedder = MemoryStore(), SyntheticStandInEmbedder()
    first_id, _, _ = ingest_file(path, university="Synthetic University A", directory=tmp_path / "index", store=store, embedder=embedder)
    second_id, _, _ = ingest_file(path, university="Synthetic University B", directory=tmp_path / "index", store=store, embedder=embedder)
    assert first_id != second_id
    assert store.count() == 2
    registry = SourceRegistry(tmp_path / "index").read()
    assert {entry["university"] for entry in registry.values()} == {"Synthetic University A", "Synthetic University B"}


def test_chroma_rejects_incompatible_embedding_revision(tmp_path: Path):
    chunk = IndexedChunk("revision", "source", "Synthetic University", "SYNTHETIC TEST FIXTURE", None, "now", "1", None, "Entry", "synthetic passage")
    vector = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    store = ChromaVectorStore(tmp_path / "index")
    store.upsert([chunk], [vector])
    store.collection.modify(metadata={
        "embedding_model": EMBEDDING_MODEL,
        "embedding_revision": "incompatible-revision",
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "origin": "standalone",
    })
    with pytest.raises(RuntimeError, match="revision"):
        ChromaVectorStore(tmp_path / "index")
