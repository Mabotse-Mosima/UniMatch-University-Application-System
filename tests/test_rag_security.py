from pathlib import Path
import pytest

from unimatch.rag import (
    ExtractiveGroundedAnswerProvider,
    OpenAICompatibleGroundedAnswerProvider,
    RagChunk,
    RagDocument,
    RagGenerationUnavailableError,
    _validate_generated_answer,
    _validate_generated_citations,
    answer_provider_from_environment,
    is_retryable_generation_error,
)
from datetime import datetime, timezone
from uuid import uuid4


def test_source_does_not_reference_forbidden_global_key_name():
    forbidden = "OPENAI" + "_API_KEY"
    source_root = Path(__file__).parents[1] / "src"
    assert all(forbidden not in path.read_text(encoding="utf-8", errors="ignore") for path in source_root.rglob("*.py"))


def test_provider_selection_is_explicit(monkeypatch):
    monkeypatch.delenv("RAG_PROVIDER", raising=False)
    assert isinstance(answer_provider_from_environment(), ExtractiveGroundedAnswerProvider)
    monkeypatch.setenv("RAG_PROVIDER", "local_openai_compatible")
    with pytest.raises(RagGenerationUnavailableError, match="requires"):
        answer_provider_from_environment()
    monkeypatch.setenv("RAG_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RagGenerationUnavailableError, match="GEMINI_API_KEY"):
        answer_provider_from_environment()


@pytest.mark.parametrize("message, expected", [
    ("timed out", True),
    ("getaddrinfo failed", True),
    ("Name or service not known", True),
    ("HTTP 503 overload", True),
    ("HTTP 401 unauthorized", False),
    ("quota exceeded", False),
])
def test_retry_classification(message, expected):
    assert is_retryable_generation_error(RuntimeError(message)) is expected


def test_retry_classification_checks_exception_class_name_and_message():
    class DroppedConnectionError(Exception):
        pass

    assert is_retryable_generation_error(DroppedConnectionError("temporary outage"))
    assert is_retryable_generation_error(RuntimeError("Name or service not known"))
    assert not is_retryable_generation_error(RuntimeError("HTTP 400 bad request"))


def test_local_openai_compatible_generation_is_testable_without_network(monkeypatch):
    document = RagDocument(
        document_id=uuid4(), university_id=uuid4(), title="SYNTHETIC TEST FIXTURE",
        file_name="fixture.txt", content_type="text/plain", content_sha256="x",
        uploaded_by=uuid4(), created_at=datetime.now(timezone.utc),
    )
    chunk = RagChunk(uuid4(), document.document_id, 0, "SYNTHETIC TEST FIXTURE: Mathematics requires 70.", (0.1,) * 384)

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            import json
            return json.dumps(self.payload).encode()

    replies = iter([
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "Mathematics requires 70. [Source 1]"}}]},
    ])
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse(next(replies)))
    answer, citations = OpenAICompatibleGroundedAnswerProvider(
        "http://synthetic.invalid", "synthetic-model"
    ).generate("What is required?", [(0.9, document, chunk)])
    assert "Mathematics requires 70" in answer
    assert citations[0]["title"] == "SYNTHETIC TEST FIXTURE"


def test_local_openai_compatible_generation_fails_clearly_after_transient_error(monkeypatch):
    document = RagDocument(
        document_id=uuid4(), university_id=uuid4(), title="SYNTHETIC TEST FIXTURE",
        file_name="fixture.txt", content_type="text/plain", content_sha256="y",
        uploaded_by=uuid4(), created_at=datetime.now(timezone.utc),
    )
    chunk = RagChunk(uuid4(), document.document_id, 0, "SYNTHETIC TEST FIXTURE: no invented requirements.", (0.1,) * 384)
    def fail(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(RagGenerationUnavailableError, match="unavailable"):
        OpenAICompatibleGroundedAnswerProvider(
            "http://synthetic.invalid", "synthetic-model"
        ).generate("What is required?", [(0.9, document, chunk)])


@pytest.mark.parametrize("base_url", ["http://synthetic.invalid", "http://synthetic.invalid/v1"])
def test_local_provider_normalises_v1_endpoint(monkeypatch, base_url):
    captured = []

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b'{"choices":[{"message":{"content":"Answer [Source 1]"}}]}'

    def fake_urlopen(request, **kwargs):
        captured.append(request.full_url)
        return FakeResponse()

    document = RagDocument(
        document_id=uuid4(), university_id=uuid4(), title="SYNTHETIC TEST FIXTURE",
        file_name="fixture.txt", content_type="text/plain", content_sha256="z",
        uploaded_by=uuid4(), created_at=datetime.now(timezone.utc),
    )
    chunk = RagChunk(uuid4(), document.document_id, 0, "SYNTHETIC TEST FIXTURE passage", (0.1,) * 384)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    OpenAICompatibleGroundedAnswerProvider(base_url, "synthetic-model").generate(
        "What is stated?", [(0.9, document, chunk)]
    )
    assert captured == ["http://synthetic.invalid/v1/chat/completions"]


def test_generated_answer_rejects_admission_guarantees():
    with pytest.raises(RagGenerationUnavailableError):
        _validate_generated_answer("You are guaranteed admission [Source 1].")


def test_generated_citation_validation_accepts_only_supplied_sources():
    supplied = [{"chunk_id": "real", "title": "SYNTHETIC TEST FIXTURE"}]
    assert _validate_generated_citations("Supported claim [Source 1].", supplied) == supplied
    assert _validate_generated_citations("Supported [Source 1], repeated [Source 1].", supplied) == supplied
    with pytest.raises(RagGenerationUnavailableError, match="did not cite"):
        _validate_generated_citations("Supported claim.", supplied)
    with pytest.raises(RagGenerationUnavailableError, match="not supplied"):
        _validate_generated_citations("Unsupported claim [Source 2].", supplied)
    with pytest.raises(RagGenerationUnavailableError, match="invalid"):
        _validate_generated_citations("Unsupported claim [Source one].", supplied)


def test_generated_citations_are_rejected_when_no_retrieved_evidence_exists():
    with pytest.raises(RagGenerationUnavailableError, match="no source passage"):
        _validate_generated_citations("Unsupported claim [Source 1].", [])
