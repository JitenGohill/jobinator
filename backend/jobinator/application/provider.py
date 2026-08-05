from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from jobinator.application.models import (
    ApplicationPacketRequest,
    CanonicalFact,
    GeneratedApplicationPlan,
    MatchedProfileContext,
    ScreeningAnswerPlan,
)
from jobinator.discovery.models import ScoredOpportunity
from jobinator.profile.models import CanonicalProfile


@dataclass(frozen=True)
class ApplicationGenerationInput:
    profile: CanonicalProfile
    opportunity: ScoredOpportunity
    matched_context: MatchedProfileContext
    missing_requirements: list[str]
    request: ApplicationPacketRequest
    cover_letter_useful: bool
    available_facts: tuple[CanonicalFact, ...]


class ApplicationContentProvider(Protocol):
    name: str
    model: str

    async def generate(
        self,
        generation_input: ApplicationGenerationInput,
        prompt: str,
    ) -> GeneratedApplicationPlan: ...


class DeterministicApplicationContentProvider:
    name = "fake"
    model = "deterministic-v1"

    async def generate(
        self,
        generation_input: ApplicationGenerationInput,
        prompt: str,
    ) -> GeneratedApplicationPlan:
        del prompt
        context = generation_input.matched_context
        selected_fact_ids = [
            fact.id
            for fact in generation_input.available_facts
            if fact.kind == "base_cv"
            or (
                fact.group in context.projects
                and fact.kind
                in {"project_name", "project_summary", "project_highlight"}
            )
        ]
        cover_letter_fact_ids = []
        if (
            generation_input.request.cover_letter_requested
            or generation_input.cover_letter_useful
        ):
            style_fact = next(
                (
                    fact
                    for fact in generation_input.available_facts
                    if fact.kind == "writing_sample"
                ),
                next(
                    fact
                    for fact in generation_input.available_facts
                    if fact.kind == "base_cv"
                ),
            )
            cover_letter_fact_ids = [style_fact.id]
        answer_plans = [
            ScreeningAnswerPlan(question_index=index, fact_ids=[])
            for index, _ in enumerate(generation_input.request.screening_questions)
        ]
        return GeneratedApplicationPlan(
            selected_fact_ids=selected_fact_ids,
            cover_letter_fact_ids=cover_letter_fact_ids,
            screening_answers=answer_plans,
        )


class OpenAIApplicationContentProvider:
    name = "openai"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self.model = model

    async def generate(
        self,
        generation_input: ApplicationGenerationInput,
        prompt: str,
    ) -> GeneratedApplicationPlan:
        response = await self._client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "instructions": prompt,
                "input": json.dumps(_generation_input_payload(generation_input)),
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "application_packet_plan",
                        "strict": True,
                        "schema": GeneratedApplicationPlan.model_json_schema(),
                    }
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return GeneratedApplicationPlan.model_validate_json(part["text"])
        raise ValueError("OpenAI response did not contain structured application content.")


def _generation_input_payload(
    generation_input: ApplicationGenerationInput,
) -> dict[str, object]:
    return {
        "profile": generation_input.profile.model_dump(mode="json"),
        "opportunity": generation_input.opportunity.model_dump(mode="json"),
        "matched_context": generation_input.matched_context.model_dump(mode="json"),
        "missing_requirements": generation_input.missing_requirements,
        "request": generation_input.request.model_dump(mode="json"),
        "cover_letter_useful": generation_input.cover_letter_useful,
        "available_facts": [
            fact.model_dump(mode="json") for fact in generation_input.available_facts
        ],
    }
