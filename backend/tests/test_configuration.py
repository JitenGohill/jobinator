from pydantic import SecretStr
from pytest import MonkeyPatch

from jobinator.config import Settings


def test_api_key_is_loaded_from_environment_and_masked(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JOBINATOR_OPENAI_API_KEY", "test-only-secret")

    settings = Settings()

    assert isinstance(settings.openai_api_key, SecretStr)
    assert settings.openai_api_key.get_secret_value() == "test-only-secret"
    assert "test-only-secret" not in repr(settings)


def test_reachable_posting_urls_are_loaded_from_environment(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "JOBINATOR_CAREER_PAGE_URLS",
        '["https://careers.acme.example/jobs/123"]',
    )
    monkeypatch.setenv(
        "JOBINATOR_WORKDAY_POSTING_URLS",
        '["https://acme.wd5.myworkdayjobs.com/en-US/jobs/job/Chicago/role_123"]',
    )

    settings = Settings()

    assert settings.career_page_urls == [
        "https://careers.acme.example/jobs/123",
    ]
    assert settings.workday_posting_urls == [
        "https://acme.wd5.myworkdayjobs.com/en-US/jobs/job/Chicago/role_123",
    ]
