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
                identifier="strategy-advice",
                company="Fixture",
            )
        ],
        adapters={"fixture": FixtureAdapter(postings)},
        clock=lambda: datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
    )


async def record_outcome(
    client: AsyncClient,
    opportunity_id: int,
    outcome_type: str,
) -> None:
    await client.post(f"/api/application-packets/{opportunity_id}", json={})
    await client.post(
        f"/api/application-workflow/{opportunity_id}/transitions",
        json={"target_stage": "reviewed"},
    )
    await client.post(
        f"/api/application-workflow/{opportunity_id}/transitions",
        json={"target_stage": "applied", "submitted_externally": True},
    )
    response = await client.post(
        f"/api/application-workflow/{opportunity_id}/transitions",
        json={
            "target_stage": "outcome",
            "outcome_type": outcome_type,
            "outcome": f"Recorded {outcome_type} outcome.",
        },
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_strategy_advice_aggregates_supported_gaps_and_requires_proposal_approval(
    tmp_path: Path,
    load_fixture: Any,
) -> None:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(app, load_fixture("strategy_advice.json")["jobs"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": load_fixture("profile.json"), "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        await record_outcome(client, 1, "interview")
        await record_outcome(client, 2, "rejection")

        queue_before = (await client.get("/api/discovery/queue")).json()
        advice = (await client.get("/api/strategy-advice")).json()
        queue_while_pending = (await client.get("/api/discovery/queue")).json()

        assert advice["gap_findings"] == [
            {
                "requirement": "Go",
                "occurrences": 3,
                "priority_options": ["learning", "portfolio", "profile_presentation"],
                "opportunities": [
                    {
                        "opportunity_id": 1,
                        "company": "Alpha Systems",
                        "title": "Junior Backend Engineer",
                        "score": 90.0,
                        "source_platform": "company",
                        "matched_skills": ["Python"],
                        "matched_projects": ["Queue Lens"],
                        "matched_work_experience": [],
                    },
                    {
                        "opportunity_id": 2,
                        "company": "Beta Cloud",
                        "title": "Junior Backend Engineer",
                        "score": 86.75,
                        "source_platform": "lever",
                        "matched_skills": ["Python"],
                        "matched_projects": ["Queue Lens"],
                        "matched_work_experience": [],
                    },
                    {
                        "opportunity_id": 3,
                        "company": "Gamma Tools",
                        "title": "Junior Backend Engineer",
                        "score": 86.75,
                        "source_platform": "greenhouse",
                        "matched_skills": ["Python"],
                        "matched_projects": ["Queue Lens"],
                        "matched_work_experience": [],
                    },
                ],
            }
        ]
        assert len(advice["ranking_proposals"]) == 1
        proposal = advice["ranking_proposals"][0]
        assert proposal["status"] == "pending"
        assert proposal["dimension"] == "company_quality"
        assert proposal["direction"] == "increase"
        assert "interview" in proposal["rationale"]
        assert "rejection" in proposal["rationale"]
        assert proposal["evidence"] == [
            {
                "opportunity_id": 1,
                "company": "Alpha Systems",
                "title": "Junior Backend Engineer",
                "outcome": "interview",
                "dimension_value": 100.0,
            },
            {
                "opportunity_id": 2,
                "company": "Beta Cloud",
                "title": "Junior Backend Engineer",
                "outcome": "rejection",
                "dimension_value": 85.0,
            },
        ]
        assert queue_while_pending["candidates"][0]["score"]["weights"] == (
            queue_before["candidates"][0]["score"]["weights"]
        )

        accepted = await client.post(
            f"/api/strategy-proposals/{proposal['id']}/decision",
            json={"decision": "accepted"},
        )
        queue_after = (await client.get("/api/discovery/queue")).json()

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert queue_after["candidates"][0]["score"]["weights"] == proposal["proposed_weights"]
    assert queue_after["candidates"][0]["score"]["weights"] != (
        queue_before["candidates"][0]["score"]["weights"]
    )


@pytest.mark.anyio
async def test_rejected_proposal_stays_dismissed_instead_of_returning_as_new(
    tmp_path: Path,
    load_fixture: Any,
) -> None:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(app, load_fixture("strategy_advice.json")["jobs"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": load_fixture("profile.json"), "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        await record_outcome(client, 1, "interview")
        await record_outcome(client, 2, "rejection")
        first = (await client.get("/api/strategy-advice")).json()["ranking_proposals"][0]
        rejected = await client.post(
            f"/api/strategy-proposals/{first['id']}/decision",
            json={"decision": "rejected"},
        )
        refreshed = (await client.get("/api/strategy-advice")).json()["ranking_proposals"]

    assert rejected.status_code == 200
    assert refreshed == [{**first, "status": "rejected"}]


@pytest.mark.anyio
async def test_latest_recorded_outcome_drives_proposal_evidence_and_mixed_labels_are_honest(
    tmp_path: Path,
    load_fixture: Any,
) -> None:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'jobinator.db'}")
    configure_fixture_discovery(app, load_fixture("strategy_advice.json")["jobs"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.put(
            "/api/profile",
            json={"profile": load_fixture("profile.json"), "expected_version": None},
        )
        await client.post("/api/discovery/ingest")
        await record_outcome(client, 1, "interview")
        await client.post(
            "/api/application-workflow/1/transitions",
            json={
                "target_stage": "outcome",
                "outcome_type": "rejection",
                "outcome": "Rejected after interview.",
            },
        )
        await record_outcome(client, 2, "response")
        await record_outcome(client, 3, "interview")

        proposal = (await client.get("/api/strategy-advice")).json()[
            "ranking_proposals"
        ][0]

    assert "interview and response outcomes" in proposal["rationale"]
    assert [entry["outcome"] for entry in proposal["evidence"]] == [
        "rejection",
        "response",
        "interview",
    ]
