# UniMatch implementation, testing, and submission readiness

This report records the implementation and verification evidence available for
the submission review. Synthetic evaluation fixtures are explicitly identified;
they are not real learner records, official university rules, or proof of a
production deployment. Fresh verification was run on 2026-11-03.

The 2026-11-03 full-suite and synthetic-evaluation results below predate the
learner-document workflow added afterward; they are not a full verification of
the current code snapshot. Current focused document tests and frontend checks
are listed separately.

## Delivered functionality

- **Eligibility:** APS and programme eligibility are calculated by deterministic
  application services. Synthetic RAG answers may explain retrieved source
  passages and the deterministic learner result; RAG does not decide eligibility
  or admission.
- **Applications:** applications can be created and their lifecycle transitions
  are validated and recorded in status history. Submission remains guarded by
  payment-reference, human-verified required-document, status, and deadline
  checks. Manual payment status changes remain disabled.
- **Learner documents:** school-scoped staff can upload supported PDF/DOC/DOCX
  files, link them to an application, download them, and record a `Verified` or
  `Rejected` human review with reviewer identity, timestamp, and note. Local
  development persists file bytes and JSON metadata outside the repository.
  Files are explicitly marked `NotScanned`; this is not malware detection.
- **University review:** `UniversityAdmissions` users can list and view submitted
  applications for programmes owned by their university and record permitted
  decisions. Reviewer identity, timestamp, and note are included in status
  history. `SchoolAdmin` users can manage their school's applications but cannot
  make admissions decisions. Learners cannot review applications.
- **Frontend:** the React client has a university application list and review
  interface, with role-based routing and loading, empty, error/forbidden, and
  review states. The live learner profile supports document upload, download,
  and auditable human review.
- **RAG:** the API retrieves university-scoped sources, checks citations against
  retrieved passages, and uses an extractive response by default. Local
  generation is optional and requires an operator-configured provider.

### Application endpoints and authorization

| Endpoint | Intended role | Behavior |
|---|---|---|
| `GET /api/university/applications` | `UniversityAdmissions` | Lists reviewable applications whose programme belongs to the authenticated university |
| `GET /api/university/applications/{application_id}` | `UniversityAdmissions` | Returns an application only when it belongs to that university; cross-university records return 404 |
| `PUT /api/university/applications/{application_id}/review` | `UniversityAdmissions` | Validates and records an allowed review transition; a document request requires a nonblank note |
| `GET /api/applications` and school application routes | `SchoolAdmin` | Restrict learner/application access to the administrator's school; admissions decisions remain forbidden |
| `POST /api/learners/{learner_id}/documents` and `GET /api/learners/{learner_id}/documents` | `SchoolAdmin`, scoped `Teacher` | Upload and list learner documents within the authenticated school |
| `GET /api/documents/{document_id}/download` | School staff; owning `UniversityAdmissions` for submitted applications | Checks school ownership or the submitted application's university before download |
| `PUT /api/documents/{document_id}/review` | `SchoolAdmin`, scoped `Teacher` | Records a human `Verified`/`Rejected` decision and required note for the owning school |

Learner accounts cannot use the university review routes. Status transitions
are enforced by the domain model and API; an invalid transition is rejected
without changing the application.

## Verified evaluation and tests

| Check | Result | Scope and caveats |
|---|---:|---|
| Complete backend suite, database access disabled (`python -m pytest tests -q -p no:cacheprovider`) | **489 passed, 31 skipped, 2 warnings** | 30 PostgreSQL integration tests skipped because an approved isolated test database was unavailable; one opt-in embedding-cache test skipped |
| Synthetic eligibility evaluation | **9/9 predictions correct** | 8 synthetic learner profiles, 9 programme predictions, 47 synthetic marks |
| Synthetic RAG evaluation | **5/5 checks passed** | Synthetic passages and questions only; tests grounding, citations, university scope, and abstention, not real-world accuracy |
| University review evaluation | **Passed** | Own-university listing succeeded; cross-university access returned 404; SchoolAdmin decision returned 403; invalid transition returned 422; a synthetic review reached `Accepted` with reviewer identity, timestamp, and note |
| Evaluation regression tests (`python -m pytest tests/evaluation/test_submission_evaluation.py -q`) | **4 passed, 1 warning** | `tests/evaluation/test_submission_evaluation.py` |
| Learner document focused backend tests | **13 passed, 2 warnings** | Current changed code: local metadata restart persistence, upload type/signature checks, school isolation, review auditing, and payment-less submission guard; warnings are the existing Starlette/AnyIO deprecation and `TestContext` collection warning |
| Frontend type-check (`npm run check`) | **Passed** | Run after the learner-document UI changes |
| Frontend production build (`npm run build`) | **Passed** | Run after the learner-document UI changes; existing mixed import and large-chunk advisories remain |
| Full backend suite | **489 passed, 31 skipped, 2 warnings (pre-document-change baseline)** | Fresh full run on 2026-11-03; must be rerun before treating this as current full-suite verification |
| PostgreSQL integration / migration verification | **Not run** | No approved isolated test database was available; migration `0008_learner_document_storage` is unapplied; no database was accessed |
| Browser end-to-end and visual accessibility testing | **Not run** | Automated type-check/build do not establish browser behavior or visual accessibility |

The full backend run was performed with `DATABASE_URL` and approved PostgreSQL
test-database settings unset, Chroma telemetry disabled, and `RAG_INDEX_DIR`
pointing to a fresh temporary directory. The temporary directory was removed
after the run. The two full-suite warnings were a Starlette/AnyIO deprecation
notice and pytest's intentional non-collection of the helper `TestContext`
class. The synthetic evaluation runner uses an in-memory vector-store test
double and did not access a Chroma collection. The results file was refreshed
by running `python tests/evaluation/evaluate_submission.py`. No PostgreSQL
connection or migration was performed.

### Submission and review workflow boundary

The pre-document-change synthetic school-to-application run created an
application but submission returned **HTTP 409**, as designed, because a
payment reference and linked documents were absent. In the current focused
document tests, staff upload and verify required documents, but the application
still cannot become `PackageReady` or be submitted without confirmed payment.
No payment reference or verified payment state is fabricated.

The review evaluation is a separate authorization/transition test against a
synthetic application fixture pre-seeded as `Submitted`. It proves the review
routes and controls in isolation; it does **not** prove that an application can
pass the blocked payment/document submission path or that an end-to-end
admissions workflow is available.

### Synthetic in-memory performance observations

These are local, single-process FastAPI `TestClient` timings on small synthetic
datasets, not production benchmarks, capacity measurements, or service-level
objectives.

| Operation | Requests | Median | p95 |
|---|---:|---:|---:|
| Eligibility recommendations across 8 synthetic profiles | 8 | 3.150 ms | 6.171 ms |
| Repeated recommendations for one synthetic profile | 10 | 3.875 ms | 5.372 ms |
| Published-programme catalogue listing | 10 | 3.687 ms | 6.468 ms |
| Fixed synthetic RAG questions | 4 | 5.155 ms | 5.572 ms |
| Repeated synthetic RAG retrieval and response | 10 | 8.519 ms | 13.432 ms |

The RAG test corpus contains two synthetic documents from two synthetic
universities. It uses deterministic hashed-token embeddings and an in-memory
vector-store test double, not the production embedding model, Chroma, or an
external generation provider. These results do not establish admission-policy
accuracy or answer accuracy for real university documents.

## Outstanding limitations and submission blockers

1. **Historical credential-shaped database URL — owner assessment required.**
   The unsafe `.env.example` was removed from the Git index and is absent from
   the working tree. The staged [SETUP.md](../../SETUP.md) no longer instructs
   users to copy it. The local `.env` is ignored, not tracked, and has no
   committed versions. A credential-shaped database URL remains in historical
   `.env.example` content at commit
   `ad9c57209df277915cbdf778638e0078102cbe17`; its validity and use have not
   been established. No values are reproduced, and no credentials were rotated
   or revoked. The credential owner must assess whether it was usable and
   rotate it if warranted. Removing the current index entry does not erase
   historical Git objects.
2. **Payment integration is absent.** There is no gateway confirmation or
   trusted payment callback. Manual status changes cannot be used to pretend
   payment occurred; submission must continue returning HTTP 409 when payment
   evidence is missing.
3. **Application document handling is incomplete.** Full upload, persistence,
   and verification are absent. Linked-document metadata or a requested
   document is not proof of verification.
4. **PostgreSQL remains unverified.** The latest full run skipped all 30
   PostgreSQL integration tests. Migration application and PostgreSQL runtime
   behavior need verification against an explicitly approved isolated test
   database.
5. **Browser verification remains outstanding.** No browser-driven end-to-end
   flow or visual accessibility assessment was run.
6. **Pre-existing staged whitespace warning.** The full cached diff check reports
   a blank line at `IMPLEMENTATION_STATUS.md:45`. It predates this audit and was
   left untouched to preserve unrelated staged work; the corrected staged
   `SETUP.md` passes its whitespace check.

### Environment file and history status

The local `.env` remains present and ignored by `.gitignore`; it is not in the
Git index and has no commit history. It was not read or modified for this audit.
There is currently no `.env.example` in the working tree or index. The staged
`SETUP.md` documents that configuration is read from the process environment,
that `.env` is not loaded automatically, and that `DATABASE_URL` should remain
unset for in-memory development. If a template is desired later, create one
containing only blank or clearly nonfunctional placeholders and keep its setup
instructions consistent with how configuration reaches the process.

The historical database URL requires a separate owner assessment. Do not
rewrite Git history or rotate credentials blindly. Decide whether the value
was usable and rotate it if warranted; this review did not establish its
validity or use.

## Practical local demonstration checklist

### Before starting

- [x] Remove the unsafe environment template from the Git index and correct the
  staged setup instructions; do not recreate or copy `.env.example`.
- [ ] Have the credential owner assess the historical database URL at commit
  `ad9c57209df277915cbdf778638e0078102cbe17` and rotate it if warranted.
- [ ] Use only synthetic learner/programme/document data and accounts provisioned
  for an explicitly approved isolated environment. Do not use real learner
  records or production/development databases.
- [ ] Do not use `DATABASE_URL` unless the target is an approved isolated
  database. For an in-memory demonstration, leave it unset.
- [ ] Give the API a fresh temporary `RAG_INDEX_DIR` and keep
  `ANONYMIZED_TELEMETRY=False`. API RAG uses `unimatch_rag_api_v1`; do not run
  the standalone pipeline or access legacy Chroma collections.
- [ ] Confirm the required Python and Node dependencies are already installed.
  Do not run database migrations as part of the demo.

### Start the services (Windows PowerShell)

In the backend repository:

```powershell
Set-Location <path-to-UniMatch-University-Application-System>
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:ANONYMIZED_TELEMETRY = "False"
$env:RAG_INDEX_DIR = Join-Path $env:TEMP ("unimatch-demo-" + [guid]::NewGuid().ToString("N"))
python -m uvicorn unimatch.main:app --reload
```

Create and activate the virtual environment only if one does not already exist.
If dependencies are not installed, install the project's declared dependencies
in that environment before starting the API:

```powershell
python -m pip install -e ".[dev]"
```

In a second terminal, start the frontend from its repository:

```powershell
Set-Location <path-to-UniMatch-University-Application-System-Front-End>
npm run dev:client
```

Open `http://localhost:5000`. The Vite development server proxies `/api`
requests to the backend at `http://127.0.0.1:8000`. The API's interactive
documentation is available at `http://localhost:8000/docs`.

### Demonstrate the implemented paths honestly

1. Sign in with an operator-provisioned `SchoolAdmin` account. Create or open a
   synthetic learner, record marks, and show deterministic APS/recommendations.
2. Select a published synthetic programme and create an application. Show its
   status and submission blockers.
3. Upload and manually review synthetic learner documents from the learner
   profile. Show their `NotScanned` label and review audit information. Attempt
   submission and show the expected HTTP 409 because payment confirmation is
   not integrated; do not fabricate a payment reference.
4. Show that the SchoolAdmin can manage school applications but cannot make
   `Accepted`, `Rejected`, or other admissions decisions.
5. A university review UI demonstration requires a legitimately submitted
   synthetic application in the approved isolated environment. If none exists,
   do not invent one or claim a full workflow; instead show the separately
   labelled automated review regression result.
6. Where a legitimately submitted synthetic application exists, sign in as its
   owning `UniversityAdmissions` account, list and inspect it, begin review,
   then demonstrate a valid decision or a document request with a nonblank
   note. Do not use an account from another university to access it; the API
   must not disclose that record.
7. If demonstrating RAG, use synthetic/approved university source material.
   Present answers as cited guidance, not an admission decision or guaranteed
   requirement.
8. State the unverified PostgreSQL migration, browser end-to-end, visual
   accessibility, payment, and malware-scanning limitations during the
   demonstration. The local JSON metadata repository is single-process only.

## Readiness recommendation

**Conditional NO-GO pending historical credential-owner assessment.** Fresh
verification passed, the staged `.env.example` issue is resolved, and `.env`
remains ignored. Before submission, the owner must assess the historical
credential-shaped database URL and rotate it if warranted. If that assessment
is complete, the project is demonstrable as a functionally advanced academic
prototype with payment, PostgreSQL migration/integration, malware-scanning, and
browser-testing limitations disclosed. It is not production-ready on the
evidence available.
