from __future__ import annotations

import asyncio
import sys
from typing import TextIO

import httpx

from jobinator.config import Settings
from jobinator.database import Base, create_database_engine, create_session_factory
from jobinator.discovery.greenhouse import SourceFetchError, SourceNormalizationError
from jobinator.discovery.module import DiscoveryModule, SourceNotConfiguredError
from jobinator.discovery.runtime import create_discovery_module


async def run_ingestion(module: DiscoveryModule, output: TextIO) -> int:
    try:
        result = await module.ingest_configured()
    except SourceNotConfiguredError:
        output.write("No job source is configured.\n")
        return 2
    except (SourceFetchError, SourceNormalizationError):
        output.write("The configured job source could not be ingested.\n")
        return 1

    noun = "job snapshot" if result.discovered == 1 else "job snapshots"
    output.write(f"Discovered {result.discovered} {noun}.\n")
    return 0


async def _run_configured_ingestion() -> int:
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    Base.metadata.create_all(engine)
    try:
        async with httpx.AsyncClient(timeout=20) as source_client:
            module = create_discovery_module(
                sessions=create_session_factory(engine),
                settings=settings,
                source_client=source_client,
            )
            return await run_ingestion(module, sys.stdout)
    finally:
        engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_run_configured_ingestion()))
