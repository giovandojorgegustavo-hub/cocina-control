from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COCINA_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 8  # 8-hour default matches a full work shift
    jwt_algorithm: str = "HS256"


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
