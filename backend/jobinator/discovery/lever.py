from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from jobinator.discovery.errors import SourceFetchError, SourceNormalizationError
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.posting_text import parse_posting_html


class _LeverCategories(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location: str


class _LeverList(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    content: str


class _LeverPosting(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    text: str
    categories: _LeverCategories
    descriptionPlain: str
    lists: list[_LeverList]
    hostedUrl: HttpUrl


class LeverAdapter:
    platform = "lever"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        url = f"https://api.lever.co/v0/postings/{source.identifier}"
        try:
            response = await self._client.get(url, params={"mode": "json"})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SourceFetchError(
                f"Lever request failed ({type(error).__name__})."
            ) from error

        try:
            payload: Any = response.json()
            if not isinstance(payload, list) or not all(
                isinstance(raw_posting, dict) for raw_posting in payload
            ):
                raise SourceNormalizationError("Lever returned an invalid posting.")
            postings = [_LeverPosting.model_validate(raw_posting) for raw_posting in payload]
            return [
                self._normalize(posting, raw_posting, source, fetched_at)
                for posting, raw_posting in zip(postings, payload, strict=True)
            ]
        except (ValueError, ValidationError) as error:
            raise SourceNormalizationError("Lever returned an invalid posting.") from error

    @staticmethod
    def _normalize(
        posting: _LeverPosting,
        raw_posting: dict[str, Any],
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> JobSnapshot:
        list_html = "".join(
            f"<h2>{escape(posting_list.text)}</h2>{posting_list.content}"
            for posting_list in posting.lists
        )
        list_lines, requirements = parse_posting_html(list_html)
        description_lines = [posting.descriptionPlain.strip(), *list_lines]
        canonical_url = str(posting.hostedUrl)
        return JobSnapshot(
            source_url=canonical_url,
            fetched_at=fetched_at,
            company=source.company,
            title=posting.text,
            location=posting.categories.location,
            description_text="\n".join(line for line in description_lines if line),
            detected_requirements=requirements,
            source_platform="lever",
            ats_posting_id=posting.id,
            canonical_url=canonical_url,
            raw_posting=raw_posting,
        )
