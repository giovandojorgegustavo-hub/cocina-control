import pytest

from cocina_control.config import Settings

_DUMMY_DB_URL = "postgresql+psycopg://user:pass@localhost/db"


def test_default_settings() -> None:
    s = Settings(database_url=_DUMMY_DB_URL)

    assert s.app_env == "dev"
    assert s.log_level == "INFO"
    assert s.database_url == _DUMMY_DB_URL


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCINA_APP_ENV", "production")
    monkeypatch.setenv("COCINA_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("COCINA_DATABASE_URL", _DUMMY_DB_URL)

    s = Settings()

    assert s.app_env == "production"
    assert s.log_level == "WARNING"
    assert s.database_url == _DUMMY_DB_URL


def test_database_url_required() -> None:
    """Settings must raise ValidationError when database_url is missing."""
    import os

    from pydantic import ValidationError

    # Remove the env var if it happens to be set.
    env_backup = os.environ.pop("COCINA_DATABASE_URL", None)
    try:
        with pytest.raises(ValidationError, match="database_url"):
            Settings()
    finally:
        if env_backup is not None:
            os.environ["COCINA_DATABASE_URL"] = env_backup
