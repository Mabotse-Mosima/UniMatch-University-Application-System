"""File-backed semantic RAG pipeline used by the Stage 4 demo.

This module deliberately sits beside the legacy relational RAG repository.  The
default index is Chroma with local sentence-transformer embeddings; no network
is required at query time after the model has been cached.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from .rag import MAX_DOCUMENT_BYTES, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, EMBEDDING_REVISION, embed_texts, extract_document_text

DEFAULT_INDEX_DIR = Path("./var/rag-index")
REGISTRY_NAME = "source_registry.json"
API_RAG_COLLECTION_NAME = "unimatch_rag_api_v1"
STANDALONE_RAG_COLLECTION_NAME = "unimatch_standalone_rag_chunks"
_REGISTRY_LOCK = threading.RLock()
# Uncalibrated initial abstention threshold; calibrate against supplied corpus/evaluation questions.
DEFAULT_RETRIEVAL_THRESHOLD = 0.30


@dataclass(frozen=True)
class IndexedChunk:
    chunk_id: str
    source_id: str
    university: str
    title: str
    source_url: str | None
    retrieved_at: str
    version: str
    page: int | None
    section: str
    text: str
    origin: Literal["api", "standalone"] = "standalone"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: IndexedChunk
    score: float


class VectorStore(Protocol):
    def upsert(self, chunks: list[IndexedChunk], embeddings: list[list[float]]) -> None: ...
    def query(self, embedding: list[float], limit: int, allowed_universities: set[str] | None = None) -> list[tuple[IndexedChunk, float]]: ...
    def count(self) -> int: ...
    def contains_chunks(self, chunk_ids: list[str]) -> set[str]: ...

    def delete_source(self, source_id: str) -> None: ...
    def reconcile(self, allowed_universities: set[str], authoritative_chunk_ids: set[str]) -> int: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalSentenceTransformerEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(vector) for vector in embed_texts(texts)]


def index_dir(value: str | Path | None = None) -> Path:
    return Path(value or os.getenv("RAG_INDEX_DIR", str(DEFAULT_INDEX_DIR)))


def _metadata(chunk: IndexedChunk) -> dict[str, Any]:
    result = asdict(chunk)
    result["page"] = -1 if result["page"] is None else result["page"]
    result["_sync_hash"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {key: value for key, value in result.items() if value is not None}


class ChromaVectorStore:
    """Persistent Chroma collection with model metadata guardrails."""

    def __init__(
        self,
        directory: str | Path | None = None,
        *,
        collection_name: str = STANDALONE_RAG_COLLECTION_NAME,
        origin: Literal["api", "standalone"] = "standalone",
    ) -> None:
        if origin not in {"api", "standalone"}:
            raise ValueError("Chroma origin must be 'api' or 'standalone'.")
        if not collection_name:
            raise ValueError("A Chroma collection name is required.")
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        import chromadb
        from chromadb.config import Settings

        self.origin = origin
        self.collection_name = collection_name
        self.directory = index_dir(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.directory), settings=Settings(anonymized_telemetry=False))
        collection_metadata = {
            "embedding_model": EMBEDDING_MODEL,
            "embedding_revision": EMBEDDING_REVISION,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "hnsw:space": "cosine",
            "origin": origin,
        }
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata=collection_metadata,
        )
        self._lock = threading.RLock()
        metadata = self.collection.metadata or {}
        has_vectors = bool(self.collection.count())
        if metadata.get("origin") != origin:
            if has_vectors:
                raise RuntimeError(
                    "The configured Chroma collection contains vectors with a "
                    "different or unknown origin."
                )
            self.collection.modify(metadata={**metadata, **collection_metadata})
            metadata = self.collection.metadata or {}
        if has_vectors and metadata.get("embedding_model") != EMBEDDING_MODEL:
            raise RuntimeError("RAG index was built with a different embedding model; rebuild it explicitly.")
        if has_vectors and metadata.get("embedding_revision") != EMBEDDING_REVISION:
            raise RuntimeError("RAG index was built with a different embedding revision; rebuild it explicitly.")
        if has_vectors and metadata.get("embedding_dimensions") != EMBEDDING_DIMENSIONS:
            raise RuntimeError("RAG index dimensions do not match the configured embedding model.")
        if has_vectors and metadata.get("hnsw:space") != "cosine":
            raise RuntimeError("Existing RAG index uses a different distance metric; rebuild it explicitly.")

    def upsert(self, chunks: list[IndexedChunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        if any(chunk.origin != self.origin for chunk in chunks):
            raise ValueError("Chunks cannot be written across Chroma origins.")
        with self._lock:
            ids = [chunk.chunk_id for chunk in chunks]
            current = self.collection.get(ids=ids, include=["metadatas"])
            current_origins = {
                chunk_id: metadata.get("origin")
                for chunk_id, metadata in zip(
                    current.get("ids", []), current.get("metadatas", [])
                )
            }
            if any(value != self.origin for value in current_origins.values()):
                raise RuntimeError("Refusing to overwrite vectors from another origin.")
            indexed = {
                chunk_id: metadata
                for chunk_id, metadata in zip(current.get("ids", []), current.get("metadatas", []))
            }
            changed_indexes = [
                index for index, chunk in enumerate(chunks)
                if indexed.get(chunk.chunk_id, {}).get("_sync_hash") != _metadata(chunk)["_sync_hash"]
            ]
            if not changed_indexes:
                return
            self.collection.upsert(
                ids=[chunks[index].chunk_id for index in changed_indexes],
                embeddings=[embeddings[index] for index in changed_indexes],
                documents=[chunks[index].text for index in changed_indexes],
                metadatas=[_metadata(chunks[index]) for index in changed_indexes],
            )

    def query(
        self,
        embedding: list[float],
        limit: int,
        allowed_universities: set[str] | None = None,
    ) -> list[tuple[IndexedChunk, float]]:
        if self.origin == "api" and not allowed_universities:
            raise ValueError("A non-empty university allow-list is required for Chroma queries.")
        if allowed_universities is not None and not allowed_universities:
            return []
        if not self.count():
            return []
        query_options: dict[str, Any] = {
            "query_embeddings": [list(embedding)],
            "n_results": limit,
        }
        filters: list[dict[str, Any]] = [{"origin": {"$eq": self.origin}}]
        if allowed_universities is not None:
            filters.append({"university": {"$in": sorted(allowed_universities)}})
        query_options["where"] = {"$and": filters} if len(filters) > 1 else filters[0]
        with self._lock:
            result = self.collection.query(**query_options)
        rows: list[tuple[IndexedChunk, float]] = []
        for metadata, distance in zip(result["metadatas"][0], result["distances"][0]):
            data = dict(metadata)
            data["page"] = None if data.get("page", -1) == -1 else int(data["page"])
            rows.append((IndexedChunk(**{k: data.get(k) for k in IndexedChunk.__dataclass_fields__}), max(0.0, 1.0 - float(distance))))
        return rows

    def count(self) -> int:
        return int(self.collection.count())

    def contains_chunks(self, chunk_ids: list[str]) -> set[str]:
        if not chunk_ids:
            return set()
        with self._lock:
            result = self.collection.get(
                ids=chunk_ids,
                where={"origin": {"$eq": self.origin}},
                include=["metadatas"],
            )
        return {
            chunk_id
            for chunk_id, metadata in zip(
                result.get("ids", []), result.get("metadatas", [])
            )
            if metadata.get("origin") == self.origin
        }

    def delete_source(self, source_id: str) -> None:
        with self._lock:
            self.collection.delete(
                where={
                    "$and": [
                        {"origin": {"$eq": self.origin}},
                        {"source_id": {"$eq": source_id}},
                    ]
                }
            )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if chunk_ids:
            with self._lock:
                self.collection.delete(
                    ids=chunk_ids,
                    where={"origin": {"$eq": self.origin}},
                )

    def reconcile(self, allowed_universities: set[str], authoritative_chunk_ids: set[str]) -> int:
        """Delete stale vectors only within the explicitly authorised university scope."""
        if not allowed_universities:
            if self.origin == "api":
                raise ValueError("A non-empty university allow-list is required for reconciliation.")
            return 0
        with self._lock:
            rows = self.collection.get(
                where={
                    "$and": [
                        {"origin": {"$eq": self.origin}},
                        {"university": {"$in": sorted(allowed_universities)}},
                    ]
                },
                include=["metadatas"],
            )
            stale = [
                chunk_id for chunk_id, metadata in zip(rows.get("ids", []), rows.get("metadatas", []))
                if chunk_id not in authoritative_chunk_ids
            ]
            if stale:
                self.collection.delete(
                    ids=stale,
                    where={"origin": {"$eq": self.origin}},
                )
            return len(stale)


class SourceRegistry:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.path = index_dir(directory) / REGISTRY_NAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}\n", encoding="utf-8")

    def read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def record(self, source_id: str, data: dict[str, Any]) -> None:
        with _REGISTRY_LOCK:
            registry = self.read()
            registry[source_id] = data
            temporary = self.path.with_suffix(f".tmp-{os.getpid()}")
            temporary.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)


def _clean_html(raw: str) -> str:
    raw = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def read_source(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    payload = path.read_bytes()
    if not payload:
        raise ValueError("The source document is empty.")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError("The source document exceeds the 10 MB upload limit.")
    if suffix in {".pdf", ".docx"}:
        return extract_document_text(path.name, payload)
    if suffix == ".html" or suffix == ".htm":
        return _clean_html(payload.decode("utf-8", errors="replace")), "text/html"
    if suffix == ".txt":
        return payload.decode("utf-8", errors="replace"), "text/plain"
    raise ValueError("Supported source types are PDF, DOCX, TXT and HTML.")


def _sections(text: str) -> list[tuple[str, str]]:
    current = "Document body"
    pieces: list[tuple[str, str]] = []
    body: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        heading = re.match(r"^(?:#{1,6}\s+|\[SECTION\]\s+)(.+)$", line)
        if heading:
            if body:
                pieces.append((current, " ".join(body)))
                body = []
            current = heading.group(1).strip()
        elif line:
            body.append(line)
    if body:
        pieces.append((current, " ".join(body)))
    return pieces


def build_chunks(text: str, *, source_id: str, university: str, title: str, source_url: str | None = None, version: str = "1", retrieved_at: str | None = None) -> list[IndexedChunk]:
    stamp = retrieved_at or datetime.now(timezone.utc).isoformat()
    output: list[IndexedChunk] = []
    for section, body in _sections(text):
        words = body.split()
        step = 190
        for start in range(0, len(words), step):
            words_part = words[start:start + 220]
            if not words_part:
                continue
            chunk_text = " ".join(words_part)
            chunk_id = hashlib.sha256(f"{source_id}:{version}:{section}:{start}:{chunk_text}".encode()).hexdigest()[:32]
            output.append(IndexedChunk(chunk_id, source_id, university, title, source_url, stamp, version, None, section, chunk_text))
    return output


def ingest_file(path: str | Path, *, university: str, title: str | None = None, source_url: str | None = None, version: str = "1", directory: str | Path | None = None, store: VectorStore | None = None, embedder: Embedder | None = None) -> tuple[str, int, bool]:
    source_path = Path(path)
    payload = source_path.read_bytes()
    source_id = hashlib.sha256(university.encode("utf-8") + b"\0" + payload).hexdigest()
    registry = SourceRegistry(directory)
    existing = registry.read().get(source_id)
    registry_matches = bool(
        existing
        and existing.get("version") == version
        and existing.get("university") == university
        and existing.get("title") == (title or source_path.name)
        and existing.get("source_url") == source_url
    )
    text, _ = read_source(source_path)
    chunks = build_chunks(text, source_id=source_id, university=university, title=title or source_path.name, source_url=source_url, version=version)
    active_store = store or ChromaVectorStore(
        directory,
        collection_name=STANDALONE_RAG_COLLECTION_NAME,
        origin="standalone",
    )
    if registry_matches:
        contains_chunks = getattr(active_store, "contains_chunks", None)
        if callable(contains_chunks):
            present_ids = contains_chunks([chunk.chunk_id for chunk in chunks])
            missing_chunks = [chunk for chunk in chunks if chunk.chunk_id not in present_ids]
            if not missing_chunks:
                return source_id, len(chunks), False
            active_store.upsert(
                missing_chunks,
                (embedder or LocalSentenceTransformerEmbedder()).embed(
                    [chunk.text for chunk in missing_chunks]
                ),
            )
            registry.record(source_id, {**existing, "chunk_count": len(chunks)})
            return source_id, len(chunks), True
    # Upsert uses deterministic chunk IDs, so the previous version stays
    # available until the replacement vectors are ready to atomically overwrite it.
    active_store.upsert(chunks, (embedder or LocalSentenceTransformerEmbedder()).embed([c.text for c in chunks]))
    registry.record(source_id, {"source_id": source_id, "path": source_path.name, "university": university, "title": title or source_path.name, "source_url": source_url, "version": version, "retrieved_at": chunks[0].retrieved_at if chunks else None, "chunk_count": len(chunks), "embedding_model": EMBEDDING_MODEL, "embedding_revision": EMBEDDING_REVISION, "embedding_dimensions": EMBEDDING_DIMENSIONS, "distance_metric": "cosine"})
    return source_id, len(chunks), True


def delete_source(source_id: str, *, directory: str | Path | None = None, store: VectorStore | None = None) -> None:
    active_store = store or ChromaVectorStore(
        directory,
        collection_name=STANDALONE_RAG_COLLECTION_NAME,
        origin="standalone",
    )
    active_store.delete_source(source_id)
    registry = SourceRegistry(directory)
    with _REGISTRY_LOCK:
        data = registry.read()
        data.pop(source_id, None)
        temporary = registry.path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, registry.path)


def retrieve(question: str, *, directory: str | Path | None = None, limit: int = 4, threshold: float = DEFAULT_RETRIEVAL_THRESHOLD, store: VectorStore | None = None, embedder: Embedder | None = None, source_dir: str | Path | None = None, university: str | None = None) -> list[RetrievedChunk]:
    active_store = store or ChromaVectorStore(
        directory,
        collection_name=STANDALONE_RAG_COLLECTION_NAME,
        origin="standalone",
    )
    if active_store.count() == 0:
        corpus = Path(source_dir or os.getenv("RAG_SOURCE_DIR", ""))
        if corpus.is_dir() and university:
            for path in sorted(p for p in corpus.rglob("*") if p.is_file()):
                ingest_file(path, university=university, directory=directory, store=active_store, embedder=embedder)
    rows = active_store.query((embedder or LocalSentenceTransformerEmbedder()).embed([question])[0], limit)
    return [RetrievedChunk(chunk, score) for chunk, score in rows if score >= threshold]


class Bm25Index:
    def __init__(self, chunks: list[IndexedChunk]) -> None:
        from rank_bm25 import BM25Okapi
        self.chunks = chunks
        self.engine = BM25Okapi([c.text.lower().split() for c in chunks])

    def retrieve(self, question: str, limit: int = 4) -> list[RetrievedChunk]:
        scores = self.engine.get_scores(question.lower().split())
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:limit]
        return [RetrievedChunk(self.chunks[i], float(scores[i])) for i in order]
