from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session, sessionmaker

from jobinator.config import Settings
from jobinator.discovery.greenhouse import GreenhouseAdapter
from jobinator.discovery.models import SourceConfiguration
from jobinator.discovery.module import DiscoveryModule


def create_discovery_module(
    sessions: sessionmaker[Session],
    settings: Settings,
    source_client: httpx.AsyncClient,
    clock: Callable[[], datetime] | None = None,
) -> DiscoveryModule:
    sources = (
        [
            SourceConfiguration(
                platform="greenhouse",
                identifier=settings.greenhouse_board_token,
                company=settings.greenhouse_company,
            )
        ]
        if settings.greenhouse_board_token and settings.greenhouse_company
        else []
    )
    return DiscoveryModule(
        sessions=sessions,
        sources=sources,
        adapters={"greenhouse": GreenhouseAdapter(source_client)},
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )
