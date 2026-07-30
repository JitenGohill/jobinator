from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from jobinator.config import Settings
from jobinator.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
CAREER_URL = "https://careers.acme.example/jobs/junior-software-engineer"
WORKDAY_URL = (
    "https://acme.wd5.myworkdayjobs.com/en-US/Acme_Careers/job/Chicago-IL/"
    "Junior-Platform-Engineer_JR-000123"
)
WORKDAY_API_URL = (
    "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/job/"
    "Chicago-IL/Junior-Platform-Engineer_JR-000123"
)


def load_text_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def load_json_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.anyio
async def test_reachable_company_career_and_workday_urls_enter_discovery_workflow(
    tmp_path: Path,
) -> None:
    career_html = load_text_fixture("company_career_posting.html")
    workday_payload = load_json_fixture("workday_posting.json")

    def source_response(request: httpx.Request) -> httpx.Response:
        if str(request.url) == CAREER_URL:
            return httpx.Response(200, text=career_html)
        if str(request.url) == WORKDAY_API_URL:
            return httpx.Response(200, json=workday_payload)
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(
            career_page_urls=[CAREER_URL],
            workday_posting_urls=[WORKDAY_URL],
        ),
        source_client=source_client,
        clock=lambda: datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ingestion = await client.post("/api/discovery/ingest")
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert ingestion.json() == {
        "discovered": 2,
        "sources": [
            {
                "platform": "company",
                "identifier": CAREER_URL,
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            },
            {
                "platform": "workday",
                "identifier": WORKDAY_URL,
                "status": "succeeded",
                "discovered": 1,
                "error": None,
            },
        ],
    }
    opportunities = discovered.json()
    assert {opportunity["title"] for opportunity in opportunities} == {
        "Junior Software Engineer",
        "Junior Platform Engineer",
    }
    company_snapshot = next(
        opportunity for opportunity in opportunities
        if opportunity["source_platform"] == "company"
    )
    assert company_snapshot["company"] == "Acme Corp"
    assert company_snapshot["location"] == "New York, NY"
    assert company_snapshot["ats_posting_id"] == "CAREERS-123"
    assert company_snapshot["canonical_url"] == CAREER_URL
    assert company_snapshot["detected_requirements"] == [
        "Experience with Python",
        "Clear written communication",
    ]
    assert company_snapshot["raw_posting"]["@type"] == "JobPosting"
    workday_snapshot = next(
        opportunity for opportunity in opportunities
        if opportunity["source_platform"] == "workday"
    )
    assert workday_snapshot["company"] == "Acme Corp"
    assert workday_snapshot["location"] == "Chicago, IL"
    assert workday_snapshot["ats_posting_id"] == "JR-000123"
    assert workday_snapshot["canonical_url"] == WORKDAY_URL
    assert workday_snapshot["raw_posting"] == workday_payload["jobPostingInfo"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("platform", "status_code", "fixture_name", "expected_error"),
    [
        (
            "company",
            200,
            "company_career_changed_markup.html",
            "Company career page structure is unsupported; expected schema.org "
            "JobPosting data. Browser automation was not attempted.",
        ),
        (
            "company",
            403,
            "reachable_source_failures.json:company_blocked",
            "Company career page blocked access (HTTP 403). Browser automation was not attempted.",
        ),
        (
            "workday",
            200,
            "workday_changed_markup.json",
            "Workday returned an unrecognized posting structure. "
            "Browser automation was not attempted.",
        ),
        (
            "workday",
            404,
            "reachable_source_failures.json:workday_missing",
            "Workday posting was not found (HTTP 404).",
        ),
    ],
)
async def test_unsupported_blocked_changed_and_missing_pages_report_actionable_diagnostics(
    tmp_path: Path,
    platform: str,
    status_code: int,
    fixture_name: str,
    expected_error: str,
) -> None:
    source_url = CAREER_URL if platform == "company" else WORKDAY_URL

    def source_response(_: httpx.Request) -> httpx.Response:
        if ":" in fixture_name:
            fixture_file, fixture_key = fixture_name.split(":", maxsplit=1)
            failure = load_json_fixture(fixture_file)[fixture_key]
            assert failure["status_code"] == status_code
            body = failure["body"]
            if isinstance(body, dict):
                return httpx.Response(status_code, json=body)
            return httpx.Response(status_code, text=body)
        if fixture_name.endswith(".json"):
            return httpx.Response(status_code, json=load_json_fixture(fixture_name))
        return httpx.Response(status_code, text=load_text_fixture(fixture_name))

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    settings = (
        Settings(career_page_urls=[source_url])
        if platform == "company"
        else Settings(workday_posting_urls=[source_url])
    )
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=settings,
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ingestion = await client.post("/api/discovery/ingest")

    await source_client.aclose()
    assert ingestion.json() == {
        "discovered": 0,
        "sources": [
            {
                "platform": platform,
                "identifier": source_url,
                "status": "failed",
                "discovered": 0,
                "error": expected_error,
            }
        ],
    }


@pytest.mark.anyio
async def test_later_company_page_failure_preserves_previously_captured_snapshot(
    tmp_path: Path,
) -> None:
    request_count = 0

    def source_response(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(
                200,
                text=load_text_fixture("company_career_posting.html"),
            )
        return httpx.Response(410)

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(career_page_urls=[CAREER_URL]),
        source_client=source_client,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_ingestion = await client.post("/api/discovery/ingest")
        later_ingestion = await client.post("/api/discovery/ingest")
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    assert first_ingestion.json()["discovered"] == 1
    assert later_ingestion.json()["sources"][0]["error"] == (
        "Company career posting was not found (HTTP 410)."
    )
    assert [opportunity["title"] for opportunity in discovered.json()] == [
        "Junior Software Engineer"
    ]


@pytest.mark.anyio
async def test_changed_posting_becomes_current_while_older_snapshot_remains_reviewable(
    tmp_path: Path,
) -> None:
    original = load_text_fixture("company_career_posting.html")
    changed = original.replace(
        "Build dependable tools for our operations team.",
        "Build newly redesigned tools for our operations team.",
    )
    responses = iter([original, changed])
    fetched_times = iter(
        [
            datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
        ]
    )
    source_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=next(responses))
        )
    )
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        settings=Settings(career_page_urls=[CAREER_URL]),
        source_client=source_client,
        clock=lambda: next(fetched_times),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/discovery/ingest")
        await client.post("/api/discovery/ingest")
        discovered = await client.get("/api/discovery/jobs")

    await source_client.aclose()
    opportunity = discovered.json()[0]
    assert opportunity["description_text"].startswith("Build newly redesigned tools")
    snapshot_descriptions = [
        snapshot["description_text"].splitlines()[0]
        for snapshot in opportunity["snapshots"]
    ]
    assert snapshot_descriptions == [
        "Build dependable tools for our operations team.",
        "Build newly redesigned tools for our operations team.",
    ]
