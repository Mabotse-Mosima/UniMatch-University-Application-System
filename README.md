# UniMatch – School-Based University Application & Eligibility System

UniMatch is a **centralized decision-support and application coordination platform** for South African high schools. It connects **learners**, **school staff** (teachers, counselors, administrators), **parents/guardians**, **university admissions offices**, and **district / Department of Education** stakeholders so that programme information, eligibility guidance, **secure fee payment** (via an external gateway), application packages, and outcomes are managed in one place.

- Staff manage academic data, import marks, run **AI/rule-based** eligibility recommendations, conduct guidance sessions, and upload recommendation letters.
- **Learners** authenticate to select programmes, complete fee steps, review packages, **submit** applications, and **track** status (Assignment 5 vision).
- **Universities** publish requirements and record admission decisions in UniMatch’s orchestration layer.
- **District/DoE** access **anonymized** analytics only.

**Authoritative Assignment 5 artefacts:** [Use_Case_Specifications.md](Use_Case_Specifications.md), [TEST_CASES.md](TEST_CASES.md), [ASSIGNMENT5_REFLECTION.md](ASSIGNMENT5_REFLECTION.md).  
**System specification (v2.0, aligned):** [SPECIFICATION.md](SPECIFICATION.md).

---

## Project Overview

**Domain**: School administration, higher-education guidance, and multi-party application coordination (South African context).  
**Problem**: Fragmented tools, missed deadlines, unclear eligibility, fraud-prone fee handling, and weak visibility for schools and government.  
**Solution**: UniMatch coordinates applications end-to-end while delegating card processing to a **certified payment gateway** and preserving POPIA-oriented design for district reporting.

---

## Assignment Progress

### Assignment 3: System Specification & Architecture
- System specification (**updated to v2.0** for Assignment 5 alignment)
- C4 architecture (Context, Container, Component, Code) — see **ARCHITECTURE.md** §1.1 for extended actors
- Technical stack: React, Node.js/Express, PostgreSQL

### Assignment 4: Stakeholder & System Requirements
- Stakeholder analysis and System Requirements Document (SRD v2.0)
- Functional and non-functional requirements with traceability to tests

### Assignment 5: Use Cases & Tests
- UML-style use case diagram (Mermaid) and detailed specifications
- Functional and non-functional test cases (including payment security and performance)
- Reflection on requirements-to-use-case-to-test traceability

### Assignment 6: Agile Planning
- User stories, product backlog, and Sprint 1 plan (Scrum roles and GitHub tooling)
- Traceability from stories to requirements, use cases, and tests
- Reflection on backlog prioritisation and sprint scope

### Assignment 10: From Class Diagrams to Code
- Domain classes implemented from `CLASS_DIAGRAM.md` under `src/unimatch/`
- All six creational patterns under `creational_patterns/` with unit tests under `tests/`

### Assignment 12: Service Layer & REST API
- Service layer with business logic for learners, programmes, and applications
- FastAPI REST API with 26 endpoints across 3 entities
- OpenAPI YAML documentation with Swagger UI integration
- Comprehensive unit and integration tests (73 tests passing)

### Assignment 13: CI/CD with GitHub Actions
- Branch protection rules for main branch (requires PR reviews and passing tests)
- GitHub Actions CI/CD pipeline for automated testing
- Release artifact generation (Python wheel package)
- Automated quality control and deployment workflow

---

## Project Documents

### Assignment 3
- [System Specification – SPECIFICATION.md](SPECIFICATION.md) (v2.0)
- [Architecture – ARCHITECTURE.md](ARCHITECTURE.md) (v2.0 introduction)

### Assignment 4
- [Stakeholder Analysis – STAKEHOLDER_ANALYSIS.md](STAKEHOLDER_ANALYSIS.md)
- [System Requirements – SYSTEM_REQUIREMENTS_COMPLETE.md](SYSTEM_REQUIREMENTS_COMPLETE.md)
- [Assignment 4 Reflection – ASSIGNMENT_4_REFLECTION.md](ASSIGNMENT_4_REFLECTION.md)

### Assignment 5
- [Use Case Specifications – Use_Case_Specifications.md](Use_Case_Specifications.md)
- [Test Cases – TEST_CASES.md](TEST_CASES.md)
- [Assignment 5 Reflection – ASSIGNMENT5_REFLECTION.md](ASSIGNMENT5_REFLECTION.md)

### Assignment 6
- [Agile User Stories, Backlog & Sprint Plan – ASSIGNMENT 6 AGILE PLAN.md](ASSIGNMENT%206%20AGILE%20PLAN.md)

### Assignment 12
- [Service Layer & REST API – ASSIGNMENT_12/README.md](ASSIGNMENT_12/README.md)
- [API Documentation – ASSIGNMENT_12/docs/README.md](ASSIGNMENT_12/docs/README.md)

### Assignment 13
- [Branch Protection Rules – PROTECTION.md](PROTECTION.md)
- [CI/CD Pipeline – .github/workflows/ci.yml](.github/workflows/ci.yml)

### Supporting
- [Functional Requirements – SYSTEM_REQUIREMENTS (Functional Section).md](SYSTEM_REQUIREMENTS%20(Functional%20Section).md)
- [Non-Functional Requirements – SYSTEM_REQUIREMENTS (Non-Functional Section).md](SYSTEM_REQUIREMENTS%20(Non-Functional%20Section).md)

---

## Planned Tech Stack

- **Frontends**: React (TypeScript) — staff portal, learner portal, university admissions UI (separate apps or modules as needed)
- **Backend**: Node.js with Express (RESTful API), RBAC, audit logging
- **Database**: PostgreSQL
- **Integrations**: Payment gateway (PCI scope minimized), email/SMS providers
- **Deployment**: Cloud-hosted (HTTPS everywhere)

---

- **Frontend**: React (TypeScript), responsive web dashboard
- **Backend**: Node.js with Express (RESTful API)
- **Database**: PostgreSQL (relational)
- **Notifications**: Email-based deadline reminders (conceptual; may be mocked)
- **Deployment**: Cloud-hosted (conceptual) with HTTPS access

**Traceability:** Requirement IDs in **TEST_CASES.md** map to **SYSTEM_REQUIREMENTS_COMPLETE.md** (FR1–FR15, NFR1–NFR20). **SPECIFICATION.md** v2.0 describes the same product vision as **Use_Case_Specifications.md**. Implementation may follow **Phase 1 / Phase 2** in SPECIFICATION §1.4.

## Project Board — Assignment 7

This project uses a customised **Automated Kanban** board managed through GitHub Projects.
View the live board: [UniMatch Project Board](https://github.com/users/Mabotse-Mosima/projects/6)

### Column structure

| Column | Purpose |
|---|---|
| Backlog | All issues not yet assigned to the current sprint |
| To Do | Issues committed to the current sprint, ready to start |
| In Progress | Actively being worked on |
| Blocked | Work started but waiting on an external dependency |
| In Review | Submitted deliverables pending feedback |
| Testing | Implementation complete; acceptance criteria being verified against TEST_CASES.md |
| Done | Definition of Done satisfied; issue closed and linked to sprint milestone |

### Why Automated Kanban?
Automated Kanban was selected because it auto-moves issues when opened (→ To Do) and
closed (→ Done), eliminating manual card maintenance for a solo developer playing all
three Scrum roles.

### Custom columns added
- **Blocked**: Added to make external dependencies visible. WIP limit: 2 tasks.
- **Testing**: Added to enforce the Definition of Done — coded ≠ done until tested.
  WIP limit: 3 tasks.

### Labels
Every issue is labelled with MoSCoW priority (`must-have`, `should-have`, `could-have`),
story points (`SP:2`, `SP:3`, `SP:5`, `SP:8`), and sprint (`sprint-1`, `sprint-2`, etc.).
All Sprint 1 issues are assigned to @Mabotse-Mosima.

---

## Assignment 10: Implementation (code)

**Language choice:** Python 3.10+ was used so the Assignment 9 `CLASS_DIAGRAM.md` entities and enums map cleanly to `dataclasses` and `Enum`, with a `src/` layout that matches common pytest packaging. The domain layer stays free of web-framework dependencies, which matches the documented future stack (React / Node) while still giving a verifiable object model for this coursework milestone.

**Design alignment:** Core attributes, methods, and relationships follow `CLASS_DIAGRAM.md` (composition for `LearnerProfile`–`Mark` and `Application`–`StatusHistoryEntry`, aggregation-style handling for application documents, and separate service classes as in the diagram). `DOMAIN_MODEL.md` informed a few supporting enums (for example `ProfileStatusEnum`) where the class diagram references them without re-listing every literal.

**Creational patterns (see `creational_patterns/`):**

| Pattern | Rationale (brief) |
|---|---|
| Simple Factory | `VehicleFactory` centralizes choosing `Car` / `Bike` / `Truck` from one API. |
| Factory Method | `PaymentProcessor` defers creation logic to `CreditCardProcessor` vs `PayPalProcessor`. |
| Abstract Factory | `GUIFactory` returns a family-specific `Button` (`WindowsButton` vs `MacOSButton`). |
| Builder | `PizzaBuilder` models many optional parts (`add_cheese`, `add_toppings`) with validation on `build()`. |
| Prototype | `ShapeCache` stores configured `Circle` / `Rectangle` prototypes and returns clones. |
| Singleton | `DatabaseConnection` is a process-wide single instance with a lock for thread-safe initialization. |

**Tests and coverage:** From the repository root, install dev dependencies (`pip install -r requirements.txt`) then run:

`python -m pytest --cov=unimatch --cov=creational_patterns --cov-report=term-missing`

For an HTML coverage report, add `--cov-report=html` and open `htmlcov/index.html`.

---

## Running Tests Locally

### Assignment 12 Tests (Service Layer & API)

```bash
cd ASSIGNMENT_12
python -m pip install -r requirements.txt
python -m pytest tests/ -v
```

Expected: **73 passed** (service unit tests + API integration tests).

### Assignment 10 Tests (Domain Model & Patterns)

```bash
python -m pip install -r requirements.txt
python -m pytest --cov=unimatch --cov=creational_patterns --cov-report=term-missing
```

For HTML coverage report: `python -m pytest --cov=unimatch --cov=creational_patterns --cov-report=html`

---

## CI/CD Pipeline (Assignment 13)

### How It Works

The project uses GitHub Actions for continuous integration and deployment:

1. **Trigger**: Runs on every push to any branch and pull request to `main`
2. **Test Job**: 
   - Sets up Python 3.11 environment
   - Installs dependencies from `ASSIGNMENT_12/requirements.txt`
   - Runs all tests using pytest
   - Uploads test results as artifacts
3. **Build Job** (only on main branch):
   - Builds Python wheel package
   - Uploads release artifact (retained for 30 days)

### Branch Protection Rules

The `main` branch is protected with the following rules:

- **Require pull request reviews**: At least 1 approval before merging
- **Require status checks to pass**: CI workflow must succeed
- **Disallow direct pushes**: All changes must go through PRs
- **Require branches to be up to date**: PR must be based on latest main

These rules ensure code quality and prevent buggy code from reaching the main branch.

### PR Workflow

1. Create a new branch from `main`
2. Make changes and commit
3. Push branch and create pull request
4. CI pipeline runs automatically
5. Tests must pass before merge is allowed
6. Review and approve PR
7. Merge to `main` triggers artifact generation

See [PROTECTION.md](PROTECTION.md) for detailed explanation of branch protection rules.

---

## CI/CD Screenshots

![CI/CD Pipeline - Workflow Overview](screenshot/Test%20Automation%20(1).png)

![CI/CD Pipeline - Test Results](screenshot/Test%20Automation%20(2).png)

![CI/CD Pipeline - Successful Tests](screenshot/Test%20Automation%20(3).png)

![CI/CD Pipeline - Artifact Generation](screenshot/Test%20Automation%20(4).png)

![CI/CD Pipeline - Build Artifact](screenshot/Test%20Automation%20(5).png)

![CI/CD Pipeline - Completed Workflow](screenshot/Test%20Automation%20(6).png)

![CI/CD Pipeline - Generated Artifact](screenshot/Artifact%20screenshot%20(1).png)

![CI/CD Pipeline - Artifact Details](screenshot/Artifact%20screenshot%20(2).png)
