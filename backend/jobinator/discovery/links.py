from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobinator.database import DiscoveryLinkRow
from jobinator.discovery.ashby import AshbyAdapter
from jobinator.discovery.company_career import (
    CompanyCareerAdapter,
    find_job_posting,
    normalize_job_posting,
)
from jobinator.discovery.errors import SourceDiscoveryError
from jobinator.discovery.greenhouse import GreenhouseAdapter
from jobinator.discovery.http_source import fetch_reachable_source
from jobinator.discovery.lever import LeverAdapter
from jobinator.discovery.link_sources import identify_discovery_link_source
from jobinator.discovery.models import (
    DiscoveryLink,
    DiscoveryLinkIntakeRequest,
    DiscoveryLinkIntakeResult,
    DiscoveryLinkSubmission,
    JobSnapshot,
    SourceConfiguration,
)
from jobinator.discovery.persistence import snapshot_row
from jobinator.discovery.workday import WorkdayAdapter

_LINKEDIN_MANUAL_REVIEW = (
    "LinkedIn links are preserved for manual review; automated LinkedIn browsing "
    "was not attempted."
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LinkOutcome:
    submission: DiscoveryLinkSubmission
    platform: str
    snapshot: JobSnapshot | None
    reason: str | None


class _PostingAdapter(Protocol):
    platform: str

    def discover(
        self,
        source: SourceConfiguration,
        fetched_at: datetime,
    ) -> Awaitable[list[JobSnapshot]]: ...


@dataclass(frozen=True)
class _AtsRoute:
    domains: tuple[str, ...]
    adapter: Callable[[httpx.AsyncClient], _PostingAdapter]
    direct_posting: bool = False

    def matches(self, hostname: str) -> bool:
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.domains
        )


_ATS_ROUTES: tuple[_AtsRoute, ...] = (
    _AtsRoute(
        ("boards.greenhouse.io", "job-boards.greenhouse.io"),
        GreenhouseAdapter,
    ),
    _AtsRoute(("jobs.lever.co",), LeverAdapter),
    _AtsRoute(("jobs.ashbyhq.com",), AshbyAdapter),
    _AtsRoute(("myworkdayjobs.com",), WorkdayAdapter, direct_posting=True),
)


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


class DiscoveryLinkIntake:
    """Preserve user-submitted discovery links and resolve reachable postings."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        client: httpx.AsyncClient,
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._client = client
        self._clock = clock

    async def add(self, request: DiscoveryLinkIntakeRequest) -> DiscoveryLinkIntakeResult:
        created_at = self._clock()
        outcomes: list[_LinkOutcome] = []
        for submission in request.links:
            detected_platform = identify_discovery_link_source(submission.url)
            platform = submission.source_platform or detected_platform
            outcomes.append(
                _LinkOutcome(submission, platform, None, _LINKEDIN_MANUAL_REVIEW)
                if platform == "linkedin" or detected_platform == "linkedin"
                else await self._resolve(submission, platform, created_at)
            )
        with self._sessions.begin() as session:
            rows = []
            discovered = 0
            for outcome in outcomes:
                snapshot_id = None
                resolved_url = None
                if outcome.snapshot is not None:
                    persisted_snapshot = snapshot_row(outcome.snapshot)
                    session.add(persisted_snapshot)
                    session.flush()
                    snapshot_id = persisted_snapshot.id
                    resolved_url = outcome.snapshot.canonical_url
                    discovered += 1
                row = DiscoveryLinkRow(
                    url=outcome.submission.url,
                    source_platform=outcome.platform,
                    status="resolved" if outcome.snapshot is not None else "unresolved",
                    resolved_url=resolved_url,
                    snapshot_id=snapshot_id,
                    reason=outcome.reason,
                    created_at=created_at,
                )
                session.add(row)
                rows.append(row)
            session.flush()
            links = [self._to_link(row) for row in rows]
        return DiscoveryLinkIntakeResult(discovered=discovered, links=links)

    async def _resolve(
        self,
        submission: DiscoveryLinkSubmission,
        platform: str,
        fetched_at: datetime,
    ) -> _LinkOutcome:
        url = submission.url
        label = platform.replace("-", " ").title()
        try:
            response = await fetch_reachable_source(
                self._client,
                url,
                source_label=label,
                posting_label=f"{label} listing",
            )
        except SourceDiscoveryError as error:
            return _LinkOutcome(
                submission,
                platform,
                None,
                f"{error} Open the source link for manual review.",
            )
        for official_url in _official_links(response.text, str(response.url)):
            try:
                snapshots = await self._discover_official(official_url, fetched_at)
            except Exception as error:
                logger.warning(
                    "Discovery-link resolution failed for %s destination (%s).",
                    platform,
                    type(error).__name__,
                )
                snapshots = []
            if snapshots:
                return _LinkOutcome(
                    submission,
                    platform,
                    _with_provenance(snapshots[0], url, platform),
                    None,
                )
        posting = find_job_posting(response.text)
        if posting is not None:
            try:
                normalized = normalize_job_posting(
                    posting,
                    SourceConfiguration(platform="company", identifier=url),
                    fetched_at,
                )
            except SourceDiscoveryError:
                normalized = None
            if normalized is not None:
                return _LinkOutcome(
                    submission,
                    platform,
                    _with_provenance(normalized, url, platform),
                    None,
                )
        return _LinkOutcome(
            submission,
            platform,
            None,
            f"{label} did not expose a reachable official posting. "
            "Open the source link for manual review.",
        )

    async def _discover_official(
        self,
        official_url: str,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        parts = urlsplit(official_url)
        host = (parts.hostname or "").lower()
        path_parts = [part for part in parts.path.split("/") if part]
        ats_route = _ats_route(host)
        if ats_route is not None:
            adapter = ats_route.adapter(self._client)
            if ats_route.direct_posting:
                return await adapter.discover(
                    SourceConfiguration(
                        platform=adapter.platform,
                        identifier=official_url,
                    ),
                    fetched_at,
                )
            return await self._discover_board_posting(
                adapter,
                path_parts,
                official_url,
                fetched_at,
            )
        return await CompanyCareerAdapter(self._client).discover(
            SourceConfiguration(platform="company", identifier=official_url),
            fetched_at,
        )

    async def _discover_board_posting(
        self,
        adapter: _PostingAdapter,
        path_parts: list[str],
        official_url: str,
        fetched_at: datetime,
    ) -> list[JobSnapshot]:
        if len(path_parts) < 2:
            return []
        identifier = path_parts[0]
        snapshots = await adapter.discover(
            SourceConfiguration(
                platform=adapter.platform,
                identifier=identifier,
                company=_company_from_identifier(identifier),
            ),
            fetched_at,
        )
        return [
            snapshot
            for snapshot in snapshots
            if _same_posting(snapshot.canonical_url, official_url)
        ]

    def list(self) -> list[DiscoveryLink]:
        with self._sessions() as session:
            rows = session.scalars(
                select(DiscoveryLinkRow).order_by(DiscoveryLinkRow.id.desc())
            ).all()
            return [self._to_link(row) for row in rows]

    @staticmethod
    def _to_link(row: DiscoveryLinkRow) -> DiscoveryLink:
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return DiscoveryLink(
            id=row.id,
            url=row.url,
            source_platform=row.source_platform,
            status=row.status,
            resolved_url=row.resolved_url,
            snapshot_id=row.snapshot_id,
            reason=row.reason,
            created_at=created_at,
        )


def _official_links(content: str, source_url: str) -> list[str]:
    parser = _HrefParser()
    parser.feed(content)
    source_host = (urlsplit(source_url).hostname or "").lower()
    candidates: list[tuple[int, int, str]] = []
    for href in parser.hrefs:
        candidate = urljoin(source_url, href)
        parts = urlsplit(candidate)
        hostname = (parts.hostname or "").lower()
        if hostname == source_host or hostname.endswith(f".{source_host}"):
            outbound = _outbound_target(candidate)
            if outbound is None:
                continue
            candidate = outbound
            parts = urlsplit(candidate)
            hostname = (parts.hostname or "").lower()
        candidate_platform = identify_discovery_link_source(candidate)
        if candidate_platform != "engineering-list":
            continue
        score = _official_link_score(hostname, parts.path)
        if parts.scheme == "https" and hostname and candidate != source_url and score > 0:
            candidates.append((score, -len(candidates), candidate))
    ranked = [candidate for _, _, candidate in sorted(candidates, reverse=True)]
    return list(dict.fromkeys(ranked))[:10]


def _outbound_target(url: str) -> str | None:
    query = parse_qs(urlsplit(url).query)
    for key in ("url", "target", "redirect", "redirect_url", "destination", "dest", "to"):
        values = query.get(key)
        if not values:
            continue
        target = values[0]
        parts = urlsplit(target)
        if parts.scheme == "https" and parts.hostname:
            return target
    return None


def _official_link_score(hostname: str, path: str) -> int:
    if _ats_route(hostname) is not None:
        return 100
    path_words = set(re.findall(r"[a-z]+", path.lower()))
    host_words = set(re.findall(r"[a-z]+", hostname))
    if path_words & {
        "apply",
        "career",
        "careers",
        "job",
        "jobs",
        "opening",
        "openings",
        "opportunities",
        "position",
        "positions",
        "role",
        "roles",
    }:
        return 50
    if host_words & {"career", "careers", "job", "jobs"}:
        return 25
    return 10


def _ats_route(hostname: str) -> _AtsRoute | None:
    return next((route for route in _ATS_ROUTES if route.matches(hostname)), None)


def _same_posting(left: str, right: str) -> bool:
    left_parts = urlsplit(left)
    right_parts = urlsplit(right)
    return (
        left_parts.netloc.lower(),
        left_parts.path.rstrip("/").lower(),
    ) == (
        right_parts.netloc.lower(),
        right_parts.path.rstrip("/").lower(),
    )


def _company_from_identifier(identifier: str) -> str:
    return " ".join(word.capitalize() for word in re.split(r"[-_]", identifier) if word)


def _with_provenance(
    snapshot: JobSnapshot,
    source_url: str,
    platform: str,
) -> JobSnapshot:
    return snapshot.model_copy(
        update={
            "source_url": source_url,
            "source_platform": platform,
            "raw_posting": {
                **snapshot.raw_posting,
                "_discovery": {
                    "source_platform": platform,
                    "source_url": source_url,
                },
            },
        }
    )
