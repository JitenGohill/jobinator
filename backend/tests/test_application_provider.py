from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from jobinator.application.models import (
    ApplicationPacketRequest,
    CanonicalFact,
    FactId,
    GeneratedApplicationPlan,
    MatchedProfileContext,
)
from jobinator.application.provider import (
    ApplicationGenerationInput,
    OpenAIApplicationContentProvider,
)
from jobinator.discovery.models import ScoredOpportunity
from jobinator.profile.models import CanonicalProfile


def generation_input(load_fixture: Callable[[str], Any]) -> ApplicationGenerationInput:
    posting = load_fixture("candidate_queue.json")["jobs"][0]
    snapshot = {
        **posting,
        "id": 1,
        "fetched_at": datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
        "raw_posting": posting,
    }
    return ApplicationGenerationInput(
        profile=CanonicalProfile.model_validate(load_fixture("profile.json")),
        opportunity=ScoredOpportunity.model_validate(
            {
                **snapshot,
                "preferred_apply_url": posting["canonical_url"],
                "snapshots": [snapshot],
                "screening": {"lane": "eligible", "reasons": ["Fixture eligible."]},
                "score": {
                    "total": 100,
                    "weights": {"fixture": 1},
                    "eligibility": {"value": 100, "explanation": "Eligible."},
                    "role_fit": {"value": 100, "explanation": "Role fit."},
                    "skill_overlap": {"value": 100, "explanation": "Skills match."},
                    "company_quality": {"value": 100, "explanation": "Official."},
                    "application_effort": {"value": 100, "explanation": "Low."},
                },
            }
        ),
        matched_context=MatchedProfileContext(
            skills=["FastAPI", "Python"],
            projects=["Queue Lens"],
            work_experience=[],
        ),
        missing_requirements=[],
        request=ApplicationPacketRequest(cover_letter_requested=True),
        cover_letter_useful=True,
        available_facts=(
            CanonicalFact(
                id=FactId("profile.base_cv"),
                kind="base_cv",
                text="Junior software engineer focused on reliable backend systems.",
            ),
            CanonicalFact(
                id=FactId("job.title"),
                kind="job",
                text="Junior Backend Engineer",
            ),
        ),
    )


@pytest.mark.anyio
async def test_openai_provider_uses_responses_structured_output_contract(
    load_fixture: Callable[[str], Any],
) -> None:
    captured_request: httpx.Request | None = None

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        content = {
            "selected_fact_ids": ["profile.base_cv"],
            "cover_letter_fact_ids": [],
            "screening_answers": [],
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(content)}],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAIApplicationContentProvider(
            client=client,
            api_key="test-key",
            model="test-model",
        )
        generated = await provider.generate(
            generation_input(load_fixture),
            "versioned prompt",
        )

    assert isinstance(generated, GeneratedApplicationPlan)
    assert generated.selected_fact_ids == [FactId("profile.base_cv")]
    assert captured_request is not None
    assert captured_request.url == "https://api.openai.com/v1/responses"
    assert captured_request.headers["authorization"] == "Bearer test-key"
    body = json.loads(captured_request.content)
    assert body["model"] == "test-model"
    assert body["instructions"] == "versioned prompt"
    assert body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["name"] == "application_packet_plan"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    supplied_input = json.loads(body["input"])
    assert supplied_input["profile"]["projects"][0]["name"] == "Queue Lens"
    assert supplied_input["opportunity"]["title"] == "Junior Backend Engineer"
    assert supplied_input["cover_letter_useful"] is True
    assert supplied_input["available_facts"][1]["text"] == "Junior Backend Engineer"
