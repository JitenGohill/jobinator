from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ScreeningLane = Literal["eligible", "stretch", "maybe", "rejected"]
SourcePlatform = Annotated[str, Field(min_length=1)]


class DiscoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceConfiguration(DiscoveryModel):
    platform: SourcePlatform
    identifier: str = Field(min_length=1)
    company: str = Field(min_length=1)


class JobSnapshot(DiscoveryModel):
    id: int | None = Field(default=None, ge=1)
    source_url: str
    fetched_at: datetime
    company: str
    title: str
    location: str
    description_text: str
    detected_requirements: list[str]
    source_platform: SourcePlatform
    ats_posting_id: str | None
    canonical_url: str
    raw_posting: dict[str, Any]


class ScreeningResult(DiscoveryModel):
    lane: ScreeningLane
    reasons: list[str]


class ScreenedJob(JobSnapshot):
    screening: ScreeningResult


class Opportunity(JobSnapshot):
    preferred_apply_url: str
    snapshots: list[JobSnapshot] = Field(min_length=1)


class ScreenedOpportunity(Opportunity):
    screening: ScreeningResult


class SourceIngestionDiagnostic(DiscoveryModel):
    platform: SourcePlatform
    identifier: str
    status: Literal["succeeded", "failed"]
    discovered: int = Field(ge=0)
    error: str | None


class IngestionResult(DiscoveryModel):
    discovered: int = Field(ge=0)
    sources: list[SourceIngestionDiagnostic]
