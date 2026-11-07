# UniMatch local setup

These commands target Windows PowerShell and Python 3.12. The commands do not apply database migrations.

```powershell
Set-Location "C:\path\to\UniMatch-University-Application-System"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The application reads configuration from its process environment; it does not
load `.env` automatically. `.env` is ignored by Git and may be used locally to
keep operator-managed values, but those values must be provided to the process
through an approved local secret-loading mechanism. Do not create `.env` from a
tracked template or commit it. For the default in-memory development setup,
leave `DATABASE_URL` unset. Set it only when intentionally targeting an
approved isolated database.

Learner documents are stored outside the repository. The default local storage
root is `~/.unimatch/documents`; set `DOCUMENT_STORAGE_DIR` to an approved
private, persistent directory when you need a specific location:

```powershell
$env:DOCUMENT_STORAGE_DIR = Join-Path $HOME ".unimatch\documents"
```

In database-disabled development, document bytes and their JSON metadata persist
locally, but the metadata store is intended for a single API process. With
PostgreSQL, migration `0008_learner_document_storage` must be applied before
starting the updated API; its integration has not been verified without an
approved isolated test database. Do not use the local JSON store as a
multi-worker or production persistence solution. Uploaded files are not
virus-scanned; human review is not malware detection.

The safe default is `RAG_PROVIDER=extractive`. The local Chroma index is rebuildable at `./var/rag-index/`; its checked-in source registry is retained, while generated index files and raw documents are not committed. If the embedding model, revision, dimensions, or distance metric changes, delete the generated contents of `var/rag-index` and re-ingest the supplied documents. The application refuses incompatible index metadata rather than silently mixing vectors.

The current default retrieval threshold is **uncalibrated** (`0.30`). It is an initial abstention threshold and must be evaluated against the corpus and question file supplied by the project owner.

Run backend tests from the fresh environment:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
$env:RAG_RUN_LOCAL_MODEL_TESTS="1"
& .\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

The second command enables the separate real local embedding smoke test after the pinned model has been provisioned. Tests use synthetic fixtures only and do not make network calls or call Gemini.

Run the frontend checks from `UniMatch-University-Application-System-Front-End`:

```powershell
npm install
npm run check
npm run build
```

Ingest supplied documents only after confirming their licence and university ownership:

```powershell
& .\.venv\Scripts\python.exe -m unimatch.rag_ingest .\documents --university "University supplied by owner"
```
