import pytest

from cocina_control.config import Settings

_DUMMY_DB_URL = "postgresql+psycopg://user:pass@localhost/db"
_VALID_SECRET = "test-secret-not-for-prod-min-32-chars-1234"


def test_default_settings() -> None:
    s = Settings(database_url=_DUMMY_DB_URL, jwt_secret=_VALID_SECRET)

    assert s.app_env == "dev"
    assert s.log_level == "INFO"
    assert s.database_url == _DUMMY_DB_URL


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCINA_APP_ENV", "production")
    monkeypatch.setenv("COCINA_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("COCINA_DATABASE_URL", _DUMMY_DB_URL)
    monkeypatch.setenv("COCINA_JWT_SECRET", _VALID_SECRET)

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


def test_config_jwt_secret_too_short_rejected() -> None:
    """Settings must raise ValidationError when jwt_secret is shorter than 32 chars."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="jwt_secret must be at least 32 characters"):
        Settings(database_url=_DUMMY_DB_URL, jwt_secret="short")


def test_config_jwt_secret_exactly_32_chars_accepted() -> None:
    """A jwt_secret of exactly 32 characters must be accepted."""
    secret_32 = "a" * 32
    s = Settings(database_url=_DUMMY_DB_URL, jwt_secret=secret_32)
    assert s.jwt_secret == secret_32


def test_config_jwt_secret_required() -> None:
    """Settings must raise ValidationError when jwt_secret is missing entirely."""
    import os

    from pydantic import ValidationError

    env_backup = os.environ.pop("COCINA_JWT_SECRET", None)
    try:
        with pytest.raises(ValidationError, match="jwt_secret"):
            Settings(database_url=_DUMMY_DB_URL)
    finally:
        if env_backup is not None:
            os.environ["COCINA_JWT_SECRET"] = env_backup


def test_business_timezone_default_is_lima() -> None:
    """Default business_timezone must be America/Lima."""
    s = Settings(database_url=_DUMMY_DB_URL, jwt_secret=_VALID_SECRET)
    assert s.business_timezone == "America/Lima"


def test_business_timezone_valid_iana_accepted() -> None:
    """Any valid IANA timezone string must be accepted."""
    s = Settings(
        database_url=_DUMMY_DB_URL,
        jwt_secret=_VALID_SECRET,
        business_timezone="America/Buenos_Aires",
    )
    assert s.business_timezone == "America/Buenos_Aires"


def test_business_timezone_invalid_rejected() -> None:
    """An invalid IANA timezone name must raise ValidationError with a clear message."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="valid IANA timezone name"):
        Settings(
            database_url=_DUMMY_DB_URL,
            jwt_secret=_VALID_SECRET,
            business_timezone="Not/ATimezone",
        )


def test_business_timezone_empty_string_rejected() -> None:
    """An empty string is not a valid timezone (ZoneInfo raises ValueError)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="valid IANA timezone name"):
        Settings(
            database_url=_DUMMY_DB_URL,
            jwt_secret=_VALID_SECRET,
            business_timezone="",
        )


def test_business_timezone_slash_only_rejected() -> None:
    """A slash-only value must be rejected (ZoneInfo raises ValueError, not KeyError)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="valid IANA timezone name"):
        Settings(
            database_url=_DUMMY_DB_URL,
            jwt_secret=_VALID_SECRET,
            business_timezone="/",
        )


def test_business_timezone_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """business_timezone can be set end-to-end via COCINA_BUSINESS_TIMEZONE."""
    monkeypatch.setenv("COCINA_DATABASE_URL", _DUMMY_DB_URL)
    monkeypatch.setenv("COCINA_JWT_SECRET", _VALID_SECRET)
    monkeypatch.setenv("COCINA_BUSINESS_TIMEZONE", "America/Buenos_Aires")
    s = Settings()
    assert s.business_timezone == "America/Buenos_Aires"
