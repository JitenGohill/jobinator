from __future__ import annotations

from dataclasses import dataclass

import httpx

from jobinator.application.provider import (
    ApplicationContentProvider,
    DeterministicApplicationContentProvider,
    OpenAIApplicationContentProvider,
)
from jobinator.config import Settings


class ApplicationProviderConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ApplicationGenerationRuntime:
    provider: ApplicationContentProvider
    prompt: str
    prompt_version: str


def create_application_provider(
    settings: Settings,
    client: httpx.AsyncClient,
) -> ApplicationContentProvider:
    if settings.application_provider == "fake":
        return DeterministicApplicationContentProvider()
    if settings.openai_api_key is None:
        raise ApplicationProviderConfigurationError(
            "JOBINATOR_OPENAI_API_KEY is required when the application provider is openai."
        )
    return OpenAIApplicationContentProvider(
        client=client,
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.application_model,
    )
