from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    secret_key: str | None = None
    document_storage_dir: Path | None = None
    session_lifetime_seconds: int = 86400
    environment: str = "development"
    lockout_threshold: int = 5
    lockout_duration_seconds: int = 900  # 15 minutes

    @classmethod
    def from_environment(cls) -> Settings:
        database_url = os.environ.get("DATABASE_URL", "").strip() or None
        secret_key = os.environ.get("SECRET_KEY", "").strip() or None
        environment = os.environ.get("ENVIRONMENT", "development").strip().lower()
        document_storage_dir = (
            Path(value).expanduser()
            if (value := os.environ.get("DOCUMENT_STORAGE_DIR", "").strip())
            else None
        )
        lifetime = int(os.environ.get("SESSION_LIFETIME_SECONDS", "86400"))
        lockout_threshold = int(os.environ.get("LOCKOUT_THRESHOLD", "5"))
        lockout_duration_seconds = int(os.environ.get("LOCKOUT_DURATION_SECONDS", "900"))
        return cls(
            database_url=database_url,
            secret_key=secret_key,
            document_storage_dir=document_storage_dir,
            session_lifetime_seconds=lifetime,
            environment=environment,
            lockout_threshold=lockout_threshold,
            lockout_duration_seconds=lockout_duration_seconds,
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def lockout_duration(self) -> timedelta:
        return timedelta(seconds=self.lockout_duration_seconds)

    def require_secret_key(self) -> str:
        """Return the secret key or raise RuntimeError in production.
        Fails closed: production mode without a key is a configuration error.
        """
        if not self.secret_key:
            if self.is_production:
                raise RuntimeError(
                    "SECRET_KEY environment variable is required in production mode."
                )
            return "dev-insecure-key-do-not-use-in-production"
        return self.secret_key
