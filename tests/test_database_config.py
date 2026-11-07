import pytest

from unimatch.config import Settings
from unimatch.api import create_app


def test_database_url_is_optional(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings.from_environment().database_url is None


def test_database_url_is_read_from_environment(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test-user:test-password@localhost/unimatch_dev",
    )

    assert Settings.from_environment().database_url is not None


def test_create_app_without_database_url_does_not_create_engine(monkeypatch):
    def fail_if_engine_is_created(_database_url):
        raise AssertionError("in-memory app construction must not create a database engine")

    monkeypatch.setattr(
        "unimatch.api.create_session_factory",
        fail_if_engine_is_created,
    )

    app = create_app(database_url=None)

    assert app.title == "UniMatch API"


def test_production_startup_fails_without_database_url(monkeypatch):
    """Production mode must refuse to start without DATABASE_URL (no in-memory fallback)."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a-sufficiently-long-production-secret-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required in production mode"):
        create_app(database_url=None)


def test_lockout_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("LOCKOUT_THRESHOLD", "3")
    monkeypatch.setenv("LOCKOUT_DURATION_SECONDS", "300")
    s = Settings.from_environment()
    assert s.lockout_threshold == 3
    assert s.lockout_duration_seconds == 300
    from datetime import timedelta
    assert s.lockout_duration == timedelta(seconds=300)


def test_lockout_settings_have_secure_defaults():
    s = Settings(lockout_threshold=5, lockout_duration_seconds=900)
    assert s.lockout_threshold == 5
    assert s.lockout_duration_seconds == 900
