from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from jobinator.application.models import ApplicationPacket, ApplicationPacketRequest
from jobinator.application.module import (
    ApplicationPacketModule,
    QueuedOpportunityNotFoundError,
)
from jobinator.application.provider import (
    ApplicationContentProvider,
)
from jobinator.application.runtime import (
    ApplicationGenerationRuntime,
    create_application_provider,
)
from jobinator.config import Settings
from jobinator.database import Base, create_database_engine, create_session_factory
from jobinator.discovery.link_sources import DISCOVERY_LINK_SOURCES
from jobinator.discovery.links import DiscoveryLinkIntake
from jobinator.discovery.models import (
    CandidateQueue,
    DiscoveryLink,
    DiscoveryLinkIntakeRequest,
    DiscoveryLinkIntakeResult,
    DiscoveryLinkSource,
    IngestionResult,
    ScreenedOpportunity,
)
from jobinator.discovery.module import DiscoveryModule, SourceNotConfiguredError
from jobinator.discovery.queue import CanonicalProfileRequiredError
from jobinator.discovery.runtime import create_discovery_module
from jobinator.profile.models import SavedProfile, SaveProfileRequest
from jobinator.profile.module import (
    ProfileModule,
    ProfileNotFoundError,
    ProfileVersionConflictError,
)


async def get_profile_module(request: Request) -> ProfileModule:
    return cast(ProfileModule, request.app.state.profile_module)


ProfileDependency = Annotated[ProfileModule, Depends(get_profile_module)]


async def get_discovery_module(request: Request) -> DiscoveryModule:
    return cast(DiscoveryModule, request.app.state.discovery_module)


DiscoveryDependency = Annotated[DiscoveryModule, Depends(get_discovery_module)]


async def get_discovery_link_intake(request: Request) -> DiscoveryLinkIntake:
    return cast(DiscoveryLinkIntake, request.app.state.discovery_link_intake)


DiscoveryLinkDependency = Annotated[DiscoveryLinkIntake, Depends(get_discovery_link_intake)]


async def get_application_module(request: Request) -> ApplicationPacketModule:
    return ApplicationPacketModule(
        profile_module=cast(ProfileModule, request.app.state.profile_module),
        discovery_module=cast(DiscoveryModule, request.app.state.discovery_module),
        generation_runtime=cast(
            ApplicationGenerationRuntime,
            request.app.state.application_generation_runtime,
        ),
    )


ApplicationDependency = Annotated[ApplicationPacketModule, Depends(get_application_module)]


def create_app(
    database_url: str | None = None,
    settings: Settings | None = None,
    source_client: httpx.AsyncClient | None = None,
    clock: Callable[[], datetime] | None = None,
    application_provider: ApplicationContentProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    engine = create_database_engine(database_url or resolved_settings.database_url)
    Base.metadata.create_all(engine)
    sessions = create_session_factory(engine)
    profile_module = ProfileModule(sessions)
    owns_source_client = source_client is None
    resolved_source_client = source_client or httpx.AsyncClient(timeout=20)
    discovery_module = create_discovery_module(
        sessions=sessions,
        settings=resolved_settings,
        source_client=resolved_source_client,
        clock=clock,
    )
    discovery_link_intake = DiscoveryLinkIntake(
        sessions=sessions,
        client=resolved_source_client,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )
    prompt_version = "application-packet-v1"
    prompt = (
        Path(__file__).parent
        / "application"
        / "prompts"
        / f"{prompt_version}.txt"
    ).read_text()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_source_client:
                await resolved_source_client.aclose()
            engine.dispose()

    app = FastAPI(title="Jobinator", version="0.1.0", lifespan=lifespan)
    app.state.database_engine = engine
    app.state.profile_module = profile_module
    app.state.discovery_module = discovery_module
    app.state.discovery_link_intake = discovery_link_intake
    app.state.application_generation_runtime = ApplicationGenerationRuntime(
        provider=(
            application_provider
            or create_application_provider(resolved_settings, resolved_source_client)
        ),
        prompt=prompt,
        prompt_version=prompt_version,
    )
    app.state.settings = resolved_settings

    @app.get("/api/profile", response_model=SavedProfile)
    async def get_profile(module: ProfileDependency) -> SavedProfile:
        try:
            return module.get_profile()
        except ProfileNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canonical profile has not been created.",
            ) from error

    @app.put("/api/profile", response_model=SavedProfile)
    async def save_profile(
        request: SaveProfileRequest,
        module: ProfileDependency,
    ) -> SavedProfile:
        try:
            return module.save_profile(request.profile, request.expected_version)
        except ProfileVersionConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The canonical profile was changed by another request.",
            ) from error

    @app.get("/api/discovery/jobs", response_model=list[ScreenedOpportunity])
    async def list_discovered(module: DiscoveryDependency) -> list[ScreenedOpportunity]:
        return module.list_discovered()

    @app.post("/api/discovery/ingest", response_model=IngestionResult)
    async def ingest_discovered(module: DiscoveryDependency) -> IngestionResult:
        try:
            return await module.ingest_configured()
        except SourceNotConfiguredError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No job source is configured.",
            ) from error

    @app.get("/api/discovery/queue", response_model=CandidateQueue)
    async def get_candidate_queue(
        module: DiscoveryDependency,
        minimum_score: Annotated[int, Query(ge=0, le=100)] = 60,
        include_maybe: bool = False,
    ) -> CandidateQueue:
        try:
            return module.build_daily_queue(
                minimum_score=minimum_score,
                include_maybe=include_maybe,
            )
        except CanonicalProfileRequiredError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Save the canonical profile before generating a candidate queue.",
            ) from error

    @app.post(
        "/api/application-packets/{opportunity_id}",
        response_model=ApplicationPacket,
    )
    async def generate_application_packet(
        opportunity_id: int,
        packet_request: ApplicationPacketRequest,
        module: ApplicationDependency,
    ) -> ApplicationPacket:
        try:
            return await module.generate_packet(opportunity_id, packet_request)
        except QueuedOpportunityNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The opportunity is not in the current candidate queue.",
            ) from error

    @app.get("/api/discovery/links", response_model=list[DiscoveryLink])
    async def list_discovery_links(
        intake: DiscoveryLinkDependency,
    ) -> list[DiscoveryLink]:
        return intake.list()

    @app.get("/api/discovery/link-sources", response_model=list[DiscoveryLinkSource])
    async def list_discovery_link_sources() -> list[DiscoveryLinkSource]:
        return [
            DiscoveryLinkSource(
                id=source.id,
                label=source.label,
                domains=list(source.domains),
            )
            for source in DISCOVERY_LINK_SOURCES
        ]

    @app.post("/api/discovery/links", response_model=DiscoveryLinkIntakeResult)
    async def add_discovery_links(
        request: DiscoveryLinkIntakeRequest,
        intake: DiscoveryLinkDependency,
    ) -> DiscoveryLinkIntakeResult:
        return await intake.add(request)
    return app


app = create_app()
