from __future__ import annotations

import hashlib
from uuid import UUID, uuid4
import asyncio
import threading
import pytest
from datetime import datetime, timezone
from unimatch.api import _assistant_numbers_match_engine
from unimatch.rag import (
    EMBEDDING_DIMENSIONS,
    ExtractiveGroundedAnswerProvider,
    RagChunk,
    RagConversation,
    RagDocument,
    RagEmbeddingUnavailableError,
)
from unimatch.rag_pipeline import IndexedChunk

from tests.api.test_authorization import (
    _create_learner_for,
    _make_two_school_app,
    _upload_rag_doc,
)


def _publish_programme(state, client_key: str, csrf_key: str, university_id):
    response = state[client_key].post(
        "/api/programmes",
        json={
            "university_id": str(university_id),
            "name": "Synthetic BSc Fixture",
            "faculty": "Synthetic Faculty",
            "minimum_aps": 20,
            "application_deadline": "2099-12-31",
            "application_fee": "100.00",
            "required_documents": [],
            "published_by": str(uuid4()),
            "required_subjects": {"Mathematics": 70},
        },
        headers={"X-CSRF-Token": state[csrf_key]},
    )
    assert response.status_code == 201, response.text
    programme_id = response.json()["programme_id"]
    published = state[client_key].post(
        f"/api/programmes/{programme_id}/publish",
        headers={"X-CSRF-Token": state[csrf_key]},
    )
    assert published.status_code == 200, published.text
    return programme_id


class _MemoryScopedVectorStore:
    def __init__(self):
        self.rows: dict[str, tuple[IndexedChunk, list[float]]] = {}
        self.query_calls = 0

    def upsert(self, chunks, embeddings):
        self.rows.update(
            {
                chunk.chunk_id: (chunk, embedding)
                for chunk, embedding in zip(chunks, embeddings)
            }
        )

    def reconcile(self, allowed_universities, authoritative_chunk_ids):
        stale = [
            chunk_id
            for chunk_id, (chunk, _embedding) in self.rows.items()
            if chunk.university in allowed_universities
            and chunk_id not in authoritative_chunk_ids
        ]
        for chunk_id in stale:
            del self.rows[chunk_id]
        return len(stale)

    def delete_source(self, source_id):
        self.rows = {
            chunk_id: value
            for chunk_id, value in self.rows.items()
            if value[0].source_id != source_id
        }

    def query(self, embedding, limit, allowed_universities=None):
        self.query_calls += 1
        allowed = allowed_universities or set()
        return [
            (chunk, 1.0)
            for chunk, _stored_embedding in self.rows.values()
            if chunk.university in allowed
        ][:limit]


def test_assistant_contract_citations_and_legacy_route_survive(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_INDEX_DIR", str(tmp_path / "chroma-index"))
    state = _make_two_school_app()
    assert _upload_rag_doc(
        state["client_x"],
        state["csrf_x"],
        "SYNTHETIC TEST FIXTURE: Mathematics requires a minimum mark of 70.",
    ).status_code == 201
    _publish_programme(state, "client_x", "csrf_x", state["uni_x"])

    response = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What Mathematics mark is required?", "university_id": str(state["uni_x"])},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"answer", "citations", "mode", "model", "abstained", "request_id"} <= body.keys()
    assert body["mode"] == "offline-extractive" or body["mode"].startswith("live: "), (
        f"Unexpected generation mode: {body['mode']!r}. Expected 'offline-extractive' or 'live: <model>'."
    )
    assert body["citations"]
    assert body["citations"][0]["university"] == str(state["uni_x"])
    legacy_school_chat = state["client_a"].post(
        "/api/agent/chat",
        json={"message": "What Mathematics mark is required?"},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert legacy_school_chat.status_code == 200
    cross_university = state["client_y"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What Mathematics mark is required?", "university_id": str(state["uni_x"])},
        headers={"X-CSRF-Token": state["csrf_y"]},
    )
    assert cross_university.status_code == 404
    assert state["client_x"].post(
        "/api/agent/chat",
        json={"message": "What is required?"},
        headers={"X-CSRF-Token": state["csrf_x"]},
    ).status_code == 403
    document_id = state["client_x"].get("/api/agent/documents", headers={"X-CSRF-Token": state["csrf_x"]}).json()[0]["document_id"]
    deleted = state["client_x"].delete(
        f"/api/agent/documents/{document_id}", headers={"X-CSRF-Token": state["csrf_x"]}
    )
    assert deleted.status_code == 204
    after_delete = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What Mathematics mark is required?", "university_id": str(state["uni_x"])},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert after_delete.status_code == 200
    assert after_delete.json()["citations"] == []
    assert after_delete.json()["abstained"] is True


def test_retrieval_and_chroma_reconciliation_exclude_superseded_and_deleted_versions(
    monkeypatch,
):
    vector = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    monkeypatch.setattr(
        "unimatch.api.embed_texts",
        lambda texts: [vector.copy() for _text in texts],
    )
    monkeypatch.setattr(
        "unimatch.api.retrieve_chunks",
        lambda _question, chunks: [(1.0, document, chunk) for document, chunk in chunks],
    )
    store = _MemoryScopedVectorStore()
    state = _make_two_school_app(vector_store=store)
    first_upload = _upload_rag_doc(
        state["client_x"],
        state["csrf_x"],
        "SYNTHETIC TEST FIXTURE: superseded-only sentinel text.",
    )
    assert first_upload.status_code == 201, first_upload.text
    first = state["knowledge_repo"].list_documents(state["uni_x"])[0]

    replacement_text = "SYNTHETIC TEST FIXTURE: current-version requirement."
    replacement = RagDocument(
        document_id=uuid4(),
        university_id=state["uni_x"],
        title="Synthetic replacement fixture",
        file_name="replacement.txt",
        content_type="text/plain",
        content_sha256=hashlib.sha256(replacement_text.encode()).hexdigest(),
        uploaded_by=state["account_repo"].find_by_email("ua_x@test").user_id,
        created_at=datetime.now(timezone.utc),
        logical_document_id=first.logical_document_id,
    )
    replacement_chunk = RagChunk(
        chunk_id=uuid4(),
        document_id=replacement.document_id,
        chunk_index=0,
        text=replacement_text,
        embedding=tuple(vector),
    )
    stored_replacement = state["knowledge_repo"].ingest_document(
        replacement, [replacement_chunk]
    )
    assert stored_replacement.version_number == 2
    assert len(state["knowledge_repo"].list_chunks({state["uni_x"]})) == 2
    _publish_programme(state, "client_x", "csrf_x", state["uni_x"])

    legacy_chat = state["client_a"].post(
        "/api/agent/chat",
        json={"message": "What is the current requirement?"},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert legacy_chat.status_code == 200, legacy_chat.text
    assert legacy_chat.json()["sources"]
    assert all(
        source["chunk_id"] == str(replacement_chunk.chunk_id)
        for source in legacy_chat.json()["sources"]
    )

    semantic_chat = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={
            "question": "What is the current requirement?",
            "university_id": str(state["uni_x"]),
        },
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert semantic_chat.status_code == 200, semantic_chat.text
    assert semantic_chat.json()["citations"]
    assert all(
        source["chunk_id"] == str(replacement_chunk.chunk_id)
        for source in semantic_chat.json()["citations"]
    )
    assert set(store.rows) == {str(replacement_chunk.chunk_id)}

    deleted = state["client_x"].delete(
        f"/api/agent/documents/{stored_replacement.document_id}",
        headers={"X-CSRF-Token": state["csrf_x"]},
    )
    assert deleted.status_code == 204, deleted.text
    assert store.rows == {}

    after_delete = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={
            "question": "What is the current requirement?",
            "university_id": str(state["uni_x"]),
        },
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert after_delete.status_code == 200, after_delete.text
    assert after_delete.json()["citations"] == []
    assert after_delete.json()["abstained"] is True


def test_assistant_csrf_role_and_cross_school_learner_isolation():
    state = _make_two_school_app()
    assert _upload_rag_doc(
        state["client_x"], state["csrf_x"],
        "SYNTHETIC TEST FIXTURE: Applications require the supplied documents.",
    ).status_code == 201
    _publish_programme(state, "client_x", "csrf_x", state["uni_x"])
    learner_a = _create_learner_for(state["client_a"], state["school_a"], state["csrf_a"])
    learner_b = _create_learner_for(state["client_b"], state["school_b"], state["csrf_b"])

    missing_csrf = state["client_a"].post(
        "/api/v1/guidance/assistant/ask", json={"question": "What is required?"}
    )
    assert missing_csrf.status_code == 403
    assert state["teacher_client"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What is required?"},
        headers={"X-CSRF-Token": state["teacher_csrf"]},
    ).status_code == 403
    denied = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What is my result?", "learner_id": learner_b["learner_id"]},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert denied.status_code == 404
    assert learner_a["learner_id"] != learner_b["learner_id"]


def test_assistant_rejects_another_users_conversation():
    state = _make_two_school_app()
    owner = state["account_repo"].find_by_email("sa_a@test")
    conversation_id = uuid4()
    state["knowledge_repo"].create_conversation(
        RagConversation(conversation_id, owner.user_id, state["school_a"])
    )
    response = state["client_b"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "Synthetic question", "conversation_id": str(conversation_id)},
        headers={"X-CSRF-Token": state["csrf_b"]},
    )
    assert response.status_code == 404


def test_assistant_rate_limit_and_request_validation(monkeypatch):
    monkeypatch.setenv("RAG_RATE_LIMIT_PER_MINUTE", "1")
    store = _MemoryScopedVectorStore()
    state = _make_two_school_app(vector_store=store)
    headers = {"X-CSRF-Token": state["csrf_a"]}
    first = state["client_a"].post(
        "/api/v1/guidance/assistant/ask", json={"question": "Unknown fixture question"}, headers=headers
    )
    assert first.status_code == 200
    assert store.query_calls == 0
    second = state["client_a"].post(
        "/api/v1/guidance/assistant/ask", json={"question": "Another question"}, headers=headers
    )
    assert second.status_code == 429

    other = state["client_b"].post(
        "/api/v1/guidance/assistant/ask", json={"question": "   "}, headers={"X-CSRF-Token": state["csrf_b"]}
    )
    assert other.status_code == 422


def test_engine_validation_binds_aps_and_labels_to_named_programme():
    engine_results = [
        {"programme_name": "Synthetic Nursing", "aps_score": 24, "minimum_aps": 22, "eligibility": "Likely"},
        {"programme_name": "Synthetic Engineering", "aps_score": 24, "minimum_aps": 30, "eligibility": "NotEligible"},
    ]
    assert _assistant_numbers_match_engine(
        "Synthetic Nursing: APS 24 against minimum APS 22; result Likely. "
        "Synthetic Engineering: APS 24 against minimum APS 30; result NotEligible.",
        engine_results,
    )
    assert not _assistant_numbers_match_engine(
        "Synthetic Nursing: APS 24 against minimum APS 30; result Likely.", engine_results
    )
    assert not _assistant_numbers_match_engine(
        "Synthetic Engineering: APS 24 against minimum APS 30; result Likely.", engine_results
    )
    assert not _assistant_numbers_match_engine(
        "APS 24; result Not Eligible.", engine_results
    )


def test_legacy_chat_rejects_programme_aps_claims_not_from_engine(monkeypatch):
    class IncorrectGenerativeProvider:
        generation_mode = "local-generative"

        def generate(self, question, matches, eligibility=None):
            return "Synthetic BSc Fixture: APS 999; result Guaranteed.", []

    monkeypatch.setattr("unimatch.api.retrieve_chunks", lambda question, chunks: [])
    state = _make_two_school_app(answer_provider=IncorrectGenerativeProvider())
    programme_id = _publish_programme(
        state, "client_x", "csrf_x", state["uni_x"]
    )
    learner = _create_learner_for(
        state["client_a"], state["school_a"], state["csrf_a"]
    )

    response = state["client_a"].post(
        "/api/agent/chat",
        json={
            "message": "What is my APS for Synthetic BSc Fixture?",
            "learner_id": learner["learner_id"],
        },
        headers={"X-CSRF-Token": state["csrf_a"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generation_mode"] == "local-extractive"
    assert "APS 999" not in body["answer"]
    assert "Synthetic BSc Fixture" in body["answer"]
    assert programme_id


def test_upload_and_reindex_embedding_failures_leave_relational_state_intact(monkeypatch):
    state = _make_two_school_app()

    def fail_embedding(_texts):
        raise RagEmbeddingUnavailableError("synthetic embedding failure")

    monkeypatch.setattr("unimatch.api.embed_texts", fail_embedding)
    failed_upload = _upload_rag_doc(
        state["client_x"],
        state["csrf_x"],
        "SYNTHETIC TEST FIXTURE upload failure handling",
    )
    assert failed_upload.status_code == 503
    assert state["client_x"].get("/api/agent/documents").json() == []

    monkeypatch.undo()
    uploaded = _upload_rag_doc(
        state["client_x"],
        state["csrf_x"],
        "SYNTHETIC TEST FIXTURE reindex failure handling",
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["document_id"]
    before, before_chunks = state["knowledge_repo"].get_document_chunks(
        UUID(document_id), state["uni_x"]
    )
    monkeypatch.setattr("unimatch.api.embed_texts", fail_embedding)

    failed_reindex = state["client_x"].post(
        f"/api/agent/documents/{document_id}/reindex",
        headers={"X-CSRF-Token": state["csrf_x"]},
    )

    assert failed_reindex.status_code == 503
    after, after_chunks = state["knowledge_repo"].get_document_chunks(
        UUID(document_id), state["uni_x"]
    )
    assert after == before
    assert after_chunks == before_chunks


def test_failed_chroma_delete_cannot_return_deleted_relational_content():
    class DeleteFailureStore:
        fail_next_reconcile = False

        def reconcile(self, allowed_universities, authoritative_chunk_ids):
            if self.fail_next_reconcile:
                self.fail_next_reconcile = False
                raise OSError("synthetic Chroma reconciliation failure")
            return 0

        def upsert(self, chunks, embeddings):
            return None

        def delete_source(self, source_id):
            return None

        def query(self, embedding, limit, allowed_universities=None):
            return []

    store = DeleteFailureStore()
    state = _make_two_school_app(vector_store=store)
    uploaded = _upload_rag_doc(
        state["client_x"],
        state["csrf_x"],
        "SYNTHETIC TEST FIXTURE deleted-source text must not be returned",
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["document_id"]
    _publish_programme(state, "client_x", "csrf_x", state["uni_x"])
    store.fail_next_reconcile = True

    deletion = state["client_x"].delete(
        f"/api/agent/documents/{document_id}",
        headers={"X-CSRF-Token": state["csrf_x"]},
    )
    assert deletion.status_code == 503
    assert state["knowledge_repo"].get_document_chunks(
        UUID(document_id), state["uni_x"]
    ) is None

    answer = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What is in the deleted source?", "university_id": str(state["uni_x"])},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["citations"] == []
    assert "deleted-source text" not in answer.json()["answer"]


@pytest.mark.parametrize("failure_point", ["reconcile", "upsert", "query"])
def test_assistant_fails_closed_when_chroma_synchronization_or_query_fails(failure_point):
    class BrokenStore:
        def reconcile(self, allowed_universities, authoritative_chunk_ids):
            if failure_point == "reconcile":
                raise OSError("synthetic unavailable store")
            return 0

        def upsert(self, chunks, embeddings):
            if failure_point == "upsert":
                raise OSError("synthetic upsert failure")
            return None

        def query(self, embedding, limit, allowed_universities=None):
            raise OSError("synthetic query failure")

    state = _make_two_school_app(vector_store=BrokenStore())
    assert _upload_rag_doc(
        state["client_x"], state["csrf_x"], "SYNTHETIC TEST FIXTURE: Synthetic requirement."
    ).status_code == 201
    _publish_programme(state, "client_x", "csrf_x", state["uni_x"])
    response = state["client_a"].post(
        "/api/v1/guidance/assistant/ask",
        json={"question": "What requirement applies?", "university_id": str(state["uni_x"])},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    assert response.status_code == 503


def test_delete_waits_until_retrieved_answer_is_persisted(tmp_path, monkeypatch):
    import httpx

    started = threading.Event()
    release = threading.Event()

    class BlockingExtractiveProvider(ExtractiveGroundedAnswerProvider):
        def generate(self, question, matches, eligibility=None):
            started.set()
            assert release.wait(10), "test did not release the generation barrier"
            return super().generate(question, matches, eligibility)

    monkeypatch.setenv("RAG_INDEX_DIR", str(tmp_path / "race-index"))
    state = _make_two_school_app(answer_provider=BlockingExtractiveProvider())
    uploaded = _upload_rag_doc(
        state["client_x"], state["csrf_x"], "SYNTHETIC TEST FIXTURE: Requirements are listed here."
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["document_id"]
    _publish_programme(state, "client_x", "csrf_x", state["uni_x"])

    async def exercise_race():
        transport = httpx.ASGITransport(app=state["app"])
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies=dict(state["client_a"].cookies),
        ) as school_client, httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies=dict(state["client_x"].cookies),
        ) as university_client:
            ask_task = asyncio.create_task(school_client.post(
                "/api/v1/guidance/assistant/ask",
                json={"question": "What requirements are listed?", "university_id": str(state["uni_x"])},
                headers={"X-CSRF-Token": state["csrf_a"]},
            ))
            assert await asyncio.to_thread(started.wait, 10)
            delete_task = asyncio.create_task(university_client.delete(
                f"/api/agent/documents/{document_id}",
                headers={"X-CSRF-Token": state["csrf_x"]},
            ))
            await asyncio.sleep(0.05)
            assert not delete_task.done()
            release.set()
            ask_response = await ask_task
            delete_response = await delete_task
            return ask_response, delete_response

    ask_response, delete_response = asyncio.run(exercise_race())
    assert ask_response.status_code == 200
    assert ask_response.json()["citations"]
    assert delete_response.status_code == 204
