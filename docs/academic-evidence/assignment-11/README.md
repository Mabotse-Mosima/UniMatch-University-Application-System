# UniMatch — Assignment 11: Repository Layer

> **81 tests · 0 failures · 0 errors** (run `python -m pytest tests/ -q` from `ASSIGNMENT_11/`)

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Design Decisions](#design-decisions)
4. [Repository Interfaces](#repository-interfaces)
5. [In-Memory Implementations](#in-memory-implementations)
6. [Abstraction Mechanism — Factory Pattern](#abstraction-mechanism--factory-pattern)
7. [Dependency Injection — Application Services](#dependency-injection--application-services)
8. [Future-Proofing — Stubs](#future-proofing--stubs)
9. [Backlog / Issues](#backlog--issues)
10. [How to Run](#how-to-run)
11. [Updated Class Diagram](#updated-class-diagram)

---

## Overview

Assignment 11 adds a **persistence repository layer** on top of the
UniMatch domain model from Assignment 10.  The layer:

- Abstracts all storage details behind Python ABCs so the rest of the
  application never touches storage directly.
- Provides full CRUD (`save / find_by_id / find_all / delete`) plus
  domain-specific queries for every entity.
- Ships with an in-memory HashMap implementation (fast, zero-dependency
  unit tests) and stubs for filesystem (JSON), database, and **HTTP/REST**
  (`HttpApplicationRepository`) backends.
- Uses a **Factory Pattern** to select the storage backend at runtime
  from a single string key.

---

## Project Structure

```
ASSIGNMENT_11/
│
├── unimatch/                        # Domain model (Assignment 10, unchanged)
│   ├── entities.py
│   ├── enums.py
│   ├── services.py
│   ├── status_history.py
│   └── __init__.py
│
├── repositories/                    # ← NEW (Assignment 11)
│   ├── __init__.py                  # Generic Repository[T,ID] + 9 entity interfaces
│   ├── inmemory/
│   │   └── __init__.py             # HashMap-backed implementations (9 classes)
│   └── stubs/
│       └── __init__.py             # FileSystem, Database & HTTP stubs (5 classes)
│
├── factories/                       # ← NEW (Assignment 11)
│   └── __init__.py                 # RepositoryFactory — selects backend by key
│
├── application_services.py         # ← DI: services take repository interfaces
│
├── tests/
│   ├── __init__.py
│   ├── test_repositories.py        # repository + factory unit tests
│   └── test_application_services.py  # DI wiring tests
│
├── BACKLOG.md                       # GitHub-issue checklist (assignment NOTE)
├── conftest.py                      # sys.path setup for pytest
└── README.md
```

---

## Design Decisions

### Generic `Repository[T, ID]`

```python
class Repository(ABC, Generic[T, ID]):
    @abstractmethod
    def save(self, entity: T) -> None: ...
    @abstractmethod
    def find_by_id(self, entity_id: ID) -> Optional[T]: ...
    @abstractmethod
    def find_all(self) -> List[T]: ...
    @abstractmethod
    def delete(self, entity_id: ID) -> None: ...
```

**Why generics?**  Without generics every entity would need its own
four-method CRUD definition, producing duplicate boilerplate across 9
entity types.  A single parameterised base keeps the contract in one
place and lets type checkers verify that, e.g., an
`ApplicationRepository` can only `save` an `Application`.

### `save` as upsert

`save` performs a create-or-update.  This matches the behaviour of
`HashMap.put` (Java), Python `dict.__setitem__`, and SQL `UPSERT`, and
simplifies calling code — the caller never needs to check whether an
entity already exists before persisting it.

### Idempotent `delete`

`delete` silently succeeds when the key is absent.  This prevents
defensive `if repo.find_by_id(id) is not None: repo.delete(id)` guards
throughout the codebase.

---

## Repository Interfaces

File: `repositories/__init__.py`

| Interface | Entity | Extra domain queries |
|---|---|---|
| `UserAccountRepository` | `UserAccount` | `find_by_email`, `find_by_role` |
| `LearnerProfileRepository` | `LearnerProfile` | `find_by_counselor`, `find_by_school` |
| `UniversityProgrammeRepository` | `UniversityProgramme` | `find_by_university`, `find_published` |
| `ApplicationRepository` | `Application` | `find_by_learner`, `find_by_programme`, `find_by_status` |
| `DocumentRepository` | `Document` | `find_by_learner`, `find_by_application` |
| `MarkRepository` | `Mark` | `find_by_learner` |
| `PaymentTransactionRepository` | `PaymentTransaction` | `find_by_application` |
| `NotificationRepository` | `Notification` | `find_by_recipient`, `find_unread` |
| `AuditLogRepository` | `AuditLogEntry` | `find_by_actor`, `find_by_target` |

All 9 interfaces extend the generic `Repository[T, UUID]` base.

---

## In-Memory Implementations

File: `repositories/inmemory/__init__.py`

Each class stores entities in a plain `dict[UUID, Entity]` — the Python
equivalent of Java's `HashMap<UUID, Entity>`:

```python
class InMemoryApplicationRepository(ApplicationRepository):
    def __init__(self) -> None:
        self._store: dict[UUID, Application] = {}   # ← HashMap storage

    def save(self, entity: Application) -> None:
        self._store[entity.application_id] = entity  # upsert

    def find_by_id(self, entity_id: UUID) -> Optional[Application]:
        return self._store.get(entity_id)            # None if absent

    def find_all(self) -> List[Application]:
        return list(self._store.values())

    def delete(self, entity_id: UUID) -> None:
        self._store.pop(entity_id, None)             # idempotent

    def find_by_learner(self, learner_id: UUID) -> List[Application]:
        return [a for a in self._store.values() if a.learner_id == learner_id]
    # ... etc.
```

Nine classes follow this exact pattern, one per entity.

---

## Abstraction Mechanism — Factory Pattern

File: `factories/__init__.py`

### Why Factory over Dependency Injection?

| Criterion | Factory Pattern ✔ | DI Container |
|---|---|---|
| External dependencies | None | Requires a DI library |
| Explicit configuration | Single call, readable string key | Wiring DSL hidden in container |
| Consistency with Assignment 10 | Extends existing `SimpleFactory` / `FactoryMethod` patterns | New idiom |
| Extensibility | Add one branch per new backend | Register binding in container |

The Factory Pattern was chosen because it requires no additional
packages, is immediately readable by any Python developer, and follows
the creational-patterns idiom already established in Assignment 10.

### Usage

```python
from factories import RepositoryFactory

# In-memory (default) — for unit tests and local development
repo = RepositoryFactory.create_application_repo("MEMORY")

# Filesystem JSON — when file_path is ready
repo = RepositoryFactory.create_application_repo("FILE", file_path="data/apps.json")

# SQL/NoSQL database — when driver is installed
repo = RepositoryFactory.create_application_repo("DATABASE", dsn="postgresql://...")

# Services receive the interface type — completely unaware of the backend
service = ApplicationService(repo)
```

Swapping from in-memory to a real database requires **changing exactly
one string** at the call site.  No service or test code changes.

---

## Dependency Injection — Application Services

The assignment allows **either** a Factory **or** DI; this project uses **both**:

| Concern | Pattern |
|--------|---------|
| **Choosing** the concrete repository (`InMemory…`, `FileSystem…`, …) | **Factory** — `RepositoryFactory.create_*` |
| **Using** a repository inside business-facing code | **DI** — constructor parameters typed as the interface |

File: `application_services.py`

- `ApplicationService` holds an `ApplicationRepository` (interface type only).
- `UserAccountService` holds a `UserAccountRepository`.

Composition at the entrypoint (tests, CLI, future `main.py`):

```python
from factories import RepositoryFactory
from application_services import ApplicationService

repo = RepositoryFactory.create_application_repo("MEMORY")
service = ApplicationService(applications=repo)
```

The service never imports `InMemoryApplicationRepository`; swapping backends means changing the **factory call**, not the service class.  Unit tests in `tests/test_application_services.py` assert this wiring.

---

## Backlog / Issues

Per the assignment NOTE, work is tracked as **issues**.  See **`BACKLOG.md`** for suggested GitHub issue titles (A11-1 … A11-11) you can paste when creating issues, plus a submission checklist.

---

## Future-Proofing — Stubs

File: `repositories/stubs/__init__.py`

Backends are stubbed for `UserAccount` and `Application` (filesystem +
database), plus **`HttpApplicationRepository`** for a future external
REST API.  Stubs compile, can be instantiated, and raise
`NotImplementedError` where a driver, serialiser, or HTTP client is not
yet wired.  Add a `RepositoryFactory` branch when you implement a new
backend.

### Filesystem (JSON) stub

```python
class FileSystemUserAccountRepository(UserAccountRepository):
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    def save(self, entity: UserAccount) -> None:
        data = self._load()
        data[str(entity.user_id)] = vars(entity)   # TODO: proper serialiser
        self._dump(data)

    def find_by_id(self, entity_id: UUID) -> Optional[UserAccount]:
        raise NotImplementedError("Deserialisation not yet implemented")
    # ...
```

**To complete:** replace `vars(entity)` with a proper `to_dict` /
`from_dict` that handles `UUID`, `datetime`, `Enum`, and `Decimal`
types.

### Database stub

```python
class DatabaseUserAccountRepository(UserAccountRepository):
    def __init__(self, connection_string: str) -> None:
        self._connection_string = connection_string
        # TODO: initialise SQLAlchemy engine / motor client here

    def save(self, entity: UserAccount) -> None:
        raise NotImplementedError("Database backend not yet connected")
    # ...
```

**To complete:**
1. `pip install sqlalchemy pymysql` (or `motor` for MongoDB).
2. Map `UserAccount` to an ORM model.
3. Replace `raise NotImplementedError` with driver calls.

---

## How to Run

```bash
# Install test dependency
pip install pytest

# From the project root
cd ASSIGNMENT_11
python -m pytest tests/ -v
```

Expected output:
```
81 passed in …
```

---

## Updated Class Diagram

The **authoritative Mermaid class diagram** for Assignment 11 (repository interfaces, in-memory and stub implementations, factory, and DI services) is **§4** in the repo root file [`CLASS_DIAGRAM.md`](../CLASS_DIAGRAM.md).  
Below is the same structure as a quick **ASCII** reference.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Repository[T, ID]  (ABC, Generic)                 │
│  + save(entity: T) → None                                            │
│  + find_by_id(id: ID) → Optional[T]                                  │
│  + find_all() → List[T]                                              │
│  + delete(id: ID) → None                                             │
└──────────────┬───────────────────────────────────────────────────────┘
               │ extends (9 entity-specific interfaces)
    ┌──────────┴────────────┬──────────────────────────────────┐
    │                       │                                  │
UserAccountRepository  ApplicationRepository  ...7 more interfaces...
+ find_by_email()      + find_by_learner()
+ find_by_role()       + find_by_programme()
                       + find_by_status()
    │                       │
    │ implements             │ implements
    ▼                       ▼
InMemoryUserAccount    InMemoryApplication   (+ 7 more InMemory classes)
Repository             Repository
_store: dict           _store: dict

    │                       │
    │ implements (stub)      │ implements (stub)
    ▼                       ▼
FileSystemUserAccount  FileSystemApplication  DatabaseUserAccount
Repository             Repository             Repository
DatabaseApplication    HttpApplication
Repository             Repository

────────────────────────────────────────────────────────────────────────

RepositoryFactory
+ create_user_repo(storage_type) → UserAccountRepository
+ create_application_repo(storage_type) → ApplicationRepository
+ create_programme_repo(storage_type) → UniversityProgrammeRepository
+ create_learner_profile_repo(storage_type) → LearnerProfileRepository
+ create_document_repo(storage_type) → DocumentRepository
+ create_mark_repo(storage_type) → MarkRepository
+ create_payment_repo(storage_type) → PaymentTransactionRepository
+ create_notification_repo(storage_type) → NotificationRepository
+ create_audit_log_repo(storage_type) → AuditLogRepository

ApplicationService(applications: ApplicationRepository)
+ save_application / get_application / list_for_learner / …

UserAccountService(accounts: UserAccountRepository)
+ save_account / find_by_email / list_by_role / …
```
