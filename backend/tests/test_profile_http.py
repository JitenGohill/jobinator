from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from jobinator.main import create_app


def load_profile_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).parent / "fixtures" / "profile.json"
    return json.loads(fixture_path.read_text())


@pytest.mark.anyio
async def test_profile_survives_restart_and_can_be_updated(tmp_path: Path) -> None:
    database_path = tmp_path / "jobinator.db"
    database_url = f"sqlite:///{database_path}"
    profile = load_profile_fixture()

    first_app = create_app(database_url=database_url)
    async with AsyncClient(
        transport=ASGITransport(app=first_app),
        base_url="http://test",
    ) as client:
        missing_response = await client.get("/api/profile")
        assert missing_response.status_code == 404

        create_response = await client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": None},
        )
        assert create_response.status_code == 200
        assert create_response.json()["profile"] == profile
        assert create_response.json()["version"] == 1

    restarted_app = create_app(database_url=database_url)
    async with AsyncClient(
        transport=ASGITransport(app=restarted_app),
        base_url="http://test",
    ) as restarted_client:
        read_response = await restarted_client.get("/api/profile")
        assert read_response.status_code == 200
        assert read_response.json()["profile"] == profile
        assert read_response.json()["version"] == 1

        updated_profile = {
            **profile,
            "preferred_stack": [*profile["preferred_stack"], "PostgreSQL"],
        }
        update_response = await restarted_client.put(
            "/api/profile",
            json={"profile": updated_profile, "expected_version": 1},
        )
        assert update_response.status_code == 200
        assert update_response.json()["profile"] == updated_profile
        assert update_response.json()["version"] == 2

        stale_response = await restarted_client.put(
            "/api/profile",
            json={"profile": profile, "expected_version": 1},
        )
        assert stale_response.status_code == 409

        unchanged_response = await restarted_client.get("/api/profile")
        assert unchanged_response.json()["profile"] == updated_profile
        assert unchanged_response.json()["version"] == 2
