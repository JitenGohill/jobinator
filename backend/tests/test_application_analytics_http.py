from __future__ import annotations

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


class FixtureAdapter:
    platform = "fixture"

    def __init__(self, postings: list[dict[str, Any]]) -> None:
        self._postings = postings

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        del source
        return [
            JobSnapshot.model_validate(
                {**posting, "fetched_at": fetched_at, "raw_posting": posting}
            )
            for posting in self._postings
        ]


def configure_fixture_discovery(app: FastAPI, postings: list[dict[str, Any]]) -> None:
    sessions: sessionmaker[Session] = create_session_factory(app.state.database_engine)
    app.state.discovery_module = DiscoveryModule(
        sessions=sessions,
        sources=[
            SourceConfiguration(
                platform="fixture",
                identifier="application-analytics",
                company="Fixture",
            )
        ],
        adapters={"fixture": FixtureAdapter(postings)},
        clock=lambda: datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
    )


async def prepare_reviewed(
    client: AsyncClient,
    opportunity_id: int,
) -> dict[str, Any]:
    packet = (await client.post(f"/api/application-packets/{opportunity_id}", json={})).json()
    await client.post(
        f"/api/application-workflow/{opportunity_id}/transitions",
        json={"target_stage": "reviewed"},
    )
    return packet


@pytest.mark.anyio
async def test_analytics_are_empty_and_explicit_before_any_history(tmp_path: Path) -> None:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/application-analytics")

    assert response.status_code == 200
    assert response.json() == {
        "packets_prepared": 0,
        "applications_submitted": 0,
        "applications_per_day": [],
        "review_rejection_rate": {
            "numerator": 0,
            "denominator": 0,
            "rate": None,
        },
        "source_quality": [],
        "score_distribution": [
            {"label": "0–59", "minimum": 0, "maximum": 59, "count": 0},
            {"label": "60–69", "minimum": 60, "maximum": 69, "count": 0},
            {"label": "70–79", "minimum": 70, "maximum": 79, "count": 0},
            {"label": "80–89", "minimum": 80, "maximum": 89, "count": 0},
            {"label": "90–100", "minimum": 90, "maximum": 100, "count": 0},
        ],
        "response_rate_by_role": [],
        "response_rate_by_source": [],
        "response_rate_by_company_type": [],
        "common_reject_reasons": [],
        "definitions": {
            "review_rejection_rate": (
                "Reviewed opportunities skipped before submission divided by all "
                "opportunities with a completed review decision."
            ),
            "source_quality": (
                "Explicit response events divided by submitted applications for each source."
            ),
            "response_rate": (
                "Submitted applications with an explicit response event divided by submitted "
                "applications in the group."
            ),
        },
    }


@pytest.mark.anyio
async def test_dated_histories_drive_all_analytics_without_mutating_original_context(
    tmp_path: Path,
    load_fixture: Any,
) -> None:
    profile = load_fixture("profile.json")
    postings = load_fixture("candidate_queue.json")["jobs"]
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'jobinator.db'}",
        export_directory=tmp_path / "exports",
    )
    configure_fixture_discovery(app, postings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put("/api/profile", json={"profile": profile, "expected_version": None})
        await client.post("/api/discovery/ingest")
        first_packet = await prepare_reviewed(client, 1)
        first_export = (
            await client.post(f"/api/application-packets/{first_packet['id']}/exports")
        ).json()
        first_applied = await client.post(
            "/api/application-workflow/1/transitions",
            json={
                "target_stage": "applied",
                "submitted_externally": True,
                "occurred_at": "2026-08-01T10:00:00Z",
                "company_type": "product",
                "document_versions": [{"document_type": "cv", "version": 1}],
            },
        )
        first_response = await client.post(
            "/api/application-workflow/1/transitions",
            json={
                "target_stage": "outcome",
                "outcome_type": "response",
                "outcome": "Recruiter replied.",
                "occurred_at": "2026-08-02T09:00:00Z",
            },
        )
        first_interview = await client.post(
            "/api/application-workflow/1/transitions",
            json={
                "target_stage": "outcome",
                "outcome_type": "interview",
                "outcome": "Technical interview.",
                "occurred_at": "2026-08-04T15:00:00Z",
            },
        )

        await prepare_reviewed(client, 4)
        second_applied = await client.post(
            "/api/application-workflow/4/transitions",
            json={
                "target_stage": "applied",
                "submitted_externally": True,
                "occurred_at": "2026-08-01T11:00:00Z",
                "company_type": "enterprise",
                "document_versions": [],
            },
        )
        second_rejected = await client.post(
            "/api/application-workflow/4/transitions",
            json={
                "target_stage": "outcome",
                "outcome_type": "rejection",
                "outcome": "Experience requirement",
                "occurred_at": "2026-08-03T12:00:00Z",
            },
        )

        await prepare_reviewed(client, 2)
        skipped = await client.post(
            "/api/application-workflow/2/transitions",
            json={
                "target_stage": "rejected_skipped",
                "skip_reason": "Compensation mismatch",
                "occurred_at": "2026-08-01T12:00:00Z",
            },
        )
        analytics = await client.get("/api/application-analytics")
        board = await client.get("/api/application-workflow")

    assert first_export["documents"][0]["version"] == 1
    assert first_applied.status_code == 200
    assert first_response.status_code == 200
    assert first_interview.status_code == 200
    assert second_applied.status_code == 200
    assert second_rejected.status_code == 200
    assert skipped.status_code == 200

    first_item = next(item for item in board.json()["items"] if item["opportunity_id"] == 1)
    assert first_item["applied_at"] == "2026-08-01T10:00:00Z"
    assert first_item["source_platform"] == "company"
    assert first_item["original_score"]["total"] == 100
    assert first_item["packet_id"] == first_packet["id"]
    assert first_item["document_versions"] == [{"document_type": "cv", "version": 1}]
    assert [event["outcome_type"] for event in first_item["outcomes"]] == [
        "response",
        "interview",
    ]
    assert first_item["packet"]["score"]["total"] == 100

    report = analytics.json()
    assert report["packets_prepared"] == 3
    assert report["applications_submitted"] == 2
    assert report["applications_per_day"] == [{"date": "2026-08-01", "count": 2}]
    assert report["review_rejection_rate"] == {
        "numerator": 1,
        "denominator": 3,
        "rate": pytest.approx(1 / 3),
    }
    assert report["source_quality"] == [
        {
            "group": "company",
            "applications": 1,
            "responses": 1,
            "response_rate": 1.0,
        },
        {
            "group": "lever",
            "applications": 1,
            "responses": 0,
            "response_rate": 0.0,
        },
    ]
    assert report["score_distribution"] == [
        {"label": "0–59", "minimum": 0, "maximum": 59, "count": 0},
        {"label": "60–69", "minimum": 60, "maximum": 69, "count": 0},
        {"label": "70–79", "minimum": 70, "maximum": 79, "count": 0},
        {"label": "80–89", "minimum": 80, "maximum": 89, "count": 1},
        {"label": "90–100", "minimum": 90, "maximum": 100, "count": 1},
    ]
    assert report["response_rate_by_role"] == [
        {
            "group": "Junior Backend Engineer",
            "applications": 1,
            "responses": 1,
            "response_rate": 1.0,
        },
        {
            "group": "Platform Engineer",
            "applications": 1,
            "responses": 0,
            "response_rate": 0.0,
        },
    ]
    assert report["response_rate_by_source"] == report["source_quality"]
    assert report["response_rate_by_company_type"] == [
        {
            "group": "enterprise",
            "applications": 1,
            "responses": 0,
            "response_rate": 0.0,
        },
        {
            "group": "product",
            "applications": 1,
            "responses": 1,
            "response_rate": 1.0,
        },
    ]
    assert report["common_reject_reasons"] == [
        {"reason": "Experience requirement", "count": 1}
    ]
