# CHANGELOG

All notable changes to the UniMatch project are documented here.

---

## [Assignment 12] – 2026-05-15 – Service Layer & REST API

### Added

**Service Layer (`/services`)**
- `LearnerProfileService` – CRUD for learner profiles; validates marks (0–100); calculates NSC APS; cascades deactivation to cancel open applications.
- `UniversityProgrammeService` – CRUD for programmes; enforces future-deadline rule on publish; eligibility classification (Guaranteed / Likely / Borderline / NotEligible).
- `ApplicationService` – Full application lifecycle; enforces 5-application active cap per learner; rejects duplicate applications; requires Published + non-expired programme.
- Custom exceptions: `LearnerNotFoundError`, `ProgrammeNotFoundError`, `ApplicationNotFoundError`, `TooManyActiveApplicationsError`, `DuplicateApplicationError`, `ProgrammeNotActiveError`, `InvalidStatusTransitionError`.

**REST API (`/api`)**
- `GET /api/learners` – list all learner profiles.
- `POST /api/learners` – create a learner profile.
- `GET /api/learners/{id}` – get a learner profile.
- `PUT /api/learners/{id}` – update a learner profile.
- `DELETE /api/learners/{id}` – delete a learner profile.
- `POST /api/learners/{id}/marks` – add a subject mark.
- `GET /api/learners/{id}/aps` – get current APS score.
- `POST /api/learners/{id}/deactivate` – deactivate profile and cancel applications.
- `GET /api/programmes` – list programmes (with `?published_only=true` filter).
- `POST /api/programmes` – create a programme.
- `GET /api/programmes/{id}` – get a programme.
- `PUT /api/programmes/{id}` – update a programme.
- `DELETE /api/programmes/{id}` – delete a programme.
- `POST /api/programmes/{id}/publish` – publish a programme.
- `POST /api/programmes/{id}/deactivate` – deactivate a programme.
- `POST /api/programmes/{id}/extend-deadline` – extend application deadline.
- `GET /api/programmes/{id}/eligibility?learner_aps=N` – eligibility check.
- `GET /api/applications` – list all applications.
- `POST /api/applications` – create an application (with all business rule enforcement).
- `GET /api/applications/{id}` – get an application.
- `DELETE /api/applications/{id}` – hard-delete an application.
- `GET /api/applications/learner/{id}` – get applications for a learner.
- `PUT /api/applications/{id}/status` – update application status.
- `POST /api/applications/{id}/submit` – submit an application.
- `POST /api/applications/{id}/cancel` – soft-cancel an application.
- `GET /health` – service health check.

**Tests (`/tests`)**
- 38 unit tests for `LearnerProfileService`, `UniversityProgrammeService`, and `ApplicationService`.
- 35 integration tests for all API endpoints using FastAPI `TestClient`.
- Covers happy paths and all error conditions (404, 409, 422, 400).

**API Documentation (`/docs`)**
- `openapi.yaml` – full OpenAPI 3.0.3 specification with schemas, error responses, and examples.
- Auto-generated Swagger UI available at `http://localhost:8000/docs`.
- Auto-generated ReDoc available at `http://localhost:8000/redoc`.

### Fixed (2026-05-15 follow-up)
- **FastAPI body binding:** Pydantic request/response models moved to **module scope** inside `api/__init__.py` (nested classes inside `create_app()` were parsed as query parameters). The FastAPI instance variable was renamed to `fastapi_app` to avoid clashing with the domain `Application` variable name `app` in route handlers.
- **FastAPI parameters:** Renamed route handler argument `body` → `payload` where applicable (and rely on module-level models for correct JSON bodies).
- **Repositories import:** `repositories_inmemory` now imports interfaces from `repositories` (removed duplicate `repositories_tmp.py`).
- **Unit test:** `test_add_valid_mark` asserts `len(profile.marks)` instead of non-existent `mark_count` on `LearnerProfile`.

### Fixed
- Business rule: deactivating a learner profile now correctly cascades to cancel active applications.
- Business rule: expired programmes are excluded from published listings even when status is still `Published`.

---

## [Assignment 11] – 2026-05-10 – Repository Layer

### Added
- Generic `Repository[T, ID]` interface with CRUD contract.
- Entity-specific interfaces: `UserAccountRepository`, `LearnerProfileRepository`, `UniversityProgrammeRepository`, `ApplicationRepository`, `DocumentRepository`, `MarkRepository`, `PaymentTransactionRepository`, `NotificationRepository`, `AuditLogRepository`.
- `InMemory*` implementations for all nine repositories.
- Stub implementations for testing isolation.
- 40+ repository unit tests.

---

## [Assignment 9] – 2026-04-26 – Domain Model

### Added
- Core entities: `UserAccount`, `LearnerProfile`, `Mark`, `UniversityProgramme`, `Application`, `Document`, `PaymentTransaction`, `RecommendationResult`, `Notification`, `AuditLogEntry`.
- Enums: `RoleEnum`, `ApplicationStatusEnum`, `EligibilityEnum`, `ProgrammeStatusEnum`, `PaymentStatusEnum`, `ProfileStatusEnum`.
- APS calculation (NSC 7-point scale, top 6 subjects).
- Application status-history tracking via `StatusHistoryEntry`.


## GitHub Screenshots

![GitHub - Repository Overview](../screenshot/Assignment_12%20(1).png)

![GitHub - Issues and Tasks](../screenshot/Assignment_12%20(2).png)

![GitHub - Project Documentation](../screenshot/Assignment_12%20(3).png)