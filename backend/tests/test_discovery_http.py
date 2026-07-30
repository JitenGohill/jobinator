from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from jobinator.config import Settings
from jobinator.database import create_session_factory
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.module import DiscoveryModule
from jobinator.main import create_app


def load_greenhouse_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).parent / "fixtures" / "greenhouse_jobs.json"
    return json.loads(fixture_path.read_text())


def load_lever_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).parent / "fixtures" / "lever_postings.json"
    return json.loads(fixture_path.read_text())


def load_ashby_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).parent / "fixtures" / "ashby_postings.json"
    return json.loads(fixture_path.read_text())


def load_screening_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).parent / "fixtures" / "screening_jobs.json"
    return json.loads(fixture_path.read_text())


def load_opportunity_fixture() -> dict[str, list[dict[str, Any]]]:
    fixture_path = Path(__file__).parent / "fixtures" / "opportunity_duplicates.json"
    return json.loads(fixture_path.read_text())


class FixtureAdapter:
    def __init__(self, platform: str, postings: list[dict[str, Any]]) -> None:
        self.platform = platform
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
            if posting["source_platform"] == source.platform
        ]


def configure_fixture_discovery(
    app: FastAPI,
    postings: list[dict[str, Any]],
    clock: Callable[[], datetime],
) -> None:
    sessions: sessionmaker[Session] = create_session_factory(app.state.database_engine)
    platforms = list(dict.fromkeys(posting["source_platform"] for posting in postings))
    app.state.discovery_module = DiscoveryModule(
        sessions=sessions,
        sources=[
            SourceConfiguration(platform=platform, identifier=platform, company="Fixture")
            for platform in platforms
        ],
        adapters={
            platform: FixtureAdapter(platform, postings)
            for platform in platforms
        },
        clock=clock,
    )


async def ingest_fixture_postings(
    tmp_path: Path,
    postings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(
        app,
        postings,
        lambda: datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ingestion_response = await client.post("/api/discovery/ingest")
        response = await client.get("/api/discovery/jobs")
    assert ingestion_response.status_code == 200
    assert response.status_code == 200
    return response.json()


async def screen_fixture_jobs(
    tmp_path: Path,
    fixture_group: str = "jobs",
    *,
    with_profile: bool = False,
) -> list[dict[str, Any]]:
    fixture = load_screening_fixture()
    fixture["jobs"] = fixture[fixture_group]
    source_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=fixture))
    )
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(
            greenhouse_board_token="acme",
            greenhouse_company="Acme Corp",
        ),
        source_client=source_client,
        clock=lambda: datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if with_profile:
            profile = json.loads(
                (Path(__file__).parent / "fixtures" / "profile.json").read_text()
            )
            profile_response = await client.put(
                "/api/profile",
                json={"profile": profile, "expected_version": None},
            )
            assert profile_response.status_code == 200
        ingestion_response = await client.post("/api/discovery/ingest")
        response = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert ingestion_response.status_code == 200
    assert response.status_code == 200
    return response.json()


@pytest.mark.anyio
async def test_configured_greenhouse_board_is_ingested_as_a_discovered_snapshot(
    tmp_path: Path,
) -> None:
    fixture = load_greenhouse_fixture()

    def greenhouse_response(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        return httpx.Response(200, json=fixture)

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(greenhouse_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(
            greenhouse_board_token="acme",
            greenhouse_company="Acme Corp",
        ),
        source_client=source_client,
        clock=lambda: datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ingestion_response = await client.post("/api/discovery/ingest")
        discovered_response = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert ingestion_response.status_code == 200
    assert ingestion_response.json() == {
        "discovered": 1,
        "sources": [
            {
                "platform": "greenhouse",
                "identifier": "acme",
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            }
        ],
    }
    assert discovered_response.status_code == 200
    expected_snapshot = {
        "id": 1,
        "source_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "fetched_at": "2026-07-29T12:00:00Z",
        "company": "Acme Corp",
        "title": "Junior Software Engineer",
        "location": "New York, NY",
        "description_text": (
            "Build dependable tools for our operations team.\n"
            "What we're looking for\n"
            "Experience with Python\n"
            "Clear written communication\n"
            "Benefits\n"
            "Health insurance"
        ),
        "detected_requirements": [
            "Experience with Python",
            "Clear written communication",
        ],
        "source_platform": "greenhouse",
        "ats_posting_id": "12345",
        "canonical_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "raw_posting": fixture["jobs"][0],
    }
    assert discovered_response.json() == [
        {
            **expected_snapshot,
            "preferred_apply_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "snapshots": [expected_snapshot],
            "screening": {
                "lane": "eligible",
                "reasons": [
                    "Target role type: software engineering.",
                    "Target location: New York.",
                    "Junior-friendly role: junior.",
                ],
            },
        }
    ]


@pytest.mark.anyio
async def test_configured_lever_and_ashby_sources_normalize_and_merge_as_one_opportunity(
    tmp_path: Path,
) -> None:
    lever_fixture = load_lever_fixture()
    ashby_fixture = load_ashby_fixture()

    def source_response(request: httpx.Request) -> httpx.Response:
        if request.url == "https://api.lever.co/v0/postings/acme?mode=json":
            return httpx.Response(200, json=lever_fixture["postings"])
        if request.url == "https://api.ashbyhq.com/posting-api/job-board/acme":
            return httpx.Response(200, json={"jobs": ashby_fixture["jobs"]})
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(
            lever_site="acme",
            lever_company="Acme Corp",
            ashby_board="acme",
            ashby_company="Acme Corp",
        ),
        source_client=source_client,
        clock=lambda: datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ingestion_response = await client.post("/api/discovery/ingest")
        discovered_response = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert ingestion_response.status_code == 200
    assert ingestion_response.json() == {
        "discovered": 2,
        "sources": [
            {
                "platform": "lever",
                "identifier": "acme",
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            },
            {
                "platform": "ashby",
                "identifier": "acme",
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            },
        ],
    }
    opportunities = discovered_response.json()
    assert len(opportunities) == 1
    assert opportunities[0]["screening"]["lane"] == "eligible"
    snapshots = {
        snapshot["source_platform"]: snapshot
        for snapshot in opportunities[0]["snapshots"]
    }
    assert snapshots["lever"] == {
        "id": 1,
        "source_url": "https://jobs.lever.co/acme/lever-123",
        "fetched_at": "2026-07-29T12:00:00Z",
        "company": "Acme Corp",
        "title": "Junior Software Engineer",
        "location": "New York, NY",
        "description_text": (
            "Build dependable tools for our operations team.\n"
            "What we're looking for\n"
            "Experience with Python\n"
            "Clear written communication"
        ),
        "detected_requirements": [
            "Experience with Python",
            "Clear written communication",
        ],
        "source_platform": "lever",
        "ats_posting_id": "lever-123",
        "canonical_url": "https://jobs.lever.co/acme/lever-123",
        "raw_posting": lever_fixture["postings"][0],
    }
    assert snapshots["ashby"] == {
        "id": 2,
        "source_url": "https://jobs.ashbyhq.com/acme/ashby-456",
        "fetched_at": "2026-07-29T12:00:00Z",
        "company": "Acme Corp",
        "title": "Junior Software Engineer",
        "location": "New York, NY",
        "description_text": (
            "Build dependable tools for our operations team.\n"
            "What we're looking for\n"
            "Experience with Python\n"
            "Clear written communication"
        ),
        "detected_requirements": [
            "Experience with Python",
            "Clear written communication",
        ],
        "source_platform": "ashby",
        "ats_posting_id": "ashby-456",
        "canonical_url": "https://jobs.ashbyhq.com/acme/ashby-456",
        "raw_posting": ashby_fixture["jobs"][0],
    }


@pytest.mark.anyio
async def test_changed_ats_responses_are_reported_without_blocking_successful_sources(
    tmp_path: Path,
) -> None:
    greenhouse_fixture = load_greenhouse_fixture()
    lever_fixture = load_lever_fixture()
    ashby_fixture = load_ashby_fixture()

    def source_response(request: httpx.Request) -> httpx.Response:
        if request.url.host == "boards-api.greenhouse.io":
            return httpx.Response(200, json=greenhouse_fixture)
        if request.url.host == "api.lever.co":
            return httpx.Response(200, json=lever_fixture["malformed_response"])
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(200, json=ashby_fixture["malformed_response"])
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(
            greenhouse_board_token="acme",
            greenhouse_company="Acme Corp",
            lever_site="acme",
            lever_company="Acme Corp",
            ashby_board="acme",
            ashby_company="Acme Corp",
        ),
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ingestion_response = await client.post("/api/discovery/ingest")
        discovered_response = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert ingestion_response.status_code == 200
    assert ingestion_response.json() == {
        "discovered": 1,
        "sources": [
            {
                "platform": "greenhouse",
                "identifier": "acme",
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            },
            {
                "platform": "lever",
                "identifier": "acme",
                "status": "failed",
                "discovered": 0,
                "error": "Lever returned an invalid posting.",
            },
            {
                "platform": "ashby",
                "identifier": "acme",
                "status": "failed",
                "discovered": 0,
                "error": "Ashby returned an invalid posting.",
            },
        ],
    }
    assert [job["title"] for job in discovered_response.json()] == [
        "Junior Software Engineer"
    ]


@pytest.mark.anyio
async def test_definite_duplicate_discoveries_are_one_opportunity_with_both_snapshots(
    tmp_path: Path,
) -> None:
    postings = load_opportunity_fixture()["definite_duplicates"]
    opportunities = await ingest_fixture_postings(tmp_path, postings)
    assert len(opportunities) == 1
    assert opportunities[0]["preferred_apply_url"] == (
        "https://boards.greenhouse.io/acme/jobs/12345"
    )
    assert [
        snapshot["raw_posting"] for snapshot in opportunities[0]["snapshots"]
    ] == postings


@pytest.mark.anyio
async def test_similar_but_distinct_roles_remain_separate_opportunities(
    tmp_path: Path,
) -> None:
    postings = load_opportunity_fixture()["similar_distinct"]
    opportunities = await ingest_fixture_postings(tmp_path, postings)
    assert {opportunity["title"] for opportunity in opportunities} == {
        "Software Engineer I",
        "Software Engineer II",
    }


@pytest.mark.anyio
async def test_cross_source_duplicates_prefer_the_ats_apply_route(
    tmp_path: Path,
) -> None:
    postings = load_opportunity_fixture()["cross_source_duplicates"]
    opportunities = await ingest_fixture_postings(tmp_path, postings)
    assert len(opportunities) == 1
    assert opportunities[0]["preferred_apply_url"] == (
        "https://boards.greenhouse.io/acme/jobs/2468"
    )
    assert {snapshot["source_platform"] for snapshot in opportunities[0]["snapshots"]} == {
        "greenhouse",
        "job_board",
    }


@pytest.mark.anyio
async def test_a_discovery_that_bridges_duplicate_groups_coalesces_them(
    tmp_path: Path,
) -> None:
    postings = load_opportunity_fixture()["bridging_duplicate"]
    opportunities = await ingest_fixture_postings(tmp_path, postings)
    assert len(opportunities) == 1
    assert len(opportunities[0]["snapshots"]) == 3


@pytest.mark.anyio
async def test_repeated_ingestion_keeps_each_snapshot_under_one_opportunity(
    tmp_path: Path,
) -> None:
    postings = load_opportunity_fixture()["repeated_snapshot"]
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    fetched_times = iter(
        [
            datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
        ]
    )
    configure_fixture_discovery(app, postings, lambda: next(fetched_times))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_ingestion = await client.post("/api/discovery/ingest")
        second_ingestion = await client.post("/api/discovery/ingest")
        response = await client.get("/api/discovery/jobs")

    expected_ingestion = {
        "discovered": 1,
        "sources": [
            {
                "platform": "greenhouse",
                "identifier": "greenhouse",
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            }
        ],
    }
    assert first_ingestion.json() == expected_ingestion
    assert second_ingestion.json() == expected_ingestion
    opportunities = response.json()
    assert len(opportunities) == 1
    assert [snapshot["fetched_at"] for snapshot in opportunities[0]["snapshots"]] == [
        "2026-07-29T12:00:00Z",
        "2026-07-30T12:00:00Z",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("failure_kind", ["fetch", "normalization"])
async def test_ingestion_failure_preserves_snapshots_without_logging_upstream_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    failure_kind: str,
) -> None:
    fixture = load_greenhouse_fixture()
    request_count = 0

    def greenhouse_response(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(200, json=fixture)
        if failure_kind == "fetch":
            return httpx.Response(500, text="private-upstream-response")
        return httpx.Response(200, json={"jobs": [{"private": "private-upstream-response"}]})

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(greenhouse_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(
            greenhouse_board_token="acme",
            greenhouse_company="Acme Corp",
        ),
        source_client=source_client,
    )

    with caplog.at_level(logging.WARNING):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            successful_response = await client.post("/api/discovery/ingest")
            failed_response = await client.post("/api/discovery/ingest")
            discovered_response = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert successful_response.status_code == 200
    assert failed_response.status_code == 200
    expected_error = (
        "Greenhouse request failed (HTTPStatusError)."
        if failure_kind == "fetch"
        else "Greenhouse returned an invalid posting."
    )
    assert failed_response.json() == {
        "discovered": 0,
        "sources": [
            {
                "platform": "greenhouse",
                "identifier": "acme",
                "status": "failed",
                "discovered": 0,
                "error": expected_error,
            }
        ],
    }
    assert len(discovered_response.json()) == 1
    assert "private-upstream-response" not in caplog.text


@pytest.mark.anyio
async def test_discovered_roles_are_screened_into_eligible_stretch_and_maybe_lanes(
    tmp_path: Path,
) -> None:
    jobs = await screen_fixture_jobs(tmp_path)
    screening_results = {
        job["title"]: (job["screening"]["lane"], job["screening"]["reasons"])
        for job in jobs
    }
    assert screening_results == {
        "Junior Backend Engineer": (
            "eligible",
            [
                "Target role type: backend engineering.",
                "Target location: New York.",
                "Junior-friendly experience requirement: 1 year.",
            ],
        ),
        "Platform Engineer": (
            "stretch",
            [
                "Target role type: platform engineering.",
                "Target location: US-based remote.",
                "Stretch experience requirement: 3 years.",
            ],
        ),
        "Junior Full-Stack Engineer": (
            "maybe",
            [
                    "Target role type: full-stack engineering.",
                    "Target location: Chicago.",
                    "Junior-friendly experience requirement: 2 years.",
                    "Staffing-agency listing retained for manual review because it is a "
                    "direct-hire role with a named client and compensation.",
            ],
        ),
        "Junior Internal Tools Engineer": (
            "maybe",
            [
                    "Target role type: internal-tools engineering.",
                    "Target location: New York.",
                    "Junior-friendly experience requirement: 1 year.",
                    "Unclear-employer listing retained for manual review because it is a "
                    "direct-hire role with compensation and detailed requirements.",
            ],
        ),
    }


@pytest.mark.anyio
async def test_discovered_roles_expose_every_hard_reject_category(tmp_path: Path) -> None:
    screened_jobs = await screen_fixture_jobs(
        tmp_path,
        "hard_reject_jobs",
        with_profile=True,
    )
    expected_reasons = {
        "Junior Backend Engineer - Austin": "Outside target locations: Austin, TX.",
        "Junior Backend Engineer - Relocation": "Requires relocation outside New York or Chicago.",
        "Frontend Engineer": "Excluded role type: pure frontend.",
        "Mobile Engineer": "Excluded role type: mobile.",
        "QA Engineer": "Excluded role type: QA.",
        "IT Support Specialist": "Excluded role type: IT support.",
        "Data Analyst": "Excluded role type: data analyst.",
        "Software Engineering Intern": "Excluded role type: unpaid internship.",
        "Backend Engineer IV": (
            "Experience requirement is 4+ years without an accepted junior-equivalent path."
        ),
        "Senior Backend Engineer": "Excluded seniority: senior role.",
        "Staff Software Engineer": "Excluded seniority: staff role.",
        "Principal Platform Engineer": "Excluded seniority: principal role.",
        "Engineering Manager": "Excluded seniority: manager role.",
        "Junior Backend Engineer - Unpaid": "Compensation is explicitly unpaid.",
        "Junior Backend Engineer - Commission": "Compensation is commission-only.",
        "Junior Platform Engineer - Clearance": "Requires an active security clearance.",
        "Junior Backend Engineer - Closed": "Application deadline has passed.",
        "Junior Backend Engineer - Java": (
            "Requires professional Java experience that is absent from the canonical profile."
        ),
        "Junior Backend Engineer - Agency": "Staffing-agency listing rejected by default.",
        "Junior Backend Engineer - Confidential": "Employer identity is unclear.",
    }
    jobs = {job["title"]: job["screening"] for job in screened_jobs}
    assert jobs.keys() == expected_reasons.keys()
    for title, reason in expected_reasons.items():
        assert jobs[title]["lane"] == "rejected", title
        assert reason in jobs[title]["reasons"], title


@pytest.mark.anyio
async def test_junior_friendly_role_types_and_equivalent_experience_paths_remain_eligible(
    tmp_path: Path,
) -> None:
    screened_jobs = await screen_fixture_jobs(tmp_path, "junior_friendly_jobs")
    jobs = {job["title"]: job["screening"] for job in screened_jobs}
    assert jobs == {
        "Entry-Level Internal Tools Engineer": {
            "lane": "eligible",
            "reasons": [
                "Target role type: internal-tools engineering.",
                "Target location: New York.",
                "Junior-friendly role: entry-level.",
            ],
        },
        "New Grad AI Applications Engineer": {
            "lane": "eligible",
            "reasons": [
                "Target role type: AI-adjacent engineering.",
                "Target location: Chicago.",
                "Junior-friendly role: new grad.",
            ],
        },
        "Software Engineer Apprentice": {
            "lane": "eligible",
            "reasons": [
                "Target role type: software engineering.",
                "Target location: US-based remote.",
                "Junior-friendly role: apprenticeship.",
            ],
        },
        "Backend Engineer - Equivalent Experience": {
            "lane": "stretch",
            "reasons": [
                "Target role type: backend engineering.",
                "Target location: US-based remote.",
                "Stretch experience requirement: 5 years, with an accepted junior-equivalent path.",
            ],
        },
        "Junior Full-Stack Engineer - Zero to Two": {
            "lane": "eligible",
            "reasons": [
                "Target role type: full-stack engineering.",
                "Target location: New York.",
                "Junior-friendly experience requirement: 2 years.",
            ],
        },
    }


@pytest.mark.anyio
async def test_screening_handles_realistic_policy_wording_without_false_rejects(
    tmp_path: Path,
) -> None:
    screened_jobs = await screen_fixture_jobs(
        tmp_path,
        "review_cases",
        with_profile=True,
    )
    jobs = {job["title"]: job["screening"] for job in screened_jobs}
    assert jobs["Account Executive"] == {
        "lane": "rejected",
        "reasons": [
            "Target location: New York.",
            "Outside target software engineering role types.",
        ],
    }
    assert jobs["Junior Full-Stack / Frontend Engineer"]["lane"] == "eligible"
    assert jobs["Junior Backend Engineer - Benefits"]["lane"] == "eligible"
    assert jobs["Software Engineer - Senior Scope"]["lane"] == "rejected"
    assert "Excluded seniority: senior role." in jobs["Software Engineer - Senior Scope"]["reasons"]
    assert jobs["Junior Platform Engineer - TS/SCI"]["lane"] == "rejected"
    assert "Requires an active security clearance." in jobs[
        "Junior Platform Engineer - TS/SCI"
    ]["reasons"]
    assert jobs["Junior Backend Engineer - Apply By"]["lane"] == "rejected"
    assert "Application deadline has passed." in jobs[
        "Junior Backend Engineer - Apply By"
    ]["reasons"]
    assert jobs["Junior Backend Engineer - Professional Java"]["lane"] == "rejected"
    assert (
        "Requires professional Java experience that is absent from the canonical profile."
        in jobs["Junior Backend Engineer - Professional Java"]["reasons"]
    )
    assert jobs["Junior Backend Engineer - Staffing Firm"]["lane"] == "rejected"
    assert "Staffing-agency listing rejected by default." in jobs[
        "Junior Backend Engineer - Staffing Firm"
    ]["reasons"]
    assert jobs["Junior Backend Engineer - Recruiting Agency"]["lane"] == "maybe"
    assert jobs["Junior Backend Engineer - Undisclosed Client"]["lane"] == "rejected"
    assert "Employer identity is unclear." in jobs[
        "Junior Backend Engineer - Undisclosed Client"
    ]["reasons"]
    assert jobs["Entry-Level Software Development Engineer I"]["lane"] == "eligible"
    assert jobs["Software Engineer - Product"]["lane"] == "rejected"
    assert "Excluded role type: mobile." in jobs[
        "Software Engineer - Product"
    ]["reasons"]
    assert jobs["Software Engineer - Web Product"]["lane"] == "rejected"
    assert "Excluded role type: pure frontend." in jobs[
        "Software Engineer - Web Product"
    ]["reasons"]
    assert jobs["Frontend & Backend Software Engineer"]["lane"] == "eligible"
    assert jobs["Junior Backend Engineer - Confidential Direct Hire"]["lane"] == "maybe"
    assert jobs["Junior Backend Engineer - Remote Only"]["lane"] == "eligible"
    assert jobs["Junior Backend Engineer - No Relocation"]["lane"] == "eligible"
    for title in (
        "Backend Engineer - Experience In",
        "Backend Engineer - Experience Developing",
        "Backend Engineer - Years In Development",
    ):
        assert jobs[title]["lane"] == "rejected"
        assert (
            "Experience requirement is 4+ years without an accepted junior-equivalent path."
            in jobs[title]["reasons"]
        )
