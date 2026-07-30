from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from jobinator.config import Settings
from jobinator.database import Base, create_database_engine, create_session_factory
from jobinator.discovery.models import CandidateQueue, IngestionResult, ScreenedOpportunity
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


def create_app(
    database_url: str | None = None,
    settings: Settings | None = None,
    source_client: httpx.AsyncClient | None = None,
    clock: Callable[[], datetime] | None = None,
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
    return app


app = create_app()
