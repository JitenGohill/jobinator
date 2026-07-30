from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session, sessionmaker

from jobinator.config import Settings
from jobinator.discovery.ashby import AshbyAdapter
from jobinator.discovery.greenhouse import GreenhouseAdapter
from jobinator.discovery.lever import LeverAdapter
from jobinator.discovery.models import SourceConfiguration
from jobinator.discovery.module import DiscoveryModule


def create_discovery_module(
    sessions: sessionmaker[Session],
    settings: Settings,
    source_client: httpx.AsyncClient,
    clock: Callable[[], datetime] | None = None,
) -> DiscoveryModule:
    sources = []
    if settings.greenhouse_board_token and settings.greenhouse_company:
        sources.append(
            SourceConfiguration(
                platform="greenhouse",
                identifier=settings.greenhouse_board_token,
                company=settings.greenhouse_company,
            )
        )
    if settings.lever_site and settings.lever_company:
        sources.append(
            SourceConfiguration(
                platform="lever",
                identifier=settings.lever_site,
                company=settings.lever_company,
            )
        )
    if settings.ashby_board and settings.ashby_company:
        sources.append(
            SourceConfiguration(
                platform="ashby",
                identifier=settings.ashby_board,
                company=settings.ashby_company,
            )
        )
    return DiscoveryModule(
        sessions=sessions,
        sources=sources,
        adapters={
            "greenhouse": GreenhouseAdapter(source_client),
            "lever": LeverAdapter(source_client),
            "ashby": AshbyAdapter(source_client),
        },
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )
