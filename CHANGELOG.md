# Changelog

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
