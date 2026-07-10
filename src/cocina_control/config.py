from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COCINA_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 8  # 8-hour default matches a full work shift
    jwt_algorithm: str = "HS256"

    # Photo storage root — override with COCINA_PHOTOS_ROOT in production.
    # In production this should be an absolute path: /var/lib/cocina-control/photos
    photos_root: Path = Path("./var/lib/cocina-control/photos")

    # Business timezone — used for all calendar-day calculations (correction windows,
    # dashboard date filters, etc.). Override with COCINA_BUSINESS_TIMEZONE in production.
    # The kitchen operates in Peru → America/Lima (UTC-5, no DST).
    business_timezone: str = "America/Lima"

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "jwt_secret must be at least 32 characters "
                "(recommended: 64). "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @field_validator("business_timezone")
    @classmethod
    def _business_timezone_valid(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError, ValueError):
            # ValueError covers "" and "/" and other malformed paths.
            raise ValueError(
                f"business_timezone must be a valid IANA timezone name, e.g. America/Lima. "
                f"Got: {v!r}"
            )
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the application settings singleton.

    Instantiated on first call so that importing this module never fails
    when COCINA_DATABASE_URL is absent (e.g. during test collection).
    The application raises a clear ValidationError at startup if the
    variable is missing.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
