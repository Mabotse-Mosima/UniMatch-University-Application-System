# Assignment 12 — GitHub issues checklist

Create/close issues on your **UniMatch** project board to satisfy the “GitHub Updates” deliverable.

| ID | Suggested title | Typical status (if code matches this repo) |
|----|-----------------|---------------------------------------------|
| A12-1 | Service layer: `LearnerProfileService` + unit tests | Done |
| A12-2 | Service layer: `UniversityProgrammeService` + unit tests | Done |
| A12-3 | Service layer: `ApplicationService` (cap, duplicates, rules) + tests | Done |
| A12-4 | REST: `/api/learners` CRUD + marks + APS + deactivate | Done |
| A12-5 | REST: `/api/programmes` CRUD + publish + eligibility | Done |
| A12-6 | REST: `/api/applications` CRUD + status + submit + cancel | Done |
| A12-7 | OpenAPI: Swagger `/docs` + `docs/openapi.yaml` | Done |
| A12-8 | Integration tests (`tests/api`) with `TestClient` | Done |
| A12-9 | `CHANGELOG.md` for Assignment 12 | Done |
| A12-10 | Screenshot: Swagger UI (`http://localhost:8000/docs`)

---

## Route ordering note

`GET /api/applications/learner/{learner_id}` is registered **before** `GET /api/applications/{application_id}` so FastAPI does not treat `learner` as a malformed UUID path parameter.

## GitHub Screenshots

![GitHub - Repository Overview](../screenshot/Assignment_12%20(1).png)

![GitHub - Issues and Tasks](../screenshot/Assignment_12%20(2).png)

![GitHub - Project Documentation](../screenshot/Assignment_12%20(3).png)