from __future__ import annotations

import json
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from jobinator.discovery.errors import SourceFetchError, SourceNormalizationError
from jobinator.discovery.http_source import fetch_reachable_source
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.normalization import required_string
from jobinator.discovery.posting_text import parse_posting_html


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.documents: list[str] = []
        self._parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attributes = {key.lower(): (value or "").lower() for key, value in attrs}
        if attributes.get("type") == "application/ld+json":
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._parts is not None:
            self.documents.append("".join(self._parts))
            self._parts = None


class CompanyCareerAdapter:
    platform = "company"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        url = _validated_https_url(source.identifier, "Company career page")
        response = await fetch_reachable_source(
            self._client,
            url,
            source_label="Company career page",
            posting_label="Company career posting",
        )

        posting = find_job_posting(response.text)
        if posting is None:
            raise SourceNormalizationError(
                "Company career page structure is unsupported; expected schema.org "
                "JobPosting data. Browser automation was not attempted."
            )
        return [normalize_job_posting(posting, source, fetched_at)]


def _validated_https_url(value: str, label: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise SourceFetchError(f"{label} URL must be a public HTTPS URL.")
    return value


def find_job_posting(content: str) -> dict[str, Any] | None:
    parser = _JsonLdParser()
    parser.feed(content)
    for document in parser.documents:
        try:
            payload: Any = json.loads(document)
        except json.JSONDecodeError:
            continue
        for item in _json_ld_items(payload):
            posting_type = item.get("@type")
            types = posting_type if isinstance(posting_type, list) else [posting_type]
            if "JobPosting" in types:
                return item
    return None


def _json_ld_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            item
            for nested in payload
            for item in _json_ld_items(nested)
        ]
    if not isinstance(payload, dict):
        return []
    items = [payload]
    graph = payload.get("@graph")
    if isinstance(graph, list):
        items.extend(item for item in graph if isinstance(item, dict))
    return items


def normalize_job_posting(
    posting: dict[str, Any],
    source: SourceConfiguration,
    fetched_at: datetime,
) -> JobSnapshot:
    title = required_string(posting, "title", _unsupported_structure)
    description = required_string(posting, "description", _unsupported_structure)
    company = _nested_string(posting, "hiringOrganization", "name")
    canonical_url = posting.get("url", source.identifier)
    if not isinstance(canonical_url, str):
        raise _unsupported_structure()
    canonical_url = _validated_https_url(canonical_url, "Company career canonical")
    description_lines, requirements = parse_posting_html(description)
    if not description_lines:
        raise _unsupported_structure()
    return JobSnapshot(
        source_url=source.identifier,
        fetched_at=fetched_at,
        company=company,
        title=title,
        location=_job_location(posting),
        description_text="\n".join(description_lines),
        detected_requirements=requirements,
        source_platform="company",
        ats_posting_id=_posting_id(posting),
        canonical_url=canonical_url,
        raw_posting=posting,
    )


def _nested_string(payload: dict[str, Any], key: str, nested_key: str) -> str:
    nested = payload.get(key)
    if not isinstance(nested, dict):
        raise _unsupported_structure()
    return required_string(nested, nested_key, _unsupported_structure)


def _posting_id(posting: dict[str, Any]) -> str | None:
    identifier = posting.get("identifier")
    if isinstance(identifier, (str, int)):
        return str(identifier)
    if isinstance(identifier, dict):
        value = identifier.get("value")
        if isinstance(value, (str, int)):
            return str(value)
    return None


def _job_location(posting: dict[str, Any]) -> str:
    location = posting.get("jobLocation")
    if isinstance(location, list):
        location = next((item for item in location if isinstance(item, dict)), None)
    if isinstance(location, dict):
        address = location.get("address")
        if isinstance(address, str) and address.strip():
            return address.strip()
        if isinstance(address, dict):
            locality = address.get("addressLocality")
            region = address.get("addressRegion")
            parts = [
                value.strip()
                for value in (locality, region)
                if isinstance(value, str) and value.strip()
            ]
            if parts:
                return ", ".join(parts)
    job_location_type = posting.get("jobLocationType")
    if job_location_type == "TELECOMMUTE":
        return "Remote"
    return "Location not specified"


def _unsupported_structure() -> SourceNormalizationError:
    return SourceNormalizationError(
        "Company career page structure is unsupported; expected schema.org "
        "JobPosting data. Browser automation was not attempted."
    )
