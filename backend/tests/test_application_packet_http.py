from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from jobinator.application.models import (
    FactId,
    GeneratedApplicationPlan,
    ScreeningAnswerPlan,
)
from jobinator.application.provider import ApplicationGenerationInput
from jobinator.database import create_session_factory
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.module import DiscoveryModule
from jobinator.main import create_app


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


class InvalidFactProvider:
    name = "fixture-ai"
    model = "fixture-model"

    async def generate(
        self,
        generation_input: ApplicationGenerationInput,
        prompt: str,
    ) -> GeneratedApplicationPlan:
        del generation_input, prompt
        return GeneratedApplicationPlan(
            selected_fact_ids=[
                FactId("profile.base_cv"),
                FactId("profile.invented.employer"),
            ],
            cover_letter_fact_ids=[],
            screening_answers=[
                ScreeningAnswerPlan(
                    question_index=0,
                    fact_ids=[FactId("profile.invented.citizenship")],
                )
            ],
        )


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
                identifier="application-packet",
                company="Fixture",
            )
        ],
        adapters={"fixture": FixtureAdapter(postings)},
        clock=clock,
    )


@pytest.mark.anyio
async def test_packet_is_complete_truthful_and_deterministic_without_live_ai(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    posting = load_fixture("candidate_queue.json")["jobs"][0]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        first_response = await client.post("/api/application-packets/1", json={})
        second_response = await client.post("/api/application-packets/1", json={})

    assert first_response.status_code == 200
    assert second_response.json() == first_response.json()
    packet = first_response.json()
    assert packet["opportunity_id"] == 1
    assert packet["score"]["total"] == 100
    assert packet["job_snapshot"]["company"] == "Alpha Systems"
    assert packet["job_snapshot"]["title"] == "Junior Backend Engineer"
    assert packet["direct_apply_link"] == posting["canonical_url"]
    assert packet["estimated_application_effort"] == "low"
    assert packet["matched_profile_context"] == {
        "skills": ["FastAPI", "Python"],
        "projects": ["Queue Lens"],
        "work_experience": [],
    }
    assert packet["missing_requirements"] == []
    assert "Junior software engineer focused on reliable backend systems." in packet[
        "tailored_cv_draft"
    ]
    assert "Junior Backend Engineer" in packet["tailored_cv_draft"]
    assert "Queue Lens" in packet["tailored_cv_draft"]
    assert packet["cover_letter"] is None
    assert packet["screening_answers"] == []
    assert packet["risk_flags"] == [
        {
            "category": "unsupported_experience",
            "message": (
                "The role asks for 1 year of experience; the dated work history "
                "does not establish that duration."
            ),
        }
    ]
    assert packet["generation"] == {
        "provider": "fake",
        "model": "deterministic-v1",
        "prompt_version": "application-packet-v1",
    }


@pytest.mark.anyio
async def test_cover_letter_is_generated_when_posting_makes_it_useful(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][0],
        "description_text": (
            load_fixture("candidate_queue.json")["jobs"][0]["description_text"]
            + " Please include a cover letter explaining your interest."
        ),
    }
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        response = await client.post(
            "/api/application-packets/1",
            json={"screening_questions": ["Are you a US citizen?"]},
        )

    assert response.status_code == 200
    cover_letter = response.json()["cover_letter"]
    assert profile["writing_samples"][0]["content"] in cover_letter
    assert "Junior Backend Engineer" in cover_letter


@pytest.mark.anyio
async def test_packet_surfaces_missing_experience_location_and_review_risks(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][1],
        "description_text": (
            load_fixture("candidate_queue.json")["jobs"][1]["description_text"]
            + " Must be authorized to work in the US without sponsorship."
        ),
    }
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        response = await client.post(
            "/api/application-packets/1",
            json={"screening_questions": ["Are you authorized to work in the US?"]},
        )

    assert response.status_code == 200
    packet = response.json()
    assert packet["missing_requirements"] == ["Clear written communication", "Java"]
    assert {flag["category"] for flag in packet["risk_flags"]} == {
        "missing_requirement",
        "unsupported_experience",
        "authorization_or_location_mismatch",
        "manual_review_required",
    }
    assert packet["screening_answers"] == [
        {
            "question": "Are you authorized to work in the US?",
            "draft": (
                "Insufficient canonical-profile evidence to draft an answer."
            ),
            "review_required": True,
        }
    ]


@pytest.mark.anyio
async def test_unknown_provider_facts_are_omitted_and_flagged(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][0],
        "description_text": "Build Python and FastAPI services.",
    }
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        application_provider=InvalidFactProvider(),
    )
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        response = await client.post(
            "/api/application-packets/1",
            json={"screening_questions": ["Are you a US citizen?"]},
        )

    assert response.status_code == 200
    assert {flag["category"] for flag in response.json()["risk_flags"]} == {
        "manual_review_required",
        "possible_overstatement",
    }
    assert "InventedCo" not in response.json()["tailored_cv_draft"]
    assert response.json()["screening_answers"][0]["draft"] == (
        "Insufficient canonical-profile evidence to draft an answer."
    )


@pytest.mark.anyio
async def test_risk_review_flags_inflated_canonical_writing(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    profile["base_cv"] = "World-class expert engineer and perfect fit for every role."
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][0],
        "description_text": "Build Python and FastAPI services.",
    }
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/api/profile", json={"profile": profile, "expected_version": None})
        await client.post("/api/discovery/ingest")
        response = await client.post("/api/application-packets/1", json={})

    assert {flag["category"] for flag in response.json()["risk_flags"]} == {
        "possible_overstatement",
        "generic_or_inflated_writing",
    }


@pytest.mark.anyio
async def test_risk_review_flags_location_outside_profile_constraints(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][6],
        "detected_requirements": ["Python"],
        "description_text": (
            "Build Python AI applications. 1 year of software engineering experience."
        ),
    }
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        response = await client.post("/api/application-packets/1", json={})

    assert response.status_code == 200
    assert "authorization_or_location_mismatch" in {
        flag["category"] for flag in response.json()["risk_flags"]
    }


@pytest.mark.anyio
async def test_requirement_matching_uses_project_and_work_evidence(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][0],
        "detected_requirements": [
            "Experience building services with Python",
            "Fixture-driven tests",
            "batch job runtime",
        ],
    }
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/api/profile", json={"profile": profile, "expected_version": None})
        await client.post("/api/discovery/ingest")
        response = await client.post("/api/application-packets/1", json={})

    packet = response.json()
    assert packet["missing_requirements"] == []
    assert packet["matched_profile_context"]["projects"] == ["Queue Lens"]
    assert packet["matched_profile_context"]["work_experience"] == [
        "Software Engineering Intern at Example Labs"
    ]


@pytest.mark.anyio
async def test_authorization_review_detects_sponsorship_contradiction(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    profile["constraints"] = ["US-based remote or New York", "Requires visa sponsorship"]
    posting = {
        **load_fixture("candidate_queue.json")["jobs"][0],
        "description_text": (
            "Build Python and FastAPI services. 1 year of software engineering experience. "
            "Candidates must be authorized to work in the US without sponsorship."
        ),
    }
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/api/profile", json={"profile": profile, "expected_version": None})
        await client.post("/api/discovery/ingest")
        response = await client.post("/api/application-packets/1", json={})

    assert "authorization_or_location_mismatch" in {
        flag["category"] for flag in response.json()["risk_flags"]
    }


@pytest.mark.anyio
async def test_current_employment_counts_toward_experience_at_snapshot_date(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    profile["work_history"][0]["start_date"] = "2024-01"
    profile["work_history"][0]["end_date"] = "present"
    posting = load_fixture("candidate_queue.json")["jobs"][1]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/api/profile", json={"profile": profile, "expected_version": None})
        await client.post("/api/discovery/ingest")
        response = await client.post("/api/application-packets/1", json={})

    assert "unsupported_experience" not in {
        flag["category"] for flag in response.json()["risk_flags"]
    }


@pytest.mark.anyio
async def test_parallel_roles_do_not_double_count_experience(
    tmp_path: Path,
    load_fixture: Callable[[str], Any],
) -> None:
    profile = load_fixture("profile.json")
    role = profile["work_history"][0]
    role["start_date"] = "2024-01"
    role["end_date"] = "2024-12"
    profile["work_history"].append(
        {
            **role,
            "employer": "Example Two",
            "title": "Software Engineering Apprentice",
        }
    )
    posting = load_fixture("candidate_queue.json")["jobs"][1]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        [posting],
        lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/api/profile", json={"profile": profile, "expected_version": None})
        await client.post("/api/discovery/ingest")
        response = await client.post("/api/application-packets/1", json={})

    assert "unsupported_experience" in {
        flag["category"] for flag in response.json()["risk_flags"]
    }
