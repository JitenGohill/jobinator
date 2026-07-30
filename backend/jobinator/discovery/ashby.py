from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, ValidationError

from jobinator.discovery.errors import SourceFetchError, SourceNormalizationError
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.posting_text import parse_posting_html


class _AshbyJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    location: str
    descriptionHtml: str
    jobUrl: HttpUrl


class _AshbyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jobs: list[_AshbyJob]


class AshbyAdapter:
    platform = "ashby"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{source.identifier}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SourceFetchError(
                f"Ashby request failed ({type(error).__name__})."
            ) from error

        try:
            payload: Any = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                raise SourceNormalizationError("Ashby returned an invalid posting.")
            raw_jobs = payload["jobs"]
            if not all(isinstance(raw_job, dict) for raw_job in raw_jobs):
                raise SourceNormalizationError("Ashby returned an invalid posting.")
            ashby_response = _AshbyResponse.model_validate(payload)
            return [
                self._normalize(job, raw_job, source, fetched_at)
                for job, raw_job in zip(ashby_response.jobs, raw_jobs, strict=True)
            ]
        except (ValueError, ValidationError) as error:
            raise SourceNormalizationError("Ashby returned an invalid posting.") from error

    @staticmethod
    def _normalize(
        job: _AshbyJob,
        raw_posting: dict[str, Any],
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> JobSnapshot:
        description_lines, requirements = parse_posting_html(job.descriptionHtml)
        canonical_url = str(job.jobUrl)
        posting_id = urlsplit(canonical_url).path.rstrip("/").rsplit("/", maxsplit=1)[-1]
        if not posting_id:
            raise SourceNormalizationError("Ashby returned an invalid posting.")
        return JobSnapshot(
            source_url=canonical_url,
            fetched_at=fetched_at,
            company=source.company,
            title=job.title,
            location=job.location,
            description_text="\n".join(description_lines),
            detected_requirements=requirements,
            source_platform="ashby",
            ats_posting_id=posting_id,
            canonical_url=canonical_url,
            raw_posting=raw_posting,
        )
