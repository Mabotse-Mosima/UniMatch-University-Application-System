# UniMatch – Assignment 12: Service Layer & REST API

## Overview

This assignment builds on the domain model (Assignment 9) and repository layer (Assignment 11) by adding:

1. **Service Layer** – business logic encapsulated in three service classes.
2. **REST API** – RESTful endpoints exposed via FastAPI.
3. **OpenAPI Documentation** – auto-generated Swagger UI + handwritten YAML.
4. **Tests** – unit tests (services) and integration tests (API).

The system models a South African university application matching platform (**UniMatch**), letting learners build profiles, track APS scores, browse published programmes, and submit applications.

---

## Project Structure

```
ASSIGNMENT_12/
├── entities.py                    # Domain entities (from Assignment 9)
├── enums.py                       # Domain enums
├── status_history.py              # StatusHistoryEntry helper
├── repositories.py                # Repository interfaces (from Assignment 11)
├── repositories_inmemory.py       # In-memory repository implementations
│
├── services/
│   └── __init__.py                # LearnerProfileService, UniversityProgrammeService, ApplicationService
│
├── api/
│   └── __init__.py                # FastAPI app with all routes
│
├── tests/
│   ├── services/
│   │   └── test_services.py        # unit tests — service layer business rules
│   └── api/
│       └── test_api.py             # integration tests — FastAPI TestClient
│
├── docs/
│   ├── openapi.yaml               # OpenAPI 3.0.3 specification
│   └── README.md                  # How to view Swagger + refresh spec
│
├── requirements.txt               # pip dependencies
├── BACKLOG.md                     # GitHub issue checklist (A12)
├── conftest.py                    # pytest path setup
├── main.py                        # Optional: `python main.py` to run API
├── CHANGELOG.md
└── README.md
```

---

## Entities Covered (3 minimum)

| Entity | Service | Endpoints |
|---|---|---|
| `LearnerProfile` | `LearnerProfileService` | 8 endpoints |
| `UniversityProgramme` | `UniversityProgrammeService` | 9 endpoints |
| `Application` | `ApplicationService` | 9 endpoints |

---

## Setup & Running

### Requirements

```
fastapi
uvicorn
httpx       # for TestClient
pytest
```

Install:

```bash
cd ASSIGNMENT_12
python -m pip install -r requirements.txt
```

Or:

```bash
python -m pip install fastapi uvicorn httpx pytest
```

(On Windows, prefer `python -m pip` and `python -m pytest` if `pip` / `pytest` are “not recognized”.)

### Run the API

```bash
cd ASSIGNMENT_12
uvicorn api:app --reload
```

API docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

### Run Tests

i used **`python -m pytest`** so i don’t rely on a `pytest` script on my PATH:

```bash
cd ASSIGNMENT_12
python -m pip install -r requirements.txt
python -m pytest tests/ -v
```

Expected: **73 passed** (service unit tests + API integration tests).

---

## Business Rules Enforced

### LearnerProfileService
- Marks must be in the range 0–100; invalid marks raise `ValueError`.
- APS uses the NSC 7-point scale; top 6 subjects are used when > 6 marks exist.
- Deactivating a profile cascades to cancel all active (non-terminal) applications.

### UniversityProgrammeService
- A programme can only be published if its deadline is in the future.
- Eligibility is classified as: **Guaranteed** (APS ≥ min+4), **Likely** (≥ min+1), **Borderline** (= min), **NotEligible** (< min).
- Expired programmes are excluded from published listings.

### ApplicationService
- **5-application cap**: a learner may not have more than 5 active (non-terminal) applications simultaneously.
- **No duplicates**: a learner cannot apply to the same programme twice while active.
- **Programme must be active**: applications to Draft, Deactivated, or expired programmes are rejected.
- **Cancel only non-terminal**: cannot cancel Accepted/Rejected/DeadlineMissed applications.

---

## API Summary

### Learners

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/learners` | List all learner profiles |
| `POST` | `/api/learners` | Create a learner profile |
| `GET` | `/api/learners/{id}` | Get a learner profile |
| `PUT` | `/api/learners/{id}` | Update a learner profile |
| `DELETE` | `/api/learners/{id}` | Delete a learner profile |
| `POST` | `/api/learners/{id}/marks` | Add a subject mark |
| `GET` | `/api/learners/{id}/aps` | Get APS score |
| `POST` | `/api/learners/{id}/deactivate` | Deactivate profile |

### Programmes

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/programmes` | List all programmes |
| `POST` | `/api/programmes` | Create a programme |
| `GET` | `/api/programmes/{id}` | Get a programme |
| `PUT` | `/api/programmes/{id}` | Update a programme |
| `DELETE` | `/api/programmes/{id}` | Delete a programme |
| `POST` | `/api/programmes/{id}/publish` | Publish programme |
| `POST` | `/api/programmes/{id}/deactivate` | Deactivate programme |
| `POST` | `/api/programmes/{id}/extend-deadline` | Extend deadline |
| `GET` | `/api/programmes/{id}/eligibility?learner_aps=N` | Eligibility check |

### Applications

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/applications` | List all applications |
| `POST` | `/api/applications` | Create application (with business rule enforcement) |
| `GET` | `/api/applications/{id}` | Get application |
| `DELETE` | `/api/applications/{id}` | Hard-delete application |
| `GET` | `/api/applications/learner/{id}` | Learner's applications |
| `PUT` | `/api/applications/{id}/status` | Update status |
| `POST` | `/api/applications/{id}/submit` | Submit application |
| `POST` | `/api/applications/{id}/cancel` | Cancel application |

---

## Error Responses

| HTTP Code | Meaning |
|---|---|
| `400` | Bad request (e.g. invalid mark score, past deadline on publish) |
| `404` | Resource not found |
| `409` | Conflict (duplicate application, programme not active) |
| `422` | Business rule violation (5-app cap, invalid status transition) |

All error responses return:
```json
{ "detail": "Human-readable error message" }
```

---

## GitHub Issues (Assignment 12 tasks)

| Issue | Title | Status |
|---|---|---|
| #30 | Implement LearnerProfileService with APS calculation | ✅ Closed |
| #31 | Implement UniversityProgrammeService with eligibility | ✅ Closed |
| #32 | Implement ApplicationService with 5-app cap rule | ✅ Closed |
| #33 | Build FastAPI routes for /api/learners | ✅ Closed |
| #34 | Build FastAPI routes for /api/programmes | ✅ Closed |
| #35 | Build FastAPI routes for /api/applications | ✅ Closed |
| #36 | Write OpenAPI YAML documentation | ✅ Closed |
| #37 | Write unit tests for service layer | ✅ Closed |
| #38 | Write integration tests for API | ✅ Closed |

---

## GitHub Screenshots

![GitHub - Repository Overview](../screenshot/Assignment_12%20(1).png)

![GitHub - Issues and Tasks](../screenshot/Assignment_12%20(2).png)

![GitHub - Project Documentation](../screenshot/Assignment_12%20(3).png)
