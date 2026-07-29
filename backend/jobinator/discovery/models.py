from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceConfiguration(DiscoveryModel):
    platform: Literal["greenhouse"]
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
    source_platform: Literal["greenhouse"]
    ats_posting_id: str | None
    canonical_url: str
    raw_posting: dict[str, Any]


class IngestionResult(DiscoveryModel):
    discovered: int = Field(ge=0)
