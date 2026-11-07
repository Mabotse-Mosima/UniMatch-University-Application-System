# UniMatch — School-Based University Eligibility Recommender

**CPUT Postgraduate Diploma in ICT — Capstone Project**
*Implementation, Testing and Evaluation Phase*

---

## Project title

Design and Development of UniMatch: School-Based University Eligibility Recommender for South African Matriculants

## Problem being addressed

South African Grade 11 and Grade 12 learners often lack clear, accessible guidance on which university programmes they are eligible to apply for. Eligibility depends on the Admission Point Score (APS) — calculated from a learner's NSC subject marks using a standardised 7-point scale — which many learners find difficult to interpret. UniMatch is a school-based decision-support system that calculates each learner's APS, compares it against university programme admission requirements, and classifies eligibility so that learners and their Life Orientation teachers or counsellors can make informed guidance decisions.

## Intended users and pilot scope

The initial pilot targets a single South African school environment. The primary users are:

- **Grade 11 and Grade 12 learners** — view their eligibility results and manage applications
- **Life Orientation teachers and school counsellors** — record marks, run eligibility checks, guide learners
- **School administrators** — manage learner profiles and programme information

This is a limited pilot. It is not a national university admissions platform and does not integrate with live university systems.

---

## Implementation status

This table describes the current codebase. A feature being implemented does not
mean that its production deployment or external integrations have been verified.

| Feature | Status |
|---|---|
| APS calculation using the NSC 7-point scale | Implemented |
| Top-6 subject rule for APS calculation | Implemented |
| Eligibility classification: Guaranteed / Likely / Borderline / Not Eligible | Implemented |
| Learner profile CRUD (create, read, update, delete) | Implemented |
| Recording subject marks against a learner profile | Implemented |
| University programme CRUD | Implemented |
| Programme publication and deactivation (with deadline and status guards) | Implemented |
| Application creation with duplicate-prevention and 5-application cap | Implemented |
| Application cancellation and status transitions | Implemented |
| Application status history recording | Implemented (entity layer) |
| University application list, detail, and review decisions | Implemented; university ownership and role checks enforced |
| Application submission | Guarded; returns HTTP 409 until payment, verified required documents, status, and deadline prerequisites are met |
| Learner document upload and review | Implemented for the local prototype: PDF/DOC/DOCX validation, school-scoped access, persistent local files/metadata, and auditable human review; no malware scanner |
| Payment confirmation | Not implemented; no gateway or trusted payment confirmation |
| In-memory and PostgreSQL repository implementations | Implemented; PostgreSQL runtime not verified |
| FastAPI REST API, authentication, and role checks | Implemented; deployment security not verified |
| React/TypeScript frontend and API workflows | Implemented; complete browser-to-database flow not verified |
| Semantic PDF/DOCX extraction, chunking, retrieval, and source metadata | Implemented; tests exist, live end-to-end use not verified |
| Opt-in local OpenAI-compatible generation | Implemented; no configured/running provider verified |
| PostgreSQL migrations and RAG persistence | Implemented; migrations unapplied and persistence unverified |
| Automated backend and frontend tests/checks | Present; results depend on the current environment and must be run to verify |

### Partially implemented, unverified, and planned

- **Partially implemented:** RAG source retention stores extracted text passages and embeddings, but does not retain the uploaded original file. Source deletion removes it from future retrieval; past messages may retain answer text and cited passages.
- **Partially implemented:** AI guidance uses published-programme sources and deterministic learner eligibility context. The local generative adapter is opt-in; extractive generation is the default when no provider is configured.
- **Incomplete:** University admissions staff can review submitted applications, but the normal submission path remains blocked without payment confirmation. Local learner-document upload, storage, and human review are implemented; the PostgreSQL metadata migration is unapplied and unverified, and files are not virus-scanned. School administrators cannot make admission decisions.
- **Prototype boundary:** Without `DATABASE_URL`, document metadata is stored in a local JSON file and document contents in `DOCUMENT_STORAGE_DIR` (default: `~/.unimatch/documents`). This local store is for a single API process, not multi-worker or production deployment.
- **Unverified:** PostgreSQL-backed repositories, applied migration state, production deployment, local LLM availability, and full end-to-end frontend/API operation.
- **Planned or incomplete:** printed report generation, admission-system integrations, email/SMS delivery, and other future platform integrations described in historical requirements.
- APS and eligibility results remain the deterministic engine's output; guidance generation must not recalculate or override them.

---

## Technology stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| API framework | FastAPI |
| Data validation | Pydantic v2 |
| API server | Uvicorn |
| Testing | Pytest 8+ |
| HTTP test client | httpx / FastAPI TestClient |
| Persistence | In-memory by default; PostgreSQL via SQLAlchemy 2 and Alembic when configured |
| Frontend | React, TypeScript, Vite |
| Containerisation | Docker / docker-compose |
| CI/CD | GitHub Actions |

---

## Architecture

UniMatch uses a layered architecture:

```
src/unimatch/
├── config.py            ← Typed environment configuration
├── database.py          ← SQLAlchemy engine and session factory
├── db_models.py         ← PostgreSQL persistence models for active API data
├── entities.py          ← Domain entities (LearnerProfile, UniversityProgramme, Application, …)
├── enums.py             ← Status enums (EligibilityEnum, ApplicationStatusEnum, …)
├── status_history.py    ← Application status history entry
├── domain_services.py   ← Domain-level services (ApsCalculator, EligibilityClassifier, …)
├── api/
│   └── __init__.py      ← FastAPI route handlers and Pydantic request/response schemas
├── services/
│   └── __init__.py      ← Application services (LearnerProfileService, UniversityProgrammeService, ApplicationService)
├── repositories/
│   ├── __init__.py      ← Abstract repository interfaces (ABCs)
│   ├── inmemory.py      ← In-memory repository implementations
│   └── postgres.py      ← PostgreSQL implementations for active API repositories
└── main.py              ← Application entry point
```

The reviewed initial schema is in `migrations/versions/0001_initial.py`. It covers learners and marks, programmes, applications and status history, and scoring rules. School/counsellor and other external UUID references remain unlinked until their entities are introduced in a later phase.

**Layer responsibilities:**

- **Domain entities** (`entities.py`): Business objects with their own invariants and rules (e.g. `Mark.to_aps_points()`, `UniversityProgramme.publish()`).
- **Application services** (`services/`): Orchestrate repository reads and writes, enforce cross-entity business rules (eligibility caps, duplicate prevention).
- **Repositories** (`repositories/`): Abstract persistence interfaces, in-memory test implementations, and PostgreSQL implementations for active API resources.
- **API** (`api/`): FastAPI route handlers translate HTTP requests into service calls and format responses.

---

## Repository structure

```
UniMatch-University-Application-System/
├── README.md
├── pyproject.toml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── src/
│   └── unimatch/            ← Canonical application source
├── tests/
│   ├── api/                 ← API integration tests
│   ├── services/            ← Service unit tests
│   ├── test_domain_entities.py
│   └── test_*.py            ← Design-pattern tests (historical academic evidence)
├── docs/
│   ├── architecture/        ← ARCHITECTURE.md, DOMAIN_MODEL.md, diagrams
│   ├── requirements/        ← SPECIFICATION.md, system requirements, use cases
│   ├── testing/             ← TEST_CASES.md, TRACEABILITY.md
│   ├── design/
│   └── academic-evidence/   ← Historical assignment submissions and screenshots
└── .github/
    └── workflows/
        └── ci.yml
```

Historical academic artefacts (assignment submissions, reflections, screenshots, earlier implementations) are preserved under `docs/academic-evidence/` to serve as evidence of the project's development history.

---

## Prerequisites

- Python 3.12 or later
- Git

For Docker deployment:
- Docker Desktop

---

## Installation and environment setup

```bash
# 1. Clone the repository
git clone https://github.com/Mabotse-Mosima/UniMatch-University-Application-System.git
cd UniMatch-University-Application-System

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows Command Prompt:
.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate

# 3. Install the project and development dependencies
python -m pip install -e ".[dev]"

# 4. Start without DATABASE_URL for in-memory development
```

The local `.env` file is ignored by Git, but the API and Alembic do not load it
automatically. They read `DATABASE_URL` from the process environment. Without
that variable the API uses in-memory repositories. To ensure this in Windows
PowerShell:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

Only set `DATABASE_URL` when you have an explicitly approved isolated database
and obtain its connection string from a protected source, then provide it to
the API process through an approved secret-management mechanism. Do not copy
secrets into source files or commit `.env`. Alembic migrations are explicit and
are never applied automatically by the API.

---

## Running the application

```bash
# From the repository root
uvicorn unimatch.main:app --reload
```

The API will be available at `http://localhost:8000`.

### Application review and submission limitations

- `UniversityAdmissions` users can list and view submitted applications for
  programmes owned by their university and record review decisions through
  `GET /api/university/applications`,
  `GET /api/university/applications/{application_id}`, and
  `PUT /api/university/applications/{application_id}/review`.
- The API derives university scope from the authenticated account. Other
  universities receive no access; learners cannot review applications, and
  `SchoolAdmin` users cannot make admissions decisions.
- Review transitions and history are validated and retain the reviewer, time,
  and note. A request for additional documents requires a nonblank explanation.
- Application submission intentionally returns HTTP 409 until payment and
  required human-verified documents are present. School staff can upload and
  review local learner documents; no payment gateway or malware scanner is
  integrated. Do not represent a seeded review test as proof of end-to-end
  application submission.

### AI programme guidance (Stage 4B)

- Sign in as a verified `UniversityAdmissions` account and open **AI programme guidance**
  at `/agent` to upload an authoritative PDF or DOCX admissions document (10 MB maximum).
- Sign in as a `SchoolAdmin` and open **AI programme guidance** at `/agent` to ask about indexed programme
  requirements. Select an in-scope learner to include deterministic APS and
  eligibility results. The assistant cites retrieved document passages and does not
  represent classifications as admissions decisions.
- PDF/DOCX source text is extracted, chunked, and embedded with the pinned local
  `sentence-transformers/all-MiniLM-L6-v2` model at revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Query retrieval uses normalized
  embedding cosine similarity; the model loads from the local Hugging Face cache
  only and does not download at API runtime. If the cache is missing, provision the
  pinned model before starting the feature:

  ```bash
  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41', device='cpu')"
  ```

- Answers use a clearly labelled local extractive fallback by default. A local
  generative adapter is available for an OpenAI-compatible server such as LM
  Studio or Ollama, but it is opt-in and makes no request unless both variables
  below are set. The endpoint must be a locally controlled, privacy-approved
  service because learner context may be included in the prompt:

  ```bash
  RAG_LLM_BASE_URL=http://localhost:1234
  RAG_LLM_MODEL=your-local-model-id
  # Optional for a local server that requires one:
  RAG_LLM_API_KEY=local-only-key
  ```

  The adapter sends retrieved passages and the stored deterministic eligibility
  snapshot, requires each generated answer to cite a supplied `[Source N]`, rejects
  missing, malformed, or out-of-range citations, and instructs it not to
  invent requirements or guarantee admission. Provider failure returns a clear
  503; it does not silently fall back to an ungrounded answer. No paid provider
  calls are made by this implementation.
- Uploaded originals are not retained: only extracted passages, embeddings, and
  metadata are stored. No approved blob/object storage is configured. Source
  deletion removes the indexed content from future retrieval; prior conversation
  messages can retain the historical answer and cited passage. This stage does not
  delete conversations or prior message records. A secure policy should define
  retention periods for original files, extracted text, vectors, chats, and backups;
  restrict access by school/university and role; encrypt storage and backups; audit
  access/deletion; and provide an approved retention expiry and verified deletion
  process that covers backups. Re-indexing
  re-embeds the retained passages. If extraction or chunking rules change, the
  original must be uploaded again. Approved retention needs a configured storage
  provider, container/bucket, least-privilege access, encryption, and deletion policy.
- Retrieval is limited to sources belonging to universities with currently
  published programmes. University source ingestion, re-indexing, and removal are
  scoped to the authenticated university account.
- In-memory indexes and conversations are lost on process restart. PostgreSQL-backed
  persistence requires the migration chain through
  `0006_semantic_embedding_metadata` (including its existing prerequisites).
  Migration 0006 marks existing feature-hashed vectors as legacy so they cannot be
  compared with semantic vectors; re-index each source from its stored passages
  before retrieval. Migrations are not applied automatically.

With Docker:

```bash
docker compose up --build
```

After confirming the target is the intended fresh development database, apply the reviewed schema explicitly:

```bash
docker compose exec unimatch alembic upgrade head
```

For a locally run API, set `DATABASE_URL` in the process environment. Without it, the module-level API uses in-memory repositories. Test applications created with `create_app()` remain in-memory unless a database URL is explicitly supplied.

---

## Running the tests

```bash
# Full test suite from the repository root
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=src/unimatch --cov-report=term-missing
```

The PostgreSQL repository integration test is skipped unless an explicitly approved local test database is configured using `UNIMATCH_TEST_DATABASE_URL` and `UNIMATCH_TEST_DATABASE_APPROVED=1`. It never uses `DATABASE_URL` as a fallback.

---

## API documentation

When the application is running, interactive API documentation is available at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **Health check:** `http://localhost:8000/health`

---

## Links to capstone documentation

| Document | Location |
|---|---|
| System specification | [docs/requirements/SPECIFICATION.md](docs/requirements/SPECIFICATION.md) |
| Architecture overview | [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) |
| Domain model | [docs/architecture/DOMAIN_MODEL.md](docs/architecture/DOMAIN_MODEL.md) |
| System requirements (functional) | [docs/requirements/SYSTEM_REQUIREMENTS (Functional Section).md](<docs/requirements/SYSTEM_REQUIREMENTS (Functional Section).md>) |
| System requirements (non-functional) | [docs/requirements/SYSTEM_REQUIREMENTS (Non-Functional Section).md](<docs/requirements/SYSTEM_REQUIREMENTS (Non-Functional Section).md>) |
| Use case specifications | [docs/requirements/USE_CASE_SPECIFICATIONS.md](docs/requirements/USE_CASE_SPECIFICATIONS.md) |
| Test cases | [docs/testing/TEST_CASES.md](docs/testing/TEST_CASES.md) |
| Requirements–tests traceability | [docs/testing/TRACEABILITY.md](docs/testing/TRACEABILITY.md) |
| Implementation, testing and submission readiness | [docs/testing/IMPLEMENTATION_TESTING_EVALUATION.md](docs/testing/IMPLEMENTATION_TESTING_EVALUATION.md) |

---

## Known limitations and gaps

- Without `DATABASE_URL`, the API uses in-memory repositories and data is lost on restart. PostgreSQL implementations exist, but their end-to-end runtime behavior is not claimed as verified here. Migrations require explicit operator action.
- There is no payment gateway or malware scanner. Local document upload, persistence, download, and auditable human review are implemented; PostgreSQL persistence requires unapplied migration `0008_learner_document_storage`. Application submission continues to reject missing payment/document prerequisites with HTTP 409.
- PostgreSQL integration tests, browser-based end-to-end tests, and visual accessibility checks were not completed in the latest verification.
- Some legacy requirements and architecture material describe future integrations or workflows. They should not be interpreted as delivered functionality.
- Local LLM operation depends on an operator-configured, privacy-approved OpenAI-compatible local endpoint. No provider is required or contacted by default.
- Source citations validate references to retrieved chunks; citation correctness does not independently prove that a source passage is authoritative or that generated reasoning is factually correct.
- Uploaded originals are discarded after extraction. Historical assistant messages may preserve cited passages after source deletion; they require a separately approved retention and deletion policy.

---

## Capstone context

This repository is the working codebase for a CPUT Postgraduate Diploma in ICT capstone project. The Design Phase was completed and received 100%. This repository now hosts the Implementation, Testing and Evaluation Phase.

Historical academic artefacts — assignment submissions, sprint backlogs, reflections, and earlier implementation iterations — are preserved under [docs/academic-evidence/](docs/academic-evidence/) to demonstrate the project's development progression.
