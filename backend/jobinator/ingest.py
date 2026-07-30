from __future__ import annotations

import asyncio
import sys
from typing import TextIO

import httpx

from jobinator.config import Settings
from jobinator.database import Base, create_database_engine, create_session_factory
from jobinator.discovery.module import DiscoveryModule, SourceNotConfiguredError
from jobinator.discovery.runtime import create_discovery_module


async def run_ingestion(module: DiscoveryModule, output: TextIO) -> int:
    try:
        result = await module.ingest_configured()
    except SourceNotConfiguredError:
        output.write("No job source is configured.\n")
        return 2
    noun = "job snapshot" if result.discovered == 1 else "job snapshots"
    output.write(f"Discovered {result.discovered} {noun}.\n")
    for source in result.sources:
        if source.status == "succeeded":
            output.write(
                f"{source.platform} ({source.identifier}): "
                f"discovered {source.discovered}.\n"
            )
        else:
            output.write(
                f"{source.platform} ({source.identifier}): failed: {source.error}\n"
            )
    return 1 if any(source.status == "failed" for source in result.sources) else 0


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
