# UniMatch Stage 4 status — historical Gate 2 snapshot

Status: Gate 2 implemented and verified locally at the historical snapshot recorded below; commit and push were intentionally pending review at that stage.

> This file preserves historical Gate 2 results and is not the latest verification.
> See [docs/testing/IMPLEMENTATION_TESTING_EVALUATION.md](docs/testing/IMPLEMENTATION_TESTING_EVALUATION.md)
> for the current backend/frontend verification, synthetic evaluations, and
> remaining limitations.

## Verified in this worktree

- Semantic embeddings use `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions), with model/revision metadata and a rebuild-on-mismatch rule.
- Chroma is the default vector store; the legacy relational RAG path remains available.
- `RAG_PROVIDER=extractive` is the default. `gemini` requires `GEMINI_API_KEY`; `local_openai_compatible` requires `RAG_LOCAL_OPENAI_BASE_URL` and `RAG_LOCAL_OPENAI_MODEL`.
- The local OpenAI-compatible provider has a 40-second timeout, up to three transient retries, and one empty-reply retry. Retry classification checks both exception class name and message and excludes 4xx/quota failures.
- The assistant endpoint is `/api/v1/guidance/assistant/ask`; `/api/agent/...` routes remain present.
- CSRF, role/school/university isolation, request validation, request-size checking, in-memory rate limiting, citation post-checks, admission-guarantee rejection, and deterministic eligibility-number consistency fallback are covered by no-network tests.
- Learner context is server-authorised and external-provider context is disabled unless `RAG_EXTERNAL_LEARNER_CONTEXT=true`. Do not enable that flag for real learner data.

## Historical Gate 2 verification commands

From the backend `.venv`, with no `PYTHONPATH` override:

```powershell
$env:RAG_RUN_LOCAL_MODEL_TESTS='1'
python -m pytest tests -q -p no:cacheprovider --basetemp .pytest-tmp
```

Historical Gate 2 result: `421 passed, 26 skipped, 5 warnings`.

```powershell
python -m pytest --collect-only -q tests/test_rag_pipeline.py tests/test_rag_security.py
```

Result: 17 tests collected. The real-model test is separately marked and requires `RAG_RUN_LOCAL_MODEL_TESTS=1`.

Historical Gate 2 frontend result: `npm.cmd run check` passed. `npm.cmd run build` could not complete in that host because Node 24 returned `uv_os_get_passwd ... ENOMEM`; this was an environment resource failure, not a TypeScript/build diagnostic. This is not the latest frontend result; see the current verification report linked above.

## Not verified / infrastructure limits

- No OpenAI-compatible model server was detected on the usual local ports (1234, 11434, 8000, 8080), and no model was downloaded for one. Therefore no real local generated-answer call was run. The provider was tested with a scripted in-process stand-in only.
- No Gemini call was made. A real Gemini test needs `RAG_PROVIDER=gemini`, `GEMINI_API_KEY`, and `RAG_GEMINI_MODEL`; it must be approved separately and must use synthetic learner data only.
- Uploaded originals are not retained: the current ingestion path stores extracted text/chunks and metadata, not the original PDF/DOCX/TXT/HTML file. Safe original retention still needs an approved storage root/object-store configuration, size/type policy, ownership checks, and deletion lifecycle.
- PostgreSQL persistence was not claimed or integration-tested. Migration `0005_rag_knowledge_base.py` was not applied or changed. The relational path remains legacy; Chroma persistence is local under `RAG_INDEX_DIR`.
- No real university documents or evaluation question set were used. All test content is labelled `SYNTHETIC TEST FIXTURE`.

## Index compatibility

Existing indexes created with the previous feature-hash/cosine handling are not silently reused. Delete/rebuild `RAG_INDEX_DIR` and re-ingest all sources when the embedding model, revision, dimensions, or distance metric changes.

