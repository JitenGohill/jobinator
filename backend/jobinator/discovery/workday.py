from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from jobinator.discovery.errors import SourceFetchError, SourceNormalizationError
from jobinator.discovery.http_source import fetch_reachable_source
from jobinator.discovery.models import JobSnapshot, SourceConfiguration
from jobinator.discovery.normalization import required_string
from jobinator.discovery.posting_text import parse_posting_html


class WorkdayAdapter:
    platform = "workday"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        api_url, tenant = _workday_api_url(source.identifier)
        response = await fetch_reachable_source(
            self._client,
            api_url,
            source_label="Workday",
            posting_label="Workday posting",
        )

        try:
            payload: Any = response.json()
        except ValueError as error:
            raise _unsupported_structure() from error
        if not isinstance(payload, dict):
            raise _unsupported_structure()
        posting = payload.get("jobPostingInfo")
        if not isinstance(posting, dict):
            raise _unsupported_structure()
        return [_normalize(posting, source.identifier, tenant, fetched_at)]


def _workday_api_url(posting_url: str) -> tuple[str, str]:
    parts = urlsplit(posting_url)
    hostname = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or not hostname.endswith(".myworkdayjobs.com")
        or parts.username
        or parts.password
    ):
        raise SourceFetchError(
            "Workday posting URL must be a public HTTPS myworkdayjobs.com URL."
        )
    path_segments = [segment for segment in parts.path.split("/") if segment]
    try:
        job_index = path_segments.index("job")
    except ValueError as error:
        raise SourceFetchError(
            "Workday posting URL is unsupported; expected a direct /job/ URL."
        ) from error
    if job_index < 1 or job_index == len(path_segments) - 1:
        raise SourceFetchError(
            "Workday posting URL is unsupported; expected a direct /job/ URL."
        )
    site = path_segments[job_index - 1]
    job_path = "/".join(path_segments[job_index + 1 :])
    tenant = hostname.split(".", maxsplit=1)[0]
    api_path = f"/wday/cxs/{tenant}/{site}/job/{job_path}"
    return urlunsplit(("https", parts.netloc, api_path, "", "")), tenant


def _normalize(
    posting: dict[str, Any],
    source_url: str,
    tenant: str,
    fetched_at: datetime,
) -> JobSnapshot:
    title = required_string(posting, "title", _unsupported_structure)
    description = required_string(posting, "jobDescription", _unsupported_structure)
    location = required_string(posting, "location", _unsupported_structure)
    company_value = posting.get("company")
    company = (
        company_value.strip()
        if isinstance(company_value, str) and company_value.strip()
        else tenant
    )
    canonical_value = posting.get("externalUrl", source_url)
    if not isinstance(canonical_value, str):
        raise _unsupported_structure()
    canonical_url = _absolute_canonical_url(source_url, canonical_value)
    description_lines, requirements = parse_posting_html(description)
    if not description_lines:
        raise _unsupported_structure()
    posting_id = posting.get("id") or posting.get("jobReqId") or posting.get("jobRequisitionId")
    return JobSnapshot(
        source_url=source_url,
        fetched_at=fetched_at,
        company=company,
        title=title,
        location=location,
        description_text="\n".join(description_lines),
        detected_requirements=requirements,
        source_platform="workday",
        ats_posting_id=str(posting_id) if posting_id is not None else None,
        canonical_url=canonical_url,
        raw_posting=posting,
    )


def _absolute_canonical_url(source_url: str, canonical_value: str) -> str:
    canonical_parts = urlsplit(canonical_value)
    if not canonical_parts.scheme and canonical_value.startswith("/"):
        source_parts = urlsplit(source_url)
        canonical_value = urlunsplit(
            ("https", source_parts.netloc, canonical_value, "", "")
        )
        canonical_parts = urlsplit(canonical_value)
    if (
        canonical_parts.scheme != "https"
        or not canonical_parts.hostname
        or canonical_parts.username
        or canonical_parts.password
    ):
        raise _unsupported_structure()
    return canonical_value


def _unsupported_structure() -> SourceNormalizationError:
    return SourceNormalizationError(
        "Workday returned an unrecognized posting structure. "
        "Browser automation was not attempted."
    )
