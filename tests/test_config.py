import pytest

from cocina_control.config import Settings


def test_default_settings() -> None:
    s = Settings()

    assert s.app_env == "dev"
    assert s.log_level == "INFO"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCINA_APP_ENV", "production")
    monkeypatch.setenv("COCINA_LOG_LEVEL", "WARNING")

    s = Settings()

    assert s.app_env == "production"
    assert s.log_level == "WARNING"
