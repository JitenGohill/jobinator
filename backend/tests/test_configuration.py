from pydantic import SecretStr
from pytest import MonkeyPatch

from jobinator.config import Settings


def test_api_key_is_loaded_from_environment_and_masked(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JOBINATOR_OPENAI_API_KEY", "test-only-secret")

    settings = Settings()

    assert isinstance(settings.openai_api_key, SecretStr)
    assert settings.openai_api_key.get_secret_value() == "test-only-secret"
    assert "test-only-secret" not in repr(settings)
