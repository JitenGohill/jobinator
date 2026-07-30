from __future__ import annotations

from io import StringIO
from pathlib import Path

import httpx
import pytest
from test_discovery_http import (
    load_ashby_fixture,
    load_greenhouse_fixture,
    load_lever_fixture,
)

from jobinator.config import Settings
from jobinator.database import Base, create_database_engine, create_session_factory
from jobinator.discovery.runtime import create_discovery_module
from jobinator.ingest import run_ingestion


@pytest.mark.anyio
async def test_ingestion_command_uses_the_configured_source_adapter(tmp_path: Path) -> None:
    fixture = load_greenhouse_fixture()
    source_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=fixture))
    )
    engine = create_database_engine(f"sqlite:///{tmp_path / 'jobinator.db'}")
    Base.metadata.create_all(engine)
    module = create_discovery_module(
        sessions=create_session_factory(engine),
        settings=Settings(
            greenhouse_board_token="acme",
            greenhouse_company="Acme Corp",
        ),
        source_client=source_client,
    )
    output = StringIO()

    exit_code = await run_ingestion(module, output)

    assert exit_code == 0
    assert output.getvalue() == (
        "Discovered 1 job snapshot.\n"
        "greenhouse (acme): discovered 1.\n"
    )
    assert [snapshot.title for snapshot in module.list_discovered()] == [
        "Junior Software Engineer"
    ]
    await source_client.aclose()
    engine.dispose()


@pytest.mark.anyio
async def test_ingestion_command_reports_each_successful_and_failed_source(
    tmp_path: Path,
) -> None:
    lever_fixture = load_lever_fixture()
    ashby_fixture = load_ashby_fixture()

    def source_response(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.lever.co":
            return httpx.Response(200, json=lever_fixture["postings"])
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(200, json=ashby_fixture["malformed_response"])
        raise AssertionError(f"Unexpected source URL: {request.url}")

    source_client = httpx.AsyncClient(transport=httpx.MockTransport(source_response))
    engine = create_database_engine(f"sqlite:///{tmp_path / 'jobinator.db'}")
    Base.metadata.create_all(engine)
    module = create_discovery_module(
        sessions=create_session_factory(engine),
        settings=Settings(
            lever_site="acme",
            lever_company="Acme Corp",
            ashby_board="acme",
            ashby_company="Acme Corp",
        ),
        source_client=source_client,
    )
    output = StringIO()

    exit_code = await run_ingestion(module, output)

    assert exit_code == 1
    assert output.getvalue() == (
        "Discovered 1 job snapshot.\n"
        "lever (acme): discovered 1.\n"
        "ashby (acme): failed: Ashby returned an invalid posting.\n"
    )
    assert [snapshot.source_platform for snapshot in module.list_discovered()] == [
        "lever"
    ]
    await source_client.aclose()
    engine.dispose()
