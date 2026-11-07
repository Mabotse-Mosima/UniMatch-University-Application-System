from __future__ import annotations

import threading
from typing import ClassVar


class DatabaseConnection:
    """Process-wide singleton simulating a single DB connection handle."""

    _instance: ClassVar[DatabaseConnection | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls, *_args: object, **_kwargs: object) -> DatabaseConnection:
        raise RuntimeError("Use DatabaseConnection.instance()")

    def __init__(self, dsn: str = "") -> None:
        self.dsn = dsn
        self.connected = bool(dsn)

    @classmethod
    def instance(cls, dsn: str = "default") -> DatabaseConnection:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = object.__new__(cls)
                    obj.__init__(dsn)
                    cls._instance = obj
        return cls._instance

    @classmethod
    def reset_for_testing(cls) -> None:
        with cls._lock:
            cls._instance = None
