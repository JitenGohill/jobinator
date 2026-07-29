from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from jobinator.config import Settings
from jobinator.main import create_app


def load_greenhouse_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).parent / "fixtures" / "greenhouse_jobs.json"
    return json.loads(fixture_path.read_text())


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
    assert ingestion_response.json() == {"discovered": 1}
    assert discovered_response.status_code == 200
    assert discovered_response.json() == [
        {
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
                "Clear written communication"
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
    assert failed_response.status_code == 502
    assert failed_response.json() == {
        "detail": "The configured job source could not be ingested."
    }
    assert len(discovered_response.json()) == 1
    assert "private-upstream-response" not in caplog.text
