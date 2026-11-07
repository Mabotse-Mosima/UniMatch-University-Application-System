import threading

import pytest

from creational_patterns.singleton import DatabaseConnection


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    DatabaseConnection.reset_for_testing()
    yield
    DatabaseConnection.reset_for_testing()


def test_database_connection_singleton_same_instance() -> None:
    a = DatabaseConnection.instance("dsn-a")
    b = DatabaseConnection.instance("dsn-b")
    assert a is b


def test_direct_constructor_always_raises() -> None:
    with pytest.raises(RuntimeError):
        DatabaseConnection()


def test_direct_instantiation_after_singleton_raises() -> None:
    DatabaseConnection.instance("main")
    with pytest.raises(RuntimeError):
        DatabaseConnection()


def test_singleton_thread_safety() -> None:
    instances: list[DatabaseConnection] = []

    def worker() -> None:
        instances.append(DatabaseConnection.instance("thread"))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(x) for x in instances}) == 1
