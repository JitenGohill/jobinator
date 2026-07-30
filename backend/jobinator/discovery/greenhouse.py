from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from jobinator.discovery.errors import SourceFetchError, SourceNormalizationError
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.posting_text import parse_posting_html


class _GreenhouseLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str


class _GreenhouseJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    absolute_url: str
    content: str
    id: int | str | None = None
    location: _GreenhouseLocation
    title: str


class _GreenhouseResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jobs: list[_GreenhouseJob]


class GreenhouseAdapter:
    platform = "greenhouse"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{source.identifier}/jobs"
        try:
            response = await self._client.get(url, params={"content": "true"})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SourceFetchError(
                f"Greenhouse request failed ({type(error).__name__})."
            ) from error

        try:
            payload: Any = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise SourceNormalizationError("Greenhouse returned an invalid posting.")
            raw_jobs = payload["jobs"]
            if not all(isinstance(raw_job, dict) for raw_job in raw_jobs):
                raise SourceNormalizationError("Greenhouse returned an invalid posting.")
            greenhouse_response = _GreenhouseResponse.model_validate(payload)
            return [
                self._normalize(job, raw_job, source, fetched_at)
                for job, raw_job in zip(
                    greenhouse_response.jobs,
                    raw_jobs,
                    strict=True,
                )
            ]
        except (ValueError, ValidationError) as error:
            raise SourceNormalizationError("Greenhouse returned an invalid posting.") from error

    @staticmethod
    def _normalize(
        job: _GreenhouseJob,
        raw_posting: dict[str, Any],
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> JobSnapshot:
        description_lines, requirements = parse_posting_html(job.content)
        return JobSnapshot(
            source_url=job.absolute_url,
            fetched_at=fetched_at,
            company=source.require_company(),
            title=job.title,
            location=job.location.name,
            description_text="\n".join(description_lines),
            detected_requirements=requirements,
            source_platform="greenhouse",
            ats_posting_id=str(job.id) if job.id is not None else None,
            canonical_url=job.absolute_url,
            raw_posting=raw_posting,
        )
