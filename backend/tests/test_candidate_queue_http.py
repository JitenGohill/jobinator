from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from jobinator.database import create_session_factory
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.module import DiscoveryModule
from jobinator.main import create_app


def load_fixture(name: str) -> Any:
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


class FixtureAdapter:
    platform = "fixture"

    def __init__(self, postings: list[dict[str, Any]]) -> None:
        self._postings = postings

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        return [
            JobSnapshot.model_validate(
                {
                    **posting,
                    "fetched_at": fetched_at,
                    "raw_posting": posting,
                }
            )
            for posting in self._postings
        ]


def configure_fixture_discovery(
    app: FastAPI,
    postings: list[dict[str, Any]],
    clock: Callable[[], datetime],
) -> None:
    sessions: sessionmaker[Session] = create_session_factory(app.state.database_engine)
    app.state.discovery_module = DiscoveryModule(
        sessions=sessions,
        sources=[
            SourceConfiguration(
                platform="fixture",
                identifier="candidate-queue",
                company="Fixture",
            )
        ],
        adapters={"fixture": FixtureAdapter(postings)},
        clock=clock,
    )


@pytest.mark.anyio
async def test_daily_queue_scores_ranks_caps_stretch_and_reports_shortfall(
    tmp_path: Path,
) -> None:
    profile = load_fixture("profile.json")
    postings = load_fixture("candidate_queue.json")["jobs"]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        postings,
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        profile_response = await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        ingestion_response = await client.post("/api/discovery/ingest")
        queue_response = await client.get("/api/discovery/queue")

    assert profile_response.status_code == 200
    assert ingestion_response.status_code == 200
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert queue["target"] == {"minimum": 25, "maximum": 30}
    assert queue["criteria"] == {"minimum_score": 60, "include_maybe": False}
    assert queue["shortfall"] == 21
    assert queue["summary"] == (
        "4 candidates meet the current criteria; 21 fewer than the 25-candidate target."
    )
    assert [candidate["title"] for candidate in queue["candidates"]] == [
        "Junior Backend Engineer",
        "Junior Internal Tools Engineer",
        "Platform Engineer",
        "Junior Full-Stack Engineer",
    ]
    assert sum(
        candidate["screening"]["lane"] == "stretch"
        for candidate in queue["candidates"]
    ) == 1
    assert [candidate["title"] for candidate in queue["not_queued"]] == [
        "AI Applications Engineer",
        "Junior Backend Engineer",
        "Junior AI Engineer",
    ]
    assert all(
        candidate["screening"]["lane"] != "rejected"
        for candidate in [*queue["candidates"], *queue["not_queued"]]
    )

    top_score = queue["candidates"][0]["score"]
    assert top_score["weights"] == {
        "eligibility": 0.3,
        "role_fit": 0.25,
        "skill_overlap": 0.2,
        "company_quality": 0.15,
        "application_effort": 0.1,
    }
    assert top_score["total"] == 100
    assert {
        dimension: top_score[dimension]["value"]
        for dimension in (
            "eligibility",
            "role_fit",
            "skill_overlap",
            "company_quality",
            "application_effort",
        )
    } == {
        "eligibility": 100,
        "role_fit": 100,
        "skill_overlap": 100,
        "company_quality": 100,
        "application_effort": 100,
    }
    assert top_score["eligibility"]["explanation"] == (
        "Eligible based on screening: Target role type: backend engineering; "
        "Target location: New York; Junior-friendly experience requirement: 1 year."
    )
    assert top_score["role_fit"]["explanation"] == (
        "Strong backend fit with the canonical profile's backend focus."
    )
    assert top_score["skill_overlap"]["explanation"] == (
        "Matches 2 of 2 detected technologies: FastAPI and Python."
    )
    assert top_score["company_quality"]["explanation"] == (
        "Official company listing from Alpha Systems."
    )
    assert top_score["application_effort"]["explanation"] == (
        "Low application effort: official route and 2 detected requirements."
    )
    non_uniform_score = next(
        candidate["score"]
        for candidate in queue["candidates"]
        if candidate["title"] == "Platform Engineer"
    )
    assert {
        dimension: non_uniform_score[dimension]["value"]
        for dimension in (
            "eligibility",
            "role_fit",
            "skill_overlap",
            "company_quality",
            "application_effort",
        )
    } == {
        "eligibility": 75,
        "role_fit": 85,
        "skill_overlap": 100,
        "company_quality": 85,
        "application_effort": 90,
    }
    assert non_uniform_score["total"] == 85.5
    assert {lever["id"] for lever in queue["expansion_levers"]} == {
        "include_maybe",
        "minimum_score",
    }


@pytest.mark.anyio
async def test_queue_expansion_is_explicit_and_user_controlled(tmp_path: Path) -> None:
    profile = load_fixture("profile.json")
    postings = load_fixture("candidate_queue.json")["jobs"]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        postings,
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        default_response = await client.get("/api/discovery/queue")
        expanded_response = await client.get(
            "/api/discovery/queue",
            params={"include_maybe": "true", "minimum_score": 50},
        )

    default_queue = default_response.json()
    expanded_queue = expanded_response.json()
    assert default_queue["criteria"] == {
        "minimum_score": 60,
        "include_maybe": False,
    }
    assert expanded_queue["criteria"] == {
        "minimum_score": 50,
        "include_maybe": True,
    }
    assert len(expanded_queue["candidates"]) > len(default_queue["candidates"])
    assert not any(
        candidate["company"] == "Zeta Labs"
        for candidate in default_queue["candidates"]
    )
    assert any(
        candidate["company"] == "Zeta Labs"
        for candidate in expanded_queue["candidates"]
    )
    assert any(
        candidate["screening"]["lane"] == "maybe"
        for candidate in expanded_queue["candidates"]
    )


@pytest.mark.anyio
async def test_queue_requires_a_canonical_profile(tmp_path: Path) -> None:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/discovery/queue")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Save the canonical profile before generating a candidate queue."
    }


@pytest.mark.anyio
async def test_skill_overlap_uses_profile_technologies_beyond_builtin_names(
    tmp_path: Path,
) -> None:
    profile = load_fixture("profile.json")
    profile["skills"].append({"name": "AWS", "proficiency": "intermediate"})
    postings = [
        {
            **load_fixture("candidate_queue.json")["jobs"][0],
            "detected_requirements": ["AWS", "Kubernetes", "PostgreSQL"],
            "description_text": (
                "Build services on AWS with Kubernetes and PostgreSQL. "
                "1 year of software engineering experience."
            ),
        }
    ]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        postings,
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        response = await client.get("/api/discovery/queue")

    skill_score = response.json()["candidates"][0]["score"]["skill_overlap"]
    assert skill_score == {
        "value": 33,
        "explanation": "Matches 1 of 3 detected technologies: AWS.",
    }


@pytest.mark.anyio
async def test_filled_expanded_queue_reports_user_selected_criteria(
    tmp_path: Path,
) -> None:
    profile = load_fixture("profile.json")
    template = load_fixture("candidate_queue.json")["jobs"][0]
    postings = [
        {
            **template,
            "source_url": f"https://careers.alpha-{index}.example/backend-engineer",
            "company": f"Alpha Systems {index}",
            "ats_posting_id": f"alpha-{index}",
            "canonical_url": f"https://careers.alpha-{index}.example/backend-engineer",
        }
        for index in range(25)
    ]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        postings,
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        response = await client.get(
            "/api/discovery/queue",
            params={"minimum_score": 50},
        )

    queue = response.json()
    assert queue["shortfall"] == 0
    assert queue["summary"] == (
        "25 candidates meet the displayed user-selected criteria and the daily target."
    )
