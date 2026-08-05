from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch

from jobinator.application.provider import OpenAIApplicationContentProvider
from jobinator.config import Settings
from jobinator.main import create_app


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


@pytest.mark.anyio
async def test_application_provider_and_model_are_selected_from_environment(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("JOBINATOR_APPLICATION_PROVIDER", "openai")
    monkeypatch.setenv("JOBINATOR_APPLICATION_MODEL", "configured-model")
    monkeypatch.setenv("JOBINATOR_OPENAI_API_KEY", "test-only-secret")
    settings = Settings()

    async with AsyncClient() as client:
        app = create_app(
            database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
            settings=settings,
            source_client=client,
        )

        assert settings.application_provider == "openai"
        assert settings.application_model == "configured-model"
        assert isinstance(
            app.state.application_generation_runtime.provider,
            OpenAIApplicationContentProvider,
        )
        assert app.state.application_generation_runtime.provider.model == "configured-model"
