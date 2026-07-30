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
    company: str | None = Field(default=None, min_length=1)

    def require_company(self) -> str:
        if self.company is None:
            raise ValueError("Source company is not configured.")
        return self.company


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


class ScoreDimension(DiscoveryModel):
    value: float = Field(ge=0, le=100)
    explanation: str = Field(min_length=1)


class OpportunityScore(DiscoveryModel):
    total: float = Field(ge=0, le=100)
    weights: dict[str, float]
    eligibility: ScoreDimension
    role_fit: ScoreDimension
    skill_overlap: ScoreDimension
    company_quality: ScoreDimension
    application_effort: ScoreDimension


class ScoredOpportunity(ScreenedOpportunity):
    score: OpportunityScore


class QueueTarget(DiscoveryModel):
    minimum: int = Field(ge=1)
    maximum: int = Field(ge=1)


class QueueCriteria(DiscoveryModel):
    minimum_score: int = Field(ge=0, le=100)
    include_maybe: bool


class ExpansionLever(DiscoveryModel):
    id: Literal["include_maybe", "minimum_score"]
    label: str
    description: str
    criteria: QueueCriteria


class CandidateQueue(DiscoveryModel):
    target: QueueTarget
    criteria: QueueCriteria
    candidates: list[ScoredOpportunity]
    not_queued: list[ScoredOpportunity]
    shortfall: int = Field(ge=0)
    summary: str
    expansion_levers: list[ExpansionLever]


class SourceIngestionDiagnostic(DiscoveryModel):
    platform: SourcePlatform
    identifier: str
    status: Literal["succeeded", "failed"]
    discovered: int = Field(ge=0)
    error: str | None


class IngestionResult(DiscoveryModel):
    discovered: int = Field(ge=0)
    sources: list[SourceIngestionDiagnostic]
