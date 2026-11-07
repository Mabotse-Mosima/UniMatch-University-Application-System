# Changelog

## Capstone reorganisation — 2026-10-16

### Structural changes
- Promoted `ASSIGNMENT_12/` application to canonical `src/unimatch/` package with proper Python package imports (replaced `sys.path` hacks).
- Added `src/unimatch/api/`, `src/unimatch/services/`, `src/unimatch/repositories/` subpackages.
- Renamed `src/unimatch/services.py` → `src/unimatch/domain_services.py` to free the `services/` namespace.
- Added `src/unimatch/main.py` as the single application entry point (`uvicorn unimatch.main:app`).
- Moved `ASSIGNMENT_11/`, `ASSIGNMENT_12/`, `screenshot/` and all assignment reflection files to `docs/academic-evidence/` (preserved, not deleted).
- Moved `creational_patterns/` (Assignment 10 design-patterns exercise) and its 6 test files to `docs/academic-evidence/assignment-10/`.
- Moved architecture, requirements, testing and design documents into `docs/` subfolders.
- Moved `PROTECTION.md`, `CONTRIBUTIONS.md`, `CONTRIBUTION_PLAN.md` to `docs/academic-evidence/`.
- Deleted `test_output.txt` (stale generated artefact from a different project directory).

### Configuration updates
- `pyproject.toml`: updated to Python 3.12, `testpaths = ["tests"]`, coverage source limited to `src/unimatch`.
- `requirements.txt`: now lists all runtime deps (fastapi, uvicorn, pydantic) and dev deps (httpx, pytest, pytest-cov).
- `.github/workflows/ci.yml`: updated to run from repository root using Python 3.12.
- `Dockerfile` / `docker-compose.yml`: updated to build from `src/unimatch`.
- `.gitignore`: added `.qodo/`, `.env`, `.claude/settings.local.json`.
- `CONTRIBUTING.md`: updated Python version, commands and project structure.

### Business logic fixes
- `UniversityProgrammeService`: added guards — cannot deactivate a Draft programme; cannot delete a Published programme; programme name cannot be set to whitespace.
- Fixed corrupted indentation in `ASSIGNMENT_12/tests/services/test_services.py` (4 test methods had code at class scope).

### Test results
- Active test suite: **81 tests, all pass** (`tests/api/`, `tests/services/`, `tests/test_domain_entities.py`).
- Deprecated `datetime.utcnow()` warning remains (342 occurrences); does not affect test results.

---

## Assignment 10 — 2026-05-02

### Added
- `src/unimatch/`: domain enums, entities, `StatusHistoryEntry`, and orchestration services aligned with `CLASS_DIAGRAM.md`.
- `creational_patterns/`: Simple Factory (`VehicleFactory`), Factory Method (`PaymentProcessor` hierarchy), Abstract Factory (`GUIFactory` / platform buttons), Builder (`PizzaBuilder`), Prototype (`ShapeCache`), and thread-safe Singleton (`DatabaseConnection`).
- `tests/`: unit tests for each creational pattern plus targeted domain tests (login lockout, APS points, programme publish rule, application submit guard).
- `pyproject.toml`, `requirements.txt`: pytest and pytest-cov configuration (`pythonpath` includes `src` and project root for imports).

### Documentation
- `README.md`: Assignment 10 progress entry, language and design notes, pattern rationale table, and coverage command examples.

### GitHub workflow (manual)
- Move board cards for implemented pattern tasks and class implementation to **Done** when acceptance criteria are met.
- Open follow-up issues for any defects found in testing; reference them in commits, for example: `git commit -m "Fix #15: Thread-safe Singleton initialization"`.
