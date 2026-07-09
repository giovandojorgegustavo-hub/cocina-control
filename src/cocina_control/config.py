from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COCINA_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"


settings = Settings()
