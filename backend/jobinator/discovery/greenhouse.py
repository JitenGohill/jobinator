from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from jobinator.discovery.models import JobSnapshot, SourceConfiguration


class SourceFetchError(Exception):
    pass


class SourceNormalizationError(Exception):
    pass


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


class _PostingTextParser(HTMLParser):
    _REQUIREMENT_HEADINGS = ("requirement", "qualification", "what we're looking for")
    _BLOCK_TAGS = {"div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p"}

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.requirements: list[str] = []
        self._line_parts: list[str] = []
        self._heading_parts: list[str] | None = None
        self._strong_parts: list[str] | None = None
        self._list_item_parts: list[str] | None = None
        self._current_heading = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._BLOCK_TAGS:
            self._flush_line()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_parts = []
        elif tag == "li":
            self._list_item_parts = []
        elif tag == "strong":
            self._strong_parts = []
        elif tag == "br":
            self._flush_line()

    def handle_data(self, data: str) -> None:
        self._line_parts.append(data)
        if self._heading_parts is not None:
            self._heading_parts.append(data)
        if self._strong_parts is not None:
            self._strong_parts.append(data)
        if self._list_item_parts is not None:
            self._list_item_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading_parts is not None:
            heading = self._clean(self._heading_parts)
            self._current_heading = heading.lower()
            self._heading_parts = None
        elif tag == "li" and self._list_item_parts is not None:
            item = self._clean(self._list_item_parts)
            if item and any(
                marker in self._current_heading for marker in self._REQUIREMENT_HEADINGS
            ):
                self.requirements.append(item)
            self._list_item_parts = None
        elif tag == "strong" and self._strong_parts is not None:
            emphasized_text = self._clean(self._strong_parts)
            if self._list_item_parts is None:
                self._current_heading = emphasized_text.lower()
            self._strong_parts = None

        if tag in self._BLOCK_TAGS:
            self._flush_line()

    @staticmethod
    def _clean(parts: list[str]) -> str:
        return " ".join(" ".join(parts).split())

    def _flush_line(self) -> None:
        value = self._clean(self._line_parts)
        if value:
            self.lines.append(value)
        self._line_parts = []


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
        parser = _PostingTextParser()
        parser.feed(job.content)
        return JobSnapshot(
            source_url=job.absolute_url,
            fetched_at=fetched_at,
            company=source.company,
            title=job.title,
            location=job.location.name,
            description_text="\n".join(parser.lines),
            detected_requirements=parser.requirements,
            source_platform="greenhouse",
            ats_posting_id=str(job.id) if job.id is not None else None,
            canonical_url=job.absolute_url,
            raw_posting=raw_posting,
        )
