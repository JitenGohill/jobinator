from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Request, status

from jobinator.config import Settings
from jobinator.database import Base, create_database_engine, create_session_factory
from jobinator.profile.models import SavedProfile, SaveProfileRequest
from jobinator.profile.module import (
    ProfileModule,
    ProfileNotFoundError,
    ProfileVersionConflictError,
)


async def get_profile_module(request: Request) -> ProfileModule:
    return cast(ProfileModule, request.app.state.profile_module)


ProfileDependency = Annotated[ProfileModule, Depends(get_profile_module)]


def create_app(
    database_url: str | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    engine = create_database_engine(database_url or resolved_settings.database_url)
    Base.metadata.create_all(engine)
    sessions = create_session_factory(engine)
    profile_module = ProfileModule(sessions)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Jobinator", version="0.1.0", lifespan=lifespan)
    app.state.database_engine = engine
    app.state.profile_module = profile_module
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

    return app


app = create_app()
